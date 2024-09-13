# Copyright (c) 2015 Mirantis Inc.
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
from webob import exc

from manila.api.openstack import api_version_request as api_version
from manila.api.v2 import share_export_locations as export_locations
from manila.common import constants
from manila import context
from manila import db
from manila import exception
from manila import policy
from manila import test
from manila.tests.api import fakes
from manila.tests import db_utils


@ddt.ddt
class ShareExportLocationsAPITest(test.TestCase):

    def _get_request(self, version="2.9", use_admin_context=True):
        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/export_locations' % self.share_instance_id,
            version=version, use_admin_context=use_admin_context)
        return req

    def setUp(self):
        super(ShareExportLocationsAPITest, self).setUp()
        self.controller = (
            export_locations.ShareExportLocationController())
        self.resource_name = self.controller.resource_name
        self.ctxt = {
            'admin': context.RequestContext('admin', 'fake', True),
            'user': context.RequestContext('fake', 'fake'),
        }
        self.mock_policy_check = self.mock_object(
            policy, 'check_policy', mock.Mock(return_value=True))
        self.share = db_utils.create_share()
        self.share_instance_id = self.share.instance.id
        self.req = self._get_request()
        paths = ['fake1/1/', 'fake2/2', 'fake3/3']
        db.export_locations_update(
            self.ctxt['admin'], self.share_instance_id, paths, False)

    @ddt.data({'role': 'admin', 'version': '2.9'},
              {'role': 'user', 'version': '2.9'},
              {'role': 'admin', 'version': '2.13'},
              {'role': 'user', 'version': '2.13'})
    @ddt.unpack
    def test_list_and_show(self, role, version):

        summary_keys = ['id', 'path']
        admin_summary_keys = summary_keys + [
            'share_instance_id', 'is_admin_only']
        detail_keys = summary_keys + ['created_at', 'updated_at']
        admin_detail_keys = admin_summary_keys + ['created_at', 'updated_at']

        self._test_list_and_show(role, version, summary_keys, detail_keys,
                                 admin_summary_keys, admin_detail_keys)

    @ddt.data('admin', 'user')
    def test_list_and_show_with_preferred_flag(self, role):

        summary_keys = ['id', 'path', 'preferred']
        admin_summary_keys = summary_keys + [
            'share_instance_id', 'is_admin_only']
        detail_keys = summary_keys + ['created_at', 'updated_at']
        admin_detail_keys = admin_summary_keys + ['created_at', 'updated_at']

        self._test_list_and_show(role, '2.14', summary_keys, detail_keys,
                                 admin_summary_keys, admin_detail_keys)

    def _test_list_and_show(self, role, version, summary_keys, detail_keys,
                            admin_summary_keys, admin_detail_keys):

        req = self._get_request(version=version,
                                use_admin_context=(role == 'admin'))
        index_result = self.controller.index(req, self.share['id'])

        self.assertIn('export_locations', index_result)
        self.assertEqual(1, len(index_result))
        self.assertEqual(3, len(index_result['export_locations']))

        for index_el in index_result['export_locations']:
            self.assertIn('id', index_el)
            show_result = self.controller.show(
                req, self.share['id'], index_el['id'])
            self.assertIn('export_location', show_result)
            self.assertEqual(1, len(show_result))

            show_el = show_result['export_location']

            # Check summary keys in index result & detail keys in show result
            if role == 'admin':
                self.assertEqual(len(admin_summary_keys), len(index_el))
                for key in admin_summary_keys:
                    self.assertIn(key, index_el)
                self.assertEqual(len(admin_detail_keys), len(show_el))
                for key in admin_detail_keys:
                    self.assertIn(key, show_el)
            else:
                self.assertEqual(len(summary_keys), len(index_el))
                for key in summary_keys:
                    self.assertIn(key, index_el)
                self.assertEqual(len(detail_keys), len(show_el))
                for key in detail_keys:
                    self.assertIn(key, show_el)

            # Ensure keys common to index & show results have matching values
            for key in summary_keys:
                self.assertEqual(index_el[key], show_el[key])

    def test_list_export_locations_share_not_found(self):
        self.assertRaises(
            exc.HTTPNotFound,
            self.controller.index,
            self.req, 'inexistent_share_id',
        )

    def test_show_export_location_share_not_found(self):
        index_result = self.controller.index(self.req, self.share['id'])
        el_id = index_result['export_locations'][0]['id']
        self.assertRaises(
            exc.HTTPNotFound,
            self.controller.show,
            self.req, 'inexistent_share_id', el_id,
        )

    def test_show_export_location_not_found(self):
        self.assertRaises(
            exc.HTTPNotFound,
            self.controller.show,
            self.req, self.share['id'], 'inexistent_export_location',
        )

    def test_get_admin_export_location(self):
        el_data = {
            'path': '/admin/export/location',
            'is_admin_only': True,
            'metadata': {'foo': 'bar'},
        }
        db.export_locations_update(
            self.ctxt['admin'], self.share_instance_id, el_data, True)
        index_result = self.controller.index(self.req, self.share['id'])
        el_id = index_result['export_locations'][0]['id']

        # Not found for member
        member_req = self._get_request(use_admin_context=False)
        self.assertRaises(
            exc.HTTPForbidden,
            self.controller.show,
            member_req, self.share['id'], el_id,
        )

        # Ok for admin
        el = self.controller.show(self.req, self.share['id'], el_id)
        for k, v in el.items():
            self.assertEqual(v, el[k])

    @ddt.data(*set(('2.46', '2.47', api_version._MAX_API_VERSION)))
    def test_list_export_locations_replicated_share(self, version):
        """Test the export locations API changes between 2.46 and 2.47

        For API version <= 2.46, non-active replica export locations are
        included in the API response. They are not included in and beyond
        version 2.47.
        """
        # Setup data
        share = db_utils.create_share(
            replication_type=constants.REPLICATION_TYPE_READABLE,
            replica_state=constants.REPLICA_STATE_ACTIVE)
        active_replica_id = share.instance.id
        exports = [
            {'path': 'myshare.mydomain/active-replica-exp1',
             'is_admin_only': False},
            {'path': 'myshare.mydomain/active-replica-exp2',
             'is_admin_only': False},
        ]
        db.export_locations_update(
            self.ctxt['user'], active_replica_id, exports)

        # Replicas
        share_replica2 = db_utils.create_share_replica(
            share_id=share.id, replica_state=constants.REPLICA_STATE_IN_SYNC)
        share_replica3 = db_utils.create_share_replica(
            share_id=share.id,
            replica_state=constants.REPLICA_STATE_OUT_OF_SYNC)
        replica2_exports = [
            {'path': 'myshare.mydomain/insync-replica-exp',
             'is_admin_only': False}
        ]
        replica3_exports = [
            {'path': 'myshare.mydomain/outofsync-replica-exp',
             'is_admin_only': False}
        ]
        db.export_locations_update(
            self.ctxt['user'], share_replica2.id, replica2_exports)
        db.export_locations_update(
            self.ctxt['user'], share_replica3.id, replica3_exports)

        req = self._get_request(version=version)
        index_result = self.controller.index(req, share['id'])

        actual_paths = [el['path'] for el in index_result['export_locations']]
        if self.is_microversion_ge(version, '2.47'):
            self.assertEqual(2, len(index_result['export_locations']))
            self.assertNotIn(
                'myshare.mydomain/insync-replica-exp', actual_paths)
            self.assertNotIn(
                'myshare.mydomain/outofsync-replica-exp', actual_paths)
        else:
            self.assertEqual(4, len(index_result['export_locations']))
            self.assertIn('myshare.mydomain/insync-replica-exp', actual_paths)
            self.assertIn(
                'myshare.mydomain/outofsync-replica-exp', actual_paths)

    @ddt.data('1.0', '2.0', '2.8')
    def test_list_with_unsupported_version(self, version):
        self.assertRaises(
            exception.VersionNotFoundForAPIMethod,
            self.controller.index,
            self._get_request(version),
            self.share_instance_id,
        )

    @ddt.data('1.0', '2.0', '2.8')
    def test_show_with_unsupported_version(self, version):
        index_result = self.controller.index(self.req, self.share['id'])

        self.assertRaises(
            exception.VersionNotFoundForAPIMethod,
            self.controller.show,
            self._get_request(version),
            self.share['id'],
            index_result['export_locations'][0]['id']
        )

    def test_validate_metadata_for_update(self):
        index_result = self.controller.index(self.req, self.share['id'])
        el_id = index_result['export_locations'][0]['id']
        metadata = {"foo": "bar", "preferred": "False"}

        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/export_locations/%s/metadata' % (
                self.share_instance_id, el_id),
            version="2.87", use_admin_context=True)
        result = self.controller._validate_metadata_for_update(
            req, el_id, metadata)

        self.assertEqual(metadata, result)

    def test_validate_metadata_for_update_invalid(self):
        index_result = self.controller.index(self.req, self.share['id'])
        el_id = index_result['export_locations'][0]['id']
        metadata = {"foo": "bar", "preferred": "False"}

        self.mock_policy_check = self.mock_object(
            policy, 'check_policy', mock.Mock(
                side_effect=exception.PolicyNotAuthorized(
                    action="update_admin_only_metadata")))

        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/export_locations/%s/metadata' % (
                self.share_instance_id, el_id),
            version="2.87", use_admin_context=False)

        self.assertRaises(exc.HTTPForbidden,
                          self.controller._validate_metadata_for_update,
                          req, el_id, metadata)
        self.mock_policy_check.assert_called_once_with(
            req.environ['manila.context'], 'share_export_location',
            'update_admin_only_metadata')

    def test_create_metadata(self):
        index_result = self.controller.index(self.req, self.share['id'])
        el_id = index_result['export_locations'][0]['id']
        body = {'metadata': {'key1': 'val1', 'key2': 'val2'}}
        mock_validate = self.mock_object(
            self.controller, '_validate_metadata_for_update',
            mock.Mock(return_value=body['metadata']))
        mock_create = self.mock_object(
            self.controller, '_create_metadata',
            mock.Mock(return_value=body))

        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/export_locations/%s/metadata' % (
                self.share_instance_id, el_id),
            version="2.87", use_admin_context=True)

        res = self.controller.create_metadata(req, self.share['id'], el_id,
                                              body)
        self.assertEqual(body, res)
        mock_validate.assert_called_once_with(req, el_id, body['metadata'],
                                              delete=False)
        mock_create.assert_called_once_with(req, el_id, body)

    def test_update_all_metadata(self):
        index_result = self.controller.index(self.req, self.share['id'])
        el_id = index_result['export_locations'][0]['id']
        body = {'metadata': {'key1': 'val1', 'key2': 'val2'}}
        mock_validate = self.mock_object(
            self.controller, '_validate_metadata_for_update',
            mock.Mock(return_value=body['metadata']))
        mock_update = self.mock_object(
            self.controller, '_update_all_metadata',
            mock.Mock(return_value=body))

        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/export_locations/%s/metadata' % (
                self.share_instance_id, el_id),
            version="2.87", use_admin_context=True)

        res = self.controller.update_all_metadata(req, self.share['id'], el_id,
                                                  body)
        self.assertEqual(body, res)
        mock_validate.assert_called_once_with(req, el_id, body['metadata'])
        mock_update.assert_called_once_with(req, el_id, body)

    def test_delete_metadata(self):
        index_result = self.controller.index(self.req, self.share['id'])
        el_id = index_result['export_locations'][0]['id']
        mock_delete = self.mock_object(
            self.controller, '_delete_metadata', mock.Mock())

        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/export_locations/%s/metadata/fake_key' % (
                self.share_instance_id, el_id),
            version="2.87", use_admin_context=True)
        self.controller.delete_metadata(req, self.share['id'], el_id,
                                        'fake_key')
        mock_delete.assert_called_once_with(req, el_id, 'fake_key')
