# Copyright 2012 OpenStack Foundation.
# All Rights Reserved.
#
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
from manila.common import constants
from manila.share import share_types

CONF = cfg.CONF


class ViewBuilder(common.ViewBuilder):

    _collection_name = 'types'

    _detail_version_modifiers = [
        "add_is_public_attr_core_api_like",
        "add_is_public_attr_extension_like",
        "add_inferred_optional_extra_specs",
        "add_description_attr",
        "add_is_default_attr"
    ]

    def show(self, request, share_type, brief=False):
        """Trim away extraneous share type attributes."""

        extra_specs = share_type.get('extra_specs', {})
        required_extra_specs = share_type.get('required_extra_specs', {})

        # Remove non-tenant-visible extra specs in a non-admin context
        if not request.environ['manila.context'].is_admin:
            extra_spec_names = share_types.get_tenant_visible_extra_specs()
            extra_specs = self._filter_extra_specs(extra_specs,
                                                   extra_spec_names)
            required_extra_specs = self._filter_extra_specs(
                required_extra_specs, extra_spec_names)

        trimmed = {
            'id': share_type.get('id'),
            'name': share_type.get('name'),
            'extra_specs': extra_specs,
            'required_extra_specs': required_extra_specs,
        }
        self.update_versioned_resource_dict(request, trimmed, share_type)
        if brief:
            return trimmed
        else:
            return dict(volume_type=trimmed, share_type=trimmed)

    @common.ViewBuilder.versioned_method("2.7")
    def add_is_public_attr_core_api_like(self, context, share_type_dict,
                                         share_type):
        share_type_dict['share_type_access:is_public'] = share_type.get(
            'is_public', True)

    @common.ViewBuilder.versioned_method("1.0", "2.6")
    def add_is_public_attr_extension_like(self, context, share_type_dict,
                                          share_type):
        share_type_dict['os-share-type-access:is_public'] = share_type.get(
            'is_public', True)

    @common.ViewBuilder.versioned_method("2.24")
    def add_inferred_optional_extra_specs(self, context, share_type_dict,
                                          share_type):

        # NOTE(cknight): The admin sees exactly which extra specs have been set
        # on the type, but in order to know how shares of a type will behave,
        # the user must also see the default values of any public extra specs
        # that aren't explicitly set on the type.
        if not context.is_admin:
            for extra_spec in constants.ExtraSpecs.INFERRED_OPTIONAL_MAP:
                if extra_spec not in share_type_dict['extra_specs']:
                    share_type_dict['extra_specs'][extra_spec] = (
                        constants.ExtraSpecs.INFERRED_OPTIONAL_MAP[extra_spec])

    def index(self, request, share_types):
        """Index over trimmed share types."""
        share_types_list = [self.show(request, share_type, True)
                            for share_type in share_types]
        return dict(volume_types=share_types_list,
                    share_types=share_types_list)

    def share_type_access(self, request, share_type):
        """Return a dictionary view of the projects with access to type."""
        projects = [
            {'share_type_id': share_type['id'], 'project_id': project_id}
            for project_id in share_type['projects']
        ]
        return {'share_type_access': projects}

    def _filter_extra_specs(self, extra_specs, valid_keys):
        return {key: value for key, value in extra_specs.items()
                if key in valid_keys}

    @common.ViewBuilder.versioned_method("2.41")
    def add_description_attr(self, context, share_type_dict, share_type):
        share_type_dict['description'] = share_type.get('description')

    @common.ViewBuilder.versioned_method("2.46")
    def add_is_default_attr(self, context, share_type_dict, share_type):
        is_default = False
        type_name = share_type.get('name')
        default_name = CONF.default_share_type

        if default_name is not None:
            is_default = default_name == type_name
        share_type_dict['is_default'] = is_default
