# Copyright (C) 2015 OpenStack Foundation
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

"""Tests for db purge."""

import datetime
import uuid

from oslo_db import exception as db_exc
from oslo_db.sqlalchemy import utils as sqlalchemyutils
from oslo_utils import timeutils
from sqlalchemy.dialects import sqlite

from cinder import context
from cinder import db
from cinder.db.sqlalchemy import api as db_api
from cinder import exception
from cinder.tests.unit import test


class PurgeDeletedTest(test.TestCase):

    def setUp(self):
        super(PurgeDeletedTest, self).setUp()

        self.context = context.get_admin_context()

        # enable foreign keys
        self.engine = db_api.get_engine()
        if self.engine.url.get_dialect() == sqlite.dialect:
            with self.engine.connect() as conn:
                conn.connection.execute("PRAGMA foreign_keys = ON")

        self.volumes = sqlalchemyutils.get_table(
            self.engine, "volumes")
        # The volume_metadata table has a FK of volume_id
        self.vm = sqlalchemyutils.get_table(
            self.engine, "volume_metadata")

        self.vol_types = sqlalchemyutils.get_table(
            self.engine, "volume_types")
        # The volume_type_projects table has a FK of volume_type_id
        self.vol_type_proj = sqlalchemyutils.get_table(
            self.engine, "volume_type_projects")

        self.snapshots = sqlalchemyutils.get_table(
            self.engine, "snapshots")

        self.sm = sqlalchemyutils.get_table(
            self.engine, "snapshot_metadata")

        self.vgm = sqlalchemyutils.get_table(
            self.engine, "volume_glance_metadata")

        self.qos = sqlalchemyutils.get_table(
            self.engine, "quality_of_service_specs")

        self.uuidstrs = []
        for unused in range(6):
            self.uuidstrs.append(uuid.uuid4().hex)

        # Add 6 rows to table
        with db_api.main_context_manager.writer.using(self.context):
            for uuidstr in self.uuidstrs:
                ins_stmt = self.volumes.insert().values(id=uuidstr,
                                                        volume_type_id=uuidstr)
                self.context.session.execute(ins_stmt)
                ins_stmt = self.vm.insert().values(volume_id=uuidstr)
                self.context.session.execute(ins_stmt)
                ins_stmt = self.vgm.insert().values(
                    volume_id=uuidstr, key='image_name', value='test')
                self.context.session.execute(ins_stmt)

                ins_stmt = self.vol_types.insert().values(id=uuidstr)
                self.context.session.execute(ins_stmt)
                ins_stmt = self.vol_type_proj.insert().\
                    values(volume_type_id=uuidstr)
                self.context.session.execute(ins_stmt)

                ins_stmt = self.snapshots.insert().values(
                    id=uuidstr, volume_id=uuidstr,
                    volume_type_id=uuidstr)
                self.context.session.execute(ins_stmt)
                ins_stmt = self.sm.insert().values(snapshot_id=uuidstr)
                self.context.session.execute(ins_stmt)

                ins_stmt = self.vgm.insert().values(
                    snapshot_id=uuidstr, key='image_name', value='test')
                self.context.session.execute(ins_stmt)

                ins_stmt = self.qos.insert().values(
                    id=uuidstr, key='QoS_Specs_Name', value='test')
                self.context.session.execute(ins_stmt)

                ins_stmt = self.vol_types.insert().values(
                    id=uuid.uuid4().hex, qos_specs_id=uuidstr)
                self.context.session.execute(ins_stmt)

                ins_stmt = self.qos.insert().values(
                    id=uuid.uuid4().hex, specs_id=uuidstr, key='desc',
                    value='test')
                self.context.session.execute(ins_stmt)

        # Set 5 of them deleted
        # 2 are 60 days ago, 2 are 20 days ago, one is just now.
        now = timeutils.utcnow()
        old = timeutils.utcnow() - datetime.timedelta(days=20)
        older = timeutils.utcnow() - datetime.timedelta(days=60)

        make_vol_now = self.volumes.update().\
            where(self.volumes.c.id.in_(self.uuidstrs[0:1]))\
            .values(deleted_at=now, deleted=True)
        make_vol_old = self.volumes.update().\
            where(self.volumes.c.id.in_(self.uuidstrs[1:3]))\
            .values(deleted_at=old, deleted=True)
        make_vol_older = self.volumes.update().\
            where(self.volumes.c.id.in_(self.uuidstrs[4:6]))\
            .values(deleted_at=older, deleted=True)
        make_vol_meta_now = self.vm.update().\
            where(self.vm.c.volume_id.in_(self.uuidstrs[0:1]))\
            .values(deleted_at=now, deleted=True)
        make_vol_meta_old = self.vm.update().\
            where(self.vm.c.volume_id.in_(self.uuidstrs[1:3]))\
            .values(deleted_at=old, deleted=True)
        make_vol_meta_older = self.vm.update().\
            where(self.vm.c.volume_id.in_(self.uuidstrs[4:6]))\
            .values(deleted_at=older, deleted=True)

        make_vol_types_now = self.vol_types.update().\
            where(self.vol_types.c.id.in_(self.uuidstrs[0:1]))\
            .values(deleted_at=now, deleted=True)
        make_vol_types_old = self.vol_types.update().\
            where(self.vol_types.c.id.in_(self.uuidstrs[1:3]))\
            .values(deleted_at=old, deleted=True)
        make_vol_types_older = self.vol_types.update().\
            where(self.vol_types.c.id.in_(self.uuidstrs[4:6]))\
            .values(deleted_at=older, deleted=True)
        make_vol_type_proj_now = self.vol_type_proj.update().\
            where(self.vol_type_proj.c.volume_type_id.in_(self.uuidstrs[0:1]))\
            .values(deleted_at=now, deleted=True)
        make_vol_type_proj_old = self.vol_type_proj.update().\
            where(self.vol_type_proj.c.volume_type_id.in_(self.uuidstrs[1:3]))\
            .values(deleted_at=old, deleted=True)
        make_vol_type_proj_older = self.vol_type_proj.update().\
            where(self.vol_type_proj.c.volume_type_id.in_(self.uuidstrs[4:6]))\
            .values(deleted_at=older, deleted=True)

        make_snap_now = self.snapshots.update().\
            where(self.snapshots.c.id.in_(self.uuidstrs[0:1]))\
            .values(deleted_at=now, deleted=True)
        make_snap_old = self.snapshots.update().\
            where(self.snapshots.c.id.in_(self.uuidstrs[1:3]))\
            .values(deleted_at=old, deleted=True)
        make_snap_older = self.snapshots.update().\
            where(self.snapshots.c.id.in_(self.uuidstrs[4:6]))\
            .values(deleted_at=older, deleted=True)

        make_snap_meta_now = self.sm.update().\
            where(self.sm.c.snapshot_id.in_(self.uuidstrs[0:1]))\
            .values(deleted_at=now, deleted=True)
        make_snap_meta_old = self.sm.update().\
            where(self.sm.c.snapshot_id.in_(self.uuidstrs[1:3]))\
            .values(deleted_at=old, deleted=True)
        make_snap_meta_older = self.sm.update().\
            where(self.sm.c.snapshot_id.in_(self.uuidstrs[4:6]))\
            .values(deleted_at=older, deleted=True)

        make_vol_glance_meta_now = self.vgm.update().\
            where(self.vgm.c.volume_id.in_(self.uuidstrs[0:1]))\
            .values(deleted_at=now, deleted=True)
        make_vol_glance_meta_old = self.vgm.update().\
            where(self.vgm.c.volume_id.in_(self.uuidstrs[1:3]))\
            .values(deleted_at=old, deleted=True)
        make_vol_glance_meta_older = self.vgm.update().\
            where(self.vgm.c.volume_id.in_(self.uuidstrs[4:6]))\
            .values(deleted_at=older, deleted=True)
        make_snap_glance_meta_now = self.vgm.update().\
            where(self.vgm.c.snapshot_id.in_(self.uuidstrs[0:1]))\
            .values(deleted_at=now, deleted=True)
        make_snap_glance_meta_old = self.vgm.update().\
            where(self.vgm.c.snapshot_id.in_(self.uuidstrs[1:3]))\
            .values(deleted_at=old, deleted=True)
        make_snap_glance_meta_older = self.vgm.update().\
            where(self.vgm.c.snapshot_id.in_(self.uuidstrs[4:6]))\
            .values(deleted_at=older, deleted=True)

        make_qos_now = self.qos.update().where(
            self.qos.c.id.in_(self.uuidstrs[0:1])).values(deleted_at=now,
                                                          deleted=True)
        make_qos_old = self.qos.update().where(
            self.qos.c.id.in_(self.uuidstrs[1:3])).values(deleted_at=old,
                                                          deleted=True)
        make_qos_older = self.qos.update().where(
            self.qos.c.id.in_(self.uuidstrs[4:6])).values(deleted_at=older,
                                                          deleted=True)

        make_qos_child_record_now = self.qos.update().where(
            self.qos.c.specs_id.in_(self.uuidstrs[0:1])).values(
            deleted_at=now, deleted=True)
        make_qos_child_record_old = self.qos.update().where(
            self.qos.c.specs_id.in_(self.uuidstrs[1:3])).values(
            deleted_at=old, deleted=True)
        make_qos_child_record_older = self.qos.update().where(
            self.qos.c.specs_id.in_(self.uuidstrs[4:6])).values(
            deleted_at=older, deleted=True)

        make_vol_types1_now = self.vol_types.update().where(
            self.vol_types.c.qos_specs_id.in_(self.uuidstrs[0:1])).values(
            deleted_at=now, deleted=True)
        make_vol_types1_old = self.vol_types.update().where(
            self.vol_types.c.qos_specs_id.in_(self.uuidstrs[1:3])).values(
            deleted_at=old, deleted=True)
        make_vol_types1_older = self.vol_types.update().where(
            self.vol_types.c.qos_specs_id.in_(self.uuidstrs[4:6])).values(
            deleted_at=older, deleted=True)

        with db_api.main_context_manager.writer.using(self.context):
            self.context.session.execute(make_vol_now)
            self.context.session.execute(make_vol_old)
            self.context.session.execute(make_vol_older)
            self.context.session.execute(make_vol_meta_now)
            self.context.session.execute(make_vol_meta_old)
            self.context.session.execute(make_vol_meta_older)

            self.context.session.execute(make_vol_types_now)
            self.context.session.execute(make_vol_types_old)
            self.context.session.execute(make_vol_types_older)
            self.context.session.execute(make_vol_type_proj_now)
            self.context.session.execute(make_vol_type_proj_old)
            self.context.session.execute(make_vol_type_proj_older)

            self.context.session.execute(make_snap_now)
            self.context.session.execute(make_snap_old)
            self.context.session.execute(make_snap_older)
            self.context.session.execute(make_snap_meta_now)
            self.context.session.execute(make_snap_meta_old)
            self.context.session.execute(make_snap_meta_older)

            self.context.session.execute(make_vol_glance_meta_now)
            self.context.session.execute(make_vol_glance_meta_old)
            self.context.session.execute(make_vol_glance_meta_older)
            self.context.session.execute(make_snap_glance_meta_now)
            self.context.session.execute(make_snap_glance_meta_old)
            self.context.session.execute(make_snap_glance_meta_older)

            self.context.session.execute(make_qos_now)
            self.context.session.execute(make_qos_old)
            self.context.session.execute(make_qos_older)

            self.context.session.execute(make_qos_child_record_now)
            self.context.session.execute(make_qos_child_record_old)
            self.context.session.execute(make_qos_child_record_older)

            self.context.session.execute(make_vol_types1_now)
            self.context.session.execute(make_vol_types1_old)
            self.context.session.execute(make_vol_types1_older)

    def test_purge_deleted_rows_in_zero_age_in(self):
        # Purge at age_in_days=0, should delete one more row
        db.purge_deleted_rows(self.context, age_in_days=0)

        with db_api.main_context_manager.writer.using(self.context):
            vol_rows = self.context.session.query(self.volumes).count()
            vol_meta_rows = self.context.session.query(self.vm).count()
            vol_type_rows = self.context.session.query(self.vol_types).count()
            vol_type_proj_rows = self.context.session.query(
                self.vol_type_proj,
            ).count()
            snap_rows = self.context.session.query(self.snapshots).count()
            snap_meta_rows = self.context.session.query(self.sm).count()
            vol_glance_meta_rows = self.context.session.query(self.vgm).count()
            qos_rows = self.context.session.query(self.qos).count()

        # Verify that we only have 1 rows now
        self.assertEqual(1, vol_rows)
        self.assertEqual(1, vol_meta_rows)
        self.assertEqual(3, vol_type_rows)
        self.assertEqual(1, vol_type_proj_rows)
        self.assertEqual(1, snap_rows)
        self.assertEqual(1, snap_meta_rows)
        self.assertEqual(2, vol_glance_meta_rows)
        self.assertEqual(2, qos_rows)

    def test_purge_deleted_rows_old(self):
        # Purge at 30 days old, should only delete 2 rows
        db.purge_deleted_rows(self.context, age_in_days=30)

        with db_api.main_context_manager.writer.using(self.context):
            vol_rows = self.context.session.query(self.volumes).count()
            vol_meta_rows = self.context.session.query(self.vm).count()
            vol_type_rows = self.context.session.query(self.vol_types).count()
            vol_type_proj_rows = self.context.session.query(
                self.vol_type_proj,
            ).count()
            snap_rows = self.context.session.query(self.snapshots).count()
            snap_meta_rows = self.context.session.query(self.sm).count()
            vol_glance_meta_rows = self.context.session.query(self.vgm).count()
            qos_rows = self.context.session.query(self.qos).count()

        # Verify that we only deleted 2
        self.assertEqual(4, vol_rows)
        self.assertEqual(4, vol_meta_rows)
        self.assertEqual(9, vol_type_rows)
        self.assertEqual(4, vol_type_proj_rows)
        self.assertEqual(4, snap_rows)
        self.assertEqual(4, snap_meta_rows)
        self.assertEqual(8, vol_glance_meta_rows)
        self.assertEqual(8, qos_rows)

    def test_purge_deleted_rows_older(self):
        # Purge at 10 days old now, should delete 2 more rows
        db.purge_deleted_rows(self.context, age_in_days=10)

        with db_api.main_context_manager.writer.using(self.context):
            vol_rows = self.context.session.query(self.volumes).count()
            vol_meta_rows = self.context.session.query(self.vm).count()
            vol_type_rows = self.context.session.query(self.vol_types).count()
            vol_type_proj_rows = self.context.session.query(
                self.vol_type_proj,
            ).count()
            snap_rows = self.context.session.query(self.snapshots).count()
            snap_meta_rows = self.context.session.query(self.sm).count()
            vol_glance_meta_rows = self.context.session.query(self.vgm).count()
            qos_rows = self.context.session.query(self.qos).count()

        # Verify that we only have 2 rows now
        self.assertEqual(2, vol_rows)
        self.assertEqual(2, vol_meta_rows)
        self.assertEqual(5, vol_type_rows)
        self.assertEqual(2, vol_type_proj_rows)
        self.assertEqual(2, snap_rows)
        self.assertEqual(2, snap_meta_rows)
        self.assertEqual(4, vol_glance_meta_rows)
        self.assertEqual(4, qos_rows)

    def test_purge_deleted_rows_bad_args(self):
        # Test with no age argument
        self.assertRaises(TypeError, db.purge_deleted_rows, self.context)
        # Test purge with non-integer
        self.assertRaises(exception.InvalidParameterValue,
                          db.purge_deleted_rows, self.context,
                          age_in_days='ten')

    def test_purge_deleted_rows_integrity_failure(self):
        # add new entry in volume and volume_admin_metadata for
        # integrity check
        uuid_str = uuid.uuid4().hex
        ins_stmt = self.volumes.insert().values(id=uuid_str,
                                                volume_type_id=uuid_str)
        with db_api.main_context_manager.writer.using(self.context):
            self.context.session.execute(ins_stmt)
        ins_stmt = self.vm.insert().values(volume_id=uuid_str)
        with db_api.main_context_manager.writer.using(self.context):
            self.context.session.execute(ins_stmt)

        # set volume record to deleted 20 days ago
        old = timeutils.utcnow() - datetime.timedelta(days=20)
        make_old = self.volumes.update().where(
            self.volumes.c.id.in_([uuid_str])).values(deleted_at=old,
                                                      deleted=True)
        with db_api.main_context_manager.writer.using(self.context):
            self.context.session.execute(make_old)

        # Verify that purge_deleted_rows fails due to Foreign Key constraint
        self.assertRaises(db_exc.DBReferenceError, db.purge_deleted_rows,
                          self.context, age_in_days=10)
