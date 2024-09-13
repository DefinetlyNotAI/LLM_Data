# Copyright (c) 2011 X.commerce, a business unit of eBay Inc.
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

"""Defines interface for DB access.

The underlying driver is loaded as a :class:`LazyPluggable`.

Functions in this module are imported into the manila.db namespace. Call these
functions from manila.db namespace, not the manila.db.api namespace.

All functions in this module return objects that implement a dictionary-like
interface. Currently, many of these objects are sqlalchemy objects that
implement a dictionary interface. However, a future goal is to have all of
these objects be simple dictionaries.


**Related Flags**

:backend:  string to lookup in the list of LazyPluggable backends.
           `sqlalchemy` is the only supported backend right now.

:connection:  string specifying the sqlalchemy connection to use, like:
              `sqlite:///var/lib/manila/manila.sqlite`.

:enable_new_services:  when adding a new service to the database, is it in the
                       pool of available hardware (Default: True)

"""
from oslo_config import cfg
from oslo_db import api as db_api

db_opts = [
    cfg.StrOpt('db_backend',
               default='sqlalchemy',
               help='The backend to use for database.'),
    cfg.BoolOpt('enable_new_services',
                default=True,
                help='Services to be added to the available pool on create.'),
    cfg.StrOpt('share_name_template',
               default='share-%s',
               help='Template string to be used to generate share names.'),
    cfg.StrOpt('share_snapshot_name_template',
               default='share-snapshot-%s',
               help='Template string to be used to generate share snapshot '
                    'names.'),
    cfg.StrOpt('share_backup_name_template',
               default='share-backup-%s',
               help='Template string to be used to generate backup names.'),
]

CONF = cfg.CONF
CONF.register_opts(db_opts)

_BACKEND_MAPPING = {'sqlalchemy': 'manila.db.sqlalchemy.api'}
IMPL = db_api.DBAPI.from_config(cfg.CONF, backend_mapping=_BACKEND_MAPPING,
                                lazy=True)


def authorize_project_context(context, project_id):
    """Ensures a request has permission to access the given project."""
    return IMPL.authorize_project_context(context, project_id)


def authorize_quota_class_context(context, class_name):
    """Ensures a request has permission to access the given quota class."""
    return IMPL.authorize_quota_class_context(context, class_name)


###################


def service_destroy(context, service_id):
    """Destroy the service or raise if it does not exist."""
    return IMPL.service_destroy(context, service_id)


def service_get(context, service_id):
    """Get a service or raise if it does not exist."""
    return IMPL.service_get(context, service_id)


def service_get_by_host_and_topic(context, host, topic):
    """Get a service by host it's on and topic it listens to."""
    return IMPL.service_get_by_host_and_topic(context, host, topic)


def service_get_all(context, disabled=None):
    """Get all services."""
    return IMPL.service_get_all(context, disabled)


def service_get_all_by_topic(context, topic, consider_disabled=False):
    """Get all services for a given topic."""
    return IMPL.service_get_all_by_topic(context, topic,
                                         consider_disabled=consider_disabled)


def service_get_all_share_sorted(context):
    """Get all share services sorted by share count.

    :returns: a list of (Service, share_count) tuples.

    """
    return IMPL.service_get_all_share_sorted(context)


def service_get_by_args(context, host, binary):
    """Get the state of an service by node name and binary."""
    return IMPL.service_get_by_args(context, host, binary)


def service_create(context, values):
    """Create a service from the values dictionary."""
    return IMPL.service_create(context, values)


def service_update(context, service_id, values):
    """Set the given properties on an service and update it.

    Raises NotFound if service does not exist.

    """
    return IMPL.service_update(context, service_id, values)


####################


def quota_create(context, project_id, resource, limit, user_id=None,
                 share_type_id=None):
    """Create a quota for the given project and resource."""
    return IMPL.quota_create(context, project_id, resource, limit,
                             user_id=user_id, share_type_id=share_type_id)


def quota_get_all_by_project_and_user(context, project_id, user_id):
    """Retrieve all quotas associated with a given project and user."""
    return IMPL.quota_get_all_by_project_and_user(context, project_id, user_id)


def quota_get_all_by_project_and_share_type(context, project_id,
                                            share_type_id):
    """Retrieve all quotas associated with a given project and user."""
    return IMPL.quota_get_all_by_project_and_share_type(
        context, project_id, share_type_id)


def quota_get_all_by_project(context, project_id):
    """Retrieve all quotas associated with a given project."""
    return IMPL.quota_get_all_by_project(context, project_id)


def quota_get_all(context, project_id):
    """Retrieve all user quotas associated with a given project."""
    return IMPL.quota_get_all(context, project_id)


def quota_update(context, project_id, resource, limit, user_id=None,
                 share_type_id=None):
    """Update a quota or raise if it does not exist."""
    return IMPL.quota_update(context, project_id, resource, limit,
                             user_id=user_id, share_type_id=share_type_id)


###################


def quota_class_create(context, class_name, resource, limit):
    """Create a quota class for the given name and resource."""
    return IMPL.quota_class_create(context, class_name, resource, limit)


def quota_class_get(context, class_name, resource):
    """Retrieve a quota class or raise if it does not exist."""
    return IMPL.quota_class_get(context, class_name, resource)


def quota_class_get_default(context):
    """Retrieve all default quotas."""
    return IMPL.quota_class_get_default(context)


def quota_class_get_all_by_name(context, class_name):
    """Retrieve all quotas associated with a given quota class."""
    return IMPL.quota_class_get_all_by_name(context, class_name)


def quota_class_update(context, class_name, resource, limit):
    """Update a quota class or raise if it does not exist."""
    return IMPL.quota_class_update(context, class_name, resource, limit)


###################


def quota_usage_get(context, project_id, resource, user_id=None,
                    share_type_id=None):
    """Retrieve a quota usage or raise if it does not exist."""
    return IMPL.quota_usage_get(
        context, project_id, resource, user_id=user_id,
        share_type_id=share_type_id)


def quota_usage_get_all_by_project_and_user(context, project_id, user_id):
    """Retrieve all usage associated with a given resource."""
    return IMPL.quota_usage_get_all_by_project_and_user(context,
                                                        project_id, user_id)


def quota_usage_get_all_by_project_and_share_type(context, project_id,
                                                  share_type_id):
    """Retrieve all usage associated with a given resource."""
    return IMPL.quota_usage_get_all_by_project_and_share_type(
        context, project_id, share_type_id)


def quota_usage_get_all_by_project(context, project_id):
    """Retrieve all usage associated with a given resource."""
    return IMPL.quota_usage_get_all_by_project(context, project_id)


def quota_usage_create(context, project_id, user_id, resource, in_use,
                       reserved=0, until_refresh=None, share_type_id=None):
    """Create a quota usage."""
    return IMPL.quota_usage_create(
        context, project_id, user_id, resource, in_use, reserved,
        until_refresh, share_type_id=share_type_id)


def quota_usage_update(context, project_id, user_id, resource,
                       share_type_id=None, **kwargs):
    """Update a quota usage or raise if it does not exist."""
    return IMPL.quota_usage_update(
        context, project_id, user_id, resource, share_type_id=share_type_id,
        **kwargs)


