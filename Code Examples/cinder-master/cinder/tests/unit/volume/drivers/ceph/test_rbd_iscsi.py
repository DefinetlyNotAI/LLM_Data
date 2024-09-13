# Copyright 2012 Josh Durgin
# Copyright 2013 Canonical Ltd.
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

from unittest import mock

import ddt

from cinder import context
from cinder import exception
from cinder.tests.unit import fake_constants as fake
from cinder.tests.unit import fake_volume
from cinder.tests.unit import test
import cinder.volume.drivers.ceph.rbd_iscsi as driver

# This is used to collect raised exceptions so that tests may check what was
# raised.
# NOTE: this must be initialised in test setUp().
RAISED_EXCEPTIONS = []


@ddt.ddt
class RBDISCSITestCase(test.TestCase):

    def setUp(self):
        global RAISED_EXCEPTIONS
        RAISED_EXCEPTIONS = []
        super(RBDISCSITestCase, self).setUp()

        self.context = context.get_admin_context()

        self.fake_target_iqn = 'iqn.2019-01.com.suse.iscsi-gw:iscsi-igw'
        self.fake_valid_response = {'status': '200'}

        self.fake_clients = \
            {'response':
             {'Content-Type': 'application/json',
              'Content-Length': '55',
              'Server': 'Werkzeug/0.14.1 Python/2.7.15rc1',
              'Date': 'Wed, 19 Jun 2019 20:13:18 GMT',
              'status': '200',
              'content-location': 'http://192.168.121.11:5001/api/clients/'
                                  'XX_REPLACE_ME'},
             'body':
             {'clients': ['iqn.1993-08.org.debian:01:5d3b9abba13d']}}

        self.volume_a = fake_volume.fake_volume_obj(
            self.context,
            **{'name': u'volume-0000000a',
               'id': '4c39c3c7-168f-4b32-b585-77f1b3bf0a38',
               'size': 10})

        self.volume_b = fake_volume.fake_volume_obj(
            self.context,
            **{'name': u'volume-0000000b',
               'id': '0c7d1f44-5a06-403f-bb82-ae7ad0d693a6',
               'size': 10})

        self.volume_c = fake_volume.fake_volume_obj(
            self.context,
            **{'name': u'volume-0000000a',
               'id': '55555555-222f-4b32-b585-9991b3bf0a99',
               'size': 12,
               'encryption_key_id': fake.ENCRYPTION_KEY_ID})

    def setup_configuration(self):
        config = mock.MagicMock()
        config.rbd_cluster_name = 'nondefault'
        config.rbd_pool = 'rbd'
        config.rbd_ceph_conf = '/etc/ceph/my_ceph.conf'
        config.rbd_secret_uuid = None
        config.rbd_user = 'cinder'
        config.volume_backend_name = None
        config.rbd_iscsi_api_user = 'fake_user'
        config.rbd_iscsi_api_password = 'fake_password'
        config.rbd_iscsi_api_url = 'http://fake.com:5000'
        return config

    @mock.patch('cinder.volume.drivers.rbd.RBDDriver.do_setup',
                new=mock.MagicMock())
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.client')
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.rbd_iscsi_client')
    def test_unsupported_client_version(self, m_rbd_iscsi_client, m_client):
        m_rbd_iscsi_client.version = '0.1.0'
        m_client.version = '0.1.0'
        drv = driver.RBDISCSIDriver(configuration=self.setup_configuration())
        drv.set_initialized()
        self.assertRaisesRegex(exception.InvalidInput,
                               'version',
                               drv.do_setup,
                               None)

    @ddt.data({'user': None, 'password': 'foo',
               'url': 'http://fake.com:5000', 'iqn': None},
              {'user': None, 'password': None,
               'url': 'http://fake', 'iqn': None},
              {'user': None, 'password': None,
               'url': None, 'iqn': None},
              {'user': 'fake', 'password': 'fake',
               'url': None, 'iqn': None},
              {'user': 'fake', 'password': 'fake',
               'url': 'fake', 'iqn': None},
              )
    @ddt.unpack
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.client')
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.rbd_iscsi_client')
    def test_min_config(self, m_rbd_iscsi_client, m_client,
                        user, password, url, iqn):
        config = self.setup_configuration()
        config.rbd_iscsi_api_user = user
        config.rbd_iscsi_api_password = password
        config.rbd_iscsi_api_url = url
        config.rbd_iscsi_target_iqn = iqn

        drv = driver.RBDISCSIDriver(configuration=config)
        drv.set_initialized()

        with mock.patch('cinder.volume.drivers.rbd.RBDDriver'
                        '.check_for_setup_error'):
            self.assertRaises(exception.InvalidConfigurationValue,
                              drv.check_for_setup_error)

    @ddt.data({'response': None},
              {'response': {'nothing': 'nothing'}},
              {'response': {'status': '300'}})
    @ddt.unpack
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.RBDISCSIDriver.'
                '_create_client')
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.client')
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.rbd_iscsi_client')
    def test_do_setup(self, m_rbd_iscsi_client, m_client, m_create_client,
                      response):
        m_create_client.return_value.get_api.return_value = (response, None)
        m_client.version = '3.0.0'
        m_rbd_iscsi_client.version = '3.0.0'

        drv = driver.RBDISCSIDriver(configuration=self.setup_configuration())
        drv.set_initialized()

        with mock.patch('cinder.volume.drivers.rbd.RBDDriver.do_setup'):
            self.assertRaises(exception.InvalidConfigurationValue,
                              drv.do_setup, None)

    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.client')
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.rbd_iscsi_client')
    def test_unsupported_version(self, m_rbd_iscsi_client, m_client):
        m_rbd_iscsi_client.version = '0.1.4'
        drv = driver.RBDISCSIDriver(configuration=self.setup_configuration())
        drv.set_initialized()

        self.assertRaisesRegex(exception.InvalidInput,
                               'Invalid rbd_iscsi_client version found',
                               drv._create_client)

    @ddt.data({'status': '200',
               'target_iqn': 'iqn.2019-01.com.suse.iscsi-gw:iscsi-igw',
               'clients': ['foo']},
              {'status': '300',
               'target_iqn': 'iqn.2019-01.com.suse.iscsi-gw:iscsi-igw',
               'clients': None}
              )
    @ddt.unpack
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.RBDISCSIDriver.'
                '_create_client')
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.client')
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.rbd_iscsi_client')
    def test__get_clients(self, m_rbd_iscsi_client, m_client, m_create_client,
                          status, target_iqn, clients):
        m_create_client.return_value.get_api.return_value = (
            self.fake_valid_response, None)
        config = self.setup_configuration()
        config.rbd_iscsi_target_iqn = target_iqn

        drv = driver.RBDISCSIDriver(configuration=config)
        drv.set_initialized()

        response = self.fake_clients['response']
        response['status'] = status
        response['content-location'] = (
            response['content-location'].replace('XX_REPLACE_ME', target_iqn))

        body = self.fake_clients['body']

        m_create_client.return_value.get_clients.return_value = (response,
                                                                 body)

        with mock.patch('cinder.volume.drivers.rbd.RBDDriver.do_setup'):
            drv.do_setup(None)
            if status == '200':
                actual_response = drv._get_clients()
                self.assertEqual(actual_response, body)
            else:
                # we expect an exception
                self.assertRaisesRegex(exception.VolumeBackendAPIException,
                                       'Failed to get_clients()',
                                       drv._get_clients)

    @ddt.data({'status': '200',
               'body': {'created': 'someday',
                        'discovery_auth': 'somecrap',
                        'disks': 'fakedisks',
                        'gateways': 'fakegws',
                        'targets': 'faketargets'}},
              {'status': '300',
               'body': None})
    @ddt.unpack
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.RBDISCSIDriver.'
                '_create_client')
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.client')
    @mock.patch('cinder.volume.drivers.ceph.rbd_iscsi.rbd_iscsi_client')
    def test__get_config(self, m_rbd_iscsi_client, m_client, m_create_client,
                         status, body):
        m_create_client.return_value.get_api.return_value = (
            self.fake_valid_response, None)
        config = self.setup_configuration()
        config.rbd_iscsi_target_iqn = self.fake_target_iqn

        drv = driver.RBDISCSIDriver(configuration=config)
        drv.set_initialized()

        response = self.fake_clients['response']
        response['status'] = status
        response['content-location'] = (
            response['content-location'].replace('XX_REPLACE_ME',
                                                 self.fake_target_iqn))

        m_create_client.return_value.get_config.return_value = (response, body)

        with mock.patch('cinder.volume.drivers.rbd.RBDDriver.do_setup'):
            drv.do_setup(None)
            if status == '200':
                actual_response = drv._get_config()
                self.assertEqual(body, actual_response)
            else:
                # we expect an exception
                self.assertRaisesRegex(exception.VolumeBackendAPIException,
                                       'Failed to get_config()',
                                       drv._get_config)
