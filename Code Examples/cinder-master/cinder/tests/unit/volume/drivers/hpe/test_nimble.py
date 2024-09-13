# Nimble Storage, Inc. (c) 2013-2014
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


import http.client as http_client
import sys
from unittest import mock

from oslo_utils import uuidutils

from cinder import context
from cinder import exception
from cinder.objects import fields
from cinder.objects import volume as obj_volume
from cinder.objects import volume_type
from cinder.tests.unit import fake_constants as fake
from cinder.tests.unit import fake_group
from cinder.tests.unit import fake_snapshot
from cinder.tests.unit import fake_volume
from cinder.tests.unit import test
from cinder.volume.drivers.hpe import nimble
from cinder.volume import volume_types
from cinder.volume import volume_utils

NIMBLE_CLIENT = 'cinder.volume.drivers.hpe.nimble.NimbleRestAPIExecutor'
NIMBLE_URLLIB2 = 'cinder.volume.drivers.hpe.nimble.requests'
NIMBLE_RANDOM = 'cinder.volume.drivers.hpe.nimble.random'
NIMBLE_ISCSI_DRIVER = 'cinder.volume.drivers.hpe.nimble.NimbleISCSIDriver'
NIMBLE_FC_DRIVER = 'cinder.volume.drivers.hpe.nimble.NimbleFCDriver'
DRIVER_VERSION = '4.3.0'
nimble.DEFAULT_SLEEP = 0

FAKE_POSITIVE_LOGIN_RESPONSE_1 = '2c20aad78a220ed1dae21dcd6f9446f5'

FAKE_POSITIVE_LOGIN_RESPONSE_2 = '2c20aad78a220ed1dae21dcd6f9446ff'

FAKE_POSITIVE_HEADERS = {'X-Auth-Token': FAKE_POSITIVE_LOGIN_RESPONSE_1}

FAKE_POSITIVE_NETCONFIG_RESPONSE = {
    'role': 'active',
    'subnet_list': [{'network': '172.18.212.0',
                     'discovery_ip': '172.18.108.21',
                     'type': 'data',
                     'allow_iscsi': True,
                     'label': 'data1',
                     'allow_group': True,
                     'vlan_id': 0}],
    'array_list': [{'nic_list': [{'subnet_label': 'data1',
                                  'tagged': False,
                                  'data_ip': '172.18.212.82',
                                  'name': 'eth3'}]}],
    'name': 'test-array'}

FAKE_NEGATIVE_NETCONFIG_RESPONSE = exception.VolumeDriverException(
    "Session expired")

FAKE_CREATE_VOLUME_POSITIVE_RESPONSE = {
    'clone': False,
    'name': "testvolume"}

FAKE_CREATE_VOLUME_POSITIVE_RESPONSE_ENCRYPTION = {
    'clone': False,
    'name': "testvolume-encryption"}

FAKE_CREATE_VOLUME_POSITIVE_RESPONSE_PERF_POLICY = {
    'clone': False,
    'name': "testvolume-perf-policy"}

FAKE_CREATE_VOLUME_POSITIVE_RESPONSE_MULTI_INITIATOR = {
    'clone': False,
    'name': "testvolume-multi-initiator"}

FAKE_CREATE_VOLUME_POSITIVE_RESPONSE_DEDUPE = {
    'clone': False,
    'name': "testvolume-dedupe"}

FAKE_CREATE_VOLUME_POSITIVE_RESPONSE_QOS = {
    'clone': False,
    'name': "testvolume-qos"}

FAKE_EXTRA_SPECS = {'multiattach': '<is> True',
                    'nimble:iops-limit': '1024'}

FAKE_GET_VOL_INFO_RESPONSE = {'name': 'testvolume',
                              'clone': False,
                              'target_name': 'iqn.test',
                              'online': True,
                              'agent_type': 'openstack'}

FAKE_GET_VOL_INFO_RESPONSE_MANAGE = {'name': 'testvolume',
                                     'agent_type': 'none',
                                     'online': False,
                                     'target_name': 'iqn.test'}

FAKE_GET_VOL_INFO_ONLINE = {'name': 'testvolume',
                            'size': 2048,
                            'online': True,
                            'agent_type': 'none'}

FAKE_GET_VOL_INFO_RETYPE = {'name': 'testvolume',
                            'size': 2048,
                            'online': True,
                            'agent_type': 'none',
                            'pool_id': 'none',
                            'pool_name': 'none'}

FAKE_GET_VOL_INFO_BACKUP_RESPONSE = {'name': 'testvolume',
                                     'clone': True,
                                     'target_name': 'iqn.test',
                                     'online': False,
                                     'agent_type': 'openstack',
                                     'parent_vol_id': 'volume-' +
                                                      fake.VOLUME2_ID,
                                     'base_snap_id': 'test-backup-snap'}

FAKE_GET_SNAP_INFO_BACKUP_RESPONSE = {
    'description': "backup-vol-" + fake.VOLUME2_ID,
    'name': 'test-backup-snap',
    'id': fake.SNAPSHOT_ID,
    'vol_id': fake.VOLUME_ID,
    'volume_name': 'volume-' + fake.VOLUME_ID}

FAKE_POSITIVE_GROUP_CONFIG_RESPONSE = {
    'name': 'group-test',
    'version_current': '0.0.0.0',
    'access_protocol_list': ['iscsi']}

FAKE_LOGIN_POST_RESPONSE = {
    'data': {'session_token': FAKE_POSITIVE_LOGIN_RESPONSE_1}}

FAKE_EXTEND_VOLUME_PARAMS = {'data': {'size': 5120,
                                      'reserve': 0,
                                      'warn_level': 80,
                                      'limit': 100,
                                      'snap_limit': sys.maxsize}}

FAKE_IGROUP_LIST_RESPONSE = [
    {'iscsi_initiators': [{'iqn': 'test-initiator1'}],
     'name': 'test-igrp1'},
    {'iscsi_initiators': [{'iqn': 'test-initiator2'}],
     'name': 'test-igrp2'}]

FAKE_IGROUP_LIST_RESPONSE_FC = [
    {'fc_initiators': [{'wwpn': '10:00:00:00:00:00:00:00'}],
     'name': 'test-igrp1'},
    {'fc_initiators': [{'wwpn': '10:00:00:00:00:00:00:00'},
                       {'wwpn': '10:00:00:00:00:00:00:01'}],
     'name': 'test-igrp2'}]

FAKE_GET_VOL_INFO_REVERT = {'name': 'testvolume',
                            'id': fake.VOLUME_ID,
                            'clone': False,
                            'target_name': 'iqn.test',
                            'online': True,
                            'agent_type': 'openstack',
                            'last_snap': {'snap_id': fake.SNAPSHOT_ID}}

FAKE_SNAP_INFO_REVERT = {'name': 'testsnap',
                         'id': fake.SNAPSHOT2_ID}

FAKE_CREATE_VOLUME_NEGATIVE_RESPONSE = exception.VolumeBackendAPIException(
    "Volume testvolume not found")

FAKE_VOLUME_INFO_NEGATIVE_RESPONSE = exception.VolumeBackendAPIException(
    "Volume testvolume not found")

FAKE_CREATE_VOLUME_NEGATIVE_ENCRYPTION = exception.VolumeBackendAPIException(
    "Volume testvolume-encryption not found")

FAKE_CREATE_VOLUME_NEGATIVE_PERFPOLICY = exception.VolumeBackendAPIException(
    "Volume testvolume-perfpolicy not found")

FAKE_CREATE_VOLUME_NEGATIVE_DEDUPE = exception.VolumeBackendAPIException(
    "The specified pool is not capable of hosting deduplicated volumes")

FAKE_CREATE_VOLUME_NEGATIVE_QOS = exception.VolumeBackendAPIException(
    "Please set valid IOPS limitin the range [256, 4294967294]")

FAKE_VOLUME_RESTORE_NEGATIVE_RESPONSE = exception.VolumeBackendAPIException(
    "No recent Snapshot found")

FAKE_POSITIVE_GROUP_INFO_RESPONSE = {
    'version_current': '3.0.0.0',
    'group_target_enabled': False,
    'name': 'group-nimble',
    'usage_valid': True,
    'usable_capacity_bytes': 8016883089408,
    'free_space': 101111111901}

FAKE_GET_VOL_INFO_RESPONSE = {'name': 'testvolume-cg',
                              'clone': False,
                              'target_name': 'iqn.test',
                              'online': True,
                              'agent_type': 'openstack'}

