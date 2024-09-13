# Copyright 2011 OpenStack LLC.
# Copyright 2011 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright (c) 2015 Mirantis inc.
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
WSGI middleware for OpenStack Share API v2.
"""

from manila.api import extensions
import manila.api.openstack
from manila.api.v1 import limits
from manila.api.v1 import scheduler_stats
from manila.api.v1 import security_service
from manila.api.v1 import share_manage
from manila.api.v1 import share_types_extra_specs
from manila.api.v1 import share_unmanage
from manila.api.v2 import availability_zones
from manila.api.v2 import messages
from manila.api.v2 import quota_class_sets
from manila.api.v2 import quota_sets
from manila.api.v2 import resource_locks
from manila.api.v2 import services
from manila.api.v2 import share_access_metadata
from manila.api.v2 import share_accesses
from manila.api.v2 import share_backups
from manila.api.v2 import share_export_locations
from manila.api.v2 import share_group_snapshots
from manila.api.v2 import share_group_type_specs
from manila.api.v2 import share_group_types
from manila.api.v2 import share_groups
from manila.api.v2 import share_instance_export_locations
from manila.api.v2 import share_instances
from manila.api.v2 import share_network_subnets
from manila.api.v2 import share_networks
from manila.api.v2 import share_replica_export_locations
from manila.api.v2 import share_replicas
from manila.api.v2 import share_servers
from manila.api.v2 import share_snapshot_export_locations
from manila.api.v2 import share_snapshot_instance_export_locations
from manila.api.v2 import share_snapshot_instances
from manila.api.v2 import share_snapshots
from manila.api.v2 import share_transfer
from manila.api.v2 import share_types
from manila.api.v2 import shares
from manila.api import versions


class APIRouter(manila.api.openstack.APIRouter):
    """Route API requests.

    Routes requests on the OpenStack API to the appropriate controller
    and method.
    """
    ExtensionManager = extensions.ExtensionManager

    def _setup_routes(self, mapper):
        self.resources["versions"] = versions.create_resource()
        mapper.connect("versions", "/",
                       controller=self.resources["versions"],
                       action="index")

        mapper.redirect("", "/")

        self.resources["availability_zones_legacy"] = (
            availability_zones.create_resource_legacy())
        # TODO(vponomaryov): "os-availability-zone" is deprecated
        # since v2.7. Remove it when minimum API version becomes equal to
        # or greater than v2.7.
        mapper.resource("availability-zone",
                        "os-availability-zone",
                        controller=self.resources["availability_zones_legacy"])

        self.resources["availability_zones"] = (
            availability_zones.create_resource())
        mapper.resource("availability-zone",
                        "availability-zones",
                        controller=self.resources["availability_zones"])

        self.resources["services_legacy"] = services.create_resource_legacy()
        # TODO(vponomaryov): "os-services" is deprecated
        # since v2.7. Remove it when minimum API version becomes equal to
        # or greater than v2.7.
        mapper.resource("service",
                        "os-services",
                        controller=self.resources["services_legacy"])

        self.resources["services"] = services.create_resource()
        mapper.resource("service",
                        "services",
                        controller=self.resources["services"])
        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect("services",
                           "%s/services/ensure-shares" % path_prefix,
                           controller=self.resources["services"],
                           action="ensure_shares",
                           conditions={"method": ["POST"]})

        self.resources["quota_sets_legacy"] = (
            quota_sets.create_resource_legacy())
        # TODO(vponomaryov): "os-quota-sets" is deprecated
        # since v2.7. Remove it when minimum API version becomes equal to
        # or greater than v2.7.
        mapper.resource("quota-set",
                        "os-quota-sets",
                        controller=self.resources["quota_sets_legacy"],
                        member={"defaults": "GET"})

        self.resources["quota_sets"] = quota_sets.create_resource()
        mapper.resource("quota-set",
                        "quota-sets",
                        controller=self.resources["quota_sets"],
                        member={"defaults": "GET",
                                "detail": "GET"})

        self.resources["quota_class_sets_legacy"] = (
            quota_class_sets.create_resource_legacy())
        # TODO(vponomaryov): "os-quota-class-sets" is deprecated
        # since v2.7. Remove it when minimum API version becomes equal to
        # or greater than v2.7.
        mapper.resource("quota-class-set",
                        "os-quota-class-sets",
                        controller=self.resources["quota_class_sets_legacy"])

        self.resources["quota_class_sets"] = quota_class_sets.create_resource()
        mapper.resource("quota-class-set",
                        "quota-class-sets",
                        controller=self.resources["quota_class_sets"])

        self.resources["share_manage"] = share_manage.create_resource()
        # TODO(vponomaryov): "os-share-manage" is deprecated
        # since v2.7. Remove it when minimum API version becomes equal to
        # or greater than v2.7.
        mapper.resource("share_manage",
                        "os-share-manage",
                        controller=self.resources["share_manage"])

        self.resources["share_unmanage"] = share_unmanage.create_resource()
        # TODO(vponomaryov): "os-share-unmanage" is deprecated
        # since v2.7. Remove it when minimum API version becomes equal to
        # or greater than v2.7.
        mapper.resource("share_unmanage",
                        "os-share-unmanage",
                        controller=self.resources["share_unmanage"],
                        member={"unmanage": "POST"})

        self.resources["shares"] = shares.create_resource()
        mapper.resource("share", "shares",
                        controller=self.resources["shares"],
                        collection={"detail": "GET"},
                        member={"action": "POST"})

        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect("shares",
                           "%s/shares/manage" % path_prefix,
                           controller=self.resources["shares"],
                           action="manage",
                           conditions={"method": ["POST"]})

        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect("share_metadata",
                           "%s/shares/{resource_id}/metadata"
                           % path_prefix,
                           controller=self.resources["shares"],
                           action="create_metadata",
                           conditions={"method": ["POST"]})
            mapper.connect("share_metadata",
                           "%s/shares/{resource_id}/metadata"
                           % path_prefix,
                           controller=self.resources["shares"],
                           action="update_all_metadata",
                           conditions={"method": ["PUT"]})
            mapper.connect("share_metadata",
                           "%s/shares/{resource_id}/metadata/{key}"
                           % path_prefix,
                           controller=self.resources["shares"],
                           action="update_metadata_item",
                           conditions={"method": ["POST"]})
            mapper.connect("share_metadata",
                           "%s/shares/{resource_id}/metadata"
                           % path_prefix,
                           controller=self.resources["shares"],
                           action="index_metadata",
                           conditions={"method": ["GET"]})
            mapper.connect("share_metadata",
                           "%s/shares/{resource_id}/metadata/{key}"
                           % path_prefix,
                           controller=self.resources["shares"],
                           action="show_metadata",
                           conditions={"method": ["GET"]})
            mapper.connect("share_metadata",
                           "%s/shares/{resource_id}/metadata/{key}"
                           % path_prefix,
                           controller=self.resources["shares"],
                           action="delete_metadata",
                           conditions={"method": ["DELETE"]})

        self.resources["share_instances"] = share_instances.create_resource()
        mapper.resource("share_instance", "share_instances",
                        controller=self.resources["share_instances"],
                        collection={"detail": "GET"},
                        member={"action": "POST"})

        self.resources["share_instance_export_locations"] = (
            share_instance_export_locations.create_resource())

        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect("share_instances",
                           ("%s/share_instances/{share_instance_id}"
                            "/export_locations" % path_prefix),
                           controller=self.resources[
                               "share_instance_export_locations"],
                           action="index",
                           conditions={"method": ["GET"]})

            mapper.connect("share_instances",
                           ("%s/share_instances/{share_instance_id}"
                            "/export_locations"
                            "/{export_location_uuid}" % path_prefix),
                           controller=self.resources[
                               "share_instance_export_locations"],
                           action="show",
                           conditions={"method": ["GET"]})

            mapper.connect("share_instance",
                           "%s/shares/{share_id}/instances" % path_prefix,
                           controller=self.resources["share_instances"],
                           action="get_share_instances",
                           conditions={"method": ["GET"]})

            self.resources["share_export_locations"] = (
                share_export_locations.create_resource())
            mapper.connect("shares",
                           "%s/shares/{share_id}"
                           "/export_locations" % path_prefix,
                           controller=self.resources["share_export_locations"],
                           action="index",
                           conditions={"method": ["GET"]})
            mapper.connect("shares",
                           ("%s/shares/{share_id}/export_locations"
                            "/{export_location_uuid}" % path_prefix),
                           controller=self.resources["share_export_locations"],
                           action="show",
                           conditions={"method": ["GET"]})
            mapper.connect("export_locations_metadata",
                           "%s/shares/{share_id}/export_locations"
                           "/{resource_id}/metadata" % path_prefix,
                           controller=self.resources["share_export_locations"],
                           action="create_metadata",
                           conditions={"method": ["POST"]})
            mapper.connect("export_locations_metadata",
                           "%s/shares/{share_id}/export_locations"
                           "/{resource_id}/metadata" % path_prefix,
                           controller=self.resources["share_export_locations"],
                           action="update_all_metadata",
                           conditions={"method": ["PUT"]})
            mapper.connect("export_locations_metadata",
                           "%s/shares/{share_id}/export_locations/"
                           "{resource_id}/metadata/{key}"
                           % path_prefix,
                           controller=self.resources["share_export_locations"],
                           action="update_metadata_item",
                           conditions={"method": ["POST"]})
            mapper.connect("export_locations_metadata",
                           "%s/shares/{share_id}/export_locations/"
                           "{resource_id}/metadata" % path_prefix,
                           controller=self.resources["share_export_locations"],
                           action="index_metadata",
                           conditions={"method": ["GET"]})
            mapper.connect("export_locations_metadata",
                           "%s/shares/{share_id}/export_locations/"
                           "{resource_id}/metadata/{key}"
                           % path_prefix,
                           controller=self.resources["share_export_locations"],
                           action="show_metadata",
                           conditions={"method": ["GET"]})
            mapper.connect("export_locations_metadata",
                           "%s/shares/{share_id}/export_locations/"
                           "{resource_id}/metadata/{key}"
                           % path_prefix,
                           controller=self.resources["share_export_locations"],
                           action="delete_metadata",
                           conditions={"method": ["DELETE"]})

        self.resources["snapshots"] = share_snapshots.create_resource()
        mapper.resource("snapshot", "snapshots",
                        controller=self.resources["snapshots"],
                        collection={"detail": "GET"},
                        member={"action": "POST"})
        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect("snapshots_metadata",
                           "%s/snapshots/{resource_id}/metadata"
                           % path_prefix,
                           controller=self.resources["snapshots"],
                           action="create_metadata",
                           conditions={"method": ["POST"]})
            mapper.connect("snapshots_metadata",
                           "%s/snapshots/{resource_id}/metadata"
                           % path_prefix,
                           controller=self.resources["snapshots"],
                           action="update_all_metadata",
                           conditions={"method": ["PUT"]})
            mapper.connect("snapshots_metadata",
                           "%s/snapshots/{resource_id}/metadata/{key}"
                           % path_prefix,
                           controller=self.resources["snapshots"],
                           action="update_metadata_item",
                           conditions={"method": ["POST"]})
            mapper.connect("snapshots_metadata",
                           "%s/snapshots/{resource_id}/metadata"
                           % path_prefix,
                           controller=self.resources["snapshots"],
                           action="index_metadata",
                           conditions={"method": ["GET"]})
            mapper.connect("snapshots_metadata",
                           "%s/snapshots/{resource_id}/metadata/{key}"
                           % path_prefix,
                           controller=self.resources["snapshots"],
                           action="show_metadata",
                           conditions={"method": ["GET"]})
            mapper.connect("snapshots_metadata",
                           "%s/snapshots/{resource_id}/metadata/{key}"
                           % path_prefix,
                           controller=self.resources["snapshots"],
                           action="delete_metadata",
                           conditions={"method": ["DELETE"]})

        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect("snapshots",
                           "%s/snapshots/manage" % path_prefix,
                           controller=self.resources["snapshots"],
                           action="manage",
                           conditions={"method": ["POST"]})

            mapper.connect("snapshots",
                           "%s/snapshots/{snapshot_id}"
                           "/access-list" % path_prefix,
                           controller=self.resources["snapshots"],
                           action="access_list",
                           conditions={"method": ["GET"]})

            self.resources["share_snapshot_export_locations"] = (
                share_snapshot_export_locations.create_resource())
            mapper.connect("snapshots",
                           "%s/snapshots/{snapshot_id}"
                           "/export-locations" % path_prefix,
                           controller=self.resources[
                               "share_snapshot_export_locations"],
                           action="index",
                           conditions={"method": ["GET"]})

            mapper.connect("snapshots",
                           "%s/snapshots/{snapshot_id}/export-locations"
                           "/{export_location_id}" % path_prefix,
                           controller=self.resources[
                               "share_snapshot_export_locations"],
                           action="show",
                           conditions={"method": ["GET"]})

        self.resources['snapshot_instances'] = (
            share_snapshot_instances.create_resource())
        mapper.resource("snapshot-instance", "snapshot-instances",
                        controller=self.resources['snapshot_instances'],
                        collection={'detail': 'GET'},
                        member={'action': 'POST'})

        self.resources["share_snapshot_instance_export_locations"] = (
            share_snapshot_instance_export_locations.create_resource())

        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect("snapshot-instance",
                           "%s/snapshot-instances/{snapshot_instance_id}"
                           "/export-locations" % path_prefix,
                           controller=self.resources[
                               "share_snapshot_instance_export_locations"],
                           action="index",
                           conditions={"method": ["GET"]})

            mapper.connect("snapshot-instance",
                           "%s/snapshot-instances/{snapshot_instance_id}"
                           "/export-locations"
                           "/{export_location_id}" % path_prefix,
                           controller=self.resources[
                               "share_snapshot_instance_export_locations"],
                           action="show",
                           conditions={"method": ["GET"]})

        self.resources["limits"] = limits.create_resource()
        mapper.resource("limit", "limits",
                        controller=self.resources["limits"])

        self.resources["security_services"] = (
            security_service.create_resource())
        mapper.resource("security-service", "security-services",
                        controller=self.resources["security_services"],
                        collection={"detail": "GET"})

        self.resources["share_networks"] = share_networks.create_resource()
        mapper.resource(share_networks.RESOURCE_NAME,
                        "share-networks",
                        controller=self.resources["share_networks"],
                        collection={"detail": "GET"},
                        member={"action": "POST"})

        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            self.resources["share_network_subnets"] = (
                share_network_subnets.create_resource())
            mapper.connect("share-networks",
                           "%s/share-networks/{share_network_id}"
                           "/subnets" % path_prefix,
                           controller=self.resources["share_network_subnets"],
                           action="create",
                           conditions={"method": ["POST"]})
            mapper.connect("share-networks",
                           "%s/share-networks/{share_network_id}"
                           "/subnets/{share_network_subnet_id}" % path_prefix,
                           controller=self.resources["share_network_subnets"],
                           action="delete",
                           conditions={"method": ["DELETE"]})
            mapper.connect("share-networks",
                           "%s/share-networks/{share_network_id}"
                           "/subnets/{share_network_subnet_id}" % path_prefix,
                           controller=self.resources["share_network_subnets"],
                           action="show",
                           conditions={"method": ["GET"]})
            mapper.connect("share-networks",
                           "%s/share-networks/{share_network_id}"
                           "/subnets" % path_prefix,
                           controller=self.resources["share_network_subnets"],
                           action="index",
                           conditions={"method": ["GET"]})

        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect("subnets_metadata",
                           "%s/share-networks/{share_network_id}"
                           "/subnets/{resource_id}/metadata" % path_prefix,
                           controller=self.resources["share_network_subnets"],
                           action="create_metadata",
                           conditions={"method": ["POST"]})
            mapper.connect("subnets_metadata",
                           "%s/share-networks/{share_network_id}"
                           "/subnets/{resource_id}/metadata" % path_prefix,
                           controller=self.resources["share_network_subnets"],
                           action="update_all_metadata",
                           conditions={"method": ["PUT"]})
            mapper.connect("subnets_metadata",
                           "%s/share-networks/{share_network_id}"
                           "/subnets/{resource_id}"
                           "/metadata/{key}" % path_prefix,
                           controller=self.resources["share_network_subnets"],
                           action="update_metadata_item",
                           conditions={"method": ["POST"]})
            mapper.connect("subnets_metadata",
                           "%s/share-networks/{share_network_id}"
                           "/subnets/{resource_id}/metadata" % path_prefix,
                           controller=self.resources["share_network_subnets"],
                           action="index_metadata",
                           conditions={"method": ["GET"]})
            mapper.connect("subnets_metadata",
                           "%s/share-networks/{share_network_id}"
                           "/subnets/{resource_id}"
                           "/metadata/{key}" % path_prefix,
                           controller=self.resources["share_network_subnets"],
                           action="show_metadata",
                           conditions={"method": ["GET"]})
            mapper.connect("subnets_metadata",
                           "%s/share-networks/{share_network_id}"
                           "/subnets/{resource_id}"
                           "/metadata/{key}" % path_prefix,
                           controller=self.resources["share_network_subnets"],
                           action="delete_metadata",
                           conditions={"method": ["DELETE"]})

        self.resources["share_servers"] = share_servers.create_resource()
        mapper.resource("share_server",
                        "share-servers",
                        controller=self.resources["share_servers"],
                        member={"action": "POST"})

        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect("details",
                           "%s/share-servers/{id}/details" % path_prefix,
                           controller=self.resources["share_servers"],
                           action="details",
                           conditions={"method": ["GET"]})
            mapper.connect("share_servers",
                           "%s/share-servers/manage" % path_prefix,
                           controller=self.resources["share_servers"],
                           action="manage",
                           conditions={"method": ["POST"]})

        self.resources["types"] = share_types.create_resource()
        mapper.resource("type", "types",
                        controller=self.resources["types"],
                        collection={"detail": "GET", "default": "GET"},
                        member={"action": "POST",
                                "os-share-type-access": "GET",
                                "share_type_access": "GET"})

        self.resources["extra_specs"] = (
            share_types_extra_specs.create_resource())
        mapper.resource("extra_spec", "extra_specs",
                        controller=self.resources["extra_specs"],
                        parent_resource=dict(member_name="type",
                                             collection_name="types"))

        self.resources["scheduler_stats"] = scheduler_stats.create_resource()
        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect("pools",
                           "%s/scheduler-stats/pools" % path_prefix,
                           controller=self.resources["scheduler_stats"],
                           action="pools_index",
                           conditions={"method": ["GET"]})
            mapper.connect("pools",
                           "%s/scheduler-stats/pools/detail" % path_prefix,
                           controller=self.resources["scheduler_stats"],
                           action="pools_detail",
                           conditions={"method": ["GET"]})

        self.resources["share-groups"] = share_groups.create_resource()
        mapper.resource(
            "share-group",
            "share-groups",
            controller=self.resources["share-groups"],
            collection={"detail": "GET"})
        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect(
                "share-groups",
                "%s/share-groups/{id}/action" % path_prefix,
                controller=self.resources["share-groups"],
                action="action",
                conditions={"method": ["POST"]})

        self.resources["share-group-types"] = (
            share_group_types.create_resource())
        mapper.resource(
            "share-group-type",
            "share-group-types",
            controller=self.resources["share-group-types"],
            collection={"detail": "GET", "default": "GET"},
            member={"action": "POST"})
        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect(
                "share-group-types",
                "%s/share-group-types/{id}/access" % path_prefix,
                controller=self.resources["share-group-types"],
                action="share_group_type_access",
                conditions={"method": ["GET"]})

        # NOTE(ameade): These routes can be simplified when the following
        # issue is fixed: https://github.com/bbangert/routes/issues/68
        self.resources["group-specs"] = (
            share_group_type_specs.create_resource())

        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect(
                "share-group-types",
                "%s/share-group-types/{id}/group-specs" % path_prefix,
                controller=self.resources["group-specs"],
                action="index",
                conditions={"method": ["GET"]})
            mapper.connect(
                "share-group-types",
                "%s/share-group-types/{id}/group-specs" % path_prefix,
                controller=self.resources["group-specs"],
                action="create",
                conditions={"method": ["POST"]})
            mapper.connect(
                "share-group-types",
                "%s/share-group-types/{id}/group-specs/{key}" % path_prefix,
                controller=self.resources["group-specs"],
                action="show",
                conditions={"method": ["GET"]})
            mapper.connect(
                "share-group-types",
                "%s/share-group-types/{id}/group-specs/{key}" % path_prefix,
                controller=self.resources["group-specs"],
                action="delete",
                conditions={"method": ["DELETE"]})
            mapper.connect(
                "share-group-types",
                "%s/share-group-types/{id}/group-specs/{key}" % path_prefix,
                controller=self.resources["group-specs"],
                action="update",
                conditions={"method": ["PUT"]})

        self.resources["share-group-snapshots"] = (
            share_group_snapshots.create_resource())
        mapper.resource(
            "share-group-snapshot",
            "share-group-snapshots",
            controller=self.resources["share-group-snapshots"],
            collection={"detail": "GET"},
            member={"members": "GET", "action": "POST"})

        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect(
                "share-group-snapshots",
                "%s/share-group-snapshots/{id}/action" % path_prefix,
                controller=self.resources["share-group-snapshots"],
                action="action",
                conditions={"method": ["POST"]})

        self.resources['share-replicas'] = share_replicas.create_resource()
        mapper.resource("share-replica", "share-replicas",
                        controller=self.resources['share-replicas'],
                        collection={'detail': 'GET'},
                        member={'action': 'POST'})

        self.resources['share_transfers'] = (
            share_transfer.create_resource())
        mapper.resource("share-transfer", "share-transfers",
                        controller=self.resources['share_transfers'],
                        collection={'detail': 'GET'},
                        member={'accept': 'POST'})

        self.resources["share-replica-export-locations"] = (
            share_replica_export_locations.create_resource())
        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            mapper.connect("share-replicas",
                           ("%s/share-replicas/{share_replica_id}"
                            "/export-locations" % path_prefix),
                           controller=self.resources[
                               "share-replica-export-locations"],
                           action="index",
                           conditions={"method": ["GET"]})
            mapper.connect("share-replicas",
                           ("%s/share-replicas/{share_replica_id}"
                            "/export-locations"
                            "/{export_location_uuid}" % path_prefix),
                           controller=self.resources[
                               "share-replica-export-locations"],
                           action="show",
                           conditions={"method": ["GET"]})

        self.resources['messages'] = messages.create_resource()
        mapper.resource("message", "messages",
                        controller=self.resources['messages'])

        self.resources["share-access-rules"] = share_accesses.create_resource()
        mapper.resource(
            "share-access-rule",
            "share-access-rules",
            controller=self.resources["share-access-rules"],
            collection={"detail": "GET"})

        for path_prefix in ['/{project_id}', '']:
            # project_id is optional
            self.resources["access-metadata"] = (
                share_access_metadata.create_resource())
            access_metadata_controller = self.resources["access-metadata"]
            mapper.connect("share-access-rules",
                           "%s/share-access-rules"
                           "/{access_id}/metadata" % path_prefix,
                           controller=access_metadata_controller,
                           action="update",
                           conditions={"method": ["PUT"]})

            mapper.connect("share-access-rules",
                           "%s/share-access-rules"
                           "/{access_id}/metadata/{key}" % path_prefix,
                           controller=access_metadata_controller,
                           action="delete",
                           conditions={"method": ["DELETE"]})

        self.resources['share-backups'] = share_backups.create_resource()
        mapper.resource("share-backup",
                        "share-backups",
                        controller=self.resources['share-backups'],
                        collection={'detail': 'GET'},
                        member={'action': 'POST'})

        self.resources["resource_locks"] = resource_locks.create_resource()
        mapper.resource("resource-lock", "resource-locks",
                        controller=self.resources["resource_locks"])
