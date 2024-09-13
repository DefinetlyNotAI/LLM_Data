# Copyright (c) 2015 Red Hat, Inc.
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
"""Tests for Posix backup driver."""

import builtins
import os
import shutil
import tempfile
from unittest import mock
import uuid

from cinder.backup.drivers import posix
from cinder.common import config
from cinder import context
from cinder import objects
from cinder.tests.unit import fake_constants as fake
from cinder.tests.unit import test

CONF = config.CONF

FAKE_FILE_SIZE = 52428800
FAKE_SHA_BLOCK_SIZE_BYTES = 1024
FAKE_BACKUP_ENABLE_PROGRESS_TIMER = True

FAKE_CONTAINER = 'fake/container'
FAKE_BACKUP_ID = fake.BACKUP_ID
FAKE_BACKUP_ID_PART1 = fake.BACKUP_ID[:2]
FAKE_BACKUP_ID_PART2 = fake.BACKUP_ID[2:4]
FAKE_BACKUP_ID_REST = fake.BACKUP_ID[4:]
FAKE_BACKUP = {'id': FAKE_BACKUP_ID, 'container': None}

UPDATED_CONTAINER_NAME = os.path.join(FAKE_BACKUP_ID_PART1,
                                      FAKE_BACKUP_ID_PART2,
                                      FAKE_BACKUP_ID)

FAKE_BACKUP_MOUNT_POINT_BASE = '/fake/mount-point-base'
FAKE_EXPORT_PATH = 'fake/export/path'

FAKE_BACKUP_POSIX_PATH = os.path.join(FAKE_BACKUP_MOUNT_POINT_BASE,
                                      FAKE_EXPORT_PATH)

FAKE_PREFIX = 'prefix-'
FAKE_CONTAINER_ENTRIES = [FAKE_PREFIX + 'one', FAKE_PREFIX + 'two', 'three']
EXPECTED_CONTAINER_ENTRIES = [FAKE_PREFIX + 'one', FAKE_PREFIX + 'two']
FAKE_OBJECT_NAME = 'fake-object-name'
FAKE_OBJECT_PATH = os.path.join(FAKE_BACKUP_POSIX_PATH, FAKE_CONTAINER,
                                FAKE_OBJECT_NAME)