###################


def quota_reserve(context, resources, quotas, user_quotas, share_type_quotas,
                  deltas, expire, until_refresh, max_age,
                  project_id=None, user_id=None, share_type_id=None,
                  overquota_allowed=False):
    """Check quotas and create appropriate reservations."""
    return IMPL.quota_reserve(
        context, resources, quotas, user_quotas, share_type_quotas, deltas,
        expire, until_refresh, max_age, project_id=project_id, user_id=user_id,
        share_type_id=share_type_id, overquota_allowed=overquota_allowed)


def reservation_commit(context, reservations, project_id=None, user_id=None,
                       share_type_id=None):
    """Commit quota reservations."""
    return IMPL.reservation_commit(
        context, reservations, project_id=project_id, user_id=user_id,
        share_type_id=share_type_id)


def reservation_rollback(context, reservations, project_id=None, user_id=None,
                         share_type_id=None):
    """Roll back quota reservations."""
    return IMPL.reservation_rollback(
        context, reservations, project_id=project_id, user_id=user_id,
        share_type_id=share_type_id)


def quota_destroy_all_by_project_and_user(context, project_id, user_id):
    """Destroy all quotas associated with a given project and user."""
    return IMPL.quota_destroy_all_by_project_and_user(context,
                                                      project_id, user_id)


def quota_destroy_all_by_share_type(context, share_type_id, project_id=None):
    """Destroy all quotas associated with a given share type and project."""
    return IMPL.quota_destroy_all_by_share_type(
        context, share_type_id, project_id=project_id)


def quota_destroy_all_by_project(context, project_id):
    """Destroy all quotas associated with a given project."""
    return IMPL.quota_destroy_all_by_project(context, project_id)


def reservation_expire(context):
    """Roll back any expired reservations."""
    return IMPL.reservation_expire(context)


###################


def share_instance_get(context, instance_id, with_share_data=False):
    """Get share instance by id."""
    return IMPL.share_instance_get(context, instance_id,
                                   with_share_data=with_share_data)


def share_instance_create(context, share_id, values):
    """Create new share instance."""
    return IMPL.share_instance_create(context, share_id, values)


def share_instance_delete(context, instance_id,
                          need_to_update_usages=False):
    """Delete share instance."""
    return IMPL.share_instance_delete(
        context, instance_id,
        need_to_update_usages=need_to_update_usages)


def update_share_instance_quota_usages(context, instance_id):
    """Update share instance quota usages"""
    return IMPL.update_share_instance_quota_usages(context, instance_id)


def share_instance_update(context, instance_id, values, with_share_data=False):
    """Update share instance fields."""
    return IMPL.share_instance_update(context, instance_id, values,
                                      with_share_data=with_share_data)


def share_and_snapshot_instances_status_update(
        context, values, share_instance_ids=None, snapshot_instance_ids=None,
        current_expected_status=None):
    return IMPL.share_and_snapshot_instances_status_update(
        context, values, share_instance_ids=share_instance_ids,
        snapshot_instance_ids=snapshot_instance_ids,
        current_expected_status=current_expected_status)


def share_instance_status_update(context, share_instance_ids, values):
    """Updates the status of a bunch of share instances at once."""
    return IMPL.share_instance_status_update(
        context, share_instance_ids, values)


def share_instance_get_all(context, filters=None):
    """Returns all share instances."""
    return IMPL.share_instance_get_all(context, filters=filters)


def share_instance_get_all_by_share_server(
    context, share_server_id, with_share_data=False,
):
    """Returns all share instances with given share_server_id."""
    return IMPL.share_instance_get_all_by_share_server(
        context, share_server_id, with_share_data=with_share_data)


def share_instance_get_all_by_host(
    context, host, with_share_data=False, status=None,
):
    """Returns all share instances with given host."""
    return IMPL.share_instance_get_all_by_host(
        context, host, with_share_data=with_share_data, status=status)


def share_instance_get_all_by_share_network(context, share_network_id):
    """Returns list of shares that belong to given share network."""
    return IMPL.share_instance_get_all_by_share_network(
        context, share_network_id)


def share_instance_get_all_by_share(context, share_id):
    """Returns list of shares that belong to given share."""
    return IMPL.share_instance_get_all_by_share(context, share_id)


def share_instance_get_all_by_share_group_id(context, share_group_id):
    """Returns list of share instances that belong to given share group."""
    return IMPL.share_instance_get_all_by_share_group_id(
        context, share_group_id)

###################


def share_create(context, share_values, create_share_instance=True):
    """Create new share."""
    return IMPL.share_create(context, share_values,
                             create_share_instance=create_share_instance)


def share_update(context, share_id, values):
    """Update share fields."""
    return IMPL.share_update(context, share_id, values)


def share_get(context, share_id, **kwargs):
    """Get share by id."""
    return IMPL.share_get(context, share_id, **kwargs)


def share_get_all(context, filters=None, sort_key=None, sort_dir=None):
    """Get all shares."""
    return IMPL.share_get_all(
        context, filters=filters, sort_key=sort_key, sort_dir=sort_dir,
    )


def share_get_all_with_count(context, filters=None, sort_key=None,
                             sort_dir=None):
    """Get all shares."""
    return IMPL.share_get_all_with_count(
        context, filters=filters, sort_key=sort_key, sort_dir=sort_dir)


def share_get_all_by_project(context, project_id, filters=None,
                             is_public=False, sort_key=None, sort_dir=None):
    """Returns all shares with given project ID."""
    return IMPL.share_get_all_by_project(
        context, project_id, filters=filters, is_public=is_public,
        sort_key=sort_key, sort_dir=sort_dir)


def share_get_all_by_project_with_count(
        context, project_id, filters=None, is_public=False, sort_key=None,
        sort_dir=None,):
    """Returns all shares with given project ID."""
    return IMPL.share_get_all_by_project_with_count(
        context, project_id, filters=filters, is_public=is_public,
        sort_key=sort_key, sort_dir=sort_dir)


def share_get_all_by_share_group_id(context, share_group_id,
                                    filters=None, sort_key=None,
                                    sort_dir=None):
    """Returns all shares with given project ID and share group id."""
    return IMPL.share_get_all_by_share_group_id(
        context, share_group_id, filters=filters,
        sort_key=sort_key, sort_dir=sort_dir)


def share_get_all_by_share_group_id_with_count(context, share_group_id,
                                               filters=None, sort_key=None,
                                               sort_dir=None):
    """Returns all shares with given project ID and share group id."""
    return IMPL.share_get_all_by_share_group_id_with_count(
        context, share_group_id, filters=filters, sort_key=sort_key,
        sort_dir=sort_dir)


def share_get_all_by_share_server(context, share_server_id, filters=None,
                                  sort_key=None, sort_dir=None):
    """Returns all shares with given share server ID."""
    return IMPL.share_get_all_by_share_server(
        context, share_server_id, filters=filters, sort_key=sort_key,
        sort_dir=sort_dir)


def share_get_all_soft_deleted(
        context, share_server_id, filters=None, sort_key=None, sort_dir=None):
    """Returns all shares in recycle bin with given share server ID."""
    return IMPL.share_get_all_soft_deleted(
        context, share_server_id, filters=filters, sort_key=sort_key,
        sort_dir=sort_dir)