FAKE_EXTRA_SPECS_CG = {'consistent_group_snapshot_enabled': "<is> False"}

FAKE_VOLUME_TYPE = {'extra_specs': FAKE_EXTRA_SPECS_CG}
SRC_CG_VOLUME_ID = 'bd21d11b-c765-4c68-896c-6b07f63cfcb6'

SRC_CG_VOLUME_NAME = 'volume-' + SRC_CG_VOLUME_ID

volume_src_cg = {'name': SRC_CG_VOLUME_NAME,
                 'id': SRC_CG_VOLUME_ID,
                 'display_name': 'Foo Volume',
                 'size': 2,
                 'host': 'FAKE_CINDER_HOST',
                 'volume_type': None,
                 'volume_type_id': None}

VOLUME_TYPE_ID_CG = 'd03338a9-9115-48a3-8dfc-44444444444'

VOLUME_ID = 'd03338a9-9115-48a3-8dfc-35cdfcdc15a7'
admin_context = context.get_admin_context()

VOLUME_NAME = 'volume-' + VOLUME_ID
FAKE_GROUP = fake_group.fake_group_obj(
    admin_context, id=fake.GROUP_ID, status='available')


volume_cg = {'name': VOLUME_NAME,
             'id': VOLUME_ID,
             'display_name': 'Foo Volume',
             'provider_location': 12,
             'size': 2,
             'host': 'FAKE_CINDER_HOST',
             'volume_type': 'cg_type',
             'volume_type_id': VOLUME_TYPE_ID_CG}

FAKE_CREATE_VOLUME_POSITIVE_RESPONSE_CG = {
    'clone': False,
    'name': "testvolume-cg"}

FAKE_GET_VOLID_INFO_RESPONSE = {'vol_id': fake.VOLUME_ID}

FAKE_GET_VOLCOLL_INFO_RESPONSE = {'volcoll_id': fake.VOLUME2_ID}

FAKE_ASSOCIATE_VOLCOLL_INFO_RESPONSE = {'vol_id': fake.VOLUME_ID,
                                        'volcoll_id': fake.VOLUME2_ID}

FAKE_GENERIC_POSITIVE_RESPONSE = ""
FAKE_VOLUME_DELETE_HAS_CLONE_RESPONSE = "Object has a clone"

FAKE_TYPE_ID = fake.VOLUME_TYPE_ID
FAKE_TYPE_ID_NEW = fake.VOLUME_TYPE2_ID
FAKE_POOL_ID = fake.GROUP_ID
FAKE_PERFORMANCE_POLICY_ID = fake.OBJECT_ID
NIMBLE_MANAGEMENT_IP = "10.18.108.55"
NIMBLE_SAN_LOGIN = "nimble"
NIMBLE_SAN_PASS = "nimble_pass"

SRC_CONSIS_GROUP_ID = '7d7dfa02-ac6e-48cb-96af-8a0cd3008d47'

FAKE_SRC_GROUP = fake_group.fake_group_obj(
    admin_context, id = SRC_CONSIS_GROUP_ID, status = 'available')

REPL_DEVICES = [{
    'san_login': 'nimble',
    'san_password': 'nimble_pass',
    'san_ip': '10.18.108.66',
    'schedule_name': 'every-minute',
    'downstream_partner': 'nimblevsagroup2',
    'period': 1,
    'period_unit': 'minutes'}]


def create_configuration(username, password, ip_address,
                         pool_name=None, subnet_label=None,
                         thin_provision=True, devices=None):
    configuration = mock.Mock()
    configuration.san_login = username
    configuration.san_password = password
    configuration.san_ip = ip_address
    configuration.san_thin_provision = thin_provision
    configuration.nimble_pool_name = pool_name
    configuration.nimble_subnet_label = subnet_label
    configuration.safe_get.return_value = 'NIMBLE'
    configuration.replication_device = devices
    return configuration


class NimbleDriverBaseTestCase(test.TestCase):

    """Base Class for the NimbleDriver Tests."""

    def setUp(self):
        super(NimbleDriverBaseTestCase, self).setUp()
        self.mock_client_service = None
        self.mock_client_class = None
        self.driver = None

    @staticmethod
    def client_mock_decorator(configuration):
        def client_mock_wrapper(func):
            def inner_client_mock(
                    self, mock_client_class, mock_urllib2, *args, **kwargs):
                self.mock_client_class = mock_client_class
                self.mock_client_service = mock.MagicMock(name='Client')
                self.mock_client_class.return_value = self.mock_client_service
                self.driver = nimble.NimbleISCSIDriver(
                    configuration=configuration)
                mock_login_response = mock_urllib2.post.return_value
                mock_login_response = mock.MagicMock()
                mock_login_response.status_code.return_value = http_client.OK
                mock_login_response.json.return_value = (
                    FAKE_LOGIN_POST_RESPONSE)
                self.driver.do_setup(context.get_admin_context())
                self.driver.APIExecutor.login()
                func(self, *args, **kwargs)
            return inner_client_mock
        return client_mock_wrapper

    @staticmethod
    def client_mock_decorator_fc(configuration):
        def client_mock_wrapper(func):
            def inner_client_mock(
                    self, mock_client_class, mock_urllib2, *args, **kwargs):
                self.mock_client_class = mock_client_class
                self.mock_client_service = mock.MagicMock(name='Client')
                self.mock_client_class.return_value = (
                    self.mock_client_service)
                self.driver = nimble.NimbleFCDriver(
                    configuration=configuration)
                mock_login_response = mock_urllib2.post.return_value
                mock_login_response = mock.MagicMock()
                mock_login_response.status_code.return_value = http_client.OK
                mock_login_response.json.return_value = (
                    FAKE_LOGIN_POST_RESPONSE)
                self.driver.do_setup(context.get_admin_context())
                self.driver.APIExecutor.login()
                func(self, *args, **kwargs)
            return inner_client_mock
        return client_mock_wrapper

    @staticmethod
    def client_mock_decorator_nimble_api(username, password, ip, verify):
        def client_mock_wrapper(func):
            def inner_client_mock(
                    self, mock_client_class, mock_urllib2, *args, **kwargs):
                self.mock_client_class = mock_client_class
                self.mock_client_service = mock.MagicMock(name='Client')
                self.mock_client_class.return_value = (
                    self.mock_client_service)
                self.driver = nimble.NimbleRestAPIExecutor(
                    username=username, password=password, ip=ip, verify=verify)
                mock_login_response = mock_urllib2.post.return_value
                mock_login_response = mock.MagicMock()
                mock_login_response.status_code.return_value = http_client.OK
                mock_login_response.json.return_value = (
                    FAKE_LOGIN_POST_RESPONSE)
                func(self, *args, **kwargs)
            return inner_client_mock
        return client_mock_wrapper


class NimbleDriverLoginTestCase(NimbleDriverBaseTestCase):

    """Tests do_setup api."""

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        "nimble", "nimble_pass", "10.18.108.55", 'default', '*'))
    def test_do_setup_positive(self):
        expected_call_list = [mock.call.login()]
        self.mock_client_service.assert_has_calls(expected_call_list)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_expire_session_id(self):
        expected_call_list = [mock.call.login()]
        self.mock_client_service.assert_has_calls(expected_call_list)

        self.driver.APIExecutor.get("groups")
        expected_call_list = [mock.call.get_group_info(),
                              mock.call.login(),
                              mock.call.get("groups")]

        self.assertEqual(
            self.mock_client_service.method_calls,
            expected_call_list)


