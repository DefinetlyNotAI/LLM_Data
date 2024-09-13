# Copyright (c) 2015 Mirantis Inc.
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

import copy

from oslo_utils import strutils

from manila.api import common


class ViewBuilder(common.ViewBuilder):
    """Model export-locations API responses as a python dictionary."""

    _collection_name = "export_locations"

    _detail_version_modifiers = [
        'add_preferred_path_attribute',
        'add_metadata_attribute',
    ]

    def _get_export_location_view(self, request, export_location,
                                  detail=False, replica=False):

        context = request.environ['manila.context']

        view = {
            'id': export_location['uuid'],
            'path': export_location['path'],
        }
        self.update_versioned_resource_dict(request, view, export_location)
        if context.is_admin:
            view['share_instance_id'] = export_location['share_instance_id']
            view['is_admin_only'] = export_location['is_admin_only']

        if detail:
            view['created_at'] = export_location['created_at']
            view['updated_at'] = export_location['updated_at']

        if replica:
            share_instance = export_location['share_instance']
            view['replica_state'] = share_instance['replica_state']
            view['availability_zone'] = share_instance['availability_zone']

        return {'export_location': view}

    def summary(self, request, export_location, replica=False):
        """Summary view of a single export location."""
        return self._get_export_location_view(
            request, export_location, detail=False, replica=replica)

    def detail(self, request, export_location, replica=False):
        """Detailed view of a single export location."""
        return self._get_export_location_view(
            request, export_location, detail=True, replica=replica)

    def _list_export_locations(self, req, export_locations,
                               detail=False, replica=False):
        """View of export locations list."""
        view_method = self.detail if detail else self.summary
        return {
            self._collection_name: [
                view_method(req, elocation, replica=replica)['export_location']
                for elocation in export_locations
            ]}

    def detail_list(self, request, export_locations):
        """Detailed View of export locations list."""
        return self._list_export_locations(request, export_locations,
                                           detail=True)

    def summary_list(self, request, export_locations, replica=False):
        """Summary View of export locations list."""
        return self._list_export_locations(request, export_locations,
                                           detail=False, replica=replica)

    @common.ViewBuilder.versioned_method('2.14')
    def add_preferred_path_attribute(self, context, view_dict,
                                     export_location):
        view_dict['preferred'] = strutils.bool_from_string(
            export_location['el_metadata'].get('preferred'))

    @common.ViewBuilder.versioned_method('2.87')
    def add_metadata_attribute(self, context, view_dict,
                               export_location):
        metadata = export_location.get('el_metadata')
        meta_copy = copy.copy(metadata)
        meta_copy.pop('preferred', None)
        view_dict['metadata'] = meta_copy