def share_get_all_by_share_server_with_count(
        context, share_server_id, filters=None, sort_key=None, sort_dir=None):
    """Returns all shares with given share server ID."""
    return IMPL.share_get_all_by_share_server_with_count(
        context, share_server_id, filters=filters, sort_key=sort_key,
        sort_dir=sort_dir)


def share_get_all_soft_deleted_by_network(
        context, share_network_id, filters=None, sort_key=None, sort_dir=None):
    """Returns all shares in recycle bin with given share network ID."""
    return IMPL.share_get_all_soft_deleted_by_network(
        context, share_network_id, filters=filters, sort_key=sort_key,
        sort_dir=sort_dir)


def share_delete(context, share_id):
    """Delete share."""
    return IMPL.share_delete(context, share_id)


def share_soft_delete(context, share_id):
    """Soft delete share."""
    return IMPL.share_soft_delete(context, share_id)


def share_restore(context, share_id):
    """Restore share."""
    return IMPL.share_restore(context, share_id)

###################


def transfer_get(context, transfer_id):
    """Get a share transfer record or raise if it does not exist."""
    return IMPL.transfer_get(context, transfer_id)


def transfer_get_all(context, limit=None, sort_key=None,
                     sort_dir=None, filters=None, offset=None):
    """Get all share transfer records."""
    return IMPL.transfer_get_all(context, limit=limit,
                                 sort_key=sort_key, sort_dir=sort_dir,
                                 filters=filters, offset=offset)


def transfer_get_all_by_project(context, project_id,
                                limit=None, sort_key=None,
                                sort_dir=None, filters=None, offset=None):
    """Get all share transfer records for specified project."""
    return IMPL.transfer_get_all_by_project(context, project_id,
                                            limit=limit, sort_key=sort_key,
                                            sort_dir=sort_dir,
                                            filters=filters, offset=offset)


def transfer_get_all_expired(context):
    """Get all expired transfers DB records."""
    return IMPL.transfer_get_all_expired(context)


def transfer_create(context, values):
    """Create an entry in the transfers table."""
    return IMPL.transfer_create(context, values)


def transfer_destroy(context, transfer_id, update_share_status=True):
    """Destroy a record in the share transfer table."""
    return IMPL.transfer_destroy(context, transfer_id,
                                 update_share_status=update_share_status)


def transfer_accept(context, transfer_id, user_id, project_id,
                    accept_snapshots=False):
    """Accept a share transfer."""
    return IMPL.transfer_accept(context, transfer_id, user_id, project_id,
                                accept_snapshots=accept_snapshots)


def transfer_accept_rollback(context, transfer_id, user_id,
                             project_id, rollback_snap=False):
    """Rollback a share transfer."""
    return IMPL.transfer_accept_rollback(context, transfer_id,
                                         user_id, project_id,
                                         rollback_snap=rollback_snap)


###################


def share_access_create(context, values):
    """Allow access to share."""
    return IMPL.share_access_create(context, values)


def share_access_get(context, access_id):
    """Get share access rule."""
    return IMPL.share_access_get(context, access_id)


def share_access_get_with_context(context, access_id):
    """Get share access rule."""
    return IMPL.share_access_get_with_context(context, access_id)


def share_access_get_all_for_share(context, share_id, filters=None):
    """Get all access rules for given share."""
    return IMPL.share_access_get_all_for_share(context, share_id,
                                               filters=filters)


def share_access_get_all_for_instance(context, instance_id, filters=None,
                                      with_share_access_data=True):
    """Get all access rules related to a certain share instance."""
    return IMPL.share_access_get_all_for_instance(
        context, instance_id, filters=filters,
        with_share_access_data=with_share_access_data)


def share_access_get_all_by_type_and_access(context, share_id, access_type,
                                            access):
    """Returns share access by given type and access."""
    return IMPL.share_access_get_all_by_type_and_access(
        context, share_id, access_type, access)


def share_access_check_for_existing_access(context, share_id, access_type,
                                           access_to):
    """Returns True if rule corresponding to the type and client exists."""
    return IMPL.share_access_check_for_existing_access(
        context, share_id, access_type, access_to)


def share_instance_access_create(context, values, share_instance_id):
    """Allow access to share instance."""
    return IMPL.share_instance_access_create(
        context, values, share_instance_id)


def share_instance_access_copy(context, share_id, instance_id):
    """Maps the existing access rules for the share to the instance in the DB.

    Adds the instance mapping to the share's access rules and
    returns the share's access rules.
    """
    return IMPL.share_instance_access_copy(context, share_id, instance_id)


def share_instance_access_get(context, access_id, instance_id,
                              with_share_access_data=True):
    """Get access rule mapping for share instance."""
    return IMPL.share_instance_access_get(
        context, access_id, instance_id,
        with_share_access_data=with_share_access_data)


def share_instance_access_update(context, access_id, instance_id, updates):
    """Update the access mapping row for a given share instance and access."""
    return IMPL.share_instance_access_update(
        context, access_id, instance_id, updates)


def share_instance_access_delete(context, mapping_id):
    """Deny access to share instance."""
    return IMPL.share_instance_access_delete(context, mapping_id)


def share_access_metadata_update(context, access_id, metadata):
    """Update metadata of share access rule."""
    return IMPL.share_access_metadata_update(context, access_id, metadata)


def share_access_metadata_delete(context, access_id, key):
    """Delete metadata of share access rule."""
    return IMPL.share_access_metadata_delete(context, access_id, key)


####################


def share_snapshot_instance_update(context, instance_id, values):
    """Set the given properties on a share snapshot instance and update it.

    Raises NotFound if snapshot instance does not exist.
    """
    return IMPL.share_snapshot_instance_update(context, instance_id, values)


def share_snapshot_instances_status_update(
        context, snapshot_instance_ids, values):
    """Updates the status of a bunch of share snapshot instances at once."""
    return IMPL.share_snapshot_instances_status_update(
        context, snapshot_instance_ids, values)


def share_snapshot_instance_create(context, snapshot_id, values):
    """Create a share snapshot instance for an existing snapshot."""
    return IMPL.share_snapshot_instance_create(
        context, snapshot_id, values)


def share_snapshot_instance_get(context, instance_id, with_share_data=False):
    """Get a snapshot instance or raise a NotFound exception."""
    return IMPL.share_snapshot_instance_get(
        context, instance_id, with_share_data=with_share_data)


def share_snapshot_instance_get_all_with_filters(context, filters,
                                                 with_share_data=False):
    """Get all snapshot instances satisfying provided filters."""
    return IMPL.share_snapshot_instance_get_all_with_filters(
        context, filters, with_share_data=with_share_data)


def share_snapshot_instance_delete(context, snapshot_instance_id):
    """Delete a share snapshot instance."""
    return IMPL.share_snapshot_instance_delete(context, snapshot_instance_id)


####################


def share_snapshot_create(context, values, create_snapshot_instance=True):
    """Create a snapshot from the values dictionary."""
    return IMPL.share_snapshot_create(
        context, values, create_snapshot_instance=create_snapshot_instance)