class NimbleDriverVolumeTestCase(NimbleDriverBaseTestCase):

    """Tests volume related api's."""

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @mock.patch.object(volume_types, 'get_volume_type_extra_specs',
                       mock.Mock(type_id=FAKE_TYPE_ID, return_value={
                                 'nimble:perfpol-name': 'default',
                                 'nimble:encryption': 'yes'}))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    def test_create_volume_positive(self):
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_RESPONSE)
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)

        self.assertEqual({
            'provider_location': '172.18.108.21:3260 iqn.test',
            'provider_auth': None},
            self.driver.create_volume({'name': 'testvolume',
                                       'size': 1,
                                       'volume_type_id': None,
                                       'display_name': '',
                                       'display_description': ''}))

        self.mock_client_service.create_vol.assert_called_once_with(
            {'name': 'testvolume',
             'size': 1,
             'volume_type_id': None,
             'display_name': '',
             'display_description': ''},
            'default',
            False,
            'iSCSI',
            False)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @mock.patch.object(volume_types, 'get_volume_type_extra_specs',
                       mock.Mock(type_id=FAKE_TYPE_ID, return_value={
                                 'nimble:perfpol-name': 'default',
                                 'nimble:encryption': 'yes'}))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    def test_create_volume_with_unicode(self):
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_RESPONSE)
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)

        self.assertEqual({
            'provider_location': '172.18.108.21:3260 iqn.test',
            'provider_auth': None},
            self.driver.create_volume({'name': 'testvolume',
                                       'size': 1,
                                       'volume_type_id': None,
                                       'display_name': u'unicode_name',
                                       'display_description': ''}))

        self.mock_client_service.create_vol.assert_called_once_with(
            {'name': 'testvolume',
             'size': 1,
             'volume_type_id': None,
             'display_name': u'unicode_name',
             'display_description': ''},
            'default',
            False,
            'iSCSI',
            False)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @mock.patch.object(volume_types, 'get_volume_type_extra_specs',
                       mock.Mock(type_id=FAKE_TYPE_ID, return_value={
                           'nimble:perfpol-name': 'default',
                           'nimble:encryption': 'yes',
                           'multiattach': 'false'}))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_create_volume_encryption_positive(self):
        self.mock_client_service._execute_create_vol.return_value = (
            FAKE_CREATE_VOLUME_POSITIVE_RESPONSE_ENCRYPTION)
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_RESPONSE)
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)

        volume = {'name': 'testvolume-encryption',
                  'size': 1,
                  'volume_type_id': FAKE_TYPE_ID,
                  'display_name': '',
                  'display_description': ''}
        self.assertEqual({
            'provider_location': '172.18.108.21:3260 iqn.test',
            'provider_auth': None},
            self.driver.create_volume(volume))

        self.mock_client_service.create_vol.assert_called_once_with(
            {'name': 'testvolume-encryption',
             'size': 1,
             'volume_type_id': FAKE_TYPE_ID,
             'display_name': '',
             'display_description': '',
             },
            'default',
            False,
            'iSCSI',
            False)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @mock.patch.object(volume_types, 'get_volume_type_extra_specs',
                       mock.Mock(type_id=FAKE_TYPE_ID, return_value={
                           'nimble:perfpol-name': 'VMware ESX',
                           'nimble:encryption': 'no',
                           'multiattach': 'false'}))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_create_volume_perfpolicy_positive(self):
        self.mock_client_service._execute_create_vol.return_value = (
            FAKE_CREATE_VOLUME_POSITIVE_RESPONSE_PERF_POLICY)
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_RESPONSE)
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)

        self.assertEqual(
            {'provider_location': '172.18.108.21:3260 iqn.test',
             'provider_auth': None},
            self.driver.create_volume({'name': 'testvolume-perfpolicy',
                                       'size': 1,
                                       'volume_type_id': FAKE_TYPE_ID,
                                       'display_name': '',
                                       'display_description': ''}))

        self.mock_client_service.create_vol.assert_called_once_with(
            {'name': 'testvolume-perfpolicy',
             'size': 1,
             'volume_type_id': FAKE_TYPE_ID,
             'display_name': '',
             'display_description': '',
             },
            'default',
            False,
            'iSCSI',
            False)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @mock.patch.object(volume_types, 'get_volume_type_extra_specs',
                       mock.Mock(type_id=FAKE_TYPE_ID, return_value={
                           'nimble:perfpol-name': 'default',
                           'nimble:encryption': 'no',
                           'multiattach': 'true'}))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_create_volume_multi_initiator_positive(self):
        self.mock_client_service._execute_create_vol.return_value = (
            FAKE_CREATE_VOLUME_POSITIVE_RESPONSE_MULTI_INITIATOR)
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_RESPONSE)
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)

        self.assertEqual(
            {'provider_location': '172.18.108.21:3260 iqn.test',
             'provider_auth': None},
            self.driver.create_volume({'name': 'testvolume-multi-initiator',
                                       'size': 1,
                                       'volume_type_id': FAKE_TYPE_ID,
                                       'display_name': '',
                                       'display_description': ''}))

        self.mock_client_service.create_vol.assert_called_once_with(
            {'name': 'testvolume-multi-initiator',
             'size': 1,
             'volume_type_id': FAKE_TYPE_ID,
             'display_name': '',
             'display_description': '',
             },
            'default',
            False,
            'iSCSI',
            False)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @mock.patch.object(volume_types, 'get_volume_type_extra_specs',
                       mock.Mock(type_id=FAKE_TYPE_ID, return_value={
                           'nimble:perfpol-name': 'default',
                           'nimble:encryption': 'no',
                           'nimble:dedupe': 'true'}))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_create_volume_dedupe_positive(self):
        self.mock_client_service._execute_create_vol.return_value = (
            FAKE_CREATE_VOLUME_POSITIVE_RESPONSE_DEDUPE)
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_RESPONSE)
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)

        self.assertEqual(
            {'provider_location': '172.18.108.21:3260 iqn.test',
             'provider_auth': None},
            self.driver.create_volume({'name': 'testvolume-dedupe',
                                       'size': 1,
                                       'volume_type_id': FAKE_TYPE_ID,
                                       'display_name': '',
                                       'display_description': ''}))

        self.mock_client_service.create_vol.assert_called_once_with(
            {'name': 'testvolume-dedupe',
             'size': 1,
             'volume_type_id': FAKE_TYPE_ID,
             'display_name': '',
             'display_description': '',
             },
            'default',
            False,
            'iSCSI',
            False)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @mock.patch.object(volume_types, 'get_volume_type_extra_specs',
                       mock.Mock(type_id=FAKE_TYPE_ID, return_value={
                           'nimble:perfpol-name': 'default',
                           'nimble:iops-limit': '1024'}))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_create_volume_qos_positive(self):
        self.mock_client_service._execute_create_vol.return_value = (
            FAKE_CREATE_VOLUME_POSITIVE_RESPONSE_QOS)
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_RESPONSE)
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)

        self.assertEqual(
            {'provider_location': '172.18.108.21:3260 iqn.test',
             'provider_auth': None},
            self.driver.create_volume({'name': 'testvolume-qos',
                                       'size': 1,
                                       'volume_type_id': FAKE_TYPE_ID,
                                       'display_name': '',
                                       'display_description': ''}))

        self.mock_client_service.create_vol.assert_called_once_with(
            {'name': 'testvolume-qos',
             'size': 1,
             'volume_type_id': FAKE_TYPE_ID,
             'display_name': '',
             'display_description': '',
             },
            'default',
            False,
            'iSCSI',
            False)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    @mock.patch.object(volume_types, 'get_volume_type_extra_specs',
                       mock.Mock(type_id=FAKE_TYPE_ID, return_value={
                           'nimble:perfpol-name': 'default',
                           'nimble:encryption': 'no',
                           'multiattach': 'false'}))
    def test_create_volume_negative(self):
        self.mock_client_service.get_vol_info.side_effect = (
            FAKE_CREATE_VOLUME_NEGATIVE_RESPONSE)

        self.assertRaises(
            exception.VolumeBackendAPIException,
            self.driver.create_volume,
            {'name': 'testvolume',
             'size': 1,
             'volume_type_id': FAKE_TYPE_ID,
             'display_name': '',
             'display_description': ''})

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_create_volume_encryption_negative(self):
        self.mock_client_service.get_vol_info.side_effect = (
            FAKE_CREATE_VOLUME_NEGATIVE_ENCRYPTION)
        self.assertRaises(
            exception.VolumeBackendAPIException,
            self.driver.create_volume,
            {'name': 'testvolume-encryption',
             'size': 1,
             'volume_type_id': None,
             'display_name': '',
             'display_description': ''})

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_create_volume_perfpolicy_negative(self):
        self.mock_client_service.get_vol_info.side_effect = (
            FAKE_CREATE_VOLUME_NEGATIVE_PERFPOLICY)
        self.assertRaises(
            exception.VolumeBackendAPIException,
            self.driver.create_volume,
            {'name': 'testvolume-perfpolicy',
             'size': 1,
             'volume_type_id': None,
             'display_name': '',
             'display_description': ''})

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_create_volume_dedupe_negative(self):
        self.mock_client_service.get_vol_info.side_effect = (
            FAKE_CREATE_VOLUME_NEGATIVE_DEDUPE)
        self.assertRaises(
            exception.VolumeBackendAPIException,
            self.driver.create_volume,
            {'name': 'testvolume-dedupe',
             'size': 1,
             'volume_type_id': None,
             'display_name': '',
             'display_description': ''})

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    @mock.patch.object(volume_types, 'get_volume_type_extra_specs',
                       mock.Mock(type_id=FAKE_TYPE_ID, return_value={
                           'nimble:perfpol-name': 'default',
                           'nimble:iops-limit': '200'}))
    def test_create_volume_qos_negative(self):
        self.mock_client_service.get_vol_info.side_effect = (
            FAKE_CREATE_VOLUME_NEGATIVE_QOS)
        self.assertRaises(
            exception.VolumeBackendAPIException,
            self.driver.create_volume,
            {'name': 'testvolume-qos',
             'size': 1,
             'volume_type_id': None,
             'display_name': '',
             'display_description': ''})

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @mock.patch.object(volume_types, 'get_volume_type_extra_specs',
                       mock.Mock(type_id=FAKE_TYPE_ID, return_value={
                                 'nimble:perfpol-name': 'default',
                                 'nimble:encryption': 'yes'}))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*', devices=REPL_DEVICES))
    def test_create_volume_replicated(self):
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_RESPONSE)
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)

        self.assertEqual({
            'provider_location': '172.18.108.21:3260 iqn.test',
            'provider_auth': None,
            'replication_status': 'enabled'},
            self.driver.create_volume({'name': 'testvolume',
                                       'size': 1,
                                       'volume_type_id': None,
                                       'display_name': '',
                                       'display_description': ''}))

        self.mock_client_service.create_vol.assert_called_once_with(
            {'name': 'testvolume',
             'size': 1,
             'volume_type_id': None,
             'display_name': '',
             'display_description': ''},
            'default',
            False,
            'iSCSI',
            False)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    @mock.patch(NIMBLE_ISCSI_DRIVER + ".is_volume_backup_clone", mock.Mock(
        return_value=['', '']))
    def test_delete_volume(self):
        self.mock_client_service.online_vol.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.mock_client_service.delete_vol.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.driver.delete_volume({'name': 'testvolume'})
        expected_calls = [mock.call.online_vol(
            'testvolume', False),
            mock.call.delete_vol('testvolume')]

        self.mock_client_service.assert_has_calls(expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    @mock.patch(NIMBLE_ISCSI_DRIVER + ".is_volume_backup_clone", mock.Mock(
        return_value=['', '']))
    def test_delete_volume_with_clone(self):
        self.mock_client_service.delete_vol.side_effect = \
            nimble.NimbleAPIException(FAKE_VOLUME_DELETE_HAS_CLONE_RESPONSE)

        self.assertRaises(
            exception.VolumeIsBusy,
            self.driver.delete_volume,
            {'name': 'testvolume'})

        expected_calls = [
            mock.call.login(),
            mock.call.online_vol('testvolume', False),
            mock.call.delete_vol('testvolume'),
            mock.call.delete_vol('testvolume'),
            mock.call.delete_vol('testvolume'),
            mock.call.online_vol('testvolume', True)]

        self.mock_client_service.assert_has_calls(expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    @mock.patch(NIMBLE_ISCSI_DRIVER + ".is_volume_backup_clone", mock.Mock(
        return_value=['test-backup-snap', 'volume-' + fake.VOLUME_ID]))
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host')
    def test_delete_volume_with_backup(self, mock_volume_list):
        mock_volume_list.return_value = []
        self.mock_client_service.online_vol.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.mock_client_service.delete_vol.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.mock_client_service.online_snap.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.mock_client_service.delete_snap.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)

        self.driver.delete_volume({'name': 'testvolume'})
        expected_calls = [mock.call.online_vol(
            'testvolume', False),
            mock.call.delete_vol('testvolume'),
            mock.call.online_snap('volume-' + fake.VOLUME_ID,
                                  False,
                                  'test-backup-snap'),
            mock.call.delete_snap('volume-' + fake.VOLUME_ID,
                                  'test-backup-snap')]

        self.mock_client_service.assert_has_calls(expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*', devices=REPL_DEVICES))
    @mock.patch(NIMBLE_ISCSI_DRIVER + ".is_volume_backup_clone", mock.Mock(
        return_value=['', '']))
    def test_delete_volume_replicated(self):
        self.mock_client_service.online_vol.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.mock_client_service.delete_vol.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)

        self.driver.delete_volume({'name': 'testvolume'})
        expected_calls = [mock.call.online_vol(
            'testvolume', False),
            mock.call.delete_vol('testvolume')]

        self.mock_client_service.assert_has_calls(expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_extend_volume(self):
        self.mock_client_service.edit_vol.return_value = (
            FAKE_CREATE_VOLUME_POSITIVE_RESPONSE)
        self.driver.extend_volume({'name': 'testvolume'}, 5)

        self.mock_client_service.edit_vol.assert_called_once_with(
            'testvolume', FAKE_EXTEND_VOLUME_PARAMS)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(volume_types, 'get_volume_type_extra_specs',
                       mock.Mock(type_id=FAKE_TYPE_ID,
                                 return_value={
                                     'nimble:perfpol-name': 'default',
                                     'nimble:encryption': 'yes',
                                     'multiattach': False,
                                     'nimble:iops-limit': '1024'}))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*', False))
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host')
    @mock.patch(NIMBLE_RANDOM)
    def test_create_cloned_volume(self, mock_random, mock_volume_list):
        mock_random.sample.return_value = fake.VOLUME_ID
        mock_volume_list.return_value = []
        self.mock_client_service.snap_vol.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.mock_client_service.clone_vol.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_RESPONSE)
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)

        volume = obj_volume.Volume(context.get_admin_context(),
                                   id=fake.VOLUME_ID,
                                   size=5.0,
                                   _name_id=None,
                                   display_name='',
                                   volume_type_id=FAKE_TYPE_ID
                                   )
        src_volume = obj_volume.Volume(context.get_admin_context(),
                                       id=fake.VOLUME2_ID,
                                       _name_id=None,
                                       size=5.0)
        self.assertEqual({
            'provider_location': '172.18.108.21:3260 iqn.test',
            'provider_auth': None},
            self.driver.create_cloned_volume(volume, src_volume))

        expected_calls = [mock.call.snap_vol(
            {'volume_name': "volume-" + fake.VOLUME2_ID,
                'name': 'openstack-clone-volume-' + fake.VOLUME_ID + "-" +
                        fake.VOLUME_ID,
                'volume_size': src_volume['size'],
                'display_name': volume['display_name'],
                'display_description': ''}),
            mock.call.clone_vol(volume,
                                {'volume_name': "volume-" + fake.VOLUME2_ID,
                                 'name': 'openstack-clone-volume-' +
                                         fake.VOLUME_ID + "-" +
                                         fake.VOLUME_ID,
                                 'volume_size': src_volume['size'],
                                 'display_name': volume['display_name'],
                                 'display_description': ''},
                                True, False, 'iSCSI', 'default')]

        self.mock_client_service.assert_has_calls(expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_manage_volume_positive(self):
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_RESPONSE_MANAGE)
        self.mock_client_service.online_vol.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.mock_client_service.edit_vol.return_value = (
            FAKE_CREATE_VOLUME_POSITIVE_RESPONSE)
        self.assertEqual({
            'provider_location': '172.18.108.21:3260 iqn.test',
            'provider_auth': None},
            self.driver.manage_existing({'name': 'volume-abcdef',
                                         'id': fake.VOLUME_ID,
                                         'agent_type': None},
                                        {'source-name': 'test-vol'}))
        expected_calls = [mock.call.edit_vol(
            'test-vol', {'data': {'agent_type': 'openstack',
                                  'name': 'volume-abcdef'}}),
            mock.call.online_vol('volume-abcdef', True)]
        self.mock_client_service.assert_has_calls(expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_manage_volume_which_is_online(self):
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_ONLINE)
        self.assertRaises(
            exception.InvalidVolume,
            self.driver.manage_existing,
            {'name': 'volume-abcdef'},
            {'source-name': 'test-vol'})

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_manage_volume_get_size(self):
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_ONLINE)
        size = self.driver.manage_existing_get_size(
            {'name': 'volume-abcdef'}, {'source-name': 'test-vol'})
        self.assertEqual(2, size)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_manage_volume_with_improper_ref(self):
        self.assertRaises(
            exception.ManageExistingInvalidReference,
            self.driver.manage_existing,
            {'name': 'volume-abcdef'},
            {'source-id': 'test-vol'})

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_manage_volume_with_nonexistant_volume(self):
        self.mock_client_service.get_vol_info.side_effect = (
            FAKE_VOLUME_INFO_NEGATIVE_RESPONSE)
        self.assertRaises(
            exception.VolumeBackendAPIException,
            self.driver.manage_existing,
            {'name': 'volume-abcdef'},
            {'source-name': 'test-vol'})

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_manage_volume_with_wrong_agent_type(self):
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_RESPONSE)
        self.assertRaises(
            exception.ManageExistingAlreadyManaged,
            self.driver.manage_existing,
            {'id': 'abcdef', 'name': 'volume-abcdef'},
            {'source-name': 'test-vol'})

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_unmanage_volume_positive(self):
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_RESPONSE)
        self.mock_client_service.edit_vol.return_value = (
            FAKE_CREATE_VOLUME_POSITIVE_RESPONSE)
        self.driver.unmanage({'name': 'volume-abcdef'})
        expected_calls = [
            mock.call.edit_vol(
                'volume-abcdef',
                {'data': {'agent_type': 'none'}}),

            mock.call.online_vol('volume-abcdef', False)]

        self.mock_client_service.assert_has_calls(expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_unmanage_with_invalid_volume(self):
        self.mock_client_service.get_vol_info.side_effect = (
            FAKE_VOLUME_INFO_NEGATIVE_RESPONSE)
        self.assertRaises(
            exception.VolumeBackendAPIException,
            self.driver.unmanage,
            {'name': 'volume-abcdef'}
        )

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_unmanage_with_invalid_agent_type(self):
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_ONLINE)
        self.assertRaises(
            exception.InvalidVolume,
            self.driver.unmanage,
            {'name': 'volume-abcdef'}
        )

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @mock.patch.object(volume_types, 'get_volume_type',
                       mock.Mock(type_id=FAKE_TYPE_ID_NEW,
                                 return_value={
                                     'id': FAKE_TYPE_ID_NEW,
                                     'extra_specs':
                                     {'nimble:perfpol-name': 'default',
                                      'nimble:encryption': 'yes',
                                      'multiattach': False,
                                      'nimble:iops-limit': '1024'}}))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_retype(self):
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_ONLINE)
        retype, update = self.driver.retype(None, FAKE_GET_VOL_INFO_ONLINE,
                                            volume_types.get_volume_type(
                                                None,
                                                FAKE_TYPE_ID_NEW),
                                            None, None)
        self.assertTrue(retype)
        self.assertIsNone(update)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_ISCSI_DRIVER)
    @mock.patch.object(nimble.NimbleRestAPIExecutor, 'login')
    @mock.patch.object(nimble.NimbleRestAPIExecutor,
                       'get_performance_policy_id')
    @mock.patch.object(nimble.NimbleRestAPIExecutor, 'get_pool_info')
    @mock.patch.object(nimble.NimbleRestAPIExecutor, 'get_folder_id')
    @NimbleDriverBaseTestCase.client_mock_decorator_nimble_api(
        'nimble', 'nimble_pass', '10.18.108.55', 'False')
    def test_nimble_extraspecs_retype(self, mock_folder,
                                      mock_pool, mock_perf_id,
                                      mock_login):
        mock_folder.return_value = None
        mock_pool.return_value = None
        mock_perf_id.return_value = None
        mock_login.return_value = None
        data = self.driver.get_valid_nimble_extraspecs(
            FAKE_EXTRA_SPECS,
            FAKE_GET_VOL_INFO_RETYPE)
        self.assertTrue(data['multi_initiator'])

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_get_volume_stats(self):
        self.mock_client_service.get_group_info.return_value = (
            FAKE_POSITIVE_GROUP_INFO_RESPONSE)
        expected_res = {'driver_version': DRIVER_VERSION,
                        'vendor_name': 'Nimble',
                        'volume_backend_name': 'NIMBLE',
                        'storage_protocol': 'iSCSI',
                        'pools': [{'pool_name': 'NIMBLE',
                                   'total_capacity_gb': 7466.30419921875,
                                   'free_capacity_gb': 94.16706105787307,
                                   'reserved_percentage': 0,
                                   'QoS_support': False,
                                   'multiattach': True,
                                   'thin_provisioning_support': True,
                                   'consistent_group_snapshot_enabled': True,
                                   'replication_enabled': False,
                                   'consistent_group_replication_enabled':
                                       False}]}
        self.assertEqual(
            expected_res,
            self.driver.get_volume_stats(refresh=True))

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_is_volume_backup_clone(self):
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_BACKUP_RESPONSE)
        self.mock_client_service.get_snap_info_by_id.return_value = (
            FAKE_GET_SNAP_INFO_BACKUP_RESPONSE)
        self.mock_client_service.get_snap_info_detail.return_value = (
            FAKE_GET_SNAP_INFO_BACKUP_RESPONSE)
        self.mock_client_service.get_volume_name.return_value = (
            'volume-' + fake.VOLUME2_ID)

        volume = obj_volume.Volume(context.get_admin_context(),
                                   id=fake.VOLUME_ID,
                                   _name_id=None)
        self.assertEqual(("test-backup-snap", "volume-" + fake.VOLUME2_ID),
                         self.driver.is_volume_backup_clone(volume))
        expected_calls = [
            mock.call.get_vol_info('volume-' + fake.VOLUME_ID),
            mock.call.get_snap_info_by_id('test-backup-snap',
                                          'volume-' + fake.VOLUME2_ID)
        ]
        self.mock_client_service.assert_has_calls(expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*', devices=REPL_DEVICES))
    def test_enable_replication(self):
        ctx = context.get_admin_context()
        group = mock.MagicMock()
        volumes = [fake_volume.fake_volume_obj(None)]

        return_values = self.driver.enable_replication(ctx, group, volumes)
        self.mock_client_service.set_schedule_for_volcoll.assert_called_once()
        model_update = return_values[0]
        self.assertEqual(model_update['replication_status'], 'enabled')

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*', devices=REPL_DEVICES))
    def test_disable_replication(self):
        ctx = context.get_admin_context()
        group = mock.MagicMock()
        volumes = [fake_volume.fake_volume_obj(None)]

        return_values = self.driver.disable_replication(ctx, group, volumes)
        self.mock_client_service.delete_schedule.assert_called_once()
        model_update = return_values[0]
        self.assertEqual(model_update['replication_status'], 'disabled')

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*', devices=REPL_DEVICES))
    def test_time_to_secs(self):
        time_secs = [('01:05', 3900), ('01:02:15am', 3735),
                     ('03:07:20pm', 54440)]
        for time, seconds in time_secs:
            ret_secs = self.driver._time_to_secs(time)
            self.assertEqual(ret_secs, seconds)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*', devices=REPL_DEVICES))
    def test_failover_replication(self):
        ctx = context.get_admin_context()
        group = mock.MagicMock()
        volumes = [fake_volume.fake_volume_obj(None)]

        return_values = self.driver.failover_replication(
            ctx, group, volumes, 'secondary')
        self.mock_client_service.handover.assert_called()
        group_update = return_values[0]
        self.assertEqual(group_update['replication_status'], 'failed-over')

        return_values = self.driver.failover_replication(
            ctx, group, volumes, 'default')
        self.mock_client_service.handover.assert_called()
        group_update = return_values[0]
        self.assertEqual(group_update['replication_status'], 'enabled')


class NimbleDriverSnapshotTestCase(NimbleDriverBaseTestCase):

    """Tests snapshot related api's."""

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_create_snapshot(self):
        self.mock_client_service.snap_vol.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.driver.create_snapshot(
            {'volume_name': 'testvolume',
             'name': 'testvolume-snap1',
             'display_name': ''})
        self.mock_client_service.snap_vol.assert_called_once_with(
            {'volume_name': 'testvolume',
             'name': 'testvolume-snap1',
             'display_name': ''})

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_delete_snapshot(self):
        self.mock_client_service.online_snap.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.mock_client_service.delete_snap.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.driver.delete_snapshot(
            {'volume_name': 'testvolume',
             'name': 'testvolume-snap1'})
        expected_calls = [mock.call.online_snap(
            'testvolume', False, 'testvolume-snap1'),
            mock.call.delete_snap('testvolume',
                                  'testvolume-snap1')]
        self.mock_client_service.assert_has_calls(expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @mock.patch.object(volume_types, 'get_volume_type_extra_specs',
                       mock.Mock(type_id=FAKE_TYPE_ID, return_value={
                                 'nimble:perfpol-name': 'default',
                                 'nimble:encryption': 'yes',
                                 'multiattach': False}))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_create_volume_from_snapshot(self):
        self.mock_client_service.clone_vol.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_RESPONSE)
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)
        self.assertEqual({
            'provider_location': '172.18.108.21:3260 iqn.test',
            'provider_auth': None},
            self.driver.create_volume_from_snapshot(
                {'name': 'clone-testvolume',
                 'size': 2,
                 'volume_type_id': FAKE_TYPE_ID},
                {'volume_name': 'testvolume',
                 'name': 'testvolume-snap1',
                 'volume_size': 1}))
        expected_calls = [
            mock.call.clone_vol(
                {'name': 'clone-testvolume',
                 'volume_type_id': FAKE_TYPE_ID,
                 'size': 2},
                {'volume_name': 'testvolume',
                 'name': 'testvolume-snap1',
                 'volume_size': 1},
                False,
                False,
                'iSCSI',
                'default'),
            mock.call.edit_vol('clone-testvolume',
                               {'data': {'size': 2048,
                                         'snap_limit': sys.maxsize,
                                         'warn_level': 80,
                                         'reserve': 0,
                                         'limit': 100}})]
        self.mock_client_service.assert_has_calls(expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_revert_to_snapshot(self):
        self.mock_client_service.online_vol.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.mock_client_service.volume_restore.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_REVERT)
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)
        self.mock_client_service.get_snap_info.return_value = (
            FAKE_SNAP_INFO_REVERT)
        ctx = context.get_admin_context()
        self.driver.revert_to_snapshot(ctx,
                                       {'id': fake.VOLUME_ID,
                                        'size': 1,
                                        'name': 'testvolume'},
                                       {'id': fake.SNAPSHOT2_ID,
                                        'name': 'testsnap',
                                        'volume_id': fake.VOLUME_ID})
        expected_calls = [mock.call.online_vol('testvolume', False),
                          mock.call.volume_restore('testvolume',
                          {'data': {'id': fake.VOLUME_ID,
                           'base_snap_id': fake.SNAPSHOT2_ID}}),
                          mock.call.online_vol('testvolume', True)]
        self.mock_client_service.assert_has_calls(expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_revert_to_snapshot_negative(self):
        self.mock_client_service.online_vol.return_value = (
            FAKE_GENERIC_POSITIVE_RESPONSE)
        self.mock_client_service.volume_restore.side_effect = (
            FAKE_VOLUME_RESTORE_NEGATIVE_RESPONSE)
        self.mock_client_service.get_vol_info.return_value = (
            FAKE_GET_VOL_INFO_REVERT)
        self.mock_client_service.get_netconfig.return_value = (
            FAKE_POSITIVE_NETCONFIG_RESPONSE)
        self.mock_client_service.get_snap_info.return_value = (
            FAKE_SNAP_INFO_REVERT)
        ctx = context.get_admin_context()
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.revert_to_snapshot, ctx,
                          {'id': fake.VOLUME_ID,
                           'size': 1,
                           'name': 'testvolume'},
                          {'id': fake.SNAPSHOT_ID,
                           'name': 'testsnap',
                           'volume_id': fake.VOLUME_ID})


