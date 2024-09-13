# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
from oslo_config import cfg

from manila.api import common

CONF = cfg.CONF


class ShareGroupTypeViewBuilder(common.ViewBuilder):
    _collection_name = 'share_group_types'

    _detail_version_modifiers = [
        "add_is_default_attr",
    ]

    def show(self, request, share_group_type, brief=False):
        """Trim away extraneous share group type attributes."""
        group_specs = share_group_type.get('group_specs', {})
        trimmed = {
            'id': share_group_type.get('id'),
            'name': share_group_type.get('name'),
            'is_public': share_group_type.get('is_public'),
            'group_specs': group_specs,
            'share_types': [
                st['share_type_id'] for st in share_group_type['share_types']],
        }
        self.update_versioned_resource_dict(request, trimmed, share_group_type)
        return trimmed if brief else {"share_group_type": trimmed}

    def index(self, request, share_group_types):
        """Index over trimmed share group types."""
        share_group_types_list = [
            self.show(request, share_group_type, True)
            for share_group_type in share_group_types
        ]
        return {"share_group_types": share_group_types_list}

    @common.ViewBuilder.versioned_method("2.46")
    def add_is_default_attr(self, context,
                            share_group_type_dict,
                            share_group_type):
        is_default = False
        type_name = share_group_type.get('name')
        default_name = CONF.default_share_group_type

        if default_name is not None:
            is_default = default_name == type_name
        share_group_type_dict['is_default'] = is_default