def share_snapshot_get(context, snapshot_id, project_only=True):
    """Get a snapshot or raise if it does not exist."""
    return IMPL.share_snapshot_get(context, snapshot_id,
                                   project_only=project_only)


def share_snapshot_get_all(context, filters=None, limit=None, offset=None,
                           sort_key=None, sort_dir=None):
    """Get all snapshots."""
    return IMPL.share_snapshot_get_all(
        context, filters=filters, limit=limit, offset=offset,
        sort_key=sort_key, sort_dir=sort_dir)


def share_snapshot_get_all_with_count(context, filters=None, limit=None,
                                      offset=None, sort_key=None,
                                      sort_dir=None):
    """Get all snapshots."""
    return IMPL.share_snapshot_get_all_with_count(
        context, filters=filters, limit=limit, offset=offset,
        sort_key=sort_key, sort_dir=sort_dir)


def share_snapshot_get_all_by_project(context, project_id, filters=None,
                                      limit=None, offset=None, sort_key=None,
                                      sort_dir=None):
    """Get all snapshots belonging to a project."""
    return IMPL.share_snapshot_get_all_by_project(
        context, project_id, filters=filters, limit=limit, offset=offset,
        sort_key=sort_key, sort_dir=sort_dir)


def share_snapshot_get_all_by_project_with_count(context, project_id,
                                                 filters=None, limit=None,
                                                 offset=None, sort_key=None,
                                                 sort_dir=None):
    """Get all snapshots belonging to a project."""
    return IMPL.share_snapshot_get_all_by_project_with_count(
        context, project_id, filters=filters, limit=limit, offset=offset,
        sort_key=sort_key, sort_dir=sort_dir)


def share_snapshot_get_all_for_share(context, share_id, filters=None,
                                     sort_key=None, sort_dir=None):
    """Get all snapshots for a share."""
    return IMPL.share_snapshot_get_all_for_share(
        context, share_id, filters=filters, sort_key=sort_key,
        sort_dir=sort_dir,
    )


def share_snapshot_get_latest_for_share(context, share_id):
    """Get the most recent snapshot for a share."""
    return IMPL.share_snapshot_get_latest_for_share(context, share_id)


def share_snapshot_update(context, snapshot_id, values):
    """Set the given properties on an snapshot and update it.

    Raises NotFound if snapshot does not exist.
    """
    return IMPL.share_snapshot_update(context, snapshot_id, values)


###################
def share_snapshot_access_create(context, values):
    """Create a share snapshot access from the values dictionary."""
    return IMPL.share_snapshot_access_create(context, values)


def share_snapshot_access_get(context, access_id):
    """Get share snapshot access rule from given access_id."""
    return IMPL.share_snapshot_access_get(context, access_id)


def share_snapshot_access_get_all_for_snapshot_instance(
    context, snapshot_instance_id,
):
    """Get all access rules related to a certain snapshot instance."""
    return IMPL.share_snapshot_access_get_all_for_snapshot_instance(
        context, snapshot_instance_id)


def share_snapshot_access_get_all_for_share_snapshot(context,
                                                     share_snapshot_id,
                                                     filters):
    """Get all access rules for a given share snapshot according to filters."""
    return IMPL.share_snapshot_access_get_all_for_share_snapshot(
        context, share_snapshot_id, filters)


def share_snapshot_check_for_existing_access(context, share_snapshot_id,
                                             access_type, access_to):
    """Returns True if rule corresponding to the type and client exists."""
    return IMPL.share_snapshot_check_for_existing_access(context,
                                                         share_snapshot_id,
                                                         access_type,
                                                         access_to)


def share_snapshot_export_locations_get(context, snapshot_id):
    """Get all export locations for a given share snapshot."""
    return IMPL.share_snapshot_export_locations_get(context, snapshot_id)


def share_snapshot_instance_access_update(
        context, access_id, instance_id, updates):
    """Update the state of the share snapshot instance access."""
    return IMPL.share_snapshot_instance_access_update(
        context, access_id, instance_id, updates)


def share_snapshot_instance_access_get(context, share_snapshot_instance_id,
                                       access_id):
    """Get the share snapshot instance access related to given ids."""
    return IMPL.share_snapshot_instance_access_get(
        context, share_snapshot_instance_id, access_id)


def share_snapshot_instance_access_delete(context, access_id,
                                          snapshot_instance_id):
    """Delete share snapshot instance access given its id."""
    return IMPL.share_snapshot_instance_access_delete(
        context, access_id, snapshot_instance_id)


def share_snapshot_instance_export_location_create(context, values):
    """Create a share snapshot instance export location."""
    return IMPL.share_snapshot_instance_export_location_create(context, values)


def share_snapshot_instance_export_locations_update(
        context, share_snapshot_instance_id, export_locations, delete=True):
    """Update export locations of a share instance."""
    return IMPL.share_snapshot_instance_export_locations_update(
        context, share_snapshot_instance_id, export_locations, delete=delete)


def share_snapshot_instance_export_locations_get_all(
        context, share_snapshot_instance_id):
    """Get the share snapshot instance export locations for given id."""
    return IMPL.share_snapshot_instance_export_locations_get_all(
        context, share_snapshot_instance_id)


def share_snapshot_instance_export_location_get(context, el_id):
    """Get the share snapshot instance export location for given id."""
    return IMPL.share_snapshot_instance_export_location_get(
        context, el_id)


def share_snapshot_instance_export_location_delete(context, el_id):
    """Delete share snapshot instance export location given its id."""
    return IMPL.share_snapshot_instance_export_location_delete(context, el_id)


####################

def share_snapshot_metadata_get(context, share_snapshot_id, **kwargs):
    """Get all metadata for a share snapshot."""
    return IMPL.share_snapshot_metadata_get(context,
                                            share_snapshot_id,
                                            **kwargs)


def share_snapshot_metadata_get_item(context, share_snapshot_id, key):
    """Get metadata item for a share snapshot."""
    return IMPL.share_snapshot_metadata_get_item(context,
                                                 share_snapshot_id, key)


def share_snapshot_metadata_delete(context, share_snapshot_id, key):
    """Delete the given metadata item."""
    IMPL.share_snapshot_metadata_delete(context, share_snapshot_id, key)


def share_snapshot_metadata_update(context, share_snapshot_id,
                                   metadata, delete):
    """Update metadata if it exists, otherwise create it."""
    return IMPL.share_snapshot_metadata_update(context, share_snapshot_id,
                                               metadata, delete)


def share_snapshot_metadata_update_item(context, share_snapshot_id,
                                        metadata):
    """Update metadata item if it exists, otherwise create it."""
    return IMPL.share_snapshot_metadata_update_item(context,
                                                    share_snapshot_id,
                                                    metadata)
###################


def security_service_create(context, values):
    """Create security service DB record."""
    return IMPL.security_service_create(context, values)


def security_service_delete(context, id):
    """Delete security service DB record."""
    return IMPL.security_service_delete(context, id)


def security_service_update(context, id, values):
    """Update security service DB record."""
    return IMPL.security_service_update(context, id, values)


