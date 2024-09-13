# Copyright 2022 Infinidat Ltd.
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
"""Unit tests for INFINIDAT InfiniBox share driver."""

import copy
import functools
import itertools
from unittest import mock

import ddt
from oslo_utils import units

from manila.common import constants
from manila import exception
from manila.share import configuration
from manila.share.drivers.infinidat import infinibox
from manila import test
from manila import version


_MOCK_SHARE_ID = 1
_MOCK_SNAPSHOT_ID = 2
_MOCK_CLONE_ID = 3

_MOCK_SHARE_SIZE = 4

_MOCK_NETWORK_SPACE_IP_1 = '1.2.3.4'
_MOCK_NETWORK_SPACE_IP_2 = '1.2.3.5'


def _create_mock__getitem__(mock):
    def mock__getitem__(self, key, default=None):
        return getattr(mock, key, default)
    return mock__getitem__


test_share = mock.Mock(id=_MOCK_SHARE_ID, size=_MOCK_SHARE_SIZE,
                       share_proto='NFS')
test_share.__getitem__ = _create_mock__getitem__(test_share)

test_snapshot = mock.Mock(id=_MOCK_SNAPSHOT_ID, size=test_share.size,
                          share=test_share, share_proto='NFS')
test_snapshot.__getitem__ = _create_mock__getitem__(test_snapshot)

original_test_clone = mock.Mock(id=_MOCK_CLONE_ID, size=test_share.size,
                                share=test_snapshot, share_proto='NFS')
original_test_clone.__getitem__ = _create_mock__getitem__(original_test_clone)


def skip_driver_setup(func):
    @functools.wraps(func)
    def f(*args, **kwargs):
        return func(*args, **kwargs)
    f.__skip_driver_setup = True
    return f


class FakeInfinisdkException(Exception):
    pass


class FakeInfinisdkPermission(object):
    def __init__(self, permission):
        self._permission = permission

    def __getattr__(self, attr):
        return self._permission[attr]

    def __getitem__(self, key):
        return self._permission[key]