class PosixBackupDriverTestCase(test.TestCase):

    def setUp(self):
        super(PosixBackupDriverTestCase, self).setUp()
        self.ctxt = context.get_admin_context()

        self.override_config('backup_file_size',
                             FAKE_FILE_SIZE)
        self.override_config('backup_sha_block_size_bytes',
                             FAKE_SHA_BLOCK_SIZE_BYTES)
        self.override_config('backup_enable_progress_timer',
                             FAKE_BACKUP_ENABLE_PROGRESS_TIMER)
        self.override_config('backup_posix_path',
                             FAKE_BACKUP_POSIX_PATH)
        self.mock_object(posix, 'LOG')

        self.driver = posix.PosixBackupDriver(self.ctxt)

    def test_init(self):
        drv = posix.PosixBackupDriver(self.ctxt)
        self.assertEqual(FAKE_BACKUP_POSIX_PATH,
                         drv.backup_path)

    def test_update_container_name_container_passed(self):
        result = self.driver.update_container_name(FAKE_BACKUP, FAKE_CONTAINER)

        self.assertEqual(FAKE_CONTAINER, result)

    def test_update_container_na_container_passed(self):
        result = self.driver.update_container_name(FAKE_BACKUP, None)

        self.assertEqual(UPDATED_CONTAINER_NAME, result)

    def test_put_container(self):
        self.mock_object(os.path, 'exists', return_value=False)
        self.mock_object(os, 'makedirs')
        self.mock_object(os, 'chmod')
        path = os.path.join(self.driver.backup_path, FAKE_CONTAINER)

        self.driver.put_container(FAKE_CONTAINER)

        os.path.exists.assert_called_once_with(path)
        os.makedirs.assert_called_once_with(path)
        os.chmod.assert_called_once_with(path, 0o770)

    def test_put_container_already_exists(self):
        self.mock_object(os.path, 'exists', return_value=True)
        self.mock_object(os, 'makedirs')
        self.mock_object(os, 'chmod')
        path = os.path.join(self.driver.backup_path, FAKE_CONTAINER)

        self.driver.put_container(FAKE_CONTAINER)

        os.path.exists.assert_called_once_with(path)
        self.assertEqual(0, os.makedirs.call_count)
        self.assertEqual(0, os.chmod.call_count)

    def test_put_container_exception(self):
        self.mock_object(os.path, 'exists', return_value=False)
        self.mock_object(os, 'makedirs', side_effect=OSError)
        self.mock_object(os, 'chmod')
        path = os.path.join(self.driver.backup_path, FAKE_CONTAINER)

        self.assertRaises(OSError, self.driver.put_container,
                          FAKE_CONTAINER)
        os.path.exists.assert_called_once_with(path)
        os.makedirs.assert_called_once_with(path)
        self.assertEqual(0, os.chmod.call_count)

    def test_get_container_entries(self):
        self.mock_object(os, 'listdir', return_value=FAKE_CONTAINER_ENTRIES)

        result = self.driver.get_container_entries(FAKE_CONTAINER, FAKE_PREFIX)

        self.assertEqual(EXPECTED_CONTAINER_ENTRIES, result)

    def test_get_container_entries_no_list(self):
        self.mock_object(os, 'listdir', return_value=[])

        result = self.driver.get_container_entries(FAKE_CONTAINER, FAKE_PREFIX)

        self.assertEqual([], result)

    def test_get_container_entries_no_match(self):
        self.mock_object(os, 'listdir', return_value=FAKE_CONTAINER_ENTRIES)

        result = self.driver.get_container_entries(FAKE_CONTAINER,
                                                   FAKE_PREFIX + 'garbage')

        self.assertEqual([], result)

    def test_get_object_writer(self):
        self.mock_object(builtins, 'open', mock.mock_open())
        self.mock_object(os, 'chmod')

        self.driver.get_object_writer(FAKE_CONTAINER, FAKE_OBJECT_NAME)

        os.chmod.assert_called_once_with(FAKE_OBJECT_PATH, 0o660)
        builtins.open.assert_called_once_with(FAKE_OBJECT_PATH, 'wb')

    def test_get_object_reader(self):
        self.mock_object(builtins, 'open', mock.mock_open())

        self.driver.get_object_reader(FAKE_CONTAINER, FAKE_OBJECT_NAME)

        builtins.open.assert_called_once_with(FAKE_OBJECT_PATH, 'rb')

    def test_delete_object(self):
        self.mock_object(os, 'remove')

        self.driver.delete_object(FAKE_CONTAINER, FAKE_OBJECT_NAME)

    @mock.patch.object(posix.timeutils, 'utcnow')
    def test_generate_object_name_prefix(self, utcnow_mock):
        timestamp = '20170518102205'
        utcnow_mock.return_value.strftime.return_value = timestamp
        backup = objects.Backup(self.ctxt, volume_id=fake.VOLUME_ID,
                                id=fake.BACKUP_ID)
        res = self.driver._generate_object_name_prefix(backup)
        expected = 'volume_%s_%s_backup_%s' % (backup.volume_id,
                                               timestamp,
                                               backup.id)
        self.assertEqual(expected, res)