def security_service_get(context, id, **kwargs):
    """Get security service DB record."""
    return IMPL.security_service_get(context, id, **kwargs)


def security_service_get_all(context):
    """Get all security service DB records."""
    return IMPL.security_service_get_all(context)


def security_service_get_all_by_project(context, project_id):
    """Get all security service DB records for the given project."""
    return IMPL.security_service_get_all_by_project(context, project_id)


def security_service_get_all_by_share_network(context, share_network_id):
    """Get all security service DB records for the given share network."""
    return IMPL.security_service_get_all_by_share_network(context,
                                                          share_network_id)


####################
def share_metadata_get(context, share_id):
    """Get all metadata for a share."""
    return IMPL.share_metadata_get(context, share_id)


def share_metadata_get_item(context, share_id, key):
    """Get metadata item for given key and for a given share.."""
    return IMPL.share_metadata_get_item(context, share_id, key)


def share_metadata_delete(context, share_id, key):
    """Delete the given metadata item."""
    return IMPL.share_metadata_delete(context, share_id, key)


def share_metadata_update(context, share, metadata, delete):
    """Update metadata if it exists, otherwise create it."""
    return IMPL.share_metadata_update(context, share, metadata, delete)


def share_metadata_update_item(context, share_id, item):
    """update meta item containing key and value for given share."""
    return IMPL.share_metadata_update_item(context, share_id, item)


###################

def export_location_get_by_uuid(
    context, export_location_uuid, ignore_secondary_replicas=False,
):
    """Get specific export location of a share."""
    return IMPL.export_location_get_by_uuid(
        context, export_location_uuid,
        ignore_secondary_replicas=ignore_secondary_replicas)


def export_location_get_all(context, share_id):
    """Get all export locations of a share."""
    return IMPL.export_location_get_all(context, share_id)


def export_location_get_all_by_share_id(
    context, share_id,
    include_admin_only=True,
    ignore_migration_destination=False,
    ignore_secondary_replicas=False,
):
    """Get all export locations of a share by its ID."""
    return IMPL.export_location_get_all_by_share_id(
        context, share_id, include_admin_only=include_admin_only,
        ignore_migration_destination=ignore_migration_destination,
        ignore_secondary_replicas=ignore_secondary_replicas)


def export_location_get_all_by_share_instance_id(
    context, share_instance_id, include_admin_only=True,
):
    """Get all export locations of a share instance by its ID."""
    return IMPL.export_location_get_all_by_share_instance_id(
        context, share_instance_id, include_admin_only=include_admin_only)


def export_locations_update(
    context, share_instance_id, export_locations, delete=True,
):
    """Update export locations of a share instance."""
    return IMPL.export_locations_update(
        context, share_instance_id, export_locations, delete)


####################

def export_location_metadata_get(context, export_location_uuid):
    """Get all metadata of an export location."""
    return IMPL.export_location_metadata_get(context, export_location_uuid)


def export_location_metadata_get_item(context, export_location_uuid, key):
    """Get metadata item for a share export location."""
    return IMPL.export_location_metadata_get_item(context,
                                                  export_location_uuid,
                                                  key)


def export_location_metadata_delete(context, export_location_uuid, keys):
    """Delete metadata of an export location."""
    return IMPL.export_location_metadata_delete(
        context, export_location_uuid, keys)


def export_location_metadata_update(context, export_location_uuid, metadata,
                                    delete):
    """Update metadata of an export location."""
    return IMPL.export_location_metadata_update(
        context, export_location_uuid, metadata, delete)


def export_location_metadata_update_item(context, export_location_uuid,
                                         metadata):
    """Update metadata item if it exists, otherwise create it."""
    return IMPL.export_location_metadata_update_item(context,
                                                     export_location_uuid,
                                                     metadata)

####################


def share_network_create(context, values):
    """Create a share network DB record."""
    return IMPL.share_network_create(context, values)


def share_network_delete(context, id):
    """Delete a share network DB record."""
    return IMPL.share_network_delete(context, id)


def share_network_update(context, id, values):
    """Update a share network DB record."""
    return IMPL.share_network_update(context, id, values)


def share_network_get(context, id):
    """Get requested share network DB record."""
    return IMPL.share_network_get(context, id)


def share_network_get_all_by_filter(context, filters=None):
    """Get all share network DB records for the given filter."""
    return IMPL.share_network_get_all_by_filter(context, filters=filters)


def share_network_get_all(context):
    """Get all share network DB records."""
    return IMPL.share_network_get_all(context)


def share_network_get_all_by_project(context, project_id):
    """Get all share network DB records for the given project."""
    return IMPL.share_network_get_all_by_project(context, project_id)


def share_network_get_all_by_security_service(context, security_service_id):
    """Get all share network DB records for the given project."""
    return IMPL.share_network_get_all_by_security_service(
        context, security_service_id)


def share_network_add_security_service(context, id, security_service_id):
    """Associate a security service with a share network."""
    return IMPL.share_network_add_security_service(context,
                                                   id,
                                                   security_service_id)


def share_network_remove_security_service(context, id, security_service_id):
    """Dissociate a security service from a share network."""
    return IMPL.share_network_remove_security_service(context,
                                                      id,
                                                      security_service_id)


def share_network_security_service_association_get(
        context, share_network_id, security_service_id):
    """Get given share network and security service association."""
    return IMPL.share_network_security_service_association_get(
        context, share_network_id, security_service_id)


def share_network_update_security_service(context, id,
                                          current_security_service_id,
                                          new_security_service_id):
    """Update a security service association with a share network."""
    return IMPL.share_network_update_security_service(
        context, id, current_security_service_id, new_security_service_id)


##################


def share_network_subnet_create(context, values):
    """Create a share network subnet DB record."""
    return IMPL.share_network_subnet_create(context, values)


def share_network_subnet_delete(context, network_subnet_id):
    """Delete a share network subnet DB record."""
    return IMPL.share_network_subnet_delete(context, network_subnet_id)


def share_network_subnet_update(context, network_subnet_id, values):
    """Update a share network subnet DB record."""
    return IMPL.share_network_subnet_update(context, network_subnet_id, values)


def share_network_subnet_get(context, network_subnet_id, parent_id=None):
    """Get requested share network subnet DB record."""
    return IMPL.share_network_subnet_get(
        context,
        network_subnet_id,
        parent_id=parent_id,
    )


def share_network_subnet_get_all_with_same_az(context, network_subnet_id):
    """Get requested az share network subnets DB record."""
    return IMPL.share_network_subnet_get_all_with_same_az(
        context, network_subnet_id,
    )


def share_network_subnet_get_all(context):
    """Get all share network subnet DB record."""
    return IMPL.share_network_subnet_get_all(context)


def share_network_subnets_get_all_by_availability_zone_id(
    context, share_network_id, availability_zone_id,
    fallback_to_default=True,
):
    """Get the share network subnets DB record in a given AZ.

    This method returns list of subnets DB record for a given share network id
    and an availability zone. If the 'availability_zone_id' is 'None', a
    record may be returned and it will represent the default share network
    subnets. If there is no subnet for a specific availability zone id and
    "fallback_to_default" is True, this method will return the default share
    network subnets, if it exists.
    """
    return IMPL.share_network_subnets_get_all_by_availability_zone_id(
        context, share_network_id, availability_zone_id,
        fallback_to_default=fallback_to_default,
    )


