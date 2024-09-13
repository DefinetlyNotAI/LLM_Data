# Copyright (c) 2011 Intel Corporation
# Copyright (c) 2011 OpenStack, LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
The FilterScheduler is for scheduling of share and share group creation.
You can customize this scheduler by specifying your own share/share group
filters and weighing functions.
"""

from oslo_config import cfg
from oslo_log import log

from manila import exception
from manila.i18n import _
from manila.message import api as message_api
from manila.message import message_field
from manila import policy
from manila.scheduler.drivers import base
from manila.scheduler import scheduler_options
from manila.share import share_types

CONF = cfg.CONF
LOG = log.getLogger(__name__)

AFFINITY_HINT = 'same_host'
ANTI_AFFINITY_HINT = 'different_host'
AFFINITY_KEY = "__affinity_same_host"
ANTI_AFFINITY_KEY = "__affinity_different_host"


class FilterScheduler(base.Scheduler):
    """Scheduler that can be used for filtering and weighing."""
    def __init__(self, *args, **kwargs):
        super(FilterScheduler, self).__init__(*args, **kwargs)
        self.cost_function_cache = None
        self.options = scheduler_options.SchedulerOptions()
        self.max_attempts = self._max_attempts()
        self.message_api = message_api.API()

    def _get_configuration_options(self):
        """Fetch options dictionary. Broken out for testing."""
        return self.options.get_configuration()

    def get_pools(self, context, filters, cached):
        return self.host_manager.get_pools(context, filters, cached)

    def _post_select_populate_filter_properties(self, filter_properties,
                                                host_state):
        """Add additional information to filter properties.

        Add additional information to the filter properties after a host has
        been selected by the scheduling process.
        """
        # Add a retry entry for the selected volume backend:
        self._add_retry_host(filter_properties, host_state.host)

    def _add_retry_host(self, filter_properties, host):
        """Add retry entry for the selected volume backend.

        In the event that the request gets re-scheduled, this entry
        will signal that the given backend has already been tried.
        """
        retry = filter_properties.get('retry')
        if not retry:
            return
        hosts = retry['hosts']
        hosts.append(host)

    def _max_attempts(self):
        max_attempts = CONF.scheduler_max_attempts
        if max_attempts < 1:
            msg = _("Invalid value for 'scheduler_max_attempts', "
                    "must be >=1")
            raise exception.InvalidParameterValue(err=msg)
        return max_attempts

    def schedule_create_share(self, context, request_spec, filter_properties):
        weighed_host = self._schedule_share(context,
                                            request_spec,
                                            filter_properties)

        host = weighed_host.obj.host
        share_id = request_spec['share_id']
        snapshot_id = request_spec['snapshot_id']

        updated_share = base.share_update_db(context, share_id, host)
        self._post_select_populate_filter_properties(filter_properties,
                                                     weighed_host.obj)

        # context is not serializable
        filter_properties.pop('context', None)

        self.share_rpcapi.create_share_instance(
            context, updated_share.instance, host,
            request_spec=request_spec,
            filter_properties=filter_properties,
            snapshot_id=snapshot_id
        )

    def schedule_create_replica(self, context, request_spec,
                                filter_properties):
        share_replica_id = request_spec['share_instance_properties'].get('id')

        weighed_host = self._schedule_share(
            context, request_spec, filter_properties)

        host = weighed_host.obj.host

        updated_share_replica = base.share_replica_update_db(
            context, share_replica_id, host)
        self._post_select_populate_filter_properties(filter_properties,
                                                     weighed_host.obj)

        # context is not serializable
        filter_properties.pop('context', None)

        self.share_rpcapi.create_share_replica(
            context, updated_share_replica, host, request_spec=request_spec,
            filter_properties=filter_properties)

    def _format_filter_properties(self, context, filter_properties,
                                  request_spec):

        elevated = context.elevated()

        share_properties = request_spec['share_properties']
        share_instance_properties = (request_spec.get(
            'share_instance_properties', {}))
        share_proto = request_spec.get('share_proto',
                                       share_properties.get('share_proto'))

        resource_properties = share_properties.copy()
        resource_properties.update(share_instance_properties.copy())
        share_type = request_spec.get("share_type", {})
        if not share_type:
            msg = _("You must create a share type in advance,"
                    " and specify in request body or"
                    " set default_share_type in manila.conf.")
            LOG.error(msg)
            self.message_api.create(
                context,
                message_field.Action.CREATE,
                context.project_id,
                resource_type=message_field.Resource.SHARE,
                resource_id=request_spec.get('share_id', None),
                detail=message_field.Detail.NO_DEFAULT_SHARE_TYPE)
            raise exception.InvalidParameterValue(err=msg)

        share_type['extra_specs'] = share_type.get('extra_specs') or {}

        if share_type['extra_specs']:
            for extra_spec_name in share_types.get_boolean_extra_specs():
                extra_spec = share_type['extra_specs'].get(extra_spec_name)
                if extra_spec is not None:
                    if not extra_spec.startswith("<is>"):
                        extra_spec = "<is> %s" % extra_spec
                        share_type['extra_specs'][extra_spec_name] = extra_spec

        storage_protocol_spec = (
            share_type['extra_specs'].get('storage_protocol')
        )
        if storage_protocol_spec is None and share_proto is not None:
            # a host can report multiple protocols as "storage_protocol"
            spec_value = "<in> %s" % share_proto
            share_type['extra_specs']['storage_protocol'] = spec_value

        resource_type = share_type
        request_spec.update({'resource_properties': resource_properties})

        config_options = self._get_configuration_options()

        share_group = request_spec.get('share_group')

        # NOTE(gouthamr): If 'active_replica_host' or 'snapshot_host' is
        # present in the request spec, pass that host's 'replication_domain' to
        # the ShareReplication and CreateFromSnapshot filters.
        active_replica_host = request_spec.get('active_replica_host')
        snapshot_host = request_spec.get('snapshot_host')
        allowed_hosts = []
        if active_replica_host:
            allowed_hosts.append(active_replica_host)
        if snapshot_host:
            allowed_hosts.append(snapshot_host)
        replication_domain = None
        if active_replica_host or snapshot_host:
            temp_hosts = self.host_manager.get_all_host_states_share(elevated)
            matching_host = next((host for host in temp_hosts
                                  if host.host in allowed_hosts), None)
            if matching_host:
                replication_domain = matching_host.replication_domain

            # NOTE(zengyingzhe): remove the 'share_backend_name' extra spec,
            # let scheduler choose the available host for this replica or
            # snapshot clone creation request.
            share_type.get('extra_specs', {}).pop('share_backend_name', None)

        if filter_properties is None:
            filter_properties = {}
        self._populate_retry_share(filter_properties, resource_properties)

        filter_properties.update({'context': context,
                                  'request_spec': request_spec,
                                  'config_options': config_options,
                                  'share_type': share_type,
                                  'resource_type': resource_type,
                                  'share_group': share_group,
                                  'replication_domain': replication_domain,
                                  })

        self.populate_filter_properties_share(context, request_spec,
                                              filter_properties)

        return filter_properties, share_properties

    def _schedule_share(self, context, request_spec, filter_properties=None):
        """Returns a list of hosts that meet the required specs.

        The list is ordered by their fitness.
        """
        elevated = context.elevated()

        filter_properties, share_properties = self._format_filter_properties(
            context, filter_properties, request_spec)

        # Find our local list of acceptable hosts by filtering and
        # weighing our options. we virtually consume resources on
        # it so subsequent selections can adjust accordingly.

        # Note: remember, we are using an iterator here. So only
        # traverse this list once.
        consider_disabled = False
        if policy.check_is_host_admin(context) and filter_properties.get(
                'scheduler_hints', {}).get('only_host'):
            # Admin user can schedule share on disabled host
            consider_disabled = True

        hosts = self.host_manager.get_all_host_states_share(
            elevated,
            consider_disabled=consider_disabled
        )
        if not hosts:
            msg = _("There are no hosts to fulfill this "
                    "provisioning request. Are share "
                    "backend services down?")
            self.message_api.create(
                context,
                message_field.Action.CREATE,
                context.project_id,
                resource_type=message_field.Resource.SHARE,
                resource_id=request_spec.get('share_id', None),
                detail=message_field.Detail.SHARE_BACKEND_NOT_READY_YET)
            raise exception.WillNotSchedule(msg)

        # Filter local hosts based on requirements ...
        hosts, last_filter = self.host_manager.get_filtered_hosts(
            hosts, filter_properties)

        if not hosts:
            msg = _('Failed to find a weighted host, the last executed filter'
                    ' was %s.')
            raise exception.NoValidHost(
                reason=msg % last_filter,
                detail_data={'last_filter': last_filter})

        LOG.debug("Filtered share %(hosts)s", {"hosts": hosts})
        # weighted_host = WeightedHost() ... the best
        # host for the job.
        weighed_hosts = self.host_manager.get_weighed_hosts(hosts,
                                                            filter_properties)
        best_host = weighed_hosts[0]
        LOG.debug("Choosing for share: %(best_host)s",
                  {"best_host": best_host})
        # NOTE(rushiagr): updating the available space parameters at same place
        best_host.obj.consume_from_share(share_properties)
        return best_host

    def _populate_retry_share(self, filter_properties, properties):
        """Populate filter properties with retry history.

        Populate filter properties with history of retries for this
        request. If maximum retries is exceeded, raise NoValidHost.
        """
        max_attempts = self.max_attempts
        retry = filter_properties.pop('retry', {})

        if max_attempts == 1:
            # re-scheduling is disabled.
            return

        # retry is enabled, update attempt count:
        if retry:
            retry['num_attempts'] += 1
        else:
            retry = {
                'num_attempts': 1,
                'hosts': []  # list of share service hosts tried
            }
        filter_properties['retry'] = retry

        share_id = properties.get('share_id')
        self._log_share_error(share_id, retry)

        if retry['num_attempts'] > max_attempts:
            msg = _("Exceeded max scheduling attempts %(max_attempts)d for "
                    "share %(share_id)s") % {
                "max_attempts": max_attempts,
                "share_id": share_id
            }
            raise exception.NoValidHost(reason=msg)

    def _log_share_error(self, share_id, retry):
        """Log any exceptions from a previous share create operation.

        If the request contained an exception from a previous share
        create operation, log it to aid debugging.
        """
        exc = retry.pop('exc', None)  # string-ified exception from share
        if not exc:
            return  # no exception info from a previous attempt, skip

        hosts = retry.get('hosts')
        if not hosts:
            return  # no previously attempted hosts, skip

        last_host = hosts[-1]
        LOG.error("Error scheduling %(share_id)s from last share-service: "
                  "%(last_host)s : %(exc)s", {
                      "share_id": share_id,
                      "last_host": last_host,
                      "exc": "exc"
                      })

    def _populate_scheduler_hint(self, request_spec, hints, key, hint):
        share_properties = request_spec.get('share_properties', {})
        value = share_properties.get('metadata', {}).get(key, None)
        if value:
            hints.update({hint: value})

    def populate_filter_properties_scheduler_hints(self, context, request_spec,
                                                   filter_properties):
        share_id = request_spec.get('share_id', None)
        if not share_id:
            filter_properties['scheduler_hints'] = {}
            return
        else:
            if filter_properties.get('scheduler_hints', None):
                return
            hints = {}
            self._populate_scheduler_hint(request_spec, hints,
                                          AFFINITY_KEY,
                                          AFFINITY_HINT)
            self._populate_scheduler_hint(request_spec, hints,
                                          ANTI_AFFINITY_KEY,
                                          ANTI_AFFINITY_HINT)
            filter_properties['scheduler_hints'] = hints

    def populate_filter_properties_share(self, context, request_spec,
                                         filter_properties):
        """Stuff things into filter_properties.

        Can be overridden in a subclass to add more data.
        """
        shr = request_spec['share_properties']
        inst = request_spec['share_instance_properties']
        filter_properties['size'] = shr['size']
        filter_properties['availability_zone_id'] = (
            inst.get('availability_zone_id')
        )
        filter_properties['user_id'] = shr.get('user_id')
        filter_properties['metadata'] = shr.get('metadata')
        filter_properties['snapshot_id'] = shr.get('snapshot_id')
        filter_properties['is_share_extend'] = (
            request_spec.get('is_share_extend')
        )
        self.populate_filter_properties_scheduler_hints(context, request_spec,
                                                        filter_properties)

    def schedule_create_share_group(self, context, share_group_id,
                                    request_spec, filter_properties):

        LOG.info("Scheduling share group %s.", share_group_id)
        host = self._get_best_host_for_share_group(context, request_spec)

        if not host:
            msg = _("No hosts available for share group %s.") % share_group_id
            raise exception.NoValidHost(reason=msg)

        msg = "Chose host %(host)s for create_share_group %(group)s."
        LOG.info(msg, {'host': host, 'group': share_group_id})

        updated_share_group = base.share_group_update_db(
            context, share_group_id, host)

        self.share_rpcapi.create_share_group(
            context, updated_share_group, host)

    def _get_weighted_hosts_for_share_type(self, context, request_spec,
                                           share_type):
        config_options = self._get_configuration_options()
        # NOTE(ameade): Find our local list of acceptable hosts by
        # filtering and weighing our options. We virtually consume
        # resources on it so subsequent selections can adjust accordingly.

        # NOTE(ameade): Remember, we are using an iterator here. So only
        # traverse this list once.
        all_hosts = self.host_manager.get_all_host_states_share(context)

        if not all_hosts:
            return []

        share_type['extra_specs'] = share_type.get('extra_specs', {})

        if share_type['extra_specs']:
            for spec_name in share_types.get_required_extra_specs():
                extra_spec = share_type['extra_specs'].get(spec_name)

                if extra_spec is not None:
                    share_type['extra_specs'][spec_name] = (
                        "<is> %s" % extra_spec)

        filter_properties = {
            'context': context,
            'request_spec': request_spec,
            'config_options': config_options,
            'share_type': share_type,
            'resource_type': share_type,
            'size': 0,
        }
        # Filter local hosts based on requirements ...
        hosts, last_filter = self.host_manager.get_filtered_hosts(
            all_hosts, filter_properties)

        if not hosts:
            return []

        LOG.debug("Filtered %s", hosts)

        # weighted_host = WeightedHost() ... the best host for the job.
        weighed_hosts = self.host_manager.get_weighed_hosts(
            hosts,
            filter_properties)
        if not weighed_hosts:
            return []

        return weighed_hosts

    def _get_weighted_hosts_for_share_group_type(self, context, request_spec,
                                                 share_group_type):
        config_options = self._get_configuration_options()
        all_hosts = self.host_manager.get_all_host_states_share(context)

        if not all_hosts:
            return []

        filter_properties = {
            'context': context,
            'request_spec': request_spec,
            'config_options': config_options,
            'share_group_type': share_group_type,
            'resource_type': share_group_type,
        }

        hosts, last_filter = self.host_manager.get_filtered_hosts(
            all_hosts,
            filter_properties,
            CONF.scheduler_default_share_group_filters)

        if not hosts:
            return []

        LOG.debug("Filtered %s", hosts)

        weighed_hosts = self.host_manager.get_weighed_hosts(
            hosts,
            filter_properties)
        if not weighed_hosts:
            return []

        return weighed_hosts

    def _get_weighted_candidates_share_group(self, context, request_spec):
        """Finds hosts that support the share group.

        Returns a list of hosts that meet the required specs,
        ordered by their fitness.
        """
        elevated = context.elevated()

        shr_types = request_spec.get("share_types")

        weighed_hosts = []

        for iteration_count, share_type in enumerate(shr_types):
            temp_weighed_hosts = self._get_weighted_hosts_for_share_type(
                elevated, request_spec, share_type)

            # NOTE(ameade): Take the intersection of hosts so we have one that
            # can support all share types of the share group
            if iteration_count == 0:
                weighed_hosts = temp_weighed_hosts
            else:
                new_weighed_hosts = []
                for host1 in weighed_hosts:
                    for host2 in temp_weighed_hosts:
                        if host1.obj.host == host2.obj.host:
                            new_weighed_hosts.append(host1)
                weighed_hosts = new_weighed_hosts
                if not weighed_hosts:
                    return []

        # NOTE(ameade): Ensure the hosts support the share group type
        share_group_type = request_spec.get("resource_type", {})
        temp_weighed_group_hosts = (
            self._get_weighted_hosts_for_share_group_type(
                elevated, request_spec, share_group_type))
        new_weighed_hosts = []
        for host1 in weighed_hosts:
            for host2 in temp_weighed_group_hosts:
                if host1.obj.host == host2.obj.host:
                    new_weighed_hosts.append(host1)
        weighed_hosts = new_weighed_hosts

        return weighed_hosts

    def _get_best_host_for_share_group(self, context, request_spec):
        weighed_hosts = self._get_weighted_candidates_share_group(
            context,
            request_spec)

        if not weighed_hosts:
            return None
        return weighed_hosts[0].obj.host

    def host_passes_filters(self, context, host, request_spec,
                            filter_properties):

        elevated = context.elevated()

        filter_properties, share_properties = self._format_filter_properties(
            context, filter_properties, request_spec)

        hosts = self.host_manager.get_all_host_states_share(elevated)
        filter_class_names = None
        if request_spec.get('is_share_extend', None):
            filter_class_names = CONF.scheduler_default_extend_filters
        hosts, last_filter = self.host_manager.get_filtered_hosts(
            hosts, filter_properties,
            filter_class_names=filter_class_names)
        hosts = self.host_manager.get_weighed_hosts(hosts, filter_properties)

        for tgt_host in hosts:
            if tgt_host.obj.host == host:
                return tgt_host.obj

        msg = (_('Cannot place share %(id)s on %(host)s, the last executed'
                 ' filter was %(last_filter)s.')
               % {'id': request_spec['share_id'], 'host': host,
                  'last_filter': last_filter})
        raise exception.NoValidHost(reason=msg)