class PosixBackupTestWithData(test.TestCase):

    def _create_volume_db_entry(self, display_name='test_volume',
                                display_description='this is a test volume',
                                status='backing-up',
                                previous_status='available',
                                size=1,
                                host='testhost',
                                encryption_key_id=None,
                                project_id=None):
        """Create a volume entry in the DB.

        Return the entry ID
        """
        vol = {}
        vol['size'] = size
        vol['host'] = host
        vol['user_id'] = fake.USER_ID
        vol['project_id'] = project_id or fake.PROJECT_ID
        vol['status'] = status
        vol['display_name'] = display_name
        vol['display_description'] = display_description
        vol['attach_status'] = objects.fields.VolumeAttachStatus.DETACHED
        vol['availability_zone'] = '1'
        vol['previous_status'] = previous_status
        vol['encryption_key_id'] = encryption_key_id
        vol['volume_type_id'] = fake.VOLUME_TYPE_ID
        volume = objects.Volume(context=self.ctxt, **vol)
        volume.create()
        return volume.id

    def _create_backup_db_entry(self, volume_id=str(uuid.uuid4()),
                                restore_volume_id=None,
                                display_name='test_backup',
                                display_description='this is a test backup',
                                container='volumebackups',
                                status=objects.fields.BackupStatus.CREATING,
                                size=1,
                                object_count=0,
                                project_id=str(uuid.uuid4()),
                                service=None,
                                temp_volume_id=None,
                                temp_snapshot_id=None,
                                snapshot_id=None,
                                metadata=None,
                                parent_id=None,
                                encryption_key_id=None):
        """Create a backup entry in the DB.

        Return the entry ID
        """
        kwargs = {}
        kwargs['volume_id'] = volume_id
        kwargs['restore_volume_id'] = restore_volume_id
        kwargs['user_id'] = str(uuid.uuid4())
        kwargs['project_id'] = project_id
        kwargs['host'] = 'testhost'
        kwargs['availability_zone'] = '1'
        kwargs['display_name'] = display_name
        kwargs['display_description'] = display_description
        kwargs['container'] = container
        kwargs['status'] = status
        kwargs['fail_reason'] = ''
        kwargs['service'] = service or CONF.backup_driver
        kwargs['snapshot_id'] = snapshot_id
        kwargs['parent_id'] = parent_id
        kwargs['size'] = size
        kwargs['object_count'] = object_count
        kwargs['temp_volume_id'] = temp_volume_id
        kwargs['temp_snapshot_id'] = temp_snapshot_id
        kwargs['metadata'] = metadata or {}
        kwargs['encryption_key_id'] = encryption_key_id
        backup = objects.Backup(context=self.ctxt, **kwargs)
        backup.create()
        return backup

    def setUp(self):
        super(PosixBackupTestWithData, self).setUp()

        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tempdir)

        backup_path = os.path.join(self.tempdir, "backup-dir")
        os.mkdir(backup_path)

        self.ctxt = context.get_admin_context()

        self.override_config('backup_file_size',
                             FAKE_FILE_SIZE)
        self.override_config('backup_sha_block_size_bytes',
                             FAKE_SHA_BLOCK_SIZE_BYTES)
        self.override_config('backup_enable_progress_timer',
                             FAKE_BACKUP_ENABLE_PROGRESS_TIMER)
        self.override_config('backup_posix_path', backup_path)
        self.mock_object(posix, 'LOG')

        self.driver = posix.PosixBackupDriver(self.ctxt)

        mock_volume_filename = "restore-volume"
        self.vol_path = os.path.join(self.tempdir, mock_volume_filename)

    def test_restore_backup_with_sparseness(self):
        """Test a sparse backup restoration."""

        vol_size = 1
        vol_id = self._create_volume_db_entry(status='restoring-backup',
                                              size=vol_size)

        chunk_size = 1024 * 1024

        obj_data = b'01234567890123456789'

        backup = self._create_backup_db_entry(
            volume_id=vol_id,
            status=objects.fields.BackupStatus.RESTORING)

        with tempfile.NamedTemporaryFile() as volume_file:

            # First, we create a fake volume with a hole. Although we know that
            # the driver only detects zeroes, we create a real file with a hole
            # as a way to future-proof this a little. Also, it's easier.
            # Miraclously, tmpfs supports files with actual holes.
            volume_file.seek(3 * chunk_size)
            volume_file.write(obj_data)

            # And then, we immediately run a backup on the fake volume.
            # We don't attempt to re-create the backup volume by hand.
            volume_file.seek(0)
            self.driver.backup(backup, volume_file)

        # Next, we restore, excercising the code under test.
        with open(self.vol_path, 'wb') as volume_file:
            self.driver.restore(backup, vol_id, volume_file, True)

        # Finally, we examine the fake volume into which we restored.
        with open(self.vol_path, 'rb') as volume_file:
            volume_file.seek(3 * chunk_size)
            question_data = volume_file.read(len(obj_data))

        self.assertEqual(obj_data, question_data)

        statb = os.stat(self.vol_path)
        self.assertLess(statb.st_blocks * 512, (3 * chunk_size + 512) / 512)
