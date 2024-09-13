#    Copyright (c) 2020 Open-E, Inc.
#    All Rights Reserved.
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

from oslo_config import cfg

jdss_connection_opts = [
    cfg.ListOpt('san_hosts',
                default='',
                help='IP address of Open-E JovianDSS SA'),
    cfg.IntOpt('jovian_recovery_delay',
               default=60,
               help='Time before HA cluster failure.'),
    cfg.ListOpt('jovian_ignore_tpath',
                default=[],
                help='List of multipath ip addresses to ignore.'),
]

jdss_iscsi_opts = [
    cfg.IntOpt('chap_password_len',
               default=12,
               help='Length of the random string for CHAP password.'),
    cfg.StrOpt('jovian_pool',
               default='Pool-0',
               help='JovianDSS pool that holds all cinder volumes'),
]

jdss_volume_opts = [
    cfg.StrOpt('jovian_block_size',
               default='64K',
               choices=[('16K', 'Use 16K block size'),
                        ('32K', 'Use 32K block size'),
                        ('64K', 'Use 64K block size'),
                        ('128K', 'Use 128K block size'),
                        ('256K', 'Use 256K block size'),
                        ('512K', 'Use 512K block size'),
                        ('1M', 'Use 1M block size')],
               help='Block size for new volume')
]

CONF = cfg.CONF
CONF.register_opts(jdss_connection_opts)
CONF.register_opts(jdss_iscsi_opts)
CONF.register_opts(jdss_volume_opts)
