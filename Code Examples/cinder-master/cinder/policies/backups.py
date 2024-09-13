# Copyright (c) 2017 Huawei Technologies Co., Ltd.
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

from oslo_policy import policy

from cinder.policies import base


GET_ALL_POLICY = 'backup:get_all'
GET_POLICY = 'backup:get'
CREATE_POLICY = 'backup:create'
UPDATE_POLICY = 'backup:update'
DELETE_POLICY = 'backup:delete'
RESTORE_POLICY = 'backup:restore'
IMPORT_POLICY = 'backup:backup-import'
EXPORT_POLICY = 'backup:export-import'
BACKUP_ATTRIBUTES_POLICY = 'backup:backup_project_attribute'


deprecated_get_all_policy = base.CinderDeprecatedRule(
    name=GET_ALL_POLICY,
    check_str=base.RULE_ADMIN_OR_OWNER,
)
deprecated_get_policy = base.CinderDeprecatedRule(
    name=GET_POLICY,
    check_str=base.RULE_ADMIN_OR_OWNER,
)
deprecated_create_policy = base.CinderDeprecatedRule(
    name=CREATE_POLICY,
    check_str=""
)
deprecated_update_policy = base.CinderDeprecatedRule(
    name=UPDATE_POLICY,
    check_str=base.RULE_ADMIN_OR_OWNER
)
deprecated_delete_policy = base.CinderDeprecatedRule(
    name=DELETE_POLICY,
    check_str=base.RULE_ADMIN_OR_OWNER
)
deprecated_restore_policy = base.CinderDeprecatedRule(
    name=RESTORE_POLICY,
    check_str=base.RULE_ADMIN_OR_OWNER
)


backups_policies = [
    policy.DocumentedRuleDefault(
        name=GET_ALL_POLICY,
        check_str=base.SYSTEM_READER_OR_PROJECT_READER,
        description="List backups.",
        operations=[
            {
                'method': 'GET',
                'path': '/backups'
            },
            {
                'method': 'GET',
                'path': '/backups/detail'
            }
        ],
        deprecated_rule=deprecated_get_all_policy,
    ),
    policy.DocumentedRuleDefault(
        name=BACKUP_ATTRIBUTES_POLICY,
        check_str=base.RULE_ADMIN_API,
        description="List backups or show backup with project attributes.",
        operations=[
            {
                'method': 'GET',
                'path': '/backups/{backup_id}'
            },
            {
                'method': 'GET',
                'path': '/backups/detail'
            }
        ],
    ),
    policy.DocumentedRuleDefault(
        name=CREATE_POLICY,
        check_str=base.SYSTEM_ADMIN_OR_PROJECT_MEMBER,
        description="Create backup.",
        operations=[
            {
                'method': 'POST',
                'path': '/backups'
            }
        ],
        deprecated_rule=deprecated_create_policy,
    ),
    policy.DocumentedRuleDefault(
        name=GET_POLICY,
        check_str=base.SYSTEM_READER_OR_PROJECT_READER,
        description="Show backup.",
        operations=[
            {
                'method': 'GET',
                'path': '/backups/{backup_id}'
            }
        ],
        deprecated_rule=deprecated_get_policy
    ),
    policy.DocumentedRuleDefault(
        name=UPDATE_POLICY,
        check_str=base.SYSTEM_ADMIN_OR_PROJECT_MEMBER,
        description="Update backup.",
        operations=[
            {
                'method': 'PUT',
                'path': '/backups/{backup_id}'
            }
        ],
        deprecated_rule=deprecated_update_policy,
    ),
    policy.DocumentedRuleDefault(
        name=DELETE_POLICY,
        check_str=base.SYSTEM_ADMIN_OR_PROJECT_MEMBER,
        description="Delete backup.",
        operations=[
            {
                'method': 'DELETE',
                'path': '/backups/{backup_id}'
            }
        ],
        deprecated_rule=deprecated_delete_policy,
    ),
    policy.DocumentedRuleDefault(
        name=RESTORE_POLICY,
        check_str=base.SYSTEM_ADMIN_OR_PROJECT_MEMBER,
        description="Restore backup.",
        operations=[
            {
                'method': 'POST',
                'path': '/backups/{backup_id}/restore'
            }
        ],
        deprecated_rule=deprecated_restore_policy,
    ),
    policy.DocumentedRuleDefault(
        name=IMPORT_POLICY,
        check_str=base.RULE_ADMIN_API,
        description="Import backup.",
        operations=[
            {
                'method': 'POST',
                'path': '/backups/{backup_id}/import_record'
            }
        ],
    ),
    policy.DocumentedRuleDefault(
        name=EXPORT_POLICY,
        check_str=base.RULE_ADMIN_API,
        description="Export backup.",
        operations=[
            {
                'method': 'POST',
                'path': '/backups/{backup_id}/export_record'
            }
        ],
    ),
]


def list_rules():
    return backups_policies
