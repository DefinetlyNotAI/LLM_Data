# Copyright 2012 OpenStack Foundation
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

from http import HTTPStatus
from unittest import mock

from oslo_serialization import jsonutils
import webob

from cinder import context
from cinder.objects import fields
from cinder.policies import snapshots as snap_policy
from cinder.tests.unit.api import fakes
from cinder.tests.unit import fake_constants as fake
from cinder.tests.unit import fake_snapshot
from cinder.tests.unit import fake_volume
from cinder.tests.unit import test


UUID1 = fake.SNAPSHOT_ID
UUID2 = fake.SNAPSHOT2_ID


def _get_default_snapshot_param():
    return {'id': UUID1,
            'volume_id': fake.VOLUME_ID,
            'status': fields.SnapshotStatus.AVAILABLE,
            'volume_size': 100,
            'created_at': None,
            'display_name': 'Default name',
            'display_description': 'Default description',
            'project_id': fake.PROJECT_ID,
            'progress': '0%',
            'expected_attrs': ['metadata']}


def fake_snapshot_get(self, context, snapshot_id):
    param = _get_default_snapshot_param()
    return param


def fake_snapshot_get_all(self, context, search_opts=None):
    param = _get_default_snapshot_param()
    return [param]


class ExtendedSnapshotAttributesTest(test.TestCase):
    content_type = 'application/json'
    prefix = 'os-extended-snapshot-attributes:'

    def setUp(self):
        super(ExtendedSnapshotAttributesTest, self).setUp()
        self.user_ctxt = context.RequestContext(
            fake.USER_ID, fake.PROJECT_ID, auth_token=True)

    def _make_request(self, url):
        req = webob.Request.blank(url)
        req.headers['Accept'] = self.content_type
        res = req.get_response(fakes.wsgi_app(
            fake_auth_context=self.user_ctxt))
        return res

    def _get_snapshot(self, body):
        return jsonutils.loads(body).get('snapshot')

    def _get_snapshots(self, body):
        return jsonutils.loads(body).get('snapshots')

    def assertSnapshotAttributes(self, snapshot, project_id, progress):
        self.assertEqual(project_id,
                         snapshot.get('%sproject_id' % self.prefix))
        self.assertEqual(progress, snapshot.get('%sprogress' % self.prefix))

    @mock.patch('cinder.db.snapshot_metadata_get', return_value=dict())
    @mock.patch('cinder.objects.Volume.get_by_id')
    @mock.patch('cinder.objects.Snapshot.get_by_id')
    @mock.patch('cinder.context.RequestContext.authorize')
    def test_show(self, mock_authorize, snapshot_get_by_id, volume_get_by_id,
                  snapshot_metadata_get):
        ctx = context.RequestContext(fake.USER_ID, fake.PROJECT_ID,
                                     auth_token=True)
        snapshot = _get_default_snapshot_param()
        snapshot_obj = fake_snapshot.fake_snapshot_obj(ctx, **snapshot)
        fake_volume_obj = fake_volume.fake_volume_obj(ctx)
        mock_authorize.return_value = True
        snapshot_get_by_id.return_value = snapshot_obj
        volume_get_by_id.return_value = fake_volume_obj

        url = '/v3/%s/snapshots/%s' % (fake.PROJECT_ID, UUID1)
        res = self._make_request(url)

        self.assertEqual(HTTPStatus.OK, res.status_int)
        self.assertSnapshotAttributes(self._get_snapshot(res.body),
                                      project_id=fake.PROJECT_ID,
                                      progress='0%')
        calls = [mock.call(snap_policy.GET_POLICY, target_obj=snapshot_obj),
                 mock.call(snap_policy.EXTEND_ATTRIBUTE, fatal=False)]
        mock_authorize.assert_has_calls(calls)

    @mock.patch('cinder.context.RequestContext.authorize')
    def test_detail(self, mock_authorize):
        url = '/v3/%s/snapshots/detail' % fake.PROJECT_ID
        res = self._make_request(url)
        mock_authorize.return_value = False

        self.assertEqual(HTTPStatus.OK, res.status_int)
        for snapshot in self._get_snapshots(res.body):
            self.assertSnapshotAttributes(snapshot,
                                          project_id=fake.PROJECT_ID,
                                          progress='0%')
        calls = [mock.call(snap_policy.GET_ALL_POLICY), mock.call(
            snap_policy.EXTEND_ATTRIBUTE, fatal=False)]
        mock_authorize.assert_has_calls(calls)
