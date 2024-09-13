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
from cinder.api.views import snapshots as views_v2


class ViewBuilder(views_v2.ViewBuilder):
    """Model a snapshots API V3 response as a python dictionary."""

    def detail(self, request, snapshot):
        """Detailed view of a single snapshot."""
        snapshot_ref = super(ViewBuilder, self).detail(request, snapshot)

        req_version = request.api_version_request
        # Add group_snapshot_id if min version is greater than or equal
        # to GROUP_SNAPSHOTS.
        snap = snapshot_ref['snapshot']
        if req_version.matches(mv.GROUP_SNAPSHOTS, None):
            snap['group_snapshot_id'] = snapshot.get('group_snapshot_id')
        if req_version.matches(mv.SNAPSHOT_LIST_USER_ID, None):
            snap['user_id'] = snapshot.get('user_id')
        if req_version.matches(mv.USE_QUOTA):
            snap['consumes_quota'] = snapshot.get('use_quota')
        return snapshot_ref