class InfiniboxDriverTestCaseBase(test.TestCase):
    def _test_skips_driver_setup(self):
        test_method_name = self.id().split('.')[-1]
        test_method = getattr(self, test_method_name)
        return getattr(test_method, '__skip_driver_setup', False)

    def setUp(self):
        super(InfiniboxDriverTestCaseBase, self).setUp()

        self.configuration = configuration.Configuration(None)
        self.configuration.append_config_values(
            infinibox.infinidat_connection_opts)
        self.configuration.append_config_values(
            infinibox.infinidat_auth_opts)
        self.configuration.append_config_values(
            infinibox.infinidat_general_opts)
        self.override_config('infinibox_hostname', 'mockbox')
        self.override_config('infinidat_pool_name', 'mockpool')
        self.override_config('infinidat_nas_network_space_name', 'mockspace')
        self.override_config('infinidat_thin_provision', True)
        self.override_config('infinibox_login', 'user')
        self.override_config('infinibox_password', 'pass')
        self.override_config('infinidat_use_ssl', False)
        self.override_config('infinidat_suppress_ssl_warnings', False)
        self.override_config('network_config_group',
                             'test_network_config_group')
        self.override_config('admin_network_config_group',
                             'test_admin_network_config_group')
        self.override_config('reserved_share_percentage', 0)
        self.override_config('reserved_share_from_snapshot_percentage', 0)
        self.override_config('reserved_share_extend_percentage', 0)
        self.override_config('filter_function', None)
        self.override_config('goodness_function', None)
        self.override_config('driver_handles_share_servers', False)
        self.override_config('max_over_subscription_ratio', 2)
        self.override_config('infinidat_snapdir_accessible', True)
        self.override_config('infinidat_snapdir_visible', False)

        self.driver = infinibox.InfiniboxShareDriver(
            configuration=self.configuration)

        # mock external library dependencies
        infinisdk = self._patch(
            "manila.share.drivers.infinidat.infinibox.infinisdk")
        self._capacity_module = (
            self._patch("manila.share.drivers.infinidat.infinibox.capacity"))
        self._capacity_module.byte = 1
        self._capacity_module.GiB = units.Gi

        self._system = self._infinibox_mock()

        infinisdk.core.exceptions.InfiniSDKException = FakeInfinisdkException
        infinisdk.InfiniBox.return_value = self._system

        if not self._test_skips_driver_setup():
            self.driver.do_setup(None)

    def _infinibox_mock(self):
        result = mock.Mock()

        self._mock_export_permissions = []

        self._mock_export = mock.Mock()
        self._mock_export.get_export_path.return_value = '/mock_export'
        self._mock_export.get_permissions = self._fake_get_permissions
        self._mock_export.update_permissions = self._fake_update_permissions

        self._mock_filesystem = mock.Mock()
        self._mock_filesystem.has_children.return_value = False
        self._mock_filesystem.create_snapshot.return_value = (
            self._mock_filesystem)
        self._mock_filesystem.get_exports.return_value = [self._mock_export, ]

        self._mock_filesystem.size = 4 * self._capacity_module.GiB
        self._mock_filesystem.get_size.return_value = (
            self._mock_filesystem.size)

        self._mock_pool = mock.Mock()
        self._mock_pool.get_free_physical_capacity.return_value = units.Gi
        self._mock_pool.get_physical_capacity.return_value = units.Gi
        self._mock_pool.get_virtual_capacity.return_value = units.Gi
        self._mock_pool.get_free_virtual_capacity.return_value = units.Gi

        self._mock_network_space = mock.Mock()
        self._mock_network_space.get_ips.return_value = (
            [mock.Mock(ip_address=_MOCK_NETWORK_SPACE_IP_1, enabled=True),
             mock.Mock(ip_address=_MOCK_NETWORK_SPACE_IP_2, enabled=True)])

        result.network_spaces.safe_get.return_value = self._mock_network_space
        result.pools.safe_get.return_value = self._mock_pool
        result.filesystems.safe_get.return_value = self._mock_filesystem
        result.filesystems.create.return_value = self._mock_filesystem
        result.components.nodes.get_all.return_value = []
        return result

    def _raise_infinisdk(self, *args, **kwargs):
        raise FakeInfinisdkException()

    def _fake_get_permissions(self):
        return self._mock_export_permissions

    def _fake_update_permissions(self, new_export_permissions):
        self._mock_export_permissions = [
            FakeInfinisdkPermission(permission) for permission in
            new_export_permissions]

    def _patch(self, path, *args, **kwargs):
        patcher = mock.patch(path, *args, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result


@ddt.ddt
class InfiniboxDriverTestCase(InfiniboxDriverTestCaseBase):
    def _generate_mock_metadata(self, share):
        return {"system": "openstack",
                "openstack_version": version.version_info.release_string(),
                "manila_id": share['id'],
                "manila_name": share['name'],
                "host.created_by": infinibox._INFINIDAT_MANILA_IDENTIFIER}

    def _validate_metadata(self, share):
        self._mock_filesystem.set_metadata_from_dict.assert_called_once_with(
            self._generate_mock_metadata(share))

    @mock.patch("manila.share.drivers.infinidat.infinibox.infinisdk", None)
    def test_no_infinisdk_module(self):
        self.assertRaises(exception.ManilaException,
                          self.driver.do_setup, None)

    @mock.patch("manila.share.drivers.infinidat.infinibox.capacity", None)
    def test_no_capacity_module(self):
        self.assertRaises(exception.ManilaException,
                          self.driver.do_setup, None)

    def test_no_auth_parameters(self):
        self.override_config('infinibox_login', None)
        self.override_config('infinibox_password', None)
        self.assertRaises(exception.BadConfigurationException,
                          self.driver.do_setup, None)

    def test_empty_auth_parameters(self):
        self.override_config('infinibox_login', '')
        self.override_config('infinibox_password', '')
        self.assertRaises(exception.BadConfigurationException,
                          self.driver.do_setup, None)

    @skip_driver_setup
    def test__setup_and_get_system_object(self):
        # This test should skip the driver setup, as it generates more calls to
        # the add_auto_retry, set_source_identifier and login methods:
        auth = (self.configuration.infinibox_login,
                self.configuration.infinibox_password)

        self.driver._setup_and_get_system_object(
            self.configuration.infinibox_hostname, auth,
            self.configuration.infinidat_use_ssl)

        self._system.api.add_auto_retry.assert_called_once()
        self._system.api.set_source_identifier.assert_called_once_with(
            infinibox._INFINIDAT_MANILA_IDENTIFIER)
        self._system.login.assert_called_once()

    @skip_driver_setup
    @mock.patch('manila.share.drivers.infinidat.infinibox.'
                'infinisdk.InfiniBox')
    @mock.patch('requests.packages.urllib3')
    def test_do_setup_ssl_enabled(self, urllib3, infinibox):
        self.override_config('infinidat_use_ssl', True)
        self.override_config('infinidat_suppress_ssl_warnings', True)
        auth = (self.configuration.infinibox_login,
                self.configuration.infinibox_password)
        self.driver.do_setup(None)
        expected = [
            mock.call(urllib3.exceptions.InsecureRequestWarning),
            mock.call(urllib3.exceptions.InsecurePlatformWarning)]
        urllib3.disable_warnings.assert_has_calls(expected)
        infinibox.assert_called_once_with(
            self.configuration.infinibox_hostname, auth=auth,
            use_ssl=self.configuration.infinidat_use_ssl)

    def test_get_share_stats_refreshes(self):
        self.driver._update_share_stats()
        result = self.driver.get_share_stats()
        self.assertEqual(1, result["free_capacity_gb"])
        # change the "free space" in the pool
        self._mock_pool.get_free_physical_capacity.return_value = 0
        # no refresh - free capacity should stay the same
        result = self.driver.get_share_stats(refresh=False)
        self.assertEqual(1, result["free_capacity_gb"])
        # refresh - free capacity should change to 0
        result = self.driver.get_share_stats(refresh=True)
        self.assertEqual(0, result["free_capacity_gb"])

    def test_get_share_stats_pool_not_found(self):
        self._system.pools.safe_get.return_value = None
        self.assertRaises(exception.ManilaException,
                          self.driver._update_share_stats)

    def test__verify_share_protocol(self):
        # test_share is NFS by default:
        self.driver._verify_share_protocol(test_share)

    def test__verify_share_protocol_fails_for_non_nfs(self):
        # set test_share protocol for non-NFS (CIFS, for that matter) and see
        # that we fail:
        cifs_share = copy.deepcopy(test_share)
        cifs_share.share_proto = 'CIFS'
        # also need to re-define getitem, otherwise we'll get attributes from
        # test_share:
        cifs_share.__getitem__ = _create_mock__getitem__(cifs_share)
        self.assertRaises(exception.InvalidShare,
                          self.driver._verify_share_protocol, cifs_share)

    def test__verify_access_type_ip(self):
        self.assertTrue(self.driver._verify_access_type({'access_type': 'ip'}))

    def test__verify_access_type_fails_for_type_user(self):
        self.assertRaises(
            exception.InvalidShareAccess, self.driver._verify_access_type,
            {'access_type': 'user'})

    def test__verify_access_type_fails_for_type_cert(self):
        self.assertRaises(
            exception.InvalidShareAccess, self.driver._verify_access_type,
            {'access_type': 'cert'})

    def test__get_ip_address_range_single_ip(self):
        ip_address = self.driver._get_ip_address_range('1.2.3.4')
        self.assertEqual('1.2.3.4', ip_address)

    def test__get_ip_address_range_ip_range(self):
        ip_address_range = self.driver._get_ip_address_range('5.6.7.8/28')
        self.assertEqual('5.6.7.1-5.6.7.14', ip_address_range)

    def test__get_ip_address_range_invalid_address(self):
        self.assertRaises(ValueError, self.driver._get_ip_address_range,
                          'invalid')

    def test__get_infinidat_pool(self):
        self.driver._get_infinidat_pool()
        self._system.pools.safe_get.assert_called_once()

    def test__get_infinidat_pool_no_pools(self):
        self._system.pools.safe_get.return_value = None
        self.assertRaises(exception.ShareBackendException,
                          self.driver._get_infinidat_pool)

    def test__get_infinidat_pool_api_error(self):
        self._system.pools.safe_get.side_effect = (
            self._raise_infinisdk)
        self.assertRaises(exception.ShareBackendException,
                          self.driver._get_infinidat_pool)

    def test__get_infinidat_nas_network_space_ips(self):
        network_space_ips = self.driver._get_infinidat_nas_network_space_ips()
        self._system.network_spaces.safe_get.assert_called_once()
        self._mock_network_space.get_ips.assert_called_once()

        for network_space_ip in \
                (_MOCK_NETWORK_SPACE_IP_1, _MOCK_NETWORK_SPACE_IP_2):
            self.assertIn(network_space_ip, network_space_ips)

    def test__get_infinidat_nas_network_space_ips_only_one_ip_enabled(self):
        self._mock_network_space.get_ips.return_value = (
            [mock.Mock(ip_address=_MOCK_NETWORK_SPACE_IP_1, enabled=True),
             mock.Mock(ip_address=_MOCK_NETWORK_SPACE_IP_2, enabled=False)])
        self.assertEqual([_MOCK_NETWORK_SPACE_IP_1],
                         self.driver._get_infinidat_nas_network_space_ips())

    def test__get_infinidat_nas_network_space_ips_no_network_space(self):
        self._system.network_spaces.safe_get.return_value = None
        self.assertRaises(exception.ShareBackendException,
                          self.driver._get_infinidat_nas_network_space_ips)

    def test__get_infinidat_nas_network_space_ips_no_ips(self):
        self._mock_network_space.get_ips.return_value = []
        self.assertRaises(exception.ShareBackendException,
                          self.driver._get_infinidat_nas_network_space_ips)

    def test__get_infinidat_nas_network_space_ips_no_ips_enabled(self):
        self._mock_network_space.get_ips.return_value = (
            [mock.Mock(ip_address=_MOCK_NETWORK_SPACE_IP_1, enabled=False),
             mock.Mock(ip_address=_MOCK_NETWORK_SPACE_IP_2, enabled=False)])
        self.assertRaises(exception.ShareBackendException,
                          self.driver._get_infinidat_nas_network_space_ips)

    def test__get_infinidat_nas_network_space_api_error(self):
        self._system.network_spaces.safe_get.side_effect = (
            self._raise_infinisdk)
        self.assertRaises(exception.ShareBackendException,
                          self.driver._get_infinidat_nas_network_space_ips)

    def test__get_full_nfs_export_paths(self):
        export_paths = self.driver._get_full_nfs_export_paths(
            self._mock_export.get_export_path())
        for network_space_ip in \
                (_MOCK_NETWORK_SPACE_IP_1, _MOCK_NETWORK_SPACE_IP_2):
            self.assertIn(
                "{network_space_ip}:{export_path}".format(
                    network_space_ip=network_space_ip,
                    export_path=self._mock_export.get_export_path()),
                export_paths)

    def test__get_export(self):
        # The default return value of get_exports is [mock_export, ]:
        export = self.driver._get_export(self._mock_filesystem)
        self._mock_filesystem.get_exports.assert_called_once()
        self.assertEqual(self._mock_export, export)

    def test__get_export_no_filesystem_exports(self):
        self._mock_filesystem.get_exports.return_value = []
        self.assertRaises(exception.ShareBackendException,
                          self.driver._get_export, self._mock_filesystem)

    def test__get_export_too_many_filesystem_exports(self):
        self._mock_filesystem.get_exports.return_value = [
            self._mock_export, self._mock_export]
        self.assertRaises(exception.ShareBackendException,
                          self.driver._get_export, self._mock_filesystem)

    def test__get_export_api_error(self):
        self._mock_filesystem.get_exports.side_effect = self._raise_infinisdk
        self.assertRaises(exception.ShareBackendException,
                          self.driver._get_export, self._mock_filesystem)

    def test__get_infinidat_access_level_rw(self):
        access_level = (
            self.driver._get_infinidat_access_level(
                {'access_level': constants.ACCESS_LEVEL_RW}))
        self.assertEqual('RW', access_level)

    def test__get_infinidat_access_level_ro(self):
        access_level = (
            self.driver._get_infinidat_access_level(
                {'access_level': constants.ACCESS_LEVEL_RO}))
        self.assertEqual('RO', access_level)

    def test__get_infinidat_access_level_fails_for_invalid_level(self):
        self.assertRaises(exception.InvalidShareAccessLevel,
                          self.driver._get_infinidat_access_level,
                          {'access_level': 'invalid'})

    @ddt.data(*itertools.product((True, False), (True, False), (True, False)))
    @ddt.unpack
    def test_create_share(self, thin_provision, snapdir_accessible,
                          snapdir_visible):
        self.override_config('infinidat_thin_provision', thin_provision)
        self.override_config('infinidat_snapdir_accessible',
                             snapdir_accessible)
        self.override_config('infinidat_snapdir_visible', snapdir_visible)
        if thin_provision:
            provtype = 'THIN'
        else:
            provtype = 'THICK'
        self.driver.do_setup(None)
        self.driver.create_share(None, test_share)
        share_name = self.driver._make_share_name(test_share)
        share_size = test_share.size * self._capacity_module.GiB
        self._system.filesystems.create.assert_called_once_with(
            pool=self._mock_pool, name=share_name, size=share_size,
            provtype=provtype, snapdir_accessible=snapdir_accessible)
        self._validate_metadata(test_share)
        self._mock_filesystem.add_export.assert_called_once_with(
            permissions=[], snapdir_visible=snapdir_visible)

    def test_create_share_pool_not_found(self):
        self._system.pools.safe_get.return_value = None
        self.assertRaises(exception.ManilaException,
                          self.driver.create_share, None, test_share)

    def test_create_share_fails_non_nfs(self):
        # set test_share protocol for non-NFS (CIFS, for that matter) and see
        # that we fail:
        cifs_share = copy.deepcopy(test_share)
        cifs_share.share_proto = 'CIFS'
        # also need to re-define getitem, otherwise we'll get attributes from
        # test_share:
        cifs_share.__getitem__ = _create_mock__getitem__(cifs_share)
        self.assertRaises(exception.InvalidShare,
                          self.driver.create_share, None, cifs_share)

    def test_create_share_pools_api_fail(self):
        # will fail when trying to get pool for share creation:
        self._system.pools.safe_get.side_effect = self._raise_infinisdk
        self.assertRaises(exception.ShareBackendException,
                          self.driver.create_share, None, test_share)

    def test_create_share_network_spaces_api_fail(self):
        # will fail when trying to get full export path to the new share:
        self._system.network_spaces.safe_get.side_effect = (
            self._raise_infinisdk)
        self.assertRaises(exception.ShareBackendException,
                          self.driver.create_share, None, test_share)

    def test_delete_share(self):
        self.driver.delete_share(None, test_share)
        self._mock_filesystem.safe_delete.assert_called_once()
        self._mock_export.safe_delete.assert_called_once()

    def test_delete_share_doesnt_exist(self):
        self._system.shares.safe_get.return_value = None
        # should not raise an exception
        self.driver.delete_share(None, test_share)

    def test_delete_share_export_doesnt_exist(self):
        self._mock_filesystem.get_exports.return_value = []
        # should not raise an exception
        self.driver.delete_share(None, test_share)

    def test_delete_share_with_snapshots(self):
        # deleting a share with snapshots should succeed:
        self._mock_filesystem.has_children.return_value = True
        self.driver.delete_share(None, test_share)
        self._mock_filesystem.safe_delete.assert_called_once()
        self._mock_export.safe_delete.assert_called_once()

    def test_delete_share_wrong_share_protocol(self):
        # set test_share protocol for non-NFS (CIFS, for that matter) and see
        # that delete_share doesn't fail:
        cifs_share = copy.deepcopy(test_share)
        cifs_share.share_proto = 'CIFS'
        # also need to re-define getitem, otherwise we'll get attributes from
        # test_share:
        cifs_share.__getitem__ = _create_mock__getitem__(cifs_share)
        self.driver.delete_share(None, cifs_share)

    def test_extend_share(self):
        self.driver.extend_share(test_share, _MOCK_SHARE_SIZE * 2)
        self._mock_filesystem.resize.assert_called_once()

    def test_extend_share_api_fail(self):
        self._mock_filesystem.resize.side_effect = self._raise_infinisdk
        self.assertRaises(exception.ShareBackendException,
                          self.driver.extend_share, test_share, 8)

    @ddt.data(*itertools.product((True, False), (True, False)))
    @ddt.unpack
    def test_create_snapshot(self, snapdir_accessible, snapdir_visible):
        self.override_config('infinidat_snapdir_accessible',
                             snapdir_accessible)
        self.override_config('infinidat_snapdir_visible', snapdir_visible)
        snapshot_name = self.driver._make_snapshot_name(test_snapshot)
        self.driver.create_snapshot(None, test_snapshot)
        self._mock_filesystem.create_snapshot.assert_called_once_with(
            name=snapshot_name, snapdir_accessible=snapdir_accessible)
        self._validate_metadata(test_snapshot)
        self._mock_filesystem.add_export.assert_called_once_with(
            permissions=[], snapdir_visible=snapdir_visible)

    def test_create_snapshot_metadata(self):
        self._mock_filesystem.create_snapshot.return_value = (
            self._mock_filesystem)
        self.driver.create_snapshot(None, test_snapshot)
        self._validate_metadata(test_snapshot)

    def test_create_snapshot_share_doesnt_exist(self):
        self._system.filesystems.safe_get.return_value = None
        self.assertRaises(exception.ShareResourceNotFound,
                          self.driver.create_snapshot, None, test_snapshot)

    def test_create_snapshot_create_snapshot_api_fail(self):
        # will fail when trying to create a child to the original share:
        self._mock_filesystem.create_snapshot.side_effect = (
            self._raise_infinisdk)
        self.assertRaises(exception.ShareBackendException,
                          self.driver.create_snapshot, None, test_snapshot)

    def test_create_snapshot_network_spaces_api_fail(self):
        # will fail when trying to get full export path to the new snapshot:
        self._system.network_spaces.safe_get.side_effect = (
            self._raise_infinisdk)
        self.assertRaises(exception.ShareBackendException,
                          self.driver.create_snapshot, None, test_snapshot)

    @ddt.data(*itertools.product((True, False), (True, False)))
    @ddt.unpack
    def test_create_share_from_snapshot(self, snapdir_accessible,
                                        snapdir_visible):
        self.override_config('infinidat_snapdir_accessible',
                             snapdir_accessible)
        self.override_config('infinidat_snapdir_visible', snapdir_visible)
        share_name = self.driver._make_share_name(original_test_clone)
        self.driver.create_share_from_snapshot(None, original_test_clone,
                                               test_snapshot)
        self._mock_filesystem.create_snapshot.assert_called_once_with(
            name=share_name, write_protected=False,
            snapdir_accessible=snapdir_accessible)
        self._mock_filesystem.add_export.assert_called_once_with(
            permissions=[], snapdir_visible=snapdir_visible)

    def test_create_share_from_snapshot_bigger_size(self):
        test_clone = copy.copy(original_test_clone)
        test_clone.size = test_share.size * 2
        # also need to re-define getitem, otherwise we'll get attributes from
        # original_get_clone:
        test_clone.__getitem__ = _create_mock__getitem__(test_clone)

        self.driver.create_share_from_snapshot(None, test_clone, test_snapshot)

    def test_create_share_from_snapshot_doesnt_exist(self):
        self._system.filesystems.safe_get.return_value = None
        self.assertRaises(exception.ShareSnapshotNotFound,
                          self.driver.create_share_from_snapshot,
                          None, original_test_clone, test_snapshot)

    def test_create_share_from_snapshot_create_fails(self):
        self._mock_filesystem.create_snapshot.side_effect = (
            self._raise_infinisdk)
        self.assertRaises(exception.ShareBackendException,
                          self.driver.create_share_from_snapshot,
                          None, original_test_clone, test_snapshot)

    def test_delete_snapshot(self):
        self.driver.delete_snapshot(None, test_snapshot)
        self._mock_filesystem.safe_delete.assert_called_once()
        self._mock_export.safe_delete.assert_called_once()

    def test_delete_snapshot_with_snapshots(self):
        # deleting a snapshot with snapshots should succeed:
        self._mock_filesystem.has_children.return_value = True
        self.driver.delete_snapshot(None, test_snapshot)
        self._mock_filesystem.safe_delete.assert_called_once()
        self._mock_export.safe_delete.assert_called_once()

    def test_delete_snapshot_doesnt_exist(self):
        self._system.filesystems.safe_get.return_value = None
        # should not raise an exception
        self.driver.delete_snapshot(None, test_snapshot)

    def test_delete_snapshot_api_fail(self):
        self._mock_filesystem.safe_delete.side_effect = self._raise_infinisdk
        self.assertRaises(exception.ShareBackendException,
                          self.driver.delete_snapshot, None, test_snapshot)

    @ddt.data(*itertools.product((True, False), (True, False),
                                 (True, False), (True, False)))
    @ddt.unpack
    def test_ensure_share(self, snapdir_accessible_expected,
                          snapdir_accessible_actual,
                          snapdir_visible_expected,
                          snapdir_visible_actual):
        self.override_config('infinidat_snapdir_accessible',
                             snapdir_accessible_expected)
        self.override_config('infinidat_snapdir_visible',
                             snapdir_visible_expected)
        self._mock_filesystem.is_snapdir_accessible.return_value = (
            snapdir_accessible_actual)
        self._mock_export.is_snapdir_visible.return_value = (
            snapdir_visible_actual)
        self.driver.ensure_share(None, test_share)
        self._mock_filesystem.get_exports.assert_called_once()
        self._mock_export.get_export_path.assert_called_once()
        if snapdir_accessible_actual is not snapdir_accessible_expected:
            self._mock_filesystem.update_field.assert_called_once_with(
                'snapdir_accessible', snapdir_accessible_expected)
        else:
            self._mock_filesystem.update_field.assert_not_called()
        if snapdir_visible_actual is not snapdir_visible_expected:
            self._mock_export.update_snapdir_visible.assert_called_once_with(
                snapdir_visible_expected)
        else:
            self._mock_export.update_snapdir_visible.assert_not_called()

    @ddt.data(True, False)
    def test_ensure_share_export_missing(self, snapdir_visible):
        self.override_config('infinidat_snapdir_visible', snapdir_visible)
        self._mock_filesystem.get_exports.return_value = []
        self.driver.ensure_share(None, test_share)
        self._mock_filesystem.get_exports.assert_called_once()
        self._mock_filesystem.add_export.assert_called_once_with(
            permissions=[], snapdir_visible=snapdir_visible)

    def test_ensure_share_share_doesnt_exist(self):
        self._system.filesystems.safe_get.return_value = None
        self.assertRaises(exception.ShareResourceNotFound,
                          self.driver.ensure_share, None, test_share)

    def test_ensure_share_get_exports_api_fail(self):
        self._mock_filesystem.get_exports.side_effect = self._raise_infinisdk
        self._mock_filesystem.add_export.side_effect = self._raise_infinisdk
        self.assertRaises(exception.ShareBackendException,
                          self.driver.ensure_share, None, test_share)

    def test_ensure_share_network_spaces_api_fail(self):
        self._system.network_spaces.safe_get.side_effect = (
            self._raise_infinisdk)
        self.assertRaises(exception.ShareBackendException,
                          self.driver.ensure_share, None, test_share)

    def test_ensure_shares(self):
        test_shares = [test_share]
        test_updates = self.driver.ensure_shares(None, test_shares)
        self.assertEqual(len(test_shares), len(test_updates))

    @ddt.data(*itertools.product((True, False), (True, False)))
    @ddt.unpack
    def test_get_backend_info(self, snapdir_accessible, snapdir_visible):
        self.override_config('infinidat_snapdir_accessible',
                             snapdir_accessible)
        self.override_config('infinidat_snapdir_visible',
                             snapdir_visible)
        expected = {
            'snapdir_accessible': snapdir_accessible,
            'snapdir_visible': snapdir_visible
        }
        result = self.driver.get_backend_info(None)
        self.assertEqual(expected, result)

    def test_get_network_allocations_number(self):
        # Mostly to increase test coverage. The return value should always be 0
        # for our driver (see method documentation in base class code):
        self.assertEqual(0, self.driver.get_network_allocations_number())

    def test_revert_to_snapshot(self):
        self.driver.revert_to_snapshot(None, test_snapshot, [], [])
        self._mock_filesystem.restore.assert_called_once()

    def test_revert_to_snapshot_snapshot_doesnt_exist(self):
        self._system.filesystems.safe_get.return_value = None
        self.assertRaises(exception.ShareSnapshotNotFound,
                          self.driver.revert_to_snapshot, None, test_snapshot,
                          [], [])

    def test_revert_to_snapshot_api_fail(self):
        self._mock_filesystem.restore.side_effect = self._raise_infinisdk
        self.assertRaises(exception.ShareBackendException,
                          self.driver.revert_to_snapshot, None, test_snapshot,
                          [], [])

    def test_update_access(self):
        access_rules = [
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '1.2.3.4',
             'access_type': 'ip'},
            {'access_level': constants.ACCESS_LEVEL_RW,
             'access_to': '1.2.3.5',
             'access_type': 'ip'},
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '5.6.7.8/28',
             'access_type': 'ip'}]
        self.driver.update_access(None, test_share, access_rules, [], [])

        permissions = self._mock_filesystem.get_exports()[0].get_permissions()
        # now we are supposed to have three permissions:
        # 1. for 1.2.3.4
        # 2. for 1.2.3.5
        # 3. for 5.6.7.1-5.6.7.14
        self.assertEqual(3, len(permissions))

        # sorting according to clients, to avoid mismatch errors:
        permissions = sorted(permissions,
                             key=lambda permission: permission.client)

        self.assertEqual('RO', permissions[0].access)
        self.assertEqual('1.2.3.4', permissions[0].client)
        self.assertTrue(permissions[0].no_root_squash)

        self.assertEqual('RW', permissions[1].access)
        self.assertEqual('1.2.3.5', permissions[1].client)
        self.assertTrue(permissions[1].no_root_squash)

        self.assertEqual('RO', permissions[2].access)
        self.assertEqual('5.6.7.1-5.6.7.14', permissions[2].client)
        self.assertTrue(permissions[2].no_root_squash)

    def test_update_access_share_doesnt_exist(self):
        self._system.filesystems.safe_get.return_value = None
        access_rules = [
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '1.2.3.4',
             'access_type': 'ip'},
            {'access_level': constants.ACCESS_LEVEL_RW,
             'access_to': '1.2.3.5',
             'access_type': 'ip'},
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '5.6.7.8/28',
             'access_type': 'ip'}]
        self.assertRaises(exception.ShareResourceNotFound,
                          self.driver.update_access, None, test_share,
                          access_rules, [], [])

    def test_update_access_api_fail(self):
        self._mock_filesystem.get_exports.side_effect = self._raise_infinisdk
        access_rules = [
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '1.2.3.4',
             'access_type': 'ip'},
            {'access_level': constants.ACCESS_LEVEL_RW,
             'access_to': '1.2.3.5',
             'access_type': 'ip'},
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '5.6.7.8/28',
             'access_type': 'ip'}]
        self.assertRaises(exception.ShareBackendException,
                          self.driver.update_access, None, test_share,
                          access_rules, [], [])

    def test_update_access_fails_non_ip_access_type(self):
        access_rules = [
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '1.2.3.4',
             'access_type': 'user'}]
        self.assertRaises(exception.InvalidShareAccess,
                          self.driver.update_access, None, test_share,
                          access_rules, [], [])

    def test_update_access_fails_invalid_ip(self):
        access_rules = [
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': 'invalid',
             'access_type': 'ip'}]
        self.assertRaises(ValueError,
                          self.driver.update_access, None, test_share,
                          access_rules, [], [])

    def test_snapshot_update_access(self):
        access_rules = [
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '1.2.3.4',
             'access_type': 'ip'},
            {'access_level': constants.ACCESS_LEVEL_RW,
             'access_to': '1.2.3.5',
             'access_type': 'ip'},
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '5.6.7.8/28',
             'access_type': 'ip'}]
        self.driver.snapshot_update_access(None, test_snapshot, access_rules,
                                           [], [])

        permissions = self._mock_filesystem.get_exports()[0].get_permissions()
        # now we are supposed to have three permissions:
        # 1. for 1.2.3.4
        # 2. for 1.2.3.5
        # 3. for 5.6.7.1-5.6.7.14
        self.assertEqual(3, len(permissions))

        # sorting according to clients, to avoid mismatch errors:
        permissions = sorted(permissions,
                             key=lambda permission: permission.client)

        self.assertEqual('RO', permissions[0].access)
        self.assertEqual('1.2.3.4', permissions[0].client)
        self.assertTrue(permissions[0].no_root_squash)

        # despite sending a RW rule, all rules are converted to RO:
        self.assertEqual('RO', permissions[1].access)
        self.assertEqual('1.2.3.5', permissions[1].client)
        self.assertTrue(permissions[1].no_root_squash)

        self.assertEqual('RO', permissions[2].access)
        self.assertEqual('5.6.7.1-5.6.7.14', permissions[2].client)
        self.assertTrue(permissions[2].no_root_squash)

    def test_snapshot_update_access_snapshot_doesnt_exist(self):
        self._system.filesystems.safe_get.return_value = None
        access_rules = [
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '1.2.3.4',
             'access_type': 'ip'},
            {'access_level': constants.ACCESS_LEVEL_RW,
             'access_to': '1.2.3.5',
             'access_type': 'ip'},
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '5.6.7.8/28',
             'access_type': 'ip'}]
        self.assertRaises(exception.ShareSnapshotNotFound,
                          self.driver.snapshot_update_access, None,
                          test_snapshot, access_rules, [], [])

    def test_snapshot_update_access_api_fail(self):
        self._mock_filesystem.get_exports.side_effect = self._raise_infinisdk
        access_rules = [
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '1.2.3.4',
             'access_type': 'ip'},
            {'access_level': constants.ACCESS_LEVEL_RW,
             'access_to': '1.2.3.5',
             'access_type': 'ip'},
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '5.6.7.8/28',
             'access_type': 'ip'}]
        self.assertRaises(exception.ShareBackendException,
                          self.driver.snapshot_update_access, None,
                          test_snapshot, access_rules, [], [])

    def test_snapshot_update_access_fails_non_ip_access_type(self):
        access_rules = [
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': '1.2.3.4',
             'access_type': 'user'}]
        self.assertRaises(exception.InvalidSnapshotAccess,
                          self.driver.snapshot_update_access, None, test_share,
                          access_rules, [], [])

    def test_snapshot_update_access_fails_invalid_ip(self):
        access_rules = [
            {'access_level': constants.ACCESS_LEVEL_RO,
             'access_to': 'invalid',
             'access_type': 'ip'}]
        self.assertRaises(ValueError,
                          self.driver.snapshot_update_access, None, test_share,
                          access_rules, [], [])
