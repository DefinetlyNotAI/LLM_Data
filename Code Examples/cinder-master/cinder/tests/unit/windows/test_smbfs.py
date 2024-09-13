#  Copyright 2014 Cloudbase Solutions Srl
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
import os
from unittest import mock

import ddt
from oslo_utils import timeutils
from oslo_utils import units

from cinder import context
from cinder import exception
from cinder.image import image_utils
from cinder.objects import fields
from cinder.tests.unit import fake_constants as fake
from cinder.tests.unit import fake_volume
from cinder.tests.unit import test
from cinder.tests.unit import utils as test_utils
from cinder.volume.drivers import remotefs
from cinder.volume.drivers.windows import smbfs


@ddt.ddt
class WindowsSmbFsTestCase(test.TestCase):

    _FAKE_SHARE = '//1.2.3.4/share1'
    _FAKE_SHARE_HASH = 'db0bf952c1734092b83e8990bd321131'
    _FAKE_MNT_BASE = r'c:\openstack\mnt'
    _FAKE_MNT_POINT = os.path.join(_FAKE_MNT_BASE, _FAKE_SHARE_HASH)
    _FAKE_VOLUME_ID = '4f711859-4928-4cb7-801a-a50c37ceaccc'
    _FAKE_VOLUME_NAME = 'volume-%s.vhdx' % _FAKE_VOLUME_ID
    _FAKE_SNAPSHOT_ID = '50811859-4928-4cb7-801a-a50c37ceacba'
    _FAKE_SNAPSHOT_NAME = 'volume-%s-%s.vhdx' % (_FAKE_VOLUME_ID,
                                                 _FAKE_SNAPSHOT_ID)
    _FAKE_SNAPSHOT_PATH = os.path.join(_FAKE_MNT_POINT,
                                       _FAKE_SNAPSHOT_NAME)
    _FAKE_VOLUME_SIZE = 1
    _FAKE_TOTAL_SIZE = 2048
    _FAKE_TOTAL_AVAILABLE = 1024
    _FAKE_TOTAL_ALLOCATED = 1024
    _FAKE_SHARE_OPTS = '-o username=Administrator,password=12345'
    _FAKE_VOLUME_PATH = os.path.join(_FAKE_MNT_POINT,
                                     _FAKE_VOLUME_NAME)
    _FAKE_SHARE_OPTS = '-o username=Administrator,password=12345'

    @mock.patch.object(smbfs, 'utilsfactory')
    @mock.patch.object(smbfs, 'remotefs_brick')
    def setUp(self, mock_remotefs, mock_utilsfactory):
        super(WindowsSmbFsTestCase, self).setUp()

        self.context = context.get_admin_context()

        self._FAKE_SMBFS_CONFIG = mock.MagicMock(
            smbfs_shares_config=mock.sentinel.share_config_file,
            smbfs_default_volume_format='vhdx',
            nas_volume_prov_type='thin')

        self._smbfs_driver = smbfs.WindowsSmbfsDriver(
            configuration=self._FAKE_SMBFS_CONFIG)
        self._smbfs_driver._delete = mock.Mock()
        self._smbfs_driver._local_volume_dir = mock.Mock(
            return_value=self._FAKE_MNT_POINT)
        self._smbfs_driver.base = self._FAKE_MNT_BASE

        self._diskutils = self._smbfs_driver._diskutils
        self._vhdutils = self._smbfs_driver._vhdutils

        self.volume = self._simple_volume()
        self.snapshot = self._simple_snapshot(volume=self.volume)

        self._context = context.get_admin_context()
        self.updated_at = timeutils.utcnow()

    def _simple_volume(self, **kwargs):
        updates = {'id': self._FAKE_VOLUME_ID,
                   'size': self._FAKE_VOLUME_SIZE,
                   'provider_location': self._FAKE_SHARE}
        updates.update(kwargs)
        ctxt = context.get_admin_context()
        volume = test_utils.create_volume(ctxt, **updates)
        return volume

    def _simple_snapshot(self, **kwargs):
        volume = kwargs.pop('volume', None) or self._simple_volume()
        ctxt = context.get_admin_context()
        updates = {'id': self._FAKE_SNAPSHOT_ID,
                   'volume_id': volume.id}
        updates.update(kwargs)
        snapshot = test_utils.create_snapshot(ctxt, **updates)
        return snapshot

    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_check_os_platform')
    @mock.patch.object(remotefs.RemoteFSSnapDriverDistributed, 'do_setup')
    @mock.patch('os.path.exists')
    @mock.patch('os.path.isabs')
    @mock.patch.object(image_utils, 'check_qemu_img_version')
    def _test_setup(self, mock_check_qemu_img_version,
                    mock_is_abs, mock_exists,
                    mock_remotefs_do_setup,
                    mock_check_os_platform,
                    config, share_config_exists=True):
        mock_exists.return_value = share_config_exists
        fake_ensure_mounted = mock.MagicMock()
        self._smbfs_driver._ensure_shares_mounted = fake_ensure_mounted
        self._smbfs_driver._setup_pool_mappings = mock.Mock()
        self._smbfs_driver.configuration = config

        if not (config.smbfs_shares_config and share_config_exists):
            self.assertRaises(smbfs.SmbfsException,
                              self._smbfs_driver.do_setup,
                              mock.sentinel.context)
        else:
            self._smbfs_driver.do_setup(mock.sentinel.context)

            mock_check_qemu_img_version.assert_called_once_with(
                self._smbfs_driver._MINIMUM_QEMU_IMG_VERSION)
            mock_is_abs.assert_called_once_with(self._smbfs_driver.base)
            self.assertEqual({}, self._smbfs_driver.shares)
            fake_ensure_mounted.assert_called_once_with()
            self._smbfs_driver._setup_pool_mappings.assert_called_once_with()

        self.assertTrue(self._smbfs_driver._thin_provisioning_support)
        mock_check_os_platform.assert_called_once_with()

    def test_setup_pools(self):
        pool_mappings = {
            '//ip/share0': 'pool0',
            '//ip/share1': 'pool1',
        }
        self._smbfs_driver.configuration.smbfs_pool_mappings = pool_mappings
        self._smbfs_driver.shares = {
            '//ip/share0': None,
            '//ip/share1': None,
            '//ip/share2': None
        }

        expected_pool_mappings = pool_mappings.copy()
        expected_pool_mappings['//ip/share2'] = 'share2'

        self._smbfs_driver._setup_pool_mappings()
        self.assertEqual(expected_pool_mappings,
                         self._smbfs_driver._pool_mappings)

    def test_setup_pool_duplicates(self):
        self._smbfs_driver.configuration.smbfs_pool_mappings = {
            'share0': 'pool0',
            'share1': 'pool0'
        }
        self.assertRaises(smbfs.SmbfsException,
                          self._smbfs_driver._setup_pool_mappings)

    def test_initialize_connection(self):
        self._smbfs_driver.get_active_image_from_info = mock.Mock(
            return_value=self._FAKE_VOLUME_NAME)
        self._smbfs_driver._get_mount_point_base = mock.Mock(
            return_value=self._FAKE_MNT_BASE)
        self._smbfs_driver.shares = {self._FAKE_SHARE: self._FAKE_SHARE_OPTS}
        self._smbfs_driver.get_volume_format = mock.Mock(
            return_value=mock.sentinel.format)

        fake_data = {'export': self._FAKE_SHARE,
                     'format': mock.sentinel.format,
                     'name': self._FAKE_VOLUME_NAME,
                     'options': self._FAKE_SHARE_OPTS}
        expected = {
            'driver_volume_type': 'smbfs',
            'data': fake_data,
            'mount_point_base': self._FAKE_MNT_BASE}
        ret_val = self._smbfs_driver.initialize_connection(
            self.volume, None)

        self.assertEqual(expected, ret_val)

    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_get_snapshot_backing_file')
    @mock.patch.object(smbfs.WindowsSmbfsDriver, 'get_volume_format')
    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_get_mount_point_base')
    def test_initialize_connection_snapshot(self, mock_get_mount_base,
                                            mock_get_volume_format,
                                            mock_get_snap_by_backing_file):
        self._smbfs_driver.shares = {self._FAKE_SHARE: self._FAKE_SHARE_OPTS}
        mock_get_snap_by_backing_file.return_value = self._FAKE_VOLUME_NAME
        mock_get_volume_format.return_value = 'vhdx'
        mock_get_mount_base.return_value = self._FAKE_MNT_BASE

        exp_data = {'export': self._FAKE_SHARE,
                    'format': 'vhdx',
                    'name': self._FAKE_VOLUME_NAME,
                    'options': self._FAKE_SHARE_OPTS,
                    'access_mode': 'ro'}
        expected = {
            'driver_volume_type': 'smbfs',
            'data': exp_data,
            'mount_point_base': self._FAKE_MNT_BASE}
        ret_val = self._smbfs_driver.initialize_connection_snapshot(
            self.snapshot, mock.sentinel.connector)

        self.assertEqual(expected, ret_val)

        mock_get_snap_by_backing_file.assert_called_once_with(self.snapshot)
        mock_get_volume_format.assert_called_once_with(self.snapshot.volume)
        mock_get_mount_base.assert_called_once_with()

    def test_setup(self):
        self._test_setup(config=self._FAKE_SMBFS_CONFIG)

    def test_setup_missing_shares_config_option(self):
        fake_config = copy.copy(self._FAKE_SMBFS_CONFIG)
        fake_config.smbfs_shares_config = None
        self._test_setup(config=fake_config,
                         share_config_exists=False)

    def test_setup_missing_shares_config_file(self):
        self._test_setup(config=self._FAKE_SMBFS_CONFIG,
                         share_config_exists=False)

    @mock.patch.object(smbfs, 'context')
    @mock.patch.object(smbfs.WindowsSmbfsDriver,
                       '_get_pool_name_from_share')
    def test_get_total_allocated(self, mock_get_pool_name, mock_ctxt):
        fake_pool_name = 'pool0'
        fake_host_name = 'fake_host@fake_backend'
        fake_vol_sz_sum = 5

        mock_db = mock.Mock()
        mock_db.volume_data_get_for_host.return_value = [
            mock.sentinel.vol_count, fake_vol_sz_sum]

        self._smbfs_driver.host = fake_host_name
        self._smbfs_driver.db = mock_db

        mock_get_pool_name.return_value = fake_pool_name

        allocated = self._smbfs_driver._get_total_allocated(
            mock.sentinel.share)
        self.assertEqual(fake_vol_sz_sum << 30,
                         allocated)

        mock_get_pool_name.assert_called_once_with(mock.sentinel.share)
        mock_db.volume_data_get_for_host.assert_called_once_with(
            context=mock_ctxt.get_admin_context.return_value,
            host='fake_host@fake_backend#pool0')

    @mock.patch.object(smbfs.WindowsSmbfsDriver,
                       '_get_local_volume_path_template')
    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_lookup_local_volume_path')
    @mock.patch.object(smbfs.WindowsSmbfsDriver, 'get_volume_format')
    def _test_get_volume_path(self, mock_get_volume_format, mock_lookup_volume,
                              mock_get_path_template, volume_exists=True):
        drv = self._smbfs_driver
        (mock_get_path_template.return_value,
         ext) = os.path.splitext(self._FAKE_VOLUME_PATH)
        volume_format = ext.strip('.')

        mock_lookup_volume.return_value = (
            self._FAKE_VOLUME_PATH if volume_exists else None)
        mock_get_volume_format.return_value = volume_format

        ret_val = drv.local_path(self.volume)

        if volume_exists:
            self.assertFalse(mock_get_volume_format.called)
        else:
            mock_get_volume_format.assert_called_once_with(self.volume)
        self.assertEqual(self._FAKE_VOLUME_PATH, ret_val)

    def test_get_existing_volume_path(self):
        self._test_get_volume_path()

    def test_get_new_volume_path(self):
        self._test_get_volume_path(volume_exists=False)

    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_local_volume_dir')
    def test_get_local_volume_path_template(self, mock_get_local_dir):
        mock_get_local_dir.return_value = self._FAKE_MNT_POINT
        ret_val = self._smbfs_driver._get_local_volume_path_template(
            self.volume)
        exp_template = os.path.splitext(self._FAKE_VOLUME_PATH)[0]
        self.assertEqual(exp_template, ret_val)

    @mock.patch('os.path.exists')
    def test_lookup_local_volume_path(self, mock_exists):
        expected_path = self._FAKE_VOLUME_PATH + '.vhdx'
        mock_exists.side_effect = lambda x: x == expected_path

        ret_val = self._smbfs_driver._lookup_local_volume_path(
            self._FAKE_VOLUME_PATH)

        extensions = [
            ".%s" % ext
            for ext in self._smbfs_driver._VALID_IMAGE_EXTENSIONS]
        possible_paths = [self._FAKE_VOLUME_PATH + ext
                          for ext in extensions]
        mock_exists.assert_has_calls(
            [mock.call(path) for path in possible_paths])
        self.assertEqual(expected_path, ret_val)

    @mock.patch.object(smbfs.WindowsSmbfsDriver,
                       '_get_local_volume_path_template')
    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_lookup_local_volume_path')
    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_get_volume_format_spec')
    def _test_get_volume_format(self, mock_get_format_spec,
                                mock_lookup_volume, mock_get_path_template,
                                qemu_format=False, volume_format='vhdx',
                                expected_vol_fmt=None,
                                volume_exists=True):
        expected_vol_fmt = expected_vol_fmt or volume_format

        vol_path = '%s.%s' % (os.path.splitext(self._FAKE_VOLUME_PATH)[0],
                              volume_format)
        mock_get_path_template.return_value = vol_path
        mock_lookup_volume.return_value = (
            vol_path if volume_exists else None)

        mock_get_format_spec.return_value = volume_format

        supported_fmts = self._smbfs_driver._SUPPORTED_IMAGE_FORMATS
        if volume_format.lower() not in supported_fmts:
            self.assertRaises(smbfs.SmbfsException,
                              self._smbfs_driver.get_volume_format,
                              self.volume,
                              qemu_format)

        else:
            ret_val = self._smbfs_driver.get_volume_format(self.volume,
                                                           qemu_format)

            if volume_exists:
                self.assertFalse(mock_get_format_spec.called)
            else:
                mock_get_format_spec.assert_called_once_with(self.volume)

            self.assertEqual(expected_vol_fmt, ret_val)

    def test_get_volume_format_invalid_extension(self):
        self._test_get_volume_format(volume_format='fake')

    def test_get_existing_vhdx_volume_format(self):
        self._test_get_volume_format()

    def test_get_new_vhd_volume_format(self):
        fmt = 'vhd'
        self._test_get_volume_format(volume_format=fmt,
                                     volume_exists=False,
                                     expected_vol_fmt=fmt)

    def test_get_new_vhd_legacy_volume_format(self):
        img_fmt = 'vhd'
        expected_fmt = 'vpc'
        self._test_get_volume_format(volume_format=img_fmt,
                                     volume_exists=False,
                                     qemu_format=True,
                                     expected_vol_fmt=expected_fmt)

    @ddt.data([False, False],
              [True, True],
              [False, True])
    @ddt.unpack
    def test_get_volume_format_spec(self,
                                    volume_meta_contains_fmt,
                                    volume_type_contains_fmt):
        self._smbfs_driver.configuration = copy.copy(self._FAKE_SMBFS_CONFIG)

        fake_vol_meta_fmt = 'vhd'
        fake_vol_type_fmt = 'vhdx'

        volume_metadata = {}
        volume_type_extra_specs = {}

        if volume_meta_contains_fmt:
            volume_metadata['volume_format'] = fake_vol_meta_fmt
        elif volume_type_contains_fmt:
            volume_type_extra_specs['smbfs:volume_format'] = fake_vol_type_fmt

        volume_type = fake_volume.fake_volume_type_obj(self.context)
        volume = fake_volume.fake_volume_obj(self.context)
        # Optional arguments are not set in _from_db_object,
        # so have to set explicitly here
        volume.volume_type = volume_type
        volume.metadata = volume_metadata
        # Same for extra_specs and VolumeType
        volume_type.extra_specs = volume_type_extra_specs

        resulted_fmt = self._smbfs_driver._get_volume_format_spec(volume)

        if volume_meta_contains_fmt:
            expected_fmt = fake_vol_meta_fmt
        elif volume_type_contains_fmt:
            expected_fmt = fake_vol_type_fmt
        else:
            expected_fmt = self._FAKE_SMBFS_CONFIG.smbfs_default_volume_format

        self.assertEqual(expected_fmt, resulted_fmt)

    @mock.patch.object(remotefs.RemoteFSSnapDriverDistributed,
                       'create_volume')
    def test_create_volume_base(self, mock_create_volume):
        self._smbfs_driver.create_volume(self.volume)
        mock_create_volume.assert_called_once_with(self.volume)

    @mock.patch('os.path.exists')
    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_get_vhd_type')
    def _test_create_volume(self, mock_get_vhd_type, mock_exists,
                            volume_exists=False, volume_format='vhdx'):
        mock_exists.return_value = volume_exists
        self._smbfs_driver.create_vhd = mock.MagicMock()
        fake_create = self._smbfs_driver._vhdutils.create_vhd
        self._smbfs_driver.get_volume_format = mock.Mock(
            return_value=volume_format)

        if volume_exists or volume_format not in ('vhd', 'vhdx'):
            self.assertRaises(exception.InvalidVolume,
                              self._smbfs_driver._do_create_volume,
                              self.volume)
        else:
            fake_vol_path = self._FAKE_VOLUME_PATH
            self._smbfs_driver._do_create_volume(self.volume)
            fake_create.assert_called_once_with(
                fake_vol_path, mock_get_vhd_type.return_value,
                max_internal_size=self.volume.size << 30,
                guid=self.volume.id)

    def test_create_volume(self):
        self._test_create_volume()

    def test_create_existing_volume(self):
        self._test_create_volume(True)

    def test_create_volume_invalid_volume(self):
        self._test_create_volume(volume_format="qcow")

    def test_delete_volume(self):
        drv = self._smbfs_driver
        fake_vol_info = self._FAKE_VOLUME_PATH + '.info'

        drv._ensure_share_mounted = mock.MagicMock()
        fake_ensure_mounted = drv._ensure_share_mounted

        drv._local_volume_dir = mock.Mock(
            return_value=self._FAKE_MNT_POINT)
        drv.get_active_image_from_info = mock.Mock(
            return_value=self._FAKE_VOLUME_NAME)
        drv._delete = mock.Mock()
        drv._local_path_volume_info = mock.Mock(
            return_value=fake_vol_info)

        with mock.patch('os.path.exists', lambda x: True):
            drv.delete_volume(self.volume)

            fake_ensure_mounted.assert_called_once_with(self._FAKE_SHARE)
            drv._delete.assert_any_call(
                self._FAKE_VOLUME_PATH)
            drv._delete.assert_any_call(fake_vol_info)

    def test_ensure_mounted(self):
        self._smbfs_driver.shares = {self._FAKE_SHARE: self._FAKE_SHARE_OPTS}

        self._smbfs_driver._ensure_share_mounted(self._FAKE_SHARE)
        self._smbfs_driver._remotefsclient.mount.assert_called_once_with(
            self._FAKE_SHARE, self._FAKE_SHARE_OPTS)

    def test_get_capacity_info(self):
        self._diskutils.get_disk_capacity.return_value = (
            self._FAKE_TOTAL_SIZE, self._FAKE_TOTAL_AVAILABLE)
        self._smbfs_driver._get_mount_point_for_share = mock.Mock(
            return_value=mock.sentinel.mnt_point)
        self._smbfs_driver._get_total_allocated = mock.Mock(
            return_value=self._FAKE_TOTAL_ALLOCATED)

        ret_val = self._smbfs_driver._get_capacity_info(self._FAKE_SHARE)
        expected_ret_val = [int(x) for x in [self._FAKE_TOTAL_SIZE,
                            self._FAKE_TOTAL_AVAILABLE,
                            self._FAKE_TOTAL_ALLOCATED]]
        self.assertEqual(expected_ret_val, ret_val)

        self._smbfs_driver._get_mount_point_for_share.assert_called_once_with(
            self._FAKE_SHARE)
        self._diskutils.get_disk_capacity.assert_called_once_with(
            mock.sentinel.mnt_point)
        self._smbfs_driver._get_total_allocated.assert_called_once_with(
            self._FAKE_SHARE)

    def _test_get_img_info(self, backing_file=None):
        self._smbfs_driver._vhdutils.get_vhd_parent_path.return_value = (
            backing_file)

        image_info = self._smbfs_driver._qemu_img_info(self._FAKE_VOLUME_PATH)
        self.assertEqual(self._FAKE_VOLUME_NAME,
                         image_info.image)
        backing_file_name = backing_file and os.path.basename(backing_file)
        self.assertEqual(backing_file_name, image_info.backing_file)

    def test_get_img_info_without_backing_file(self):
        self._test_get_img_info()

    def test_get_snapshot_info(self):
        self._test_get_img_info(self._FAKE_VOLUME_PATH)

    @ddt.data('attached', 'detached')
    def test_create_snapshot(self, attach_status):
        self.snapshot.volume.attach_status = attach_status
        self.snapshot.volume.save()

        self._smbfs_driver._vhdutils.create_differencing_vhd = (
            mock.Mock())
        self._smbfs_driver._local_volume_dir = mock.Mock(
            return_value=self._FAKE_MNT_POINT)

        fake_create_diff = (
            self._smbfs_driver._vhdutils.create_differencing_vhd)

        self._smbfs_driver._do_create_snapshot(
            self.snapshot,
            os.path.basename(self._FAKE_VOLUME_PATH),
            self._FAKE_SNAPSHOT_PATH)

        if attach_status != 'attached':
            fake_create_diff.assert_called_once_with(self._FAKE_SNAPSHOT_PATH,
                                                     self._FAKE_VOLUME_PATH)
        else:
            fake_create_diff.assert_not_called()

        self.assertEqual(os.path.basename(self._FAKE_VOLUME_PATH),
                         self.snapshot.metadata['backing_file'])
        # Ensure that the changes have been saved.
        self.assertFalse(bool(self.snapshot.obj_what_changed()))

    @mock.patch.object(smbfs.WindowsSmbfsDriver,
                       '_check_extend_volume_support')
    @mock.patch.object(smbfs.WindowsSmbfsDriver,
                       '_local_path_active_image')
    def test_extend_volume(self, mock_get_active_img,
                           mock_check_ext_support):
        volume = fake_volume.fake_volume_obj(self.context)
        new_size = volume.size + 1

        self._smbfs_driver.extend_volume(volume, new_size)

        mock_check_ext_support.assert_called_once_with(volume, new_size)
        mock_get_active_img.assert_called_once_with(volume)
        self._vhdutils.resize_vhd.assert_called_once_with(
            mock_get_active_img.return_value,
            new_size * units.Gi,
            is_file_max_size=False)

    @ddt.data({'snapshots_exist': True},
              {'vol_fmt': smbfs.WindowsSmbfsDriver._DISK_FORMAT_VHD,
               'snapshots_exist': True,
               'expected_exc': exception.InvalidVolume})
    @ddt.unpack
    @mock.patch.object(smbfs.WindowsSmbfsDriver,
                       'get_volume_format')
    @mock.patch.object(smbfs.WindowsSmbfsDriver,
                       '_snapshots_exist')
    def test_check_extend_support(self, mock_snapshots_exist,
                                  mock_get_volume_format,
                                  vol_fmt=None, snapshots_exist=False,
                                  share_eligible=True,
                                  expected_exc=None):
        vol_fmt = vol_fmt or self._smbfs_driver._DISK_FORMAT_VHDX

        volume = fake_volume.fake_volume_obj(
            self.context, provider_location='fake_provider_location')
        new_size = volume.size + 1

        mock_snapshots_exist.return_value = snapshots_exist
        mock_get_volume_format.return_value = vol_fmt

        if expected_exc:
            self.assertRaises(expected_exc,
                              self._smbfs_driver._check_extend_volume_support,
                              volume, new_size)
        else:
            self._smbfs_driver._check_extend_volume_support(volume, new_size)

            mock_get_volume_format.assert_called_once_with(volume)
            mock_snapshots_exist.assert_called_once_with(volume)

    @ddt.data({},
              {'delete_latest': True},
              {'attach_status': 'detached'},
              {'snap_info_contains_snap_id': False})
    @ddt.unpack
    @mock.patch.object(remotefs.RemoteFSSnapDriverDistributed,
                       '_delete_snapshot')
    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_local_volume_dir')
    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_local_path_volume_info')
    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_write_info_file')
    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_read_info_file')
    @mock.patch.object(smbfs.WindowsSmbfsDriver,
                       '_nova_assisted_vol_snap_delete')
    @mock.patch.object(smbfs.WindowsSmbfsDriver,
                       '_get_snapshot_by_backing_file')
    def test_delete_snapshot(self, mock_get_snap_by_backing_file,
                             mock_nova_assisted_snap_del,
                             mock_read_info_file, mock_write_info_file,
                             mock_local_path_volume_info,
                             mock_get_local_dir,
                             mock_remotefs_snap_delete,
                             attach_status='attached',
                             snap_info_contains_snap_id=True,
                             delete_latest=False):
        self.snapshot.volume.attach_status = attach_status
        self.snapshot.metadata['backing_file'] = os.path.basename(
            self._FAKE_VOLUME_PATH)
        higher_snapshot = self._simple_snapshot(id=None,
                                                volume=self.volume)

        fake_snap_file = 'snap_file'
        fake_snap_parent_path = os.path.join(self._FAKE_MNT_POINT,
                                             'snap_file_parent')
        active_img = 'active_img' if not delete_latest else fake_snap_file

        snap_info = dict(active=active_img)
        if snap_info_contains_snap_id:
            snap_info[self.snapshot.id] = fake_snap_file

        mock_get_snap_by_backing_file.return_value = (
            higher_snapshot if not delete_latest else None)
        mock_info_path = mock_local_path_volume_info.return_value
        mock_read_info_file.return_value = snap_info
        mock_get_local_dir.return_value = self._FAKE_MNT_POINT
        self._vhdutils.get_vhd_parent_path.return_value = (
            fake_snap_parent_path)

        expected_delete_info = {'file_to_merge': fake_snap_file,
                                'volume_id': self.snapshot.volume.id}

        self._smbfs_driver._delete_snapshot(self.snapshot)

        if attach_status != 'attached':
            mock_remotefs_snap_delete.assert_called_once_with(self.snapshot)
        elif snap_info_contains_snap_id:
            mock_local_path_volume_info.assert_called_once_with(
                self.snapshot.volume)
            mock_read_info_file.assert_called_once_with(
                mock_info_path, empty_if_missing=True)
            mock_nova_assisted_snap_del.assert_called_once_with(
                self.snapshot._context, self.snapshot, expected_delete_info)

            exp_merged_img_path = os.path.join(self._FAKE_MNT_POINT,
                                               fake_snap_file)
            self._smbfs_driver._delete.assert_called_once_with(
                exp_merged_img_path)

            if delete_latest:
                self._vhdutils.get_vhd_parent_path.assert_called_once_with(
                    exp_merged_img_path)
                exp_active = os.path.basename(fake_snap_parent_path)
            else:
                exp_active = active_img

            self.assertEqual(exp_active, snap_info['active'])
            self.assertNotIn(snap_info, self.snapshot.id)
            mock_write_info_file.assert_called_once_with(mock_info_path,
                                                         snap_info)

        if attach_status != 'attached' or not snap_info_contains_snap_id:
            mock_nova_assisted_snap_del.assert_not_called()
            mock_write_info_file.assert_not_called()

        if not delete_latest and snap_info_contains_snap_id:
            self.assertEqual(os.path.basename(self._FAKE_VOLUME_PATH),
                             higher_snapshot.metadata['backing_file'])
            self.assertFalse(bool(higher_snapshot.obj_what_changed()))

    @ddt.data(True, False)
    def test_get_snapshot_by_backing_file(self, metadata_set):
        backing_file = 'fake_backing_file'
        if metadata_set:
            self.snapshot.metadata['backing_file'] = backing_file
            self.snapshot.save()

        for idx in range(2):
            # We're adding a few other snapshots.
            self._simple_snapshot(id=None,
                                  volume=self.volume)

        snapshot = self._smbfs_driver._get_snapshot_by_backing_file(
            self.volume, backing_file)

        if metadata_set:
            self.assertEqual(self.snapshot.id, snapshot.id)
        else:
            self.assertIsNone(snapshot)

    @ddt.data(True, False)
    @mock.patch.object(remotefs.RemoteFSSnapDriverDistributed,
                       '_get_snapshot_backing_file')
    def test_get_snapshot_backing_file_md_set(self, md_set,
                                              remotefs_get_backing_file):
        backing_file = 'fake_backing_file'
        if md_set:
            self.snapshot.metadata['backing_file'] = backing_file

        ret_val = self._smbfs_driver._get_snapshot_backing_file(
            self.snapshot)

        # If the metadata is not set, we expect the super class method to
        # be used, which is supposed to query the image.
        if md_set:
            self.assertEqual(backing_file, ret_val)
        else:
            self.assertEqual(remotefs_get_backing_file.return_value,
                             ret_val)
            remotefs_get_backing_file.assert_called_once_with(
                self.snapshot)

    def test_create_volume_from_unavailable_snapshot(self):
        self.snapshot.status = fields.SnapshotStatus.ERROR
        self.assertRaises(
            exception.InvalidSnapshot,
            self._smbfs_driver.create_volume_from_snapshot,
            self.volume, self.snapshot)

    @ddt.data(True, False)
    def test_copy_volume_to_image(self, has_parent=False):
        drv = self._smbfs_driver

        volume = test_utils.create_volume(
            self._context, volume_type_id=fake.VOLUME_TYPE_ID,
            updated_at=self.updated_at)

        extra_specs = {
            'image_service:store_id': 'fake-store'
        }
        test_utils.create_volume_type(self._context.elevated(),
                                      id=fake.VOLUME_TYPE_ID, name="test_type",
                                      extra_specs=extra_specs)

        fake_image_meta = {'id': 'fake-image-id'}
        fake_img_format = self._smbfs_driver._DISK_FORMAT_VHDX

        if has_parent:
            fake_volume_path = self._FAKE_SNAPSHOT_PATH
            fake_parent_path = self._FAKE_VOLUME_PATH
        else:
            fake_volume_path = self._FAKE_VOLUME_PATH
            fake_parent_path = None

        fake_active_image = os.path.basename(fake_volume_path)

        drv.get_active_image_from_info = mock.Mock(
            return_value=fake_active_image)
        drv._local_volume_dir = mock.Mock(
            return_value=self._FAKE_MNT_POINT)
        drv.get_volume_format = mock.Mock(
            return_value=fake_img_format)
        drv._vhdutils.get_vhd_parent_path.return_value = (
            fake_parent_path)

        with mock.patch.object(image_utils, 'upload_volume') as (
                fake_upload_volume):
            drv.copy_volume_to_image(
                mock.sentinel.context, volume,
                mock.sentinel.image_service, fake_image_meta)

            if has_parent:
                fake_temp_image_name = '%s.temp_image.%s.%s' % (
                    volume.id,
                    fake_image_meta['id'],
                    fake_img_format)
                fake_temp_image_path = os.path.join(
                    self._FAKE_MNT_POINT,
                    fake_temp_image_name)
                fake_active_image_path = os.path.join(
                    self._FAKE_MNT_POINT,
                    fake_active_image)
                upload_path = fake_temp_image_path

                drv._vhdutils.convert_vhd.assert_called_once_with(
                    fake_active_image_path,
                    fake_temp_image_path)
                drv._delete.assert_called_once_with(
                    fake_temp_image_path)
            else:
                upload_path = fake_volume_path

            fake_upload_volume.assert_called_once_with(
                mock.sentinel.context, mock.sentinel.image_service,
                fake_image_meta, upload_path, volume_format=fake_img_format,
                store_id='fake-store', base_image_ref=None, compress=True,
                run_as_root=True)

    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_get_vhd_type')
    def test_copy_image_to_volume(self, mock_get_vhd_type):
        drv = self._smbfs_driver

        drv.get_volume_format = mock.Mock(
            return_value=mock.sentinel.volume_format)
        drv.local_path = mock.Mock(
            return_value=self._FAKE_VOLUME_PATH)
        drv.configuration = mock.MagicMock()
        drv.configuration.volume_dd_blocksize = mock.sentinel.block_size

        with mock.patch.object(image_utils,
                               'fetch_to_volume_format') as fake_fetch:
            drv.copy_image_to_volume(
                mock.sentinel.context, self.volume,
                mock.sentinel.image_service,
                mock.sentinel.image_id)
            fake_fetch.assert_called_once_with(
                mock.sentinel.context,
                mock.sentinel.image_service,
                mock.sentinel.image_id,
                self._FAKE_VOLUME_PATH, mock.sentinel.volume_format,
                mock.sentinel.block_size,
                mock_get_vhd_type.return_value,
                disable_sparse=False)
            drv._vhdutils.resize_vhd.assert_called_once_with(
                self._FAKE_VOLUME_PATH,
                self.volume.size * units.Gi,
                is_file_max_size=False)
            drv._vhdutils.set_vhd_guid.assert_called_once_with(
                self._FAKE_VOLUME_PATH,
                self.volume.id)

    @mock.patch.object(smbfs.WindowsSmbfsDriver, '_get_vhd_type')
    def test_copy_volume_from_snapshot(self, mock_get_vhd_type):
        drv = self._smbfs_driver

        drv._get_snapshot_backing_file = mock.Mock(
            return_value=self._FAKE_VOLUME_NAME)
        drv._local_volume_dir = mock.Mock(
            return_value=self._FAKE_MNT_POINT)
        drv.local_path = mock.Mock(
            return_value=mock.sentinel.new_volume_path)

        drv._copy_volume_from_snapshot(self.snapshot,
                                       self.volume, self.volume.size)

        drv._get_snapshot_backing_file.assert_called_once_with(
            self.snapshot)
        drv._delete.assert_called_once_with(mock.sentinel.new_volume_path)
        drv._vhdutils.convert_vhd.assert_called_once_with(
            self._FAKE_VOLUME_PATH,
            mock.sentinel.new_volume_path,
            vhd_type=mock_get_vhd_type.return_value)
        drv._vhdutils.set_vhd_guid.assert_called_once_with(
            mock.sentinel.new_volume_path,
            self.volume.id)
        drv._vhdutils.resize_vhd.assert_called_once_with(
            mock.sentinel.new_volume_path,
            self.volume.size * units.Gi,
            is_file_max_size=False)

    def test_copy_encrypted_volume_from_snapshot(self):
        # We expect an exception to be raised if an encryption
        # key is provided since we don't support encryted volumes
        # for the time being.
        self.assertRaises(exception.NotSupportedOperation,
                          self._smbfs_driver._copy_volume_from_snapshot,
                          self.snapshot, self.volume,
                          self.volume.size,
                          mock.sentinel.src_key,
                          mock.sentinel.dest_key)

    def test_rebase_img(self):
        drv = self._smbfs_driver
        drv._rebase_img(
            self._FAKE_SNAPSHOT_PATH,
            self._FAKE_VOLUME_NAME, 'vhdx')
        drv._vhdutils.reconnect_parent_vhd.assert_called_once_with(
            self._FAKE_SNAPSHOT_PATH, self._FAKE_VOLUME_PATH)

    def test_copy_volume_image(self):
        self._smbfs_driver._copy_volume_image(mock.sentinel.src,
                                              mock.sentinel.dest)
        self._smbfs_driver._pathutils.copy.assert_called_once_with(
            mock.sentinel.src, mock.sentinel.dest)

    def test_get_pool_name_from_share(self):
        self._smbfs_driver._pool_mappings = {
            mock.sentinel.share: mock.sentinel.pool}

        pool = self._smbfs_driver._get_pool_name_from_share(
            mock.sentinel.share)
        self.assertEqual(mock.sentinel.pool, pool)

    def test_get_share_from_pool_name(self):
        self._smbfs_driver._pool_mappings = {
            mock.sentinel.share: mock.sentinel.pool}

        share = self._smbfs_driver._get_share_from_pool_name(
            mock.sentinel.pool)
        self.assertEqual(mock.sentinel.share, share)

    def test_get_pool_name_from_share_exception(self):
        self._smbfs_driver._pool_mappings = {}

        self.assertRaises(smbfs.SmbfsException,
                          self._smbfs_driver._get_share_from_pool_name,
                          mock.sentinel.pool)

    def test_get_vhd_type(self):
        drv = self._smbfs_driver

        mock_type = drv._get_vhd_type(qemu_subformat=True)
        self.assertEqual(mock_type, 'dynamic')

        mock_type = drv._get_vhd_type(qemu_subformat=False)
        self.assertEqual(mock_type, 3)

        self._smbfs_driver.configuration.nas_volume_prov_type = (
            'thick')

        mock_type = drv._get_vhd_type(qemu_subformat=True)
        self.assertEqual(mock_type, 'fixed')

    def test_get_managed_vol_expected_path(self):
        self._vhdutils.get_vhd_format.return_value = 'vhdx'
        vol_location = dict(vol_local_path=mock.sentinel.image_path,
                            mountpoint=self._FAKE_MNT_POINT)

        path = self._smbfs_driver._get_managed_vol_expected_path(
            self.volume, vol_location)
        self.assertEqual(self._FAKE_VOLUME_PATH, path)

        self._vhdutils.get_vhd_format.assert_called_once_with(
            mock.sentinel.image_path)

    @mock.patch.object(remotefs.RemoteFSManageableVolumesMixin,
                       'manage_existing')
    def test_manage_existing(self, remotefs_manage):
        model_update = dict(provider_location=self._FAKE_SHARE)
        remotefs_manage.return_value = model_update
        self._smbfs_driver.local_path = mock.Mock(
            return_value=mock.sentinel.vol_path)

        # Let's make sure that the provider location gets set.
        # It's needed by self.local_path.
        self.volume.provider_location = None

        ret_val = self._smbfs_driver.manage_existing(
            self.volume, mock.sentinel.ref)

        self.assertEqual(model_update, ret_val)
        self.assertEqual(self._FAKE_SHARE, self.volume.provider_location)

        self._vhdutils.set_vhd_guid.assert_called_once_with(
            mock.sentinel.vol_path,
            self.volume.id)
        self._smbfs_driver.local_path.assert_called_once_with(self.volume)
        remotefs_manage.assert_called_once_with(self.volume, mock.sentinel.ref)
