# Copyright (c) 2016 EMC Corporation.
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
import ddt

from manila import exception
from manila.share.drivers.dell_emc.common.enas import utils as enas_utils
from manila import test
from manila.tests.share.drivers.dell_emc.plugins.unity import fake_exceptions
from manila.tests.share.drivers.dell_emc.plugins.unity import res_mock
from manila.tests.share.drivers.dell_emc.plugins.unity import utils
from oslo_utils import units
from unittest import mock


@ddt.ddt
class TestConnection(test.TestCase):
    client = None

    @classmethod
    def setUpClass(cls):
        cls.emc_share_driver = res_mock.FakeEMCShareDriver()

    @res_mock.patch_connection_init
    def test_connect(self, connection):
        connection.connect(res_mock.FakeEMCShareDriver(dhss=True), None)

    @res_mock.patch_connection_init
    def test_connect_with_ipv6(self, connection):
        connection.connect(res_mock.FakeEMCShareDriverIPv6(
            dhss=True), None)

    @res_mock.patch_connection
    def test_connect__invalid_pool_configuration(self, connection):
        f = connection.client.system.get_pool
        f.side_effect = fake_exceptions.UnityResourceNotFoundError()

        self.assertRaises(exception.BadConfigurationException,
                          connection._config_pool,
                          'faked_pool_name')

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_create_nfs_share(self, connection, mocked_input):
        share = mocked_input['nfs_share']
        share_server = mocked_input['share_server']

        location = connection.create_share(None, share, share_server)

        exp_location = [
            {'path': 'fake_ip_addr_1:/cb532599-8dc6-4c3e-bb21-74ea54be566c'},
            {'path': 'fake_ip_addr_2:/cb532599-8dc6-4c3e-bb21-74ea54be566c'},
        ]
        exp_location = sorted(exp_location, key=lambda x: sorted(x['path']))
        location = sorted(location, key=lambda x: sorted(x['path']))
        self.assertEqual(exp_location, location)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_create_cifs_share(self, connection, mocked_input):
        share = mocked_input['cifs_share']
        share_server = mocked_input['share_server']

        location = connection.create_share(None, share, share_server)

        exp_location = [
            {'path': r'\\fake_ip_addr_1\716100cc-e0b4-416b-ac27-d38dd019330d'},
            {'path': r'\\fake_ip_addr_2\716100cc-e0b4-416b-ac27-d38dd019330d'},
        ]
        exp_location = sorted(exp_location, key=lambda x: sorted(x['path']))
        location = sorted(location, key=lambda x: sorted(x['path']))
        self.assertEqual(exp_location, location)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_create_share_with_invalid_proto(self, connection, mocked_input):
        share = mocked_input['invalid_share']
        share_server = mocked_input['share_server']

        self.assertRaises(exception.InvalidShare,
                          connection.create_share,
                          None,
                          share,
                          share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_create_share_without_share_server(self, connection,
                                               mocked_input):
        share = mocked_input['cifs_share']

        self.assertRaises(exception.InvalidInput,
                          connection.create_share,
                          None,
                          share,
                          None)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_create_share__no_server_name_in_backend_details(self, connection,
                                                             mocked_input):
        share = mocked_input['cifs_share']
        share_server = {
            'backend_details': {'share_server_name': None},
            'id': 'test',
            'identifier': '',
        }

        self.assertRaises(exception.InvalidInput,
                          connection.create_share,
                          None,
                          share,
                          share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_create_share_with_invalid_share_server(self, connection,
                                                    mocked_input):
        share = mocked_input['cifs_share']
        share_server = mocked_input['share_server']

        self.assertRaises(exception.EMCUnityError,
                          connection.create_share,
                          None,
                          share,
                          share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_delete_share(self, connection, mocked_input):
        share = mocked_input['cifs_share']
        share_server = mocked_input['share_server']

        connection.delete_share(None, share, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_delete_share__with_invalid_share(self, connection, mocked_input):
        share = mocked_input['cifs_share']

        connection.delete_share(None, share, None)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_delete_share__create_from_snap(self, connection,
                                            mocked_input):
        share = mocked_input['cifs_share']
        share_server = mocked_input['share_server']

        connection.delete_share(None, share, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_delete_share__create_from_snap_but_not_isolated(self,
                                                             connection,
                                                             mocked_input):
        share = mocked_input['cifs_share']
        share_server = mocked_input['share_server']

        connection.delete_share(None, share, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_delete_share__but_not_isolated(self, connection,
                                            mocked_input):
        share = mocked_input['cifs_share']
        share_server = mocked_input['share_server']

        connection.delete_share(None, share, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_shrink_cifs_share(self, connection, mocked_input):
        share = mocked_input['shrink_cifs_share']
        new_size = 4 * units.Gi

        connection.shrink_share(share, new_size)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_shrink_nfs_share(self, connection, mocked_input):
        share = mocked_input['shrink_nfs_share']
        new_size = 4 * units.Gi

        connection.shrink_share(share, new_size)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_extend_cifs_share(self, connection, mocked_input):
        share = mocked_input['cifs_share']
        share_server = mocked_input['share_server']
        new_size = 50 * units.Gi

        connection.extend_share(share, new_size, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_extend_nfs_share(self, connection, mocked_input):
        share = mocked_input['nfs_share']
        share_server = mocked_input['share_server']
        new_size = 50 * units.Gi

        connection.extend_share(share, new_size, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_extend_share__create_from_snap(self, connection, mocked_input):
        share = mocked_input['cifs_share']
        share_server = mocked_input['share_server']
        new_size = 50 * units.Gi

        self.assertRaises(exception.ShareExtendingError,
                          connection.extend_share,
                          share,
                          new_size,
                          share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_shrink_share_create_from_snap(self, connection, mocked_input):
        share = mocked_input['shrink_cifs_share']
        share_server = mocked_input['share_server']
        new_size = 4 * units.Gi

        self.assertRaises(exception.ShareShrinkingError,
                          connection.shrink_share,
                          share,
                          new_size,
                          share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_create_snapshot_from_filesystem(self, connection, mocked_input):
        snapshot = mocked_input['snapshot']
        share_server = mocked_input['share_server']

        result = connection.create_snapshot(None, snapshot, share_server)
        self.assertEqual('ab411797-b1cf-4035-bf14-8771a7bf1805',
                         result['provider_location'])

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_create_snapshot_from_snapshot(self, connection, mocked_input):
        snapshot = mocked_input['snapshot']
        share_server = mocked_input['share_server']

        connection.create_snapshot(None, snapshot, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_delete_snapshot(self, connection, mocked_input):
        snapshot = mocked_input['snapshot']
        share_server = mocked_input['share_server']

        connection.delete_snapshot(None, snapshot, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_ensure_share_exists(self, connection, mocked_input):
        share = mocked_input['cifs_share']

        connection.ensure_share(None, share, None)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_ensure_share_not_exists(self, connection, mocked_input):
        share = mocked_input['cifs_share']

        self.assertRaises(exception.ShareNotFound,
                          connection.ensure_share,
                          None,
                          share,
                          None)

    @res_mock.patch_connection
    def test_update_share_stats(self, connection):
        stat_dict = copy.deepcopy(res_mock.STATS)
        connection.update_share_stats(stat_dict)
        self.assertEqual(5, len(stat_dict))
        pool = stat_dict['pools'][0]
        self.assertEqual('pool_1', pool['pool_name'])
        self.assertEqual(
            enas_utils.bytes_to_gb(500000.0), pool['total_capacity_gb'])
        self.assertEqual(False, pool['qos'])
        self.assertEqual(
            enas_utils.bytes_to_gb(30000.0), pool['provisioned_capacity_gb'])
        self.assertEqual(20, pool['max_over_subscription_ratio'])
        self.assertEqual(
            enas_utils.bytes_to_gb(10000.0), pool['allocated_capacity_gb'])
        self.assertEqual(0, pool['reserved_percentage'])
        self.assertEqual(0, pool['reserved_snapshot_percentage'])
        self.assertEqual(0, pool['reserved_share_extend_percentage'])
        self.assertTrue(pool['thin_provisioning'])
        self.assertEqual(
            enas_utils.bytes_to_gb(490000.0), pool['free_capacity_gb'])

    @res_mock.patch_connection
    def test_update_share_stats__nonexistent_pools(self, connection):
        stat_dict = copy.deepcopy(res_mock.STATS)

        self.assertRaises(exception.EMCUnityError,
                          connection.update_share_stats,
                          stat_dict)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_get_pool(self, connection, mocked_input):
        share = mocked_input['cifs_share']

        connection.get_pool(share)

    @utils.patch_find_ports_by_mtu
    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_setup_server(self, connection, mocked_input, find_ports):
        find_ports.return_value = {'SPA': {'spa_eth1'}}
        network_info = mocked_input['network_info__flat']
        server_info = connection.setup_server(network_info)
        self.assertEqual(
            {'share_server_name':
             '78fd845f-8e7d-487f-bfde-051d83e78103'},
            server_info)
        self.assertIsNone(connection.client.system.create_nas_server.
                          call_args[1]['tenant'])

    @utils.patch_find_ports_by_mtu
    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_setup_server__vlan_network(self, connection, mocked_input,
                                        find_ports):
        find_ports.return_value = {'SPA': {'spa_eth1'}}
        network_info = mocked_input['network_info__vlan']

        connection.setup_server(network_info)
        self.assertEqual('tenant_1',
                         connection.client.system.create_nas_server
                         .call_args[1]['tenant'].id)

    @utils.patch_find_ports_by_mtu
    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_setup_server__vxlan_network(self, connection, mocked_input,
                                         find_ports):
        find_ports.return_value = {'SPA': {'spa_eth1'}}
        network_info = mocked_input['network_info__vxlan']

        self.assertRaises(exception.NetworkBadConfigurationException,
                          connection.setup_server,
                          network_info)

    @utils.patch_find_ports_by_mtu
    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_setup_server__active_directory(self, connection, mocked_input,
                                            find_ports):
        find_ports.return_value = {'SPA': {'spa_eth1'}}
        network_info = mocked_input['network_info__active_directory']

        connection.setup_server(network_info)

    @utils.patch_find_ports_by_mtu
    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_setup_server__kerberos(self, connection, mocked_input,
                                    find_ports):
        find_ports.return_value = {'SPA': {'spa_eth1'}}
        network_info = mocked_input['network_info__kerberos']

        connection.setup_server(network_info)

    @utils.patch_find_ports_by_mtu
    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_setup_server__throw_exception(self, connection, mocked_input,
                                           find_ports):
        find_ports.return_value = {'SPA': {'spa_eth1'}}
        network_info = mocked_input['network_info__flat']

        self.assertRaises(fake_exceptions.UnityException,
                          connection.setup_server,
                          network_info)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_teardown_server(self, connection, mocked_input):
        server_detail = mocked_input['server_detail']
        security_services = mocked_input['security_services']

        connection.teardown_server(server_detail, security_services)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_teardown_server__no_server_detail(self, connection, mocked_input):
        security_services = mocked_input['security_services']

        connection.teardown_server(None, security_services)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_teardown_server__no_share_server_name(self, connection,
                                                   mocked_input):
        server_detail = {'share_server_name': None}
        security_services = mocked_input['security_services']

        connection.teardown_server(server_detail, security_services)

    @ddt.data({'configured_pools': None,
               'matched_pools': {'pool_1', 'pool_2', 'nas_server_pool'}},
              {'configured_pools': ['*'],
               'matched_pools': {'pool_1', 'pool_2', 'nas_server_pool'}},
              {'configured_pools': ['pool_*'],
               'matched_pools': {'pool_1', 'pool_2'}},
              {'configured_pools': ['*pool'],
               'matched_pools': {'nas_server_pool'}},
              {'configured_pools': ['nas_server_pool'],
               'matched_pools': {'nas_server_pool'}},
              {'configured_pools': ['nas_*', 'pool_*'],
               'matched_pools': {'pool_1', 'pool_2', 'nas_server_pool'}})
    @res_mock.patch_connection
    @ddt.unpack
    def test__get_managed_pools(self, connection, mocked_input):
        configured_pools = mocked_input['configured_pools']
        matched_pool = mocked_input['matched_pools']

        pools = connection._get_managed_pools(configured_pools)

        self.assertEqual(matched_pool, pools)

    @res_mock.patch_connection
    def test__get_managed_pools__invalid_pool_configuration(self, connection):
        configured_pools = 'fake_pool'

        self.assertRaises(exception.BadConfigurationException,
                          connection._get_managed_pools,
                          configured_pools)

    @res_mock.patch_connection
    def test_validate_port_configuration(self, connection):
        sp_ports_map = connection.validate_port_configuration(['sp*'])

        self.assertEqual({'spa_eth1', 'spa_eth2', 'spa_la_4'},
                         sp_ports_map['SPA'])
        self.assertEqual({'spb_eth1'}, sp_ports_map['SPB'])

    @res_mock.patch_connection
    def test_validate_port_configuration_exception(self, connection):
        self.assertRaises(exception.BadConfigurationException,
                          connection.validate_port_configuration,
                          ['xxxx*'])

    @res_mock.patch_connection
    def test__get_pool_name_from_host__no_pool_name(self, connection):
        host = 'openstack@Unity'

        self.assertRaises(exception.InvalidHost,
                          connection._get_pool_name_from_host,
                          host)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_create_cifs_share_from_snapshot(self, connection, mocked_input):
        share = mocked_input['cifs_share']
        snapshot = mocked_input['snapshot']
        share_server = mocked_input['share_server']

        connection.create_share_from_snapshot(None, share, snapshot,
                                              share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_create_nfs_share_from_snapshot(self, connection, mocked_input):
        share = mocked_input['nfs_share']
        snapshot = mocked_input['snapshot']
        share_server = mocked_input['share_server']

        connection.create_share_from_snapshot(None, share, snapshot,
                                              share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_create_share_from_snapshot_no_server_name(self,
                                                       connection,
                                                       mocked_input):
        share = mocked_input['nfs_share']
        snapshot = mocked_input['snapshot']
        share_server = mocked_input['share_server__no_share_server_name']

        self.assertRaises(exception.EMCUnityError,
                          connection.create_share_from_snapshot,
                          None,
                          share,
                          snapshot,
                          share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_clear_share_access_cifs(self, connection, mocked_input):
        share = mocked_input['cifs_share']

        self.assertRaises(fake_exceptions.UnityException,
                          connection.clear_access,
                          share)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_clear_share_access_nfs(self, connection, mocked_input):
        share = mocked_input['nfs_share']

        self.assertRaises(fake_exceptions.UnityException,
                          connection.clear_access,
                          share)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_allow_rw_cifs_share_access(self, connection, mocked_input):
        share = mocked_input['cifs_share']
        rw_access = mocked_input['cifs_rw_access']
        share_server = mocked_input['share_server']

        connection.allow_access(None, share, rw_access, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_update_access_allow_rw(self, connection, mocked_input):
        share = mocked_input['cifs_share']
        rw_access = mocked_input['cifs_rw_access']
        share_server = mocked_input['share_server']

        connection.update_access(None, share, None, [rw_access], None,
                                 share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_update_access_recovery(self, connection, mocked_input):
        share = mocked_input['cifs_share']
        rw_access = mocked_input['cifs_rw_access']
        share_server = mocked_input['share_server']

        connection.update_access(None, share, [rw_access], None, None,
                                 share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_allow_ro_cifs_share_access(self, connection, mocked_input):
        share = mocked_input['cifs_share']
        rw_access = mocked_input['cifs_ro_access']
        share_server = mocked_input['share_server']

        connection.allow_access(None, share, rw_access, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_allow_rw_nfs_share_access(self, connection, mocked_input):
        share = mocked_input['nfs_share']
        rw_access = mocked_input['nfs_rw_access']
        share_server = mocked_input['share_server']

        connection.allow_access(None, share, rw_access, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_allow_rw_nfs_share_access_cidr(self, connection, mocked_input):
        share = mocked_input['nfs_share']
        rw_access = mocked_input['nfs_rw_access_cidr']
        share_server = mocked_input['share_server']

        connection.allow_access(None, share, rw_access, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_allow_ro_nfs_share_access(self, connection, mocked_input):
        share = mocked_input['nfs_share']
        ro_access = mocked_input['nfs_ro_access']
        share_server = mocked_input['share_server']

        connection.allow_access(None, share, ro_access, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_deny_cifs_share_access(self, connection, mocked_input):
        share = mocked_input['cifs_share']
        rw_access = mocked_input['cifs_rw_access']
        share_server = mocked_input['share_server']

        connection.deny_access(None, share, rw_access, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_deny_nfs_share_access(self, connection, mocked_input):
        share = mocked_input['nfs_share']
        rw_access = mocked_input['nfs_rw_access']
        share_server = mocked_input['share_server']

        connection.deny_access(None, share, rw_access, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_update_access_deny_nfs(self, connection, mocked_input):
        share = mocked_input['nfs_share']
        rw_access = mocked_input['nfs_rw_access']

        connection.update_access(None, share, None, None, [rw_access], None)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test__validate_cifs_share_access_type(self, connection, mocked_input):
        share = mocked_input['cifs_share']
        rw_access = mocked_input['invalid_access']

        self.assertRaises(exception.InvalidShareAccess,
                          connection._validate_share_access_type,
                          share,
                          rw_access)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test__validate_nfs_share_access_type(self, connection, mocked_input):
        share = mocked_input['nfs_share']
        rw_access = mocked_input['invalid_access']

        self.assertRaises(exception.InvalidShareAccess,
                          connection._validate_share_access_type,
                          share,
                          rw_access)

    @res_mock.patch_connection
    def test_get_network_allocations_number(self, connection):
        self.assertEqual(1, connection.get_network_allocations_number())

    @res_mock.patch_connection
    def test_get_proto_enum(self, connection):
        self.assertIn('FSSupportedProtocolEnum.CIFS',
                      str(connection._get_proto_enum('CIFS')))
        self.assertIn('FSSupportedProtocolEnum.NFS',
                      str(connection._get_proto_enum('nfs')))

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_allow_access_error_access_level(self, connection, mocked_input):
        share = mocked_input['nfs_share']
        rw_access = mocked_input['invalid_access']

        self.assertRaises(exception.InvalidShareAccessLevel,
                          connection.allow_access,
                          None, share, rw_access)

    @res_mock.patch_connection
    def test__create_network_interface_ipv6(self, connection):
        connection.client.create_interface = mock.Mock(return_value=None)
        nas_server = mock.Mock()
        network = {'ip_address': '2001:db8:0:1:f816:3eff:fe76:35c4',
                   'cidr': '2001:db8:0:1:f816:3eff:fe76:35c4/64',
                   'gateway': '2001:db8:0:1::1',
                   'segmentation_id': '201'}
        port_id = mock.Mock()
        connection._create_network_interface(nas_server, network, port_id)

        expected = {'ip_addr': '2001:db8:0:1:f816:3eff:fe76:35c4',
                    'netmask': None,
                    'gateway': '2001:db8:0:1::1',
                    'port_id': port_id,
                    'vlan_id': '201',
                    'prefix_length': '64'}
        connection.client.create_interface.assert_called_once_with(nas_server,
                                                                   **expected)

    @res_mock.patch_connection
    def test__create_network_interface_ipv4(self, connection):
        connection.client.create_interface = mock.Mock(return_value=None)
        nas_server = mock.Mock()
        network = {'ip_address': '192.168.1.10',
                   'cidr': '192.168.1.10/24',
                   'gateway': '192.168.1.1',
                   'segmentation_id': '201'}
        port_id = mock.Mock()
        connection._create_network_interface(nas_server, network, port_id)

        expected = {'ip_addr': '192.168.1.10',
                    'netmask': '255.255.255.0',
                    'gateway': '192.168.1.1',
                    'port_id': port_id,
                    'vlan_id': '201'}
        connection.client.create_interface.assert_called_once_with(nas_server,
                                                                   **expected)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_revert_to_snapshot(self, connection, mocked_input):
        context = mock.Mock()
        snapshot = mocked_input['snapshot']
        share_access_rules = [mocked_input['nfs_rw_access'], ]
        snapshot_access_rules = [mocked_input['nfs_rw_access'], ]

        connection.revert_to_snapshot(context, snapshot, share_access_rules,
                                      snapshot_access_rules)

    @res_mock.patch_connection_init
    def test_dhss_false_connect_without_nas_server(self, connection):
        self.assertRaises(exception.BadConfigurationException,
                          connection.connect,
                          res_mock.FakeEMCShareDriver(dhss=False), None)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_dhss_false_create_nfs_share(self, connection, mocked_input):
        connection.driver_handles_share_servers = False
        connection.unity_share_server = 'test-dhss-false-427f-b4de-0ad83el5j8'
        share = mocked_input['dhss_false_nfs_share']
        share_server = mocked_input['share_server']

        location = connection.create_share(None, share, share_server)

        exp_location = [
            {'path': 'fake_ip_addr_1:/cb532599-8dc6-4c3e-bb21-74ea54be566c'},
            {'path': 'fake_ip_addr_2:/cb532599-8dc6-4c3e-bb21-74ea54be566c'},
        ]
        exp_location = sorted(exp_location, key=lambda x: sorted(x['path']))
        location = sorted(location, key=lambda x: sorted(x['path']))
        self.assertEqual(exp_location, location)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_dhss_false_create_cifs_share(self, connection, mocked_input):
        connection.driver_handles_share_servers = False
        connection.unity_share_server = 'test-dhss-false-427f-b4de-0ad83el5j8'
        share = mocked_input['dhss_false_cifs_share']
        share_server = mocked_input['share_server']

        location = connection.create_share(None, share, share_server)

        exp_location = [
            {'path': r'\\fake_ip_addr_1\716100cc-e0b4-416b-ac27-d38dd019330d'},
            {'path': r'\\fake_ip_addr_2\716100cc-e0b4-416b-ac27-d38dd019330d'},
        ]
        exp_location = sorted(exp_location, key=lambda x: sorted(x['path']))
        location = sorted(location, key=lambda x: sorted(x['path']))
        self.assertEqual(exp_location, location)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_get_share_server_id(self, connection, mocked_input):
        share_server = mocked_input['share_server']
        result = connection._get_server_name(share_server)
        expected = 'c2e48947-98ed-4eae-999b-fa0b83731dfd'
        self.assertEqual(expected, result)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_manage_snapshot(self, connection, mocked_input):
        snapshot = mocked_input['snapshot']
        driver_options = {'size': 8}
        result = connection.manage_existing_snapshot(snapshot,
                                                     driver_options, None)
        expected = {'provider_location': '23047-ef2344-4563cvw-r4323cwed',
                    'size': 8}
        self.assertEqual(expected, result)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_manage_snapshot_wrong_size_type(self, connection, mocked_input):
        snapshot = mocked_input['snapshot']
        driver_options = {'size': 'str_size'}
        self.assertRaises(exception.ManageInvalidShareSnapshot,
                          connection.manage_existing_snapshot,
                          snapshot, driver_options, None)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_manage_snapshot_with_server(self, connection, mocked_input):
        share_server = mocked_input['share_server']
        snapshot = mocked_input['snapshot']
        driver_options = {}
        result = connection.manage_existing_snapshot_with_server(
            snapshot, driver_options, share_server)
        expected = {'provider_location': '23047-ef2344-4563cvw-r4323cwed',
                    'size': 1}
        self.assertEqual(expected, result)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_get_share_server_network_info(self, connection, mocked_input):
        share_server = mocked_input['share_server']
        identifier = 'test_manage_nas_server'
        result = connection.get_share_server_network_info(None, share_server,
                                                          identifier, None)
        expected = ['fake_ip_addr_1', 'fake_ip_addr_2']
        self.assertEqual(expected, result)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_manage_server(self, connection, mocked_input):
        share_server = mocked_input['share_server']
        identifier = 'test_manage_nas_server'
        result = connection.manage_server(None, share_server, identifier, None)
        expected = (identifier, None)
        self.assertEqual(expected, result)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_manage_nfs_share(self, connection, mocked_input):
        share = mocked_input['managed_nfs_share']
        driver_options = {'size': 3}
        result = connection.manage_existing(share, driver_options)
        path = '172.168.201.201:/ad1caddf-097e-462c-8ac6-5592ed6fe22f'
        expected = {'export_locations': {'path': path}, 'size': 3}
        self.assertEqual(expected, result)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_manage_nfs_share_with_server(self, connection, mocked_input):
        share = mocked_input['managed_nfs_share']
        share_server = mocked_input['share_server']
        driver_options = {'size': 8}
        result = connection.manage_existing_with_server(share, driver_options,
                                                        share_server)
        path = '172.168.201.201:/ad1caddf-097e-462c-8ac6-5592ed6fe22f'
        expected = {'export_locations': {'path': path}, 'size': 8}
        self.assertEqual(expected, result)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_manage_cifs_share(self, connection, mocked_input):
        share = mocked_input['managed_cifs_share']
        driver_options = {'size': 3}
        result = connection.manage_existing(share, driver_options)
        path = '\\\\10.0.0.1\\bd23121f-hg4e-432c-12cd2c5-bb93dfghe212'
        expected = {'export_locations': {'path': path}, 'size': 3}
        self.assertEqual(expected, result)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_manage_cifs_share_with_server(self, connection, mocked_input):
        connection.client.create_interface = mock.Mock(return_value=None)
        share = mocked_input['managed_cifs_share']
        share_server = mocked_input['share_server']
        driver_options = {'size': 3}
        result = connection.manage_existing_with_server(share, driver_options,
                                                        share_server)
        path = '\\\\10.0.0.1\\bd23121f-hg4e-432c-12cd2c5-bb93dfghe212'
        expected = {'export_locations': {'path': path}, 'size': 3}
        self.assertEqual(expected, result)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_manage_with_wrong_size_data_type(self, connection, mocked_input):
        connection.client.create_interface = mock.Mock(return_value=None)
        share = mocked_input['managed_nfs_share']
        share_server = mocked_input['share_server']
        driver_options = {'size': 'str_size'}
        self.assertRaises(exception.ManageInvalidShare,
                          connection.manage_existing_with_server,
                          share, driver_options, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_manage_without_size(self, connection, mocked_input):
        connection.client.create_interface = mock.Mock(return_value=None)
        share = mocked_input['managed_nfs_share']
        share_server = mocked_input['share_server']
        driver_options = {'size': 0}
        result = connection.manage_existing_with_server(share, driver_options,
                                                        share_server)
        path = '172.168.201.201:/ad1caddf-097e-462c-8ac6-5592ed6fe22f'
        expected = {'export_locations': {'path': path}, 'size': 1}
        self.assertEqual(expected, result)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_manage_without_export_locations(self, connection, mocked_input):
        connection.client.create_interface = mock.Mock(return_value=None)
        share = mocked_input['nfs_share']
        share_server = mocked_input['share_server']
        driver_options = {'size': 3}
        self.assertRaises(exception.ManageInvalidShare,
                          connection.manage_existing_with_server,
                          share, driver_options, share_server)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_get_default_filter_function_disable_report(self, connection,
                                                        mocked_input):
        expected = None
        actual = connection.get_default_filter_function()
        self.assertEqual(expected, actual)

    @res_mock.mock_manila_input
    @res_mock.patch_connection
    def test_get_default_filter_function_enable_report(self, connection,
                                                       mocked_input):
        expected = "share.size >= 3"
        connection.report_default_filter_function = True
        actual = connection.get_default_filter_function()
        self.assertEqual(expected, actual)