class NimbleDriverConnectionTestCase(NimbleDriverBaseTestCase):

    """Tests Connection related api's."""

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_initialize_connection_igroup_exist(self):
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE)
        expected_res = {
            'driver_volume_type': 'iscsi',
            'data': {
                'target_discovered': False,
                'discard': True,
                'volume_id': 12,
                'target_iqn': '13',
                'target_lun': 0,
                'target_portal': '12'}}
        self.assertEqual(
            expected_res,
            self.driver.initialize_connection(
                {'name': 'test-volume',
                 'provider_location': '12 13',
                 'id': 12},
                {'initiator': 'test-initiator1'}))

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    @mock.patch(NIMBLE_ISCSI_DRIVER + '._get_data_ips')
    @mock.patch(NIMBLE_ISCSI_DRIVER + ".get_lun_number")
    @mock.patch(NIMBLE_ISCSI_DRIVER + '._get_gst_for_group')
    def test_initialize_connection_group_scoped_target(self, mock_gst_name,
                                                       mock_lun_number,
                                                       mock_data_ips):
        mock_data_ips.return_value = ['12', '13']
        mock_lun_number.return_value = 0
        mock_gst_name.return_value = "group_target_name"
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE)
        expected_res = {
            'driver_volume_type': 'iscsi',
            'data': {
                'target_discovered': False,
                'discard': True,
                'volume_id': fake.VOLUME_ID,
                'target_iqns': ['group_target_name', 'group_target_name'],
                'target_luns': [0, 0],
                'target_portals': ['12', '13']}}
        self.assertEqual(
            expected_res,
            self.driver.initialize_connection(
                {'name': 'test-volume',
                 'provider_location': '12 group_target_name',
                 'id': fake.VOLUME_ID},
                {'initiator': 'test-initiator1'}))

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_initialize_connection_live_migration(self):
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE)
        expected_res = {
            'driver_volume_type': 'iscsi',
            'data': {
                'target_discovered': False,
                'discard': True,
                'volume_id': fake.VOLUME_ID,
                'target_iqn': '13',
                'target_lun': 0,
                'target_portal': '12'}}

        self.assertEqual(
            expected_res,
            self.driver.initialize_connection(
                {'name': 'test-volume',
                 'provider_location': '12 13',
                 'id': fake.VOLUME_ID},
                {'initiator': 'test-initiator1'}))

        self.driver.initialize_connection(
            {'name': 'test-volume',
             'provider_location': '12 13',
             'id': fake.VOLUME_ID},
            {'initiator': 'test-initiator1'})

        # 2 or more calls to initialize connection and add_acl for live
        # migration to work
        expected_calls = [
            mock.call.get_initiator_grp_list(),
            mock.call.add_acl({'name': 'test-volume',
                               'provider_location': '12 13',
                               'id': fake.VOLUME_ID},
                              'test-igrp1'),
            mock.call.get_initiator_grp_list(),
            mock.call.add_acl({'name': 'test-volume',
                               'provider_location': '12 13',
                               'id': fake.VOLUME_ID},
                              'test-igrp1')]
        self.mock_client_service.assert_has_calls(expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator_fc(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    @mock.patch(NIMBLE_FC_DRIVER + ".get_lun_number")
    @mock.patch(NIMBLE_FC_DRIVER + ".get_wwpns_from_array")
    def test_initialize_connection_fc_igroup_exist(self, mock_wwpns,
                                                   mock_lun_number):
        mock_lun_number.return_value = 13
        mock_wwpns.return_value = ["1111111111111101"]
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE_FC)
        expected_res = {
            'driver_volume_type': 'fibre_channel',
            'data': {
                'target_lun': 13,
                'target_discovered': True,
                'discard': True,
                'target_wwn': ["1111111111111101"],
                'initiator_target_map': {'1000000000000000':
                                         ['1111111111111101']}}}
        self.assertEqual(
            expected_res,
            self.driver.initialize_connection(
                {'name': 'test-volume',
                 'provider_location': 'array1',
                 'id': fake.VOLUME_ID},
                {'initiator': 'test-initiator1',
                 'wwpns': ['1000000000000000']}))

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    @mock.patch(NIMBLE_RANDOM)
    def test_initialize_connection_igroup_not_exist(self, mock_random):
        mock_random.sample.return_value = 'abcdefghijkl'
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE)
        expected_res = {
            'driver_volume_type': 'iscsi',
            'data': {
                'target_discovered': False,
                'discard': True,
                'target_lun': 0,
                'volume_id': fake.VOLUME_ID,
                'target_iqn': '13',
                'target_portal': '12'}}
        self.assertEqual(
            expected_res,
            self.driver.initialize_connection(
                {'name': 'test-volume',
                 'provider_location': '12 13',
                 'id': fake.VOLUME_ID},
                {'initiator': 'test-initiator3'}))

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator_fc(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    @mock.patch(NIMBLE_FC_DRIVER + ".get_wwpns_from_array")
    @mock.patch(NIMBLE_FC_DRIVER + ".get_lun_number")
    @mock.patch(NIMBLE_RANDOM)
    def test_initialize_connection_fc_igroup_not_exist(self, mock_random,
                                                       mock_lun_number,
                                                       mock_wwpns):
        mock_random.sample.return_value = 'abcdefghijkl'
        mock_lun_number.return_value = 13
        mock_wwpns.return_value = ["1111111111111101"]
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE_FC)
        expected_res = {
            'driver_volume_type': 'fibre_channel',
            'data': {
                'target_lun': 13,
                'target_discovered': True,
                'discard': True,
                'target_wwn': ["1111111111111101"],
                'initiator_target_map': {'1000000000000000':
                                         ['1111111111111101']}}}

        self.driver._create_igroup_for_initiator("test-initiator3",
                                                 [1111111111111101])
        self.assertEqual(
            expected_res,
            self.driver.initialize_connection(
                {'name': 'test-volume',
                 'provider_location': 'array1',
                 'id': fake.VOLUME_ID},
                {'initiator': 'test-initiator3',
                 'wwpns': ['1000000000000000']}))

        expected_calls = [mock.call.create_initiator_group_fc(
            'openstack-abcdefghijkl'),
            mock.call.add_initiator_to_igroup_fc('openstack-abcdefghijkl',
                                                 1111111111111101)]
        self.mock_client_service.assert_has_calls(expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_terminate_connection_positive(self):
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE)
        ctx = context.get_admin_context()
        volume = fake_volume.fake_volume_obj(
            ctx, name='test-volume',
            host='fakehost@nimble#Openstack',
            provider_location='12 13',
            id=fake.VOLUME_ID, multiattach=False)

        self.driver.terminate_connection(
            volume,
            {'initiator': 'test-initiator1'})
        expected_calls = [mock.call._get_igroupname_for_initiator(
            'test-initiator1'),
            mock.call.remove_acl({'name': 'test-volume'},
                                 'test-igrp1')]
        self.mock_client_service.assert_has_calls(
            self.mock_client_service.method_calls,
            expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_terminate_connection_without_connector(self):
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE)
        self.driver.terminate_connection(
            {'name': 'test-volume',
             'provider_location': '12 13',
             'id': fake.VOLUME_ID},
            None)
        expected_calls = [mock.call._get_igroupname_for_initiator(
            'test-initiator1'),
            mock.call.remove_all_acls({'name': 'test-volume'})]
        self.mock_client_service.assert_has_calls(
            self.mock_client_service.method_calls,
            expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator_fc(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    @mock.patch(NIMBLE_FC_DRIVER + ".get_wwpns_from_array")
    def test_terminate_connection_positive_fc(self, mock_wwpns):
        mock_wwpns.return_value = ["1111111111111101"]
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE_FC)
        ctx = context.get_admin_context()
        volume = fake_volume.fake_volume_obj(
            ctx, name='test-volume',
            host='fakehost@nimble#Openstack',
            provider_location='12 13',
            id=fake.VOLUME_ID, multiattach=False)

        self.driver.terminate_connection(
            volume,
            {'initiator': 'test-initiator1',
             'wwpns': ['1000000000000000']})
        expected_calls = [
            mock.call.get_igroupname_for_initiator_fc(
                "10:00:00:00:00:00:00:00"),
            mock.call.remove_acl({'name': 'test-volume'},
                                 'test-igrp1')]
        self.mock_client_service.assert_has_calls(
            self.mock_client_service.method_calls,
            expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_terminate_connection_negative(self):
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE)
        ctx = context.get_admin_context()

        volume = fake_volume.fake_volume_obj(
            ctx, name='test-volume',
            host='fakehost@nimble#Openstack',
            provider_location='12 13',
            id=fake.VOLUME_ID, multiattach=False)

        self.assertRaises(
            exception.VolumeDriverException,
            self.driver.terminate_connection,
            volume,
            {'initiator': 'test-initiator3'})

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator_fc(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    @mock.patch(NIMBLE_FC_DRIVER + ".get_wwpns_from_array")
    def test_terminate_connection_negative_fc(self, mock_wwpns):
        mock_wwpns.return_value = ["1111111111111101"]
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE_FC)
        ctx = context.get_admin_context()
        volume = fake_volume.fake_volume_obj(
            ctx, name='test-volume',
            host='fakehost@nimble#Openstack',
            provider_location='12 13',
            id=fake.VOLUME_ID, multiattach=False)
        self.assertRaises(
            exception.VolumeDriverException,
            self.driver.terminate_connection,
            volume,
            {'initiator': 'test-initiator3',
             'wwpns': ['1000000000000010']})

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_terminate_connection_multiattach(self):
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE)
        ctx = context.get_admin_context()

        att_1 = fake_volume.volume_attachment_ovo(
            ctx, id=uuidutils.generate_uuid())
        att_2 = fake_volume.volume_attachment_ovo(
            ctx, id=uuidutils.generate_uuid())
        volume = fake_volume.fake_volume_obj(
            ctx, name='test-volume',
            host='fakehost@nimble#Openstack',
            provider_location='12 13',
            id=fake.VOLUME_ID, multiattach=True)
        volume.volume_attachment.objects = [att_1, att_2]
        self.driver.terminate_connection(
            volume,
            {'initiator': 'test-initiator1'})
        self.mock_client_service.remove_acl.assert_not_called()

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    def test_terminate_connection_multiattach_complete(self):
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE)
        ctx = context.get_admin_context()

        att_1 = fake_volume.volume_attachment_ovo(
            ctx, id=uuidutils.generate_uuid())
        volume = fake_volume.fake_volume_obj(
            ctx, name='test-volume',
            host='fakehost@nimble#Openstack',
            provider_location='12 13',
            id=fake.VOLUME_ID, multiattach=True)
        volume.volume_attachment.objects = [att_1]
        self.driver.terminate_connection(
            volume,
            {'initiator': 'test-initiator1'})
        expected_calls = [mock.call._get_igroupname_for_initiator(
            'test-initiator1'),
            mock.call.remove_acl({'name': 'test-volume'},
                                 'test-igrp1')]
        self.mock_client_service.assert_has_calls(
            self.mock_client_service.method_calls,
            expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator_fc(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    @mock.patch(NIMBLE_FC_DRIVER + ".get_wwpns_from_array")
    def test_terminate_connection_multiattach_fc(self, mock_wwpns):
        mock_wwpns.return_value = ["1111111111111101"]
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE_FC)
        ctx = context.get_admin_context()

        att_1 = fake_volume.volume_attachment_ovo(
            ctx, id=uuidutils.generate_uuid())
        att_2 = fake_volume.volume_attachment_ovo(
            ctx, id=uuidutils.generate_uuid())
        volume = fake_volume.fake_volume_obj(
            ctx, name='test-volume',
            host='fakehost@nimble#Openstack',
            provider_location='12 13',
            id=fake.VOLUME_ID, multiattach=True)
        volume.volume_attachment.objects = [att_1, att_2]
        self.driver.terminate_connection(
            volume,
            {'initiator': 'test-initiator1',
             'wwpns': ['1000000000000000']})
        self.mock_client_service.remove_acl.assert_not_called()

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @mock.patch.object(obj_volume.VolumeList, 'get_all_by_host',
                       mock.Mock(return_value=[]))
    @NimbleDriverBaseTestCase.client_mock_decorator_fc(create_configuration(
        'nimble', 'nimble_pass', '10.18.108.55', 'default', '*'))
    @mock.patch(NIMBLE_FC_DRIVER + ".get_wwpns_from_array")
    def test_terminate_connection_multiattach_complete_fc(self, mock_wwpns):
        mock_wwpns.return_value = ["1111111111111101"]
        self.mock_client_service.get_initiator_grp_list.return_value = (
            FAKE_IGROUP_LIST_RESPONSE_FC)
        ctx = context.get_admin_context()

        att_1 = fake_volume.volume_attachment_ovo(
            ctx, id=uuidutils.generate_uuid())
        volume = fake_volume.fake_volume_obj(
            ctx, name='test-volume',
            host='fakehost@nimble#Openstack',
            provider_location='12 13',
            id=fake.VOLUME_ID, multiattach=True)
        volume.volume_attachment.objects = [att_1]
        self.driver.terminate_connection(
            volume,
            {'initiator': 'test-initiator1',
             'wwpns': ['1000000000000000']})
        expected_calls = [
            mock.call.get_igroupname_for_initiator_fc(
                "10:00:00:00:00:00:00:00"),
            mock.call.remove_acl({'name': 'test-volume'},
                                 'test-igrp1')]
        self.mock_client_service.assert_has_calls(
            self.mock_client_service.method_calls,
            expected_calls)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    @mock.patch.object(volume_utils, 'is_group_a_cg_snapshot_type')
    def test_create_group_positive(self, mock_is_cg):
        mock_is_cg.return_value = True
        ctx = context.get_admin_context()
        self.group = fake_group.fake_group_obj(
            ctx, id = fake.GROUP_ID)
        model_update = self.driver.create_group(ctx, self.group)
        self.assertEqual(fields.GroupStatus.AVAILABLE, model_update['status'])

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    @mock.patch.object(volume_utils, 'is_group_a_cg_snapshot_type')
    def test_create_generic_group(self, mock_is_cg):
        mock_is_cg.return_value = False
        ctx = context.get_admin_context()
        self.group = fake_group.fake_group_obj(
            ctx, id=fake.GROUP_ID, status='available')
        self.assertRaises(
            NotImplementedError,
            self.driver.create_group,
            ctx, self.group
        )
        mock_is_cg.assert_called_once_with(self.group)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    @mock.patch.object(volume_utils, 'is_group_a_cg_snapshot_type')
    def test_delete_generic_group(self, mock_is_cg):
        mock_is_cg.return_value = False
        ctx = context.get_admin_context()
        group = mock.MagicMock()
        volumes = [fake_volume.fake_volume_obj(None)]
        self.assertRaises(
            NotImplementedError,
            self.driver.delete_group,
            ctx, group, volumes
        )
        mock_is_cg.assert_called_once()

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    @mock.patch.object(volume_utils, 'is_group_a_cg_snapshot_type')
    @mock.patch('cinder.volume.group_types.get_group_type_specs')
    def test_delete_group_positive(self, mock_get_specs, mock_is_cg):
        mock_get_specs.return_value = '<is> True'
        mock_is_cg.return_value = True
        ctx = context.get_admin_context()
        group = mock.MagicMock()
        volumes = [fake_volume.fake_volume_obj(None)]
        self.driver.delete_group(ctx, group, volumes)
        self.mock_client_service.delete_volcoll.assert_called_once()

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    @mock.patch.object(volume_utils, 'is_group_a_cg_snapshot_type')
    def test_update_group(self, mock_is_cg):
        mock_is_cg.return_value = False
        group = mock.MagicMock()
        ctx = context.get_admin_context()
        self.assertRaises(
            NotImplementedError,
            self.driver.update_group,
            ctx, group
        )
        mock_is_cg.assert_called_once_with(group)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    @mock.patch.object(volume_utils, 'is_group_a_cg_snapshot_type')
    @mock.patch('cinder.volume.group_types.get_group_type_specs')
    @mock.patch(NIMBLE_ISCSI_DRIVER + '.is_volume_group_snap_type')
    def test_update_group_positive(self, vol_gs_enable,
                                   mock_get_specs, mock_is_cg):
        mock_get_specs.return_value = '<is> True'
        mock_is_cg.return_value = True
        self.mock_client_service.get_volume_id_by_name.return_value = (
            FAKE_GET_VOLID_INFO_RESPONSE)
        self.mock_client_service.get_volcoll_id_by_name.return_value = (
            FAKE_GET_VOLCOLL_INFO_RESPONSE)
        self.mock_client_service.associate_volcoll.return_value = (
            FAKE_GET_SNAP_INFO_BACKUP_RESPONSE)

        ctx = context.get_admin_context()
        group = mock.MagicMock()
        volume1 = fake_volume.fake_volume_obj(
            ctx, name='testvolume-cg1',
            host='fakehost@nimble#Openstack',
            provider_location='12 13',
            id=fake.VOLUME_ID, consistency_group_snapshot_enabled=True)
        addvollist = [volume1]
        remvollist = [volume1]
        model_update = self.driver.update_group(
            ctx,
            group,
            addvollist,
            remvollist
        )
        self.assertEqual(fields.GroupStatus.AVAILABLE,
                         model_update[0]['status'])

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    @mock.patch.object(volume_utils, 'is_group_a_cg_snapshot_type')
    def test_create_group_from_src(self, mock_is_cg):
        mock_is_cg.return_value = False
        group = mock.MagicMock()
        ctx = context.get_admin_context()
        volumes = [fake_volume.fake_volume_obj(None)]
        self.assertRaises(
            NotImplementedError,
            self.driver.create_group_from_src,
            ctx, group, volumes
        )
        mock_is_cg.assert_called_once_with(group)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    @mock.patch.object(volume_utils, 'is_group_a_cg_snapshot_type')
    @mock.patch('cinder.volume.group_types.get_group_type_specs')
    @mock.patch(NIMBLE_ISCSI_DRIVER + ".create_cloned_volume")
    def test_create_group_from_src_positive(self, mock_clone,
                                            mock_get_specs,
                                            mock_is_cg):
        source_volume = volume_src_cg
        volume = volume_cg
        volume['source_volid'] = source_volume['id']
        volume['display_name'] = "cg-volume"
        source_volume['display_name'] = "source-volume"

        mock_get_specs.return_value = '<is> True'
        mock_clone.return_value = volume['name']
        mock_is_cg.return_value = True

        self.driver.create_group_from_src(
            context.get_admin_context(), FAKE_GROUP,
            [volume], source_group=FAKE_SRC_GROUP,
            source_vols=[source_volume])
        self.mock_client_service.associate_volcoll.assert_called_once()

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    @mock.patch.object(volume_utils, 'is_group_a_cg_snapshot_type')
    @mock.patch('cinder.volume.group_types.get_group_type_specs')
    def test_create_group_snapshot_positive(self, mock_get_specs, mock_is_cg):
        mock_get_specs.return_value = '<is> True'
        mock_is_cg.return_value = True
        ctx = context.get_admin_context()
        group_snapshot = mock.MagicMock()
        snapshots = [fake_snapshot.fake_snapshot_obj(None)]

        self.driver.create_group_snapshot(
            ctx,
            group_snapshot,
            snapshots
        )
        self.mock_client_service.snapcoll_create.assert_called_once()

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    @mock.patch.object(volume_utils, 'is_group_a_cg_snapshot_type')
    def test_delete_generic_group_snapshot(self, mock_is_cg):
        mock_is_cg.return_value = False
        group_snapshot = mock.MagicMock()
        snapshots = [fake_snapshot.fake_snapshot_obj(None)]
        ctx = context.get_admin_context()
        self.assertRaises(
            NotImplementedError,
            self.driver.delete_group_snapshot,
            ctx, group_snapshot, snapshots
        )
        mock_is_cg.assert_called_once_with(group_snapshot)

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    @mock.patch.object(volume_utils, 'is_group_a_cg_snapshot_type')
    @mock.patch('cinder.volume.group_types.get_group_type_specs')
    def test_delete_group_snapshot_positive(self, mock_get_specs, mock_is_cg):
        mock_get_specs.return_value = '<is> True'
        mock_is_cg.return_value = True
        ctx = context.get_admin_context()
        group_snapshot = mock.MagicMock()
        snapshots = [mock.Mock()]

        self.driver.delete_group_snapshot(
            ctx,
            group_snapshot,
            snapshots
        )
        self.mock_client_service.snapcoll_delete.assert_called_once()

    @mock.patch(NIMBLE_URLLIB2)
    @mock.patch(NIMBLE_CLIENT)
    @NimbleDriverBaseTestCase.client_mock_decorator(create_configuration(
        NIMBLE_SAN_LOGIN, NIMBLE_SAN_PASS, NIMBLE_MANAGEMENT_IP,
        'default', '*'))
    @mock.patch.object(volume_utils, 'is_group_a_cg_snapshot_type')
    def test_create_group_negative(self, mock_is_cg):
        mock_is_cg.return_value = True
        ctx = context.get_admin_context()
        self.vol_type = volume_type.VolumeType(
            name='volume_type',
            extra_specs=
            {'consistent_group_snapshot_enabled': '<is> False'})
        FAKE_GROUP.volume_types = volume_type.VolumeTypeList(
            objects=[self.vol_type])
        self.assertRaises(exception.InvalidInput,
                          self.driver.create_group, ctx, FAKE_GROUP)