def share_network_subnet_get_default_subnets(context, share_network_id):
    """Get the default share network subnets DB records."""
    return IMPL.share_network_subnet_get_default_subnets(
        context, share_network_id,
    )


def share_network_subnet_get_all_by_share_server_id(context, share_server_id):
    """Get the subnets that are being used by the share server."""
    return IMPL.share_network_subnet_get_all_by_share_server_id(
        context, share_server_id,
    )

####################


def share_network_subnet_metadata_get(context, share_network_subnet_id,
                                      **kwargs):
    """Get all metadata for a share network subnet."""
    return IMPL.share_network_subnet_metadata_get(context,
                                                  share_network_subnet_id,
                                                  **kwargs)


def share_network_subnet_metadata_get_item(context, share_network_subnet_id,
                                           key):
    """Get metadata item for a share network subnet."""
    return IMPL.share_network_subnet_metadata_get_item(context,
                                                       share_network_subnet_id,
                                                       key)


def share_network_subnet_metadata_delete(context, share_network_subnet_id,
                                         key):
    """Delete the given metadata item."""
    IMPL.share_network_subnet_metadata_delete(context, share_network_subnet_id,
                                              key)


def share_network_subnet_metadata_update(context, share_network_subnet_id,
                                         metadata, delete):
    """Update metadata if it exists, otherwise create it."""
    return IMPL.share_network_subnet_metadata_update(context,
                                                     share_network_subnet_id,
                                                     metadata, delete)


def share_network_subnet_metadata_update_item(context, share_network_subnet_id,
                                              metadata):
    """Update metadata item if it exists, otherwise create it."""
    return IMPL.share_network_subnet_metadata_update_item(
        context, share_network_subnet_id, metadata)

###################


def network_allocation_create(context, values):
    """Create a network allocation DB record."""
    return IMPL.network_allocation_create(context, values)


def network_allocation_delete(context, id):
    """Delete a network allocation DB record."""
    return IMPL.network_allocation_delete(context, id)


def network_allocation_update(context, id, values, read_deleted=None):
    """Update a network allocation DB record."""
    return IMPL.network_allocation_update(context, id, values,
                                          read_deleted=read_deleted)


def network_allocation_get(context, id, read_deleted=None):
    """Get a network allocation DB record."""
    return IMPL.network_allocation_get(context, id, read_deleted=read_deleted)


def network_allocations_get_for_share_server(
    context, share_server_id, label=None, subnet_id=None,
):
    """Get network allocations for share server."""
    return IMPL.network_allocations_get_for_share_server(
        context, share_server_id, label=label, subnet_id=subnet_id,
    )


def network_allocations_get_by_ip_address(context, ip_address):
    """Get network allocations by IP address."""
    return IMPL.network_allocations_get_by_ip_address(context, ip_address)


##################


def share_server_create(context, values):
    """Create share server DB record."""
    return IMPL.share_server_create(context, values)


def share_server_delete(context, id):
    """Delete share server DB record."""
    return IMPL.share_server_delete(context, id)


def share_server_update(context, id, values):
    """Update share server DB record."""
    return IMPL.share_server_update(context, id, values)


def share_server_get(context, id):
    """Get share server DB record by ID."""
    return IMPL.share_server_get(context, id)


def share_server_search_by_identifier(context, identifier):
    """Search for share servers based on given identifier."""
    return IMPL.share_server_search_by_identifier(
        context, identifier,
    )


def share_server_get_all_by_host_and_share_subnet_valid(
    context, host, share_subnet_id,
):
    """Get share server DB records by host and share net not error."""
    return IMPL.share_server_get_all_by_host_and_share_subnet_valid(
        context, host, share_subnet_id,
    )


def share_server_get_all_by_host_and_share_subnet(
    context, host, share_subnet_id,
):
    """Get share server DB records by host and share net."""
    return IMPL.share_server_get_all_by_host_and_share_subnet(
        context, host, share_subnet_id,
    )


def share_server_get_all(context):
    """Get all share server DB records."""
    return IMPL.share_server_get_all(context)


def share_server_get_all_with_filters(context, filters):
    """Get all share servers that match with the specified filters."""
    return IMPL.share_server_get_all_with_filters(context, filters)


def share_server_get_all_by_host(context, host, filters=None):
    """Get all share servers related to particular host."""
    return IMPL.share_server_get_all_by_host(context, host, filters=filters)


def share_server_get_all_unused_deletable(context, host, updated_before):
    """Get all free share servers DB records."""
    return IMPL.share_server_get_all_unused_deletable(context, host,
                                                      updated_before)


def share_get_all_expired(context):
    """Get all expired share DB records."""
    return IMPL.share_get_all_expired(context)


def share_server_backend_details_set(context, share_server_id, server_details):
    """Create DB record with backend details."""
    return IMPL.share_server_backend_details_set(context, share_server_id,
                                                 server_details)


def share_server_backend_details_get_item(context, share_server_id, meta_key):
    """Get backend details."""
    return IMPL.share_server_backend_details_get_item(context, share_server_id,
                                                      meta_key)


def share_server_backend_details_delete(context, share_server_id):
    """Delete backend details DB records for a share server."""
    return IMPL.share_server_backend_details_delete(context, share_server_id)


def share_servers_update(context, share_server_ids, values):
    """Updates values of a bunch of share servers at once."""
    return IMPL.share_servers_update(
        context, share_server_ids, values)


##################


def share_type_create(context, values, projects=None):
    """Create a new share type."""
    return IMPL.share_type_create(context, values, projects)


def share_type_update(context, share_type_id, values):
    """Update an exist share type."""
    return IMPL.share_type_update(context, share_type_id, values)


def share_type_get_all(context, inactive=False, filters=None):
    """Get all share types.

    :param context: context to query under
    :param inactive: Include inactive share types to the result set
    :param filters: Filters for the query in the form of key/value.
        :is_public: Filter share types based on visibility:

            * **True**: List public share types only
            * **False**: List private share types only
            * **None**: List both public and private share types

    :returns: list of matching share types
    """
    return IMPL.share_type_get_all(context, inactive, filters)


def share_type_get(context, type_id, inactive=False, expected_fields=None):
    """Get share type by id.

    :param context: context to query under
    :param type_id: share type id to get.
    :param inactive: Consider inactive share types when searching
    :param expected_fields: Return those additional fields.
                            Supported fields are: projects.
    :returns: share type
    """
    return IMPL.share_type_get(context, type_id, inactive, expected_fields)


def share_type_get_by_name(context, name):
    """Get share type by name."""
    return IMPL.share_type_get_by_name(context, name)


def share_type_get_by_name_or_id(context, name_or_id):
    """Get share type by name or ID and return None if not found."""
    return IMPL.share_type_get_by_name_or_id(context, name_or_id)


def share_type_access_get_all(context, type_id):
    """Get all share type access of a share type."""
    return IMPL.share_type_access_get_all(context, type_id)


