# Copyright (c) 2016 Hitachi Data Systems
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

from manila.api.v2 import share_snapshot_instance_export_locations as exp_loc
from manila.common import constants
from manila import context
from manila.db.sqlalchemy import api as db_api
from manila import exception
from manila import test
from manila.tests.api import fakes
from manila.tests import db_utils


@ddt.ddt
class ShareSnapshotInstanceExportLocationsAPITest(test.TestCase):

    def _get_request(self, version="2.32", use_admin_context=True):
        req = fakes.HTTPRequest.blank(
            '/v2/fake/snapshot-instances/%s/export-locations' %
            self.snapshot_instance['id'],
            version=version, use_admin_context=use_admin_context)
        return req

    def setUp(self):
        super(ShareSnapshotInstanceExportLocationsAPITest, self).setUp()
        self.controller = (
            exp_loc.ShareSnapshotInstanceExportLocationController())

        self.share = db_utils.create_share()
        self.snapshot = db_utils.create_snapshot(
            status=constants.STATUS_AVAILABLE,
            share_id=self.share['id'])
        self.snapshot_instance = db_utils.create_snapshot_instance(
            'fake_snapshot_id_1',
            status=constants.STATUS_CREATING,
            share_instance_id=self.share['instance']['id'])

        self.values = {
            'share_snapshot_instance_id': self.snapshot_instance['id'],
            'path': 'fake/user_path',
            'is_admin_only': True,
        }
        self.el = db_api.share_snapshot_instance_export_location_create(
            context.get_admin_context(), self.values)
        self.req = self._get_request()

    def test_index(self):
        self.mock_object(
            db_api, 'share_snapshot_instance_export_locations_get_all',
            mock.Mock(return_value=[self.el]))
        out = self.controller.index(self._get_request('2.32'),
                                    self.snapshot_instance['id'])

        values = {
            'share_snapshot_export_locations': [{
                'share_snapshot_instance_id': self.snapshot_instance['id'],
                'path': 'fake/user_path',
                'is_admin_only': True,
                'id': self.el['id'],
                'links': [{
                    'href': 'http://localhost/share/v2/fake/'
                            'share_snapshot_export_locations/' + self.el['id'],
                    'rel': 'self'
                }, {
                    'href': 'http://localhost/share/fake/'
                            'share_snapshot_export_locations/' + self.el['id'],
                    'rel': 'bookmark'
                }],
            }]
        }
        self.assertSubDictMatch(values, out)

    def test_show(self):
        out = self.controller.show(self._get_request('2.32'),
                                   self.snapshot_instance['id'],
                                   self.el['id'])

        self.assertSubDictMatch(
            {'share_snapshot_export_location': self.values}, out)

    @ddt.data('1.0', '2.0', '2.5', '2.8', '2.31')
    def test_list_with_unsupported_version(self, version):
        self.assertRaises(
            exception.VersionNotFoundForAPIMethod,
            self.controller.index,
            self._get_request(version),
            self.snapshot_instance['id'],
        )

    @ddt.data('1.0', '2.0', '2.5', '2.8', '2.31')
    def test_show_with_unsupported_version(self, version):
        self.assertRaises(
            exception.VersionNotFoundForAPIMethod,
            self.controller.show,
            self._get_request(version),
            self.snapshot['id'],
            self.el['id']
        )
