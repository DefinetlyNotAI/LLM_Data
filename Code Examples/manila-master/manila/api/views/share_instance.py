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
from manila.common import constants


class ViewBuilder(common.ViewBuilder):
    """Model a server API response as a python dictionary."""

    _collection_name = 'share_instances'
    _collection_links = 'share_instances_links'

    _detail_version_modifiers = [
        "remove_export_locations",
        "add_access_rules_status_field",
        "add_replication_fields",
        "add_share_type_field",
        "add_cast_rules_to_readonly_field",
        "add_progress_field",
        "translate_creating_from_snapshot_status",
        "add_updated_at_field",
    ]

    def detail_list(self, request, instances):
        """Detailed view of a list of share instances."""
        return self._list_view(self.detail, request, instances)

    def detail(self, request, share_instance):
        """Detailed view of a single share instance."""
        export_locations = [e['path'] for e in share_instance.export_locations]

        instance_dict = {
            'id': share_instance.get('id'),
            'share_id': share_instance.get('share_id'),
            'availability_zone': share_instance.get('availability_zone'),
            'created_at': share_instance.get('created_at'),
            'host': share_instance.get('host'),
            'status': share_instance.get('status'),
            'share_network_id': share_instance.get('share_network_id'),
            'share_server_id': share_instance.get('share_server_id'),
            'export_location': share_instance.get('export_location'),
            'export_locations': export_locations,
        }

        self.update_versioned_resource_dict(
            request, instance_dict, share_instance)
        return {'share_instance': instance_dict}

    def _list_view(self, func, request, instances):
        """Provide a view for a list of share instances."""
        instances_list = [func(request, instance)['share_instance']
                          for instance in instances]
        instances_links = self._get_collection_links(request,
                                                     instances,
                                                     self._collection_name)
        instances_dict = {self._collection_name: instances_list}

        if instances_links:
            instances_dict[self._collection_links] = instances_links

        return instances_dict

    @common.ViewBuilder.versioned_method("2.9")
    def remove_export_locations(self, context, share_instance_dict,
                                share_instance):
        share_instance_dict.pop('export_location')
        share_instance_dict.pop('export_locations')

    @common.ViewBuilder.versioned_method("2.10")
    def add_access_rules_status_field(self, context, instance_dict,
                                      share_instance):
        instance_dict['access_rules_status'] = (
            share_instance.get('access_rules_status')
        )

    @common.ViewBuilder.versioned_method("2.11")
    def add_replication_fields(self, context, instance_dict, share_instance):
        instance_dict['replica_state'] = share_instance.get('replica_state')

    @common.ViewBuilder.versioned_method("2.22")
    def add_share_type_field(self, context, instance_dict, share_instance):
        instance_dict['share_type_id'] = share_instance.get('share_type_id')

    @common.ViewBuilder.versioned_method("2.30")
    def add_cast_rules_to_readonly_field(self, context, instance_dict,
                                         share_instance):
        instance_dict['cast_rules_to_readonly'] = share_instance.get(
            'cast_rules_to_readonly', False)

    @common.ViewBuilder.versioned_method("1.0", "2.53")
    def translate_creating_from_snapshot_status(self, context, instance_dict,
                                                share_instance):
        if (share_instance.get('status') ==
                constants.STATUS_CREATING_FROM_SNAPSHOT):
            instance_dict['status'] = constants.STATUS_CREATING

    @common.ViewBuilder.versioned_method("2.54")
    def add_progress_field(self, context, instance_dict, share_instance):
        instance_dict['progress'] = share_instance.get('progress')

    @common.ViewBuilder.versioned_method("2.71")
    def add_updated_at_field(self, context, instance_dict, share_instance):
        instance_dict['updated_at'] = share_instance.get('updated_at')
