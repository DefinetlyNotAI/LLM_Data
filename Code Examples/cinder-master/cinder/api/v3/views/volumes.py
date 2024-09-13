# Copyright 2016 EMC Corporation
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

from cinder.api import microversions as mv
from cinder.api.v2.views import volumes as views_v2
from cinder.common import constants as cinder_constants


class ViewBuilder(views_v2.ViewBuilder):
    """Model a volumes API V3 response as a python dictionary."""

    _collection_name = "volumes"

    def quick_summary(self, volume_count, volume_size,
                      all_distinct_metadata=None):
        """View of volumes summary.

        It includes number of volumes, size of volumes and all distinct
        metadata of volumes.
        """
        summary = {
            'volume-summary': {
                'total_count': volume_count,
                'total_size': volume_size
            }
        }
        if all_distinct_metadata is not None:
            summary['volume-summary']['metadata'] = all_distinct_metadata
        return summary

    def detail(self, request, volume):
        """Detailed view of a single volume."""
        volume_ref = super(ViewBuilder, self).detail(request, volume)

        req_version = request.api_version_request
        # Add group_id if min version is greater than or equal to GROUP_VOLUME.
        if req_version.matches(mv.GROUP_VOLUME, None):
            volume_ref['volume']['group_id'] = volume.get('group_id')

        # Add provider_id if min version is greater than or equal to
        # VOLUME_DETAIL_PROVIDER_ID for admin.
        if (request.environ['cinder.context'].is_admin and
                req_version.matches(mv.VOLUME_DETAIL_PROVIDER_ID, None)):
            volume_ref['volume']['provider_id'] = volume.get('provider_id')

        if req_version.matches(
                mv.VOLUME_SHARED_TARGETS_AND_SERVICE_FIELDS, None):

            # For microversion 3.69 or higher it is acceptable to be null
            # but for earlier versions we convert None to True
            shared = volume.get('shared_targets', False)
            if (not req_version.matches(mv.SHARED_TARGETS_TRISTATE, None)
                    and shared is None):
                shared = True

            volume_ref['volume']['shared_targets'] = shared
            volume_ref['volume']['service_uuid'] = volume.get(
                'service_uuid', None)

        if (request.environ['cinder.context'].is_admin and req_version.matches(
                mv.VOLUME_CLUSTER_NAME, None)):
            volume_ref['volume']['cluster_name'] = volume.get(
                'cluster_name', None)

        if req_version.matches(mv.VOLUME_TYPE_ID_IN_VOLUME_DETAIL, None):
            volume_ref[
                'volume']["volume_type_id"] = volume['volume_type'].get('id')

        if req_version.matches(mv.ENCRYPTION_KEY_ID_IN_DETAILS, None):
            encryption_key_id = volume.get('encryption_key_id', None)
            if (encryption_key_id and
                    encryption_key_id != cinder_constants.FIXED_KEY_ID):
                volume_ref['volume']['encryption_key_id'] = encryption_key_id

        if req_version.matches(mv.USE_QUOTA):
            volume_ref['volume']['consumes_quota'] = volume.get('use_quota')

        return volume_ref

    def _list_view(self, func, request, volumes, volume_count,
                   coll_name=_collection_name):
        """Provide a view for a list of volumes.

        :param func: Function used to format the volume data
        :param request: API request
        :param volumes: List of volumes in dictionary format
        :param volume_count: Length of the original list of volumes
        :param coll_name: Name of collection, used to generate the next link
                          for a pagination query
        :returns: Volume data in dictionary format
        """
        volumes_list = [func(request, volume)['volume'] for volume in volumes]
        volumes_links = self._get_collection_links(request,
                                                   volumes,
                                                   coll_name,
                                                   volume_count)
        volumes_dict = {"volumes": volumes_list}

        if volumes_links:
            volumes_dict['volumes_links'] = volumes_links

        req_version = request.api_version_request
        if req_version.matches(
                mv.SUPPORT_COUNT_INFO, None) and volume_count is not None:
            volumes_dict['count'] = volume_count

        return volumes_dict

    def _get_volume_type(self, request, volume):
        """Returns the volume type of the volume.

        Retrieves the volume type name for microversion 3.63.
        Otherwise, it uses the default implementation from super.
        """

        req_version = request.api_version_request
        if req_version.matches(mv.VOLUME_TYPE_ID_IN_VOLUME_DETAIL):
            if volume.get('volume_type'):
                return volume['volume_type']['name']
            return None

        return super(ViewBuilder, self)._get_volume_type(request, volume)
