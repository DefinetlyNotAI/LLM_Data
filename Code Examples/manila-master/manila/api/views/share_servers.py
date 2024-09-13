# Copyright 2014 OpenStack Foundation
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

from manila.api import common


class ViewBuilder(common.ViewBuilder):
    """Model a server API response as a python dictionary."""

    _collection_name = 'share_servers'
    _detail_version_modifiers = [
        "add_is_auto_deletable_and_identifier_fields",
        "add_share_network_subnet_id_field",
        "add_task_state_and_source_server_fields",
        "add_sec_service_update_fields",
        "add_share_network_subnet_ids_and_network_allocation_update_support"
    ]

    def build_share_server(self, request, share_server):
        """View of a share server."""
        return {
            'share_server':
                self._build_share_server_view(
                    request, share_server, detailed=True)
        }

    def build_share_servers(self, request, share_servers):
        return {
            'share_servers':
                [self._build_share_server_view(request, share_server)
                 for share_server in share_servers]
        }

    def build_share_server_details(self, details):
        return {'details': details}

    def _build_share_server_view(self, request, share_server, detailed=False):
        share_server_dict = {
            'id': share_server.id,
            'project_id': share_server.project_id,
            'updated_at': share_server.updated_at,
            'status': share_server.status,
            'host': share_server.host,
            'share_network_name': share_server.share_network_name,
            'share_network_id': share_server.share_network_id,
        }
        if detailed:
            share_server_dict['created_at'] = share_server.created_at
            share_server_dict['backend_details'] = share_server.backend_details

        self.update_versioned_resource_dict(
            request, share_server_dict, share_server)

        return share_server_dict

    @common.ViewBuilder.versioned_method("2.51", "2.69")
    def add_share_network_subnet_id_field(
            self, context, share_server_dict, share_server):
        """In 2.70, share_network_subnet_id is dropped, it becomes a list."""
        share_server_dict['share_network_subnet_id'] = (
            share_server['share_network_subnet_ids'][0]
            if share_server['share_network_subnet_ids'] else None)

    @common.ViewBuilder.versioned_method("2.49")
    def add_is_auto_deletable_and_identifier_fields(
            self, context, share_server_dict, share_server):
        share_server_dict['is_auto_deletable'] = (
            share_server['is_auto_deletable'])
        share_server_dict['identifier'] = share_server['identifier']

    @common.ViewBuilder.versioned_method("2.57")
    def add_task_state_and_source_server_fields(
            self, context, share_server_dict, share_server):
        share_server_dict['task_state'] = share_server['task_state']
        share_server_dict['source_share_server_id'] = (
            share_server['source_share_server_id'])

    @common.ViewBuilder.versioned_method("2.63")
    def add_sec_service_update_fields(
            self, context, share_server_dict, share_server):
        share_server_dict['security_service_update_support'] = share_server[
            'security_service_update_support']

    @common.ViewBuilder.versioned_method("2.70")
    def add_share_network_subnet_ids_and_network_allocation_update_support(
            self, context, share_server_dict, share_server):
        share_server_dict['share_network_subnet_ids'] = sorted(
            share_server['share_network_subnet_ids'])
        share_server_dict['network_allocation_update_support'] = (
            share_server['network_allocation_update_support'])
