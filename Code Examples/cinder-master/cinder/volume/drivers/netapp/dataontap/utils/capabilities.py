# Copyright (c) 2016 Clinton Knight.  All rights reserved.
# Copyright (c) 2017 Jose Porrua.  All rights reserved.
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
Storage service catalog (SSC) functions and classes for NetApp cDOT systems.
"""

import copy
import re

from oslo_log import log as logging


LOG = logging.getLogger(__name__)


class CapabilitiesLibrary(object):

    def __init__(self, protocol, vserver_name, zapi_client, configuration):

        self.protocol = protocol.lower()
        self.vserver_name = vserver_name
        self.zapi_client = zapi_client
        self.configuration = configuration
        self.backend_name = self.configuration.safe_get('volume_backend_name')
        self.ssc = {}
        self.invalid_extra_specs = []

    def check_api_permissions(self):
        self.invalid_extra_specs = self.zapi_client.check_api_permissions()

    def cluster_user_supported(self):
        return not self.invalid_extra_specs

    def get_ssc(self):
        """Get a copy of the Storage Service Catalog."""

        return copy.deepcopy(self.ssc)

    def get_ssc_flexvol_names(self):
        """Get the names of the FlexVols in the Storage Service Catalog."""

        ssc = self.get_ssc()
        return list(ssc.keys())

    def get_ssc_for_flexvol(self, flexvol_name):
        """Get map of Storage Service Catalog entries for a single flexvol."""

        return copy.deepcopy(self.ssc.get(flexvol_name, {}))

    def get_ssc_aggregates(self):
        """Get a list of aggregates for all SSC flexvols."""

        aggregates = set()
        for __, flexvol_info in self.ssc.items():
            if 'netapp_aggregate' in flexvol_info:
                aggr = flexvol_info['netapp_aggregate']
                if isinstance(aggr, list):
                    aggregates.update(aggr)
                else:
                    aggregates.add(aggr)
        return list(aggregates)

    def is_qos_min_supported(self, pool_name):
        for __, flexvol_info in self.ssc.items():
            if ('netapp_qos_min_support' in flexvol_info and
                    'pool_name' in flexvol_info and
                    flexvol_info['pool_name'] == pool_name):
                return flexvol_info['netapp_qos_min_support'] == 'true'

        return False

    def update_ssc(self, flexvol_map):
        """Periodically runs to update Storage Service Catalog data.

        The self.ssc attribute is updated with the following format.
        {<flexvol_name> : {<ssc_key>: <ssc_value>}}
        """
        LOG.info("Updating storage service catalog information for "
                 "backend '%s'", self.backend_name)

        ssc = {}

        for flexvol_name, flexvol_info in flexvol_map.items():

            ssc_volume = {}

            # Add metadata passed from the driver, including pool name
            ssc_volume.update(flexvol_info)

            # Get volume info
            ssc_volume.update(self._get_ssc_flexvol_info(flexvol_name))
            ssc_volume.update(self._get_ssc_dedupe_info(flexvol_name))
            ssc_volume.update(self._get_ssc_mirror_info(flexvol_name))
            ssc_volume.update(self._get_ssc_encryption_info(flexvol_name))

            # Get aggregate info
            aggregate_name = ssc_volume.get('netapp_aggregate')
            is_flexgroup = isinstance(aggregate_name, list)
            aggr_info = self._get_ssc_aggregate_info(
                aggregate_name, is_flexgroup=is_flexgroup)
            node_name = aggr_info.pop('netapp_node_name')
            ssc_volume.update(aggr_info)

            ssc_volume.update(self._get_ssc_qos_min_info(node_name))

            ssc[flexvol_name] = ssc_volume

        self.ssc = ssc

    def _update_for_failover(self, zapi_client, flexvol_map):

        self.zapi_client = zapi_client
        self.update_ssc(flexvol_map)

    def _get_ssc_flexvol_info(self, flexvol_name):
        """Gather flexvol info and recast into SSC-style volume stats."""

        volume_info = self.zapi_client.get_flexvol(flexvol_name=flexvol_name)

        netapp_thick = (volume_info.get('space-guarantee-enabled') and
                        (volume_info.get('space-guarantee') == 'file' or
                         volume_info.get('space-guarantee') == 'volume'))
        thick = self._get_thick_provisioning_support(netapp_thick)
        is_flexgroup = volume_info.get('style-extended') == 'flexgroup'

        return {
            'netapp_thin_provisioned': str(not netapp_thick).lower(),
            'thick_provisioning_support': thick,
            'thin_provisioning_support': not thick,
            'netapp_aggregate': volume_info.get('aggregate')[0],
            'netapp_is_flexgroup': str(is_flexgroup).lower(),
        }

    def _get_thick_provisioning_support(self, netapp_thick):
        """Get standard thick/thin values for a flexvol.

        The values reported for the standard thick_provisioning_support and
        thin_provisioning_support flags depend on both the flexvol state as
        well as protocol-specific configuration values.
        """

        if self.protocol == 'nfs':
            return (netapp_thick and
                    not self.configuration.nfs_sparsed_volumes)
        else:
            return (netapp_thick and
                    (self.configuration.netapp_lun_space_reservation ==
                     'enabled'))

    def _get_ssc_dedupe_info(self, flexvol_name):
        """Gather dedupe info and recast into SSC-style volume stats."""

        if ('netapp_dedup' in self.invalid_extra_specs or
                'netapp_compression' in self.invalid_extra_specs):
            dedupe = False
            compression = False
        else:
            dedupe_info = self.zapi_client.get_flexvol_dedupe_info(
                flexvol_name)
            dedupe = dedupe_info.get('dedupe')
            compression = dedupe_info.get('compression')

        return {
            'netapp_dedup': str(dedupe).lower(),
            'netapp_compression': str(compression).lower(),
        }

    def _get_ssc_encryption_info(self, flexvol_name):
        """Gather flexvol encryption info and recast into SSC-style stats."""
        encrypted = self.zapi_client.is_flexvol_encrypted(
            flexvol_name, self.vserver_name)

        return {'netapp_flexvol_encryption': str(encrypted).lower()}

    def _get_ssc_qos_min_info(self, node_name):
        """Gather Qos minimum info and recast into SSC-style stats."""
        supported = True
        is_nfs = self.protocol == 'nfs'
        if isinstance(node_name, list):
            # NOTE(felipe_rodrigues): it cannot choose which node the volume
            # is created, so the pool must have all nodes as QoS min supported
            # for enabling this feature.
            for n_name in node_name:
                if not self.zapi_client.is_qos_min_supported(is_nfs, n_name):
                    supported = False
                    break
        else:
            supported = self.zapi_client.is_qos_min_supported(is_nfs,
                                                              node_name)

        return {'netapp_qos_min_support': str(supported).lower()}

    def _get_ssc_mirror_info(self, flexvol_name):
        """Gather SnapMirror info and recast into SSC-style volume stats."""

        mirrored = self.zapi_client.is_flexvol_mirrored(
            flexvol_name, self.vserver_name)

        return {'netapp_mirrored': str(mirrored).lower()}

    def _get_ssc_aggregate_info(self, aggregate_name, is_flexgroup=False):
        """Gather aggregate info and recast into SSC-style volume stats.

        :param aggregate_name: a list of aggregate names for FlexGroup or
        a single aggregate name for FlexVol
        :param is_flexgroup: bool informing the type of aggregate_name param
        """

        if 'netapp_raid_type' in self.invalid_extra_specs:
            raid_type = None
            hybrid = None
            disk_types = None
            node_name = None
        elif is_flexgroup:
            raid_type = set()
            hybrid = set()
            disk_types = set()
            node_name = set()
            for aggr in aggregate_name:
                aggregate = self.zapi_client.get_aggregate(aggr)
                node_name.add(aggregate.get('node-name'))
                raid_type.add(aggregate.get('raid-type'))
                hybrid.add(str(aggregate.get('is-hybrid')).lower()
                           if 'is-hybrid' in aggregate else None)
                disks = set(self.zapi_client.get_aggregate_disk_types(aggr))
                disk_types = disk_types.union(disks)
            node_name = list(node_name)
            raid_type = list(raid_type)
            hybrid = list(hybrid)
            disk_types = list(disk_types)
        else:
            aggregate = self.zapi_client.get_aggregate(aggregate_name)
            node_name = aggregate.get('node-name')
            raid_type = aggregate.get('raid-type')
            hybrid = (str(aggregate.get('is-hybrid')).lower()
                      if 'is-hybrid' in aggregate else None)
            disk_types = self.zapi_client.get_aggregate_disk_types(
                aggregate_name)

        return {
            'netapp_raid_type': raid_type,
            'netapp_hybrid_aggregate': hybrid,
            'netapp_disk_type': disk_types,
            'netapp_node_name': node_name,
        }

    def get_matching_flexvols_for_extra_specs(self, extra_specs):
        """Return a list of flexvol names that match a set of extra specs."""

        extra_specs = self._modify_extra_specs_for_comparison(extra_specs)
        matching_flexvols = []

        for flexvol_name, flexvol_info in self.get_ssc().items():

            if self._flexvol_matches_extra_specs(flexvol_info, extra_specs):
                matching_flexvols.append(flexvol_name)

        return matching_flexvols

    def _flexvol_matches_extra_specs(self, flexvol_info, extra_specs):
        """Check whether the SSC data for a FlexVol matches extra specs.

        A set of extra specs is considered a match for a FlexVol if, for each
        extra spec, the value matches what is in SSC or the key is unknown to
        SSC.
        """

        for extra_spec_key, extra_spec_value in extra_specs.items():

            if extra_spec_key in flexvol_info:
                if not self._extra_spec_matches(extra_spec_value,
                                                flexvol_info[extra_spec_key]):
                    return False

        return True

    def _extra_spec_matches(self, extra_spec_value, ssc_flexvol_value):
        """Check whether an extra spec value matches something in the SSC.

        The SSC values may be scalars or lists, so the extra spec value must be
        compared to the SSC value if it is a scalar, or it must be sought in
        the list.
        """

        if isinstance(ssc_flexvol_value, list):
            return extra_spec_value in ssc_flexvol_value
        else:
            return extra_spec_value == ssc_flexvol_value

    def _modify_extra_specs_for_comparison(self, extra_specs):
        """Adjust extra spec values for simple comparison to SSC values.

        Most extra-spec key-value tuples may be directly compared. But the
        boolean values that take the form '<is> True' or '<is> False' must be
        modified to allow comparison with the values we keep in the SSC and
        report to the scheduler.
        """

        modified_extra_specs = copy.deepcopy(extra_specs)

        for key, value in extra_specs.items():

            if isinstance(value, str):
                if re.match(r'<is>\s+True', value, re.I):
                    modified_extra_specs[key] = True
                elif re.match(r'<is>\s+False', value, re.I):
                    modified_extra_specs[key] = False

        return modified_extra_specs

    def is_flexgroup(self, pool_name):
        for __, flexvol_info in self.ssc.items():
            if ('netapp_is_flexgroup' in flexvol_info and
                    'pool_name' in flexvol_info and
                    flexvol_info['pool_name'] == pool_name):
                return flexvol_info['netapp_is_flexgroup'] == 'true'

        return False

    def contains_flexgroup_pool(self):
        for __, flexvol_info in self.ssc.items():
            if ('netapp_is_flexgroup' in flexvol_info and
                    flexvol_info['netapp_is_flexgroup'] == 'true'):
                return True

        return False
