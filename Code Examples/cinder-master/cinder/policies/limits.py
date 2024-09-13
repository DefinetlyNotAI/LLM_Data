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

EXTEND_LIMIT_ATTRIBUTE_POLICY = "limits_extension:used_limits"

deprecated_limits = base.CinderDeprecatedRule(
    name=EXTEND_LIMIT_ATTRIBUTE_POLICY,
    check_str=base.RULE_ADMIN_OR_OWNER
)


limits_policies = [
    policy.DocumentedRuleDefault(
        name=EXTEND_LIMIT_ATTRIBUTE_POLICY,
        check_str=base.SYSTEM_READER_OR_PROJECT_READER,
        description="Show limits with used limit attributes.",
        operations=[
            {
                'method': 'GET',
                'path': '/limits'
            }
        ],
        deprecated_rule=deprecated_limits,
    )
]


def list_rules():
    return limits_policies