def share_type_access_add(context, type_id, project_id):
    """Add share type access for project."""
    return IMPL.share_type_access_add(context, type_id, project_id)


def share_type_access_remove(context, type_id, project_id):
    """Remove share type access for project."""
    return IMPL.share_type_access_remove(context, type_id, project_id)


def share_type_destroy(context, id):
    """Delete a share type."""
    return IMPL.share_type_destroy(context, id)


####################


def share_type_extra_specs_get(context, share_type_id):
    """Get all extra specs for a share type."""
    return IMPL.share_type_extra_specs_get(context, share_type_id)


def share_type_extra_specs_delete(context, share_type_id, key):
    """Delete the given extra specs item."""
    return IMPL.share_type_extra_specs_delete(context, share_type_id, key)


def share_type_extra_specs_update_or_create(context, share_type_id,
                                            extra_specs):
    """Create or update share type extra specs.

    This adds or modifies the key/value pairs specified in the extra
    specs dict argument.
    """
    return IMPL.share_type_extra_specs_update_or_create(context,
                                                        share_type_id,
                                                        extra_specs)


def driver_private_data_get(context, entity_id, key=None, default=None):
    """Get one, list or all key-value pairs for given entity_id."""
    return IMPL.driver_private_data_get(context, entity_id, key, default)


def driver_private_data_update(context, entity_id, details,
                               delete_existing=False):
    """Update key-value pairs for given entity_id."""
    return IMPL.driver_private_data_update(context, entity_id, details,
                                           delete_existing)


def driver_private_data_delete(context, entity_id, key=None):
    """Remove one, list or all key-value pairs for given entity_id."""
    return IMPL.driver_private_data_delete(context, entity_id, key)


####################

def availability_zone_get(context, id_or_name):
    """Get availability zone by name or id."""
    return IMPL.availability_zone_get(context, id_or_name)


def availability_zone_get_all(context):
    """Get all active availability zones."""
    return IMPL.availability_zone_get_all(context)


####################

def share_group_get(context, share_group_id):
    """Get a share group or raise if it does not exist."""
    return IMPL.share_group_get(context, share_group_id)


def share_group_get_all(context, detailed=True, filters=None, sort_key=None,
                        sort_dir=None):
    """Get all share groups."""
    return IMPL.share_group_get_all(
        context, detailed=detailed, filters=filters, sort_key=sort_key,
        sort_dir=sort_dir)


def share_group_get_all_by_host(context, host, detailed=True, filters=None,
                                sort_key=None, sort_dir=None):
    """Get all share groups belonging to a host."""
    return IMPL.share_group_get_all_by_host(
        context, host, detailed=detailed, filters=filters, sort_key=sort_key,
        sort_dir=sort_dir)


def share_group_create(context, values):
    """Create a share group from the values dictionary."""
    return IMPL.share_group_create(context, values)


def share_group_get_all_by_share_server(context, share_server_id,
                                        filters=None, sort_key=None,
                                        sort_dir=None):
    """Get all share groups associated with a share server."""
    return IMPL.share_group_get_all_by_share_server(
        context, share_server_id, filters=filters, sort_key=sort_key,
        sort_dir=sort_dir)


def share_group_get_all_by_project(context, project_id, detailed=True,
                                   filters=None, sort_key=None,
                                   sort_dir=None):
    """Get all share groups belonging to a project."""
    return IMPL.share_group_get_all_by_project(
        context, project_id, detailed=detailed, filters=filters,
        sort_key=sort_key, sort_dir=sort_dir)


def share_group_update(context, share_group_id, values):
    """Set the given properties on a share group and update it.

    Raises NotFound if share group does not exist.
    """
    return IMPL.share_group_update(context, share_group_id, values)


def share_group_destroy(context, share_group_id):
    """Destroy the share group or raise if it does not exist."""
    return IMPL.share_group_destroy(context, share_group_id)


def count_shares_in_share_group(context, share_group_id):
    """Returns the number of undeleted shares with the specified group."""
    return IMPL.count_shares_in_share_group(context, share_group_id)


def get_all_shares_by_share_group(context, share_group_id):
    return IMPL.get_all_shares_by_share_group(context, share_group_id)


def count_share_group_snapshots_in_share_group(context, share_group_id):
    """Returns the number of sg snapshots with the specified share group."""
    return IMPL.count_share_group_snapshots_in_share_group(
        context, share_group_id)


def count_share_groups_in_share_network(context, share_network_id):
    """Return the number of groups with the specified share network."""
    return IMPL.count_share_groups_in_share_network(context, share_network_id)


def count_share_group_snapshot_members_in_share(context, share_id):
    """Returns the number of group snapshot members linked to the share."""
    return IMPL.count_share_group_snapshot_members_in_share(context, share_id)


def share_group_snapshot_get(context, share_group_snapshot_id):
    """Get a share group snapshot."""
    return IMPL.share_group_snapshot_get(context, share_group_snapshot_id)


def share_group_snapshot_get_all(context, detailed=True, filters=None,
                                 sort_key=None, sort_dir=None):
    """Get all share group snapshots."""
    return IMPL.share_group_snapshot_get_all(
        context, detailed=detailed, filters=filters, sort_key=sort_key,
        sort_dir=sort_dir)


def share_group_snapshot_get_all_by_project(context, project_id, detailed=True,
                                            filters=None, sort_key=None,
                                            sort_dir=None):
    """Get all share group snapshots belonging to a project."""
    return IMPL.share_group_snapshot_get_all_by_project(
        context, project_id, detailed=detailed, filters=filters,
        sort_key=sort_key, sort_dir=sort_dir)


def share_group_snapshot_create(context, values):
    """Create a share group snapshot from the values dictionary."""
    return IMPL.share_group_snapshot_create(context, values)


def share_group_snapshot_update(context, share_group_snapshot_id, values):
    """Set the given properties on a share group snapshot and update it.

    Raises NotFound if share group snapshot does not exist.
    """
    return IMPL.share_group_snapshot_update(
        context, share_group_snapshot_id, values)


def share_group_snapshot_destroy(context, share_group_snapshot_id):
    """Destroy the share_group_snapshot or raise if it does not exist."""
    return IMPL.share_group_snapshot_destroy(context, share_group_snapshot_id)


def share_group_snapshot_members_get_all(context, share_group_snapshot_id):
    """Return the members of a share group snapshot."""
    return IMPL.share_group_snapshot_members_get_all(
        context, share_group_snapshot_id)


def share_group_snapshot_member_create(context, values):
    """Create a share group snapshot member from the values dictionary."""
    return IMPL.share_group_snapshot_member_create(context, values)


def share_group_snapshot_member_update(context, member_id, values):
    """Set the given properties on a share group snapshot member and update it.

    Raises NotFound if share_group_snapshot member does not exist.
    """
    return IMPL.share_group_snapshot_member_update(context, member_id, values)


def share_resources_host_update(context, current_host, new_host):
    """Update the host attr of all share resources that are on current_host."""
    return IMPL.share_resources_host_update(context, current_host, new_host)


####################

def share_replicas_get_all(context, with_share_server=False,
                           with_share_data=False):
    """Returns all share replicas regardless of share."""
    return IMPL.share_replicas_get_all(
        context, with_share_server=with_share_server,
        with_share_data=with_share_data)


def share_replicas_get_all_by_share(context, share_id, with_share_server=False,
                                    with_share_data=False):
    """Returns all share replicas for a given share."""
    return IMPL.share_replicas_get_all_by_share(
        context, share_id, with_share_server=with_share_server,
        with_share_data=with_share_data)


def share_replicas_get_available_active_replica(context, share_id,
                                                with_share_server=False,
                                                with_share_data=False):
    """Returns an active replica for a given share."""
    return IMPL.share_replicas_get_available_active_replica(
        context, share_id, with_share_server=with_share_server,
        with_share_data=with_share_data)


def share_replica_get(context, replica_id, with_share_server=False,
                      with_share_data=False):
    """Get share replica by id."""
    return IMPL.share_replica_get(
        context, replica_id, with_share_server=with_share_server,
        with_share_data=with_share_data)


def share_replica_update(context, share_replica_id, values,
                         with_share_data=False):
    """Updates a share replica with given values."""
    return IMPL.share_replica_update(context, share_replica_id, values,
                                     with_share_data=with_share_data)


def share_replica_delete(context, replica_id, need_to_update_usages=True):
    """Deletes a share replica."""
    return IMPL.share_replica_delete(
        context, replica_id, need_to_update_usages=need_to_update_usages)


def purge_deleted_records(context, age_in_days):
    """Purge deleted rows older than given age from all tables

    :raises: InvalidParameterValue if age_in_days is incorrect.
    """
    return IMPL.purge_deleted_records(context, age_in_days=age_in_days)


####################


def share_group_type_create(context, values, projects=None):
    """Create a new share group type."""
    return IMPL.share_group_type_create(context, values, projects)


def share_group_type_get_all(context, inactive=False, filters=None):
    """Get all share group types.

    :param context: context to query under
    :param inactive: Include inactive share group types to the result set
    :param filters: Filters for the query in the form of key/value.
        :is_public: Filter share group types based on visibility:

            * **True**: List public group types only
            * **False**: List private group types only
            * **None**: List both public and private group types

    :returns: list of matching share group types
    """
    return IMPL.share_group_type_get_all(context, inactive, filters)


def share_group_type_get(context, type_id, inactive=False,
                         expected_fields=None):
    """Get share_group type by id.

    :param context: context to query under
    :param type_id: group type id to get.
    :param inactive: Consider inactive group types when searching
    :param expected_fields: Return those additional fields.
                            Supported fields are: projects.
    :returns: share group type
    """
    return IMPL.share_group_type_get(
        context, type_id, inactive, expected_fields)


def share_group_type_get_by_name(context, name):
    """Get share group type by name."""
    return IMPL.share_group_type_get_by_name(context, name)


def share_group_type_access_get_all(context, type_id):
    """Get all share group type access of a share group type."""
    return IMPL.share_group_type_access_get_all(context, type_id)


def share_group_type_access_add(context, type_id, project_id):
    """Add share group type access for project."""
    return IMPL.share_group_type_access_add(context, type_id, project_id)


def share_group_type_access_remove(context, type_id, project_id):
    """Remove share group type access for project."""
    return IMPL.share_group_type_access_remove(context, type_id, project_id)


def share_group_type_destroy(context, type_id):
    """Delete a share group type."""
    return IMPL.share_group_type_destroy(context, type_id)


def share_group_type_specs_get(context, type_id):
    """Get all group specs for a share group type."""
    return IMPL.share_group_type_specs_get(context, type_id)


def share_group_type_specs_delete(context, type_id, key):
    """Delete the given group specs item."""
    return IMPL.share_group_type_specs_delete(context, type_id, key)


def share_group_type_specs_update_or_create(context, type_id, group_specs):
    """Create or update share group type specs.

    This adds or modifies the key/value pairs specified in the group
    specs dict argument.
    """
    return IMPL.share_group_type_specs_update_or_create(
        context, type_id, group_specs)


####################


def message_get(context, message_id):
    """Return a message with the specified ID."""
    return IMPL.message_get(context, message_id)


def message_get_all(context, filters=None, limit=None, offset=None,
                    sort_key=None, sort_dir=None):
    """Returns all messages with the project of the specified context."""
    return IMPL.message_get_all(context, filters=filters, limit=limit,
                                offset=offset, sort_key=sort_key,
                                sort_dir=sort_dir)


def message_create(context, values):
    """Creates a new message with the specified values."""
    return IMPL.message_create(context, values)


def message_destroy(context, message_id):
    """Deletes message with the specified ID."""
    return IMPL.message_destroy(context, message_id)


def cleanup_expired_messages(context):
    """Soft delete expired messages"""
    return IMPL.cleanup_expired_messages(context)


def backend_info_get(context, host):
    """Get hash info for given host."""
    return IMPL.backend_info_get(context, host)


def backend_info_update(context, host, value=None,
                        delete_existing=False):
    """Update hash info for host."""
    return IMPL.backend_info_update(context, host=host, value=value,
                                    delete_existing=delete_existing)

####################


def async_operation_data_get(context, entity_id, key=None, default=None):
    """Get one, list or all key-value pairs for given entity_id."""
    return IMPL.async_operation_data_get(context, entity_id, key, default)


def async_operation_data_update(context, entity_id, details,
                                delete_existing=False):
    """Update key-value pairs for given entity_id."""
    return IMPL.async_operation_data_update(context, entity_id, details,
                                            delete_existing)


def async_operation_data_delete(context, entity_id, key=None):
    """Remove one, list or all key-value pairs for given entity_id."""
    return IMPL.async_operation_data_delete(context, entity_id, key)

####################


def share_backup_create(context, share_id, values):
    """Create new share backup with specified values."""
    return IMPL.share_backup_create(context, share_id, values)


def share_backup_update(context, backup_id, values):
    """Updates a share backup with given values."""
    return IMPL.share_backup_update(context, backup_id, values)


def share_backup_get(context, backup_id):
    """Get share backup by id."""
    return IMPL.share_backup_get(context, backup_id)


def share_backups_get_all(context, filters=None, limit=None, offset=None,
                          sort_key=None, sort_dir=None):
    """Get all backups."""
    return IMPL.share_backups_get_all(
        context, filters=filters, limit=limit, offset=offset,
        sort_key=sort_key, sort_dir=sort_dir)


def share_backup_delete(context, backup_id):
    """Deletes backup with the specified ID."""
    return IMPL.share_backup_delete(context, backup_id)

#####################


def resource_lock_create(context, values):
    """Create a resource lock."""
    return IMPL.resource_lock_create(context, values)


def resource_lock_update(context, lock_id, values):
    """Update a resource lock."""
    return IMPL.resource_lock_update(context, lock_id, values)


def resource_lock_delete(context, lock_id):
    """Delete a resource lock."""
    return IMPL.resource_lock_delete(context, lock_id)


def resource_lock_get(context, lock_id):
    """Retrieve a resource lock."""
    return IMPL.resource_lock_get(context, lock_id)


def resource_lock_get_all(context, **kwargs):
    """Retrieve all resource locks."""
    return IMPL.resource_lock_get_all(context, **kwargs)
