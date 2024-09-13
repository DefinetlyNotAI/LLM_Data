# Copyright (c) 2015 Mirantis inc.
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
import datetime
import itertools
from unittest import mock

import ddt
from oslo_config import cfg
from oslo_serialization import jsonutils
from oslo_utils import uuidutils
import webob
import webob.exc

from manila.api import common
from manila.api.openstack import api_version_request as api_version
from manila.api.v2 import share_replicas
from manila.api.v2 import shares
from manila.common import constants
from manila import context
from manila import db
from manila import exception
from manila import policy
from manila.share import api as share_api
from manila.share import share_types
from manila import test
from manila.tests.api.contrib import stubs
from manila.tests.api import fakes
from manila.tests import db_utils
from manila.tests import fake_share
from manila.tests import utils as test_utils
from manila import utils

CONF = cfg.CONF

LATEST_MICROVERSION = api_version._MAX_API_VERSION


@ddt.ddt
class ShareAPITest(test.TestCase):
    """Share API Test."""

    def setUp(self):
        super(ShareAPITest, self).setUp()
        self.controller = shares.ShareController()
        self.mock_object(db, 'availability_zone_get')
        self.mock_object(share_api.API, 'get_all',
                         stubs.stub_get_all_shares)
        self.mock_object(share_api.API, 'get',
                         stubs.stub_share_get)
        self.mock_object(share_api.API, 'update', stubs.stub_share_update)
        self.mock_object(share_api.API, 'delete', stubs.stub_share_delete)
        self.mock_object(share_api.API, 'soft_delete',
                         stubs.stub_share_soft_delete)
        self.mock_object(share_api.API, 'restore', stubs.stub_share_restore)
        self.mock_object(share_api.API, 'get_snapshot',
                         stubs.stub_snapshot_get)
        self.mock_object(share_types, 'get_share_type',
                         stubs.stub_share_type_get)
        self.maxDiff = None
        self.share = {
            "id": "1",
            "size": 100,
            "display_name": "Share Test Name",
            "display_description": "Share Test Desc",
            "share_proto": "fakeproto",
            "availability_zone": "zone1:host1",
            "is_public": False,
            "task_state": None
        }
        self.share_in_recycle_bin = {
            "id": "1",
            "size": 100,
            "display_name": "Share Test Name",
            "display_description": "Share Test Desc",
            "share_proto": "fakeproto",
            "availability_zone": "zone1:host1",
            "is_public": False,
            "task_state": None,
            "is_soft_deleted": True,
            "status": "available"
        }
        self.share_in_recycle_bin_is_deleting = {
            "id": "1",
            "size": 100,
            "display_name": "Share Test Name",
            "display_description": "Share Test Desc",
            "share_proto": "fakeproto",
            "availability_zone": "zone1:host1",
            "is_public": False,
            "task_state": None,
            "is_soft_deleted": True,
            "status": "deleting"
        }
        self.create_mock = mock.Mock(
            return_value=stubs.stub_share(
                '1',
                display_name=self.share['display_name'],
                display_description=self.share['display_description'],
                size=100,
                share_proto=self.share['share_proto'].upper(),
                instance={
                    'availability_zone': self.share['availability_zone'],
                })
        )
        self.vt = {
            'id': 'fake_volume_type_id',
            'name': 'fake_volume_type_name',
            'required_extra_specs': {
                'driver_handles_share_servers': 'False'
            },
            'extra_specs': {
                'driver_handles_share_servers': 'False'
            }
        }
        self.snapshot = {
            'id': '2',
            'share_id': '1',
            'status': constants.STATUS_AVAILABLE,
        }

        CONF.set_default("default_share_type", None)
        self.mock_object(policy, 'check_policy')

    def _process_expected_share_detailed_response(self, shr_dict, req_version):
        """Sets version based parameters on share dictionary."""

        share_dict = copy.deepcopy(shr_dict)
        changed_parameters = {
            '2.2': {'snapshot_support': True},
            '2.5': {'task_state': None},
            '2.6': {'share_type_name': None},
            '2.10': {'access_rules_status': constants.ACCESS_STATE_ACTIVE},
            '2.11': {'replication_type': None, 'has_replicas': False},
            '2.16': {'user_id': 'fakeuser'},
            '2.24': {'create_share_from_snapshot_support': True},
            '2.27': {'revert_to_snapshot_support': False},
            '2.31': {'share_group_id': None,
                     'source_share_group_snapshot_member_id': None},
            '2.32': {'mount_snapshot_support': False},
        }

        # Apply all the share transformations
        if self.is_microversion_ge(req_version, '2.9'):
            share_dict.pop('export_locations', None)
            share_dict.pop('export_location', None)

        for version, parameters in changed_parameters.items():
            for param, default in parameters.items():
                if self.is_microversion_ge(req_version, version):
                    share_dict[param] = share_dict.get(param, default)
                else:
                    share_dict.pop(param, None)

        return share_dict

    def _get_expected_share_detailed_response(self, values=None,
                                              admin=False, version='2.0'):
        share = {
            'id': '1',
            'name': 'displayname',
            'availability_zone': 'fakeaz',
            'description': 'displaydesc',
            'export_location': 'fake_location',
            'export_locations': ['fake_location', 'fake_location2'],
            'project_id': 'fakeproject',
            'created_at': datetime.datetime(1, 1, 1, 1, 1, 1),
            'share_proto': 'FAKEPROTO',
            'metadata': {},
            'size': 1,
            'snapshot_id': '2',
            'share_network_id': None,
            'status': 'fakestatus',
            'share_type': '1',
            'volume_type': '1',
            'snapshot_support': True,
            'is_public': False,
            'task_state': None,
            'share_type_name': None,
            'links': [
                {
                    'href': 'http://localhost/share/v2/fake/shares/1',
                    'rel': 'self'
                },
                {
                    'href': 'http://localhost/share/fake/shares/1',
                    'rel': 'bookmark'
                }
            ],
        }
        if values:
            if 'display_name' in values:
                values['name'] = values.pop('display_name')
            if 'display_description' in values:
                values['description'] = values.pop('display_description')
            share.update(values)
        if share.get('share_proto'):
            share['share_proto'] = share['share_proto'].upper()
        if admin:
            share['share_server_id'] = 'fake_share_server_id'
            share['host'] = 'fakehost'
        return {
            'share': self._process_expected_share_detailed_response(
                share, version)
        }

    def test__revert(self):

        share = copy.deepcopy(self.share)
        share['status'] = constants.STATUS_AVAILABLE
        share['revert_to_snapshot_support'] = True
        share["instances"] = [
            {
                "id": "fakeid",
                "access_rules_status": constants.ACCESS_STATE_ACTIVE,
            },
        ]
        share = fake_share.fake_share(**share)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['status'] = constants.STATUS_AVAILABLE
        body = {'revert': {'snapshot_id': '2'}}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      use_admin_context=False,
                                      version='2.27')
        mock_validate_revert_parameters = self.mock_object(
            self.controller, '_validate_revert_parameters',
            mock.Mock(return_value=body['revert']))
        mock_get = self.mock_object(
            share_api.API, 'get', mock.Mock(return_value=share))
        mock_get_snapshot = self.mock_object(
            share_api.API, 'get_snapshot', mock.Mock(return_value=snapshot))
        mock_get_latest_snapshot_for_share = self.mock_object(
            share_api.API, 'get_latest_snapshot_for_share',
            mock.Mock(return_value=snapshot))
        mock_revert_to_snapshot = self.mock_object(
            share_api.API, 'revert_to_snapshot')

        response = self.controller._revert(req, '1', body=body)

        self.assertEqual(202, response.status_int)
        mock_validate_revert_parameters.assert_called_once_with(
            utils.IsAMatcher(context.RequestContext), body)
        mock_get.assert_called_once_with(
            utils.IsAMatcher(context.RequestContext), '1')
        mock_get_snapshot.assert_called_once_with(
            utils.IsAMatcher(context.RequestContext), '2')
        mock_get_latest_snapshot_for_share.assert_called_once_with(
            utils.IsAMatcher(context.RequestContext), '1')
        mock_revert_to_snapshot.assert_called_once_with(
            utils.IsAMatcher(context.RequestContext), share, snapshot)

    def test__revert_share_has_been_soft_deleted(self):
        snapshot = copy.deepcopy(self.snapshot)
        body = {'revert': {'snapshot_id': '2'}}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      use_admin_context=False,
                                      version='2.27')
        self.mock_object(
            self.controller, '_validate_revert_parameters',
            mock.Mock(return_value=body['revert']))
        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=self.share_in_recycle_bin))
        self.mock_object(
            share_api.API, 'get_snapshot', mock.Mock(return_value=snapshot))
        self.assertRaises(
            webob.exc.HTTPForbidden, self.controller._revert,
            req, 1, body)

    def test__revert_not_supported(self):

        share = copy.deepcopy(self.share)
        share['revert_to_snapshot_support'] = False
        share = fake_share.fake_share(**share)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['status'] = constants.STATUS_AVAILABLE
        snapshot['share_id'] = 'wrong_id'
        body = {'revert': {'snapshot_id': '2'}}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      use_admin_context=False,
                                      version='2.27')
        self.mock_object(
            self.controller, '_validate_revert_parameters',
            mock.Mock(return_value=body['revert']))
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        self.mock_object(
            share_api.API, 'get_snapshot', mock.Mock(return_value=snapshot))

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller._revert,
                          req,
                          '1',
                          body=body)

    def test__revert_id_mismatch(self):

        share = copy.deepcopy(self.share)
        share['status'] = constants.STATUS_AVAILABLE
        share['revert_to_snapshot_support'] = True
        share = fake_share.fake_share(**share)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['status'] = constants.STATUS_AVAILABLE
        snapshot['share_id'] = 'wrong_id'
        body = {'revert': {'snapshot_id': '2'}}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      use_admin_context=False,
                                      version='2.27')
        self.mock_object(
            self.controller, '_validate_revert_parameters',
            mock.Mock(return_value=body['revert']))
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        self.mock_object(
            share_api.API, 'get_snapshot', mock.Mock(return_value=snapshot))

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller._revert,
                          req,
                          '1',
                          body=body)

    @ddt.data(
        {
            'share_status': constants.STATUS_ERROR,
            'share_is_busy': False,
            'snapshot_status': constants.STATUS_AVAILABLE,
        }, {
            'share_status': constants.STATUS_AVAILABLE,
            'share_is_busy': True,
            'snapshot_status': constants.STATUS_AVAILABLE,
        }, {
            'share_status': constants.STATUS_AVAILABLE,
            'share_is_busy': False,
            'snapshot_status': constants.STATUS_ERROR,
        })
    @ddt.unpack
    def test__revert_invalid_status(self, share_status, share_is_busy,
                                    snapshot_status):

        share = copy.deepcopy(self.share)
        share['status'] = share_status
        share['is_busy'] = share_is_busy
        share['revert_to_snapshot_support'] = True
        share = fake_share.fake_share(**share)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['status'] = snapshot_status
        body = {'revert': {'snapshot_id': '2'}}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      use_admin_context=False,
                                      version='2.27')
        self.mock_object(
            self.controller, '_validate_revert_parameters',
            mock.Mock(return_value=body['revert']))
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        self.mock_object(
            share_api.API, 'get_snapshot', mock.Mock(return_value=snapshot))

        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller._revert,
                          req,
                          '1',
                          body=body)

    def test__revert_snapshot_latest_not_found(self):

        share = copy.deepcopy(self.share)
        share['status'] = constants.STATUS_AVAILABLE
        share['revert_to_snapshot_support'] = True
        share = fake_share.fake_share(**share)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['status'] = constants.STATUS_AVAILABLE
        body = {'revert': {'snapshot_id': '2'}}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      use_admin_context=False,
                                      version='2.27')
        self.mock_object(
            self.controller, '_validate_revert_parameters',
            mock.Mock(return_value=body['revert']))
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        self.mock_object(
            share_api.API, 'get_snapshot', mock.Mock(return_value=snapshot))
        self.mock_object(
            share_api.API, 'get_latest_snapshot_for_share',
            mock.Mock(return_value=None))

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller._revert,
                          req,
                          '1',
                          body=body)

    def test__revert_snapshot_access_applying(self):

        share = copy.deepcopy(self.share)
        share['status'] = constants.STATUS_AVAILABLE
        share['revert_to_snapshot_support'] = True
        share["instances"] = [
            {
                "id": "fakeid",
                "access_rules_status": constants.SHARE_INSTANCE_RULES_SYNCING,
            },
        ]
        share = fake_share.fake_share(**share)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['status'] = constants.STATUS_AVAILABLE
        body = {'revert': {'snapshot_id': '2'}}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      use_admin_context=False,
                                      version='2.27')
        self.mock_object(
            self.controller, '_validate_revert_parameters',
            mock.Mock(return_value=body['revert']))
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        self.mock_object(share_api.API, 'get_snapshot',
                         mock.Mock(return_value=snapshot))
        self.mock_object(share_api.API, 'get_latest_snapshot_for_share',
                         mock.Mock(return_value=snapshot))
        self.mock_object(share_api.API, 'revert_to_snapshot')

        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller._revert,
                          req,
                          '1',
                          body=body)

    def test__revert_snapshot_not_latest(self):

        share = copy.deepcopy(self.share)
        share['status'] = constants.STATUS_AVAILABLE
        share['revert_to_snapshot_support'] = True
        share = fake_share.fake_share(**share)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['status'] = constants.STATUS_AVAILABLE
        latest_snapshot = copy.deepcopy(self.snapshot)
        latest_snapshot['status'] = constants.STATUS_AVAILABLE
        latest_snapshot['id'] = '3'
        body = {'revert': {'snapshot_id': '2'}}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      use_admin_context=False,
                                      version='2.27')
        self.mock_object(
            self.controller, '_validate_revert_parameters',
            mock.Mock(return_value=body['revert']))
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        self.mock_object(
            share_api.API, 'get_snapshot', mock.Mock(return_value=snapshot))
        self.mock_object(
            share_api.API, 'get_latest_snapshot_for_share',
            mock.Mock(return_value=latest_snapshot))

        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller._revert,
                          req,
                          '1',
                          body=body)

    @ddt.data(
        {
            'caught': exception.ShareNotFound,
            'exc_args': {
                'share_id': '1',
            },
            'thrown': webob.exc.HTTPNotFound,
        }, {
            'caught': exception.ShareSnapshotNotFound,
            'exc_args': {
                'snapshot_id': '2',
            },
            'thrown': webob.exc.HTTPBadRequest,
        }, {
            'caught': exception.ShareSizeExceedsAvailableQuota,
            'exc_args': {},
            'thrown': webob.exc.HTTPForbidden,
        }, {
            'caught': exception.ReplicationException,
            'exc_args': {
                'reason': 'catastrophic failure',
            },
            'thrown': webob.exc.HTTPBadRequest,
        })
    @ddt.unpack
    def test__revert_exception(self, caught, exc_args, thrown):

        body = {'revert': {'snapshot_id': '2'}}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      use_admin_context=False,
                                      version='2.27')
        self.mock_object(
            self.controller, '_validate_revert_parameters',
            mock.Mock(return_value=body['revert']))
        self.mock_object(
            share_api.API, 'get', mock.Mock(side_effect=caught(**exc_args)))

        self.assertRaises(thrown,
                          self.controller._revert,
                          req,
                          '1',
                          body=body)

    def test_validate_revert_parameters(self):

        body = {'revert': {'snapshot_id': 'fake_snapshot_id'}}

        result = self.controller._validate_revert_parameters(
            'fake_context', body)

        self.assertEqual(body['revert'], result)

    @ddt.data(
        None,
        {},
        {'manage': {'snapshot_id': 'fake_snapshot_id'}},
        {'revert': {'share_id': 'fake_snapshot_id'}},
        {'revert': {'snapshot_id': ''}},
    )
    def test_validate_revert_parameters_invalid(self, body):

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller._validate_revert_parameters,
                          'fake_context',
                          body)

    @ddt.data("2.0", "2.1")
    def test_share_create_original(self, microversion):
        self.mock_object(share_api.API, 'create', self.create_mock)
        body = {"share": copy.deepcopy(self.share)}
        req = fakes.HTTPRequest.blank('/v2/fake/shares', version=microversion)

        res_dict = self.controller.create(req, body)

        expected = self._get_expected_share_detailed_response(
            self.share, version=microversion)
        self.assertEqual(expected, res_dict)

    @ddt.data("2.2", "2.3")
    def test_share_create_with_snapshot_support_without_cg(self, microversion):
        self.mock_object(share_api.API, 'create', self.create_mock)
        body = {"share": copy.deepcopy(self.share)}
        req = fakes.HTTPRequest.blank('/v2/fake/shares', version=microversion)

        res_dict = self.controller.create(req, body)

        expected = self._get_expected_share_detailed_response(
            self.share, version=microversion)
        self.assertEqual(expected, res_dict)

    def test_share_create_with_share_group(self):
        self.mock_object(share_api.API, 'create', self.create_mock)
        body = {"share": copy.deepcopy(self.share)}
        req = fakes.HTTPRequest.blank('/v2/fake/shares', version="2.31",
                                      experimental=True)

        res_dict = self.controller.create(req, body)

        expected = self._get_expected_share_detailed_response(
            self.share, version="2.31")
        self.assertEqual(expected, res_dict)

    def test_share_create_with_sg_and_availability_zone(self):
        sg_id = 'fake_sg_id'
        az_id = 'bar_az_id'
        az_name = 'fake_name'
        self.mock_object(share_api.API, 'create', self.create_mock)
        self.mock_object(
            db, 'availability_zone_get',
            mock.Mock(return_value=type(
                'ReqAZ', (object, ), {"id": az_id, "name": az_name})))
        self.mock_object(
            db, 'share_group_get',
            mock.Mock(return_value={"availability_zone_id": az_id}))
        body = {"share": {
            "size": 100,
            "share_proto": "fakeproto",
            "availability_zone": az_id,
            "share_group_id": sg_id,
        }}
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares', version="2.31", experimental=True)

        self.controller.create(req, body)

        self.assertEqual(db.availability_zone_get.call_count, 2)
        db.availability_zone_get.assert_called_with(
            req.environ['manila.context'], az_id)
        db.share_group_get.assert_called_once_with(
            req.environ['manila.context'], sg_id)
        share_api.API.create.assert_called_once_with(
            req.environ['manila.context'],
            body['share']['share_proto'].upper(),
            body['share']['size'],
            None,
            None,
            share_group_id=body['share']['share_group_id'],
            is_public=False,
            metadata=None,
            snapshot_id=None,
            availability_zone=az_name,
            scheduler_hints=None)

    def test_share_create_with_sg_and_different_availability_zone(self):
        sg_id = 'fake_sg_id'
        sg_az = 'foo_az_id'
        req_az = 'bar_az_id'
        req_az_name = 'fake_az_name'
        self.mock_object(share_api.API, 'create', self.create_mock)
        self.mock_object(
            db, 'availability_zone_get',
            mock.Mock(return_value=type('ReqAZ', (object, ), {
                "id": req_az, "name": req_az_name})))
        self.mock_object(
            db, 'share_group_get',
            mock.Mock(return_value={"availability_zone_id": sg_az}))
        body = {"share": {
            "size": 100,
            "share_proto": "fakeproto",
            "availability_zone": req_az,
            "share_group_id": sg_id,
        }}
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares', version="2.31", experimental=True)

        self.assertRaises(
            exception.InvalidInput, self.controller.create, req, body)

        db.availability_zone_get.assert_called_once_with(
            req.environ['manila.context'], req_az)
        db.share_group_get.assert_called_once_with(
            req.environ['manila.context'], sg_id)
        self.assertEqual(0, share_api.API.create.call_count)

    def test_share_create_with_nonexistent_share_group(self):
        sg_id = 'fake_sg_id'
        self.mock_object(share_api.API, 'create', self.create_mock)
        self.mock_object(db, 'availability_zone_get')
        self.mock_object(
            db, 'share_group_get',
            mock.Mock(side_effect=exception.ShareGroupNotFound(
                share_group_id=sg_id)))
        body = {"share": {
            "size": 100,
            "share_proto": "fakeproto",
            "share_group_id": sg_id,
        }}
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares', version="2.31", experimental=True)

        self.assertRaises(
            webob.exc.HTTPNotFound, self.controller.create, req, body)

        self.assertEqual(0, db.availability_zone_get.call_count)
        self.assertEqual(0, share_api.API.create.call_count)
        db.share_group_get.assert_called_once_with(
            req.environ['manila.context'], sg_id)

    def test_share_create_with_valid_default_share_type(self):
        self.mock_object(share_types, 'get_share_type_by_name',
                         mock.Mock(return_value=self.vt))
        CONF.set_default("default_share_type", self.vt['name'])
        self.mock_object(share_api.API, 'create', self.create_mock)

        body = {"share": copy.deepcopy(self.share)}
        req = fakes.HTTPRequest.blank('/v2/fake/shares', version='2.7')
        res_dict = self.controller.create(req, body)

        expected = self._get_expected_share_detailed_response(self.share,
                                                              version='2.7')
        share_types.get_share_type_by_name.assert_called_once_with(
            utils.IsAMatcher(context.RequestContext), self.vt['name'])
        self.assertEqual(expected, res_dict)

    def test_share_create_with_invalid_default_share_type(self):
        self.mock_object(
            share_types, 'get_default_share_type',
            mock.Mock(side_effect=exception.ShareTypeNotFoundByName(
                self.vt['name'])),
        )
        CONF.set_default("default_share_type", self.vt['name'])
        req = fakes.HTTPRequest.blank('/v2/fake/shares', version='2.7')
        self.assertRaises(exception.ShareTypeNotFoundByName,
                          self.controller.create, req, {'share': self.share})
        share_types.get_default_share_type.assert_called_once_with()

    def test_share_create_with_replication(self):
        self.mock_object(share_api.API, 'create', self.create_mock)

        body = {"share": copy.deepcopy(self.share)}
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares',
            version=share_replicas.MIN_SUPPORTED_API_VERSION)

        res_dict = self.controller.create(req, body)

        expected = self._get_expected_share_detailed_response(
            self.share, version=share_replicas.MIN_SUPPORTED_API_VERSION)

        self.assertEqual(expected, res_dict)

    def test_share_create_with_share_net(self):
        shr = {
            "size": 100,
            "name": "Share Test Name",
            "description": "Share Test Desc",
            "share_proto": "fakeproto",
            "availability_zone": "zone1:host1",
            "share_network_id": "fakenetid"
        }
        fake_network = {'id': 'fakenetid'}
        share_net_subnets = [db_utils.create_share_network_subnet(
            id='fake_subnet_id', share_network_id=fake_network['id'])]
        create_mock = mock.Mock(return_value=stubs.stub_share('1',
                                display_name=shr['name'],
                                display_description=shr['description'],
                                size=shr['size'],
                                share_proto=shr['share_proto'].upper(),
                                availability_zone=shr['availability_zone'],
                                share_network_id=shr['share_network_id']))
        self.mock_object(share_api.API, 'create', create_mock)
        self.mock_object(share_api.API, 'get_share_network', mock.Mock(
            return_value=fake_network))
        self.mock_object(common, 'check_share_network_is_active',
                         mock.Mock(return_value=True))
        self.mock_object(
            db, 'share_network_subnets_get_all_by_availability_zone_id',
            mock.Mock(return_value=share_net_subnets))

        body = {"share": copy.deepcopy(shr)}
        req = fakes.HTTPRequest.blank('/v2/fake/shares', version='2.7')
        res_dict = self.controller.create(req, body)

        expected = self._get_expected_share_detailed_response(
            shr, version='2.7')
        self.assertDictEqual(expected, res_dict)
        # pylint: disable=unsubscriptable-object
        self.assertEqual("fakenetid",
                         create_mock.call_args[1]['share_network_id'])
        common.check_share_network_is_active.assert_called_once_with(
            fake_network)

    @ddt.data("2.15", "2.16")
    def test_share_create_original_with_user_id(self, microversion):
        self.mock_object(share_api.API, 'create', self.create_mock)
        body = {"share": copy.deepcopy(self.share)}
        req = fakes.HTTPRequest.blank('/v2/fake/shares', version=microversion)

        res_dict = self.controller.create(req, body)

        expected = self._get_expected_share_detailed_response(
            self.share, version=microversion)

        self.assertEqual(expected, res_dict)

    @ddt.data(test_utils.annotated('/v2.0_az_unsupported', ('2.0', False)),
              test_utils.annotated('/v2.0_az_supported', ('2.0', True)),
              test_utils.annotated('/v2.47_az_unsupported', ('2.47', False)),
              test_utils.annotated('/v2.47_az_supported', ('2.47', True)))
    @ddt.unpack
    def test_share_create_with_share_type_azs(self, version, az_supported):
        """For API version<2.48, AZ validation should not be performed."""
        self.mock_object(share_api.API, 'create', self.create_mock)
        create_args = copy.deepcopy(self.share)
        create_args['availability_zone'] = 'az1' if az_supported else 'az2'
        create_args['share_type'] = uuidutils.generate_uuid()
        stype_with_azs = copy.deepcopy(self.vt)
        stype_with_azs['extra_specs']['availability_zones'] = 'az1,az3'
        self.mock_object(share_types, 'get_share_type', mock.Mock(
            return_value=stype_with_azs))

        req = fakes.HTTPRequest.blank('/v2/fake/shares', version=version)

        res_dict = self.controller.create(req, {'share': create_args})

        expected = self._get_expected_share_detailed_response(
            values=self.share, version=version)

        self.assertEqual(expected, res_dict)

    @ddt.data(*set([
        test_utils.annotated('v2.48_share_from_snap', ('2.48', True)),
        test_utils.annotated('v2.48_share_not_from_snap', ('2.48', False)),
        test_utils.annotated('v%s_share_from_snap' % LATEST_MICROVERSION,
                             (LATEST_MICROVERSION, True)),
        test_utils.annotated('v%s_share_not_from_snap' % LATEST_MICROVERSION,
                             (LATEST_MICROVERSION, False))]))
    @ddt.unpack
    def test_share_create_az_not_in_share_type(self, version, snap):
        """For API version>=2.48, AZ validation should be performed."""
        self.mock_object(share_api.API, 'create', self.create_mock)
        create_args = copy.deepcopy(self.share)
        create_args['availability_zone'] = 'az2'
        create_args['share_type'] = (uuidutils.generate_uuid() if not snap
                                     else None)
        create_args['snapshot_id'] = (uuidutils.generate_uuid() if snap
                                      else None)
        stype_with_azs = copy.deepcopy(self.vt)
        stype_with_azs['extra_specs']['availability_zones'] = 'az1 , az3'
        self.mock_object(share_types, 'get_share_type', mock.Mock(
            return_value=stype_with_azs))
        self.mock_object(share_api.API, 'get_snapshot',
                         stubs.stub_snapshot_get)

        req = fakes.HTTPRequest.blank('/v2/fake/shares', version=version)

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.create,
                          req, {'share': create_args})
        share_api.API.create.assert_not_called()

    def test_migration_start(self):
        share = db_utils.create_share()
        share_network = db_utils.create_share_network()
        share_type = {'share_type_id': 'fake_type_id'}
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.29')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True
        context = req.environ['manila.context']

        self.mock_object(db, 'share_network_get', mock.Mock(
            return_value=share_network))
        self.mock_object(db, 'share_type_get', mock.Mock(
            return_value=share_type))

        body = {
            'migration_start': {
                'host': 'fake_host',
                'preserve_metadata': True,
                'preserve_snapshots': True,
                'writable': True,
                'nondisruptive': True,
                'new_share_network_id': 'fake_net_id',
                'new_share_type_id': 'fake_type_id',
            }
        }
        method = 'migration_start'

        self.mock_object(share_api.API, 'migration_start',
                         mock.Mock(return_value=202))
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))

        response = getattr(self.controller, method)(req, share['id'], body)

        self.assertEqual(202, response.status_int)

        share_api.API.get.assert_called_once_with(context, share['id'])
        share_api.API.migration_start.assert_called_once_with(
            context, share, 'fake_host', False, True, True, True, True,
            new_share_network=share_network, new_share_type=share_type)
        db.share_network_get.assert_called_once_with(
            context, 'fake_net_id')
        db.share_type_get.assert_called_once_with(
            context, 'fake_type_id')

    def test_migration_start_conflict(self):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'], use_admin_context=True)
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request = api_version.APIVersionRequest('2.29')
        req.api_version_request.experimental = True

        body = {
            'migration_start': {
                'host': 'fake_host',
                'preserve_metadata': True,
                'preserve_snapshots': True,
                'writable': True,
                'nondisruptive': True,
            }
        }

        self.mock_object(share_api.API, 'migration_start',
                         mock.Mock(side_effect=exception.Conflict(err='err')))

        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.migration_start,
                          req, share['id'], body)

    @ddt.data('nondisruptive', 'writable', 'preserve_metadata',
              'preserve_snapshots', 'host', 'body')
    def test_migration_start_missing_mandatory(self, param):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.29')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        body = {
            'migration_start': {
                'host': 'fake_host',
                'preserve_metadata': True,
                'preserve_snapshots': True,
                'writable': True,
                'nondisruptive': True,
            }
        }

        if param == 'body':
            body.pop('migration_start')
        else:
            body['migration_start'].pop(param)

        method = 'migration_start'

        self.mock_object(share_api.API, 'migration_start')
        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=share))

        self.assertRaises(webob.exc.HTTPBadRequest,
                          getattr(self.controller, method),
                          req, 'fake_id', body)

    @ddt.data('nondisruptive', 'writable', 'preserve_metadata',
              'preserve_snapshots', 'force_host_assisted_migration')
    def test_migration_start_non_boolean(self, param):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.29')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        body = {
            'migration_start': {
                'host': 'fake_host',
                'preserve_metadata': True,
                'preserve_snapshots': True,
                'writable': True,
                'nondisruptive': True,
            }
        }

        body['migration_start'][param] = None

        method = 'migration_start'

        self.mock_object(share_api.API, 'migration_start')
        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=share))

        self.assertRaises(webob.exc.HTTPBadRequest,
                          getattr(self.controller, method),
                          req, 'fake_id', body)

    def test_migration_start_no_share_id(self):
        req = fakes.HTTPRequest.blank('/v2/fake/shares/%s/action' % 'fake_id',
                                      use_admin_context=True, version='2.29')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        body = {'migration_start': {'host': 'fake_host'}}
        method = 'migration_start'

        self.mock_object(share_api.API, 'get',
                         mock.Mock(side_effect=[exception.NotFound]))
        self.assertRaises(webob.exc.HTTPNotFound,
                          getattr(self.controller, method),
                          req, 'fake_id', body)

    def test_migration_start_new_share_network_not_found(self):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.29')
        context = req.environ['manila.context']
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        body = {
            'migration_start': {
                'host': 'fake_host',
                'preserve_metadata': True,
                'preserve_snapshots': True,
                'writable': True,
                'nondisruptive': True,
                'new_share_network_id': 'nonexistent'}}

        self.mock_object(db, 'share_network_get',
                         mock.Mock(side_effect=exception.NotFound()))
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.migration_start,
                          req, share['id'], body)
        db.share_network_get.assert_called_once_with(context, 'nonexistent')

    def test_migration_start_new_share_type_not_found(self):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.29')
        context = req.environ['manila.context']
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        body = {
            'migration_start': {
                'host': 'fake_host',
                'preserve_metadata': True,
                'preserve_snapshots': True,
                'writable': True,
                'nondisruptive': True,
                'new_share_type_id': 'nonexistent'}}

        self.mock_object(db, 'share_type_get',
                         mock.Mock(side_effect=exception.NotFound()))
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.migration_start,
                          req, share['id'], body)
        db.share_type_get.assert_called_once_with(context, 'nonexistent')

    def test_migration_start_invalid_force_host_assisted_migration(self):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.29')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        body = {'migration_start': {'host': 'fake_host',
                                    'force_host_assisted_migration': 'fake'}}
        method = 'migration_start'

        self.assertRaises(webob.exc.HTTPBadRequest,
                          getattr(self.controller, method),
                          req, share['id'], body)

    @ddt.data('writable', 'preserve_metadata')
    def test_migration_start_invalid_writable_preserve_metadata(
            self, parameter):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.29')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        body = {'migration_start': {'host': 'fake_host',
                                    parameter: 'invalid'}}

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.migration_start, req, share['id'],
                          body)

    @ddt.data(constants.TASK_STATE_MIGRATION_ERROR, None)
    def test_reset_task_state(self, task_state):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.22')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        update = {'task_state': task_state}
        body = {'reset_task_state': update}

        self.mock_object(db, 'share_update')

        response = self.controller.reset_task_state(req, share['id'], body)

        self.assertEqual(202, response.status_int)

        db.share_update.assert_called_once_with(utils.IsAMatcher(
            context.RequestContext), share['id'], update)

    def test_reset_task_state_error_body(self):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.22')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        update = {'error': 'error'}
        body = {'reset_task_state': update}

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.reset_task_state, req, share['id'],
                          body)

    def test_reset_task_state_error_invalid(self):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.22')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        update = {'task_state': 'error'}
        body = {'reset_task_state': update}

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.reset_task_state, req, share['id'],
                          body)

    def test_reset_task_state_not_found(self):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.22')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        update = {'task_state': constants.TASK_STATE_MIGRATION_ERROR}
        body = {'reset_task_state': update}

        self.mock_object(share_api.API, 'get',
                         mock.Mock(side_effect=exception.NotFound))
        self.mock_object(db, 'share_update')

        self.assertRaises(exception.NotFound,
                          self.controller.reset_task_state, req, share['id'],
                          body)

        share_api.API.get.assert_called_once_with(utils.IsAMatcher(
            context.RequestContext), share['id'])
        db.share_update.assert_not_called()

    def test_reset_task_state_share_other_project_public_share(self):
        share = db_utils.create_share(is_public=True)
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True, version=LATEST_MICROVERSION)
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True
        update = {'task_state': constants.TASK_STATE_MIGRATION_ERROR}
        body = {'reset_task_state': update}

        # NOTE(gouthamr): we're testing a scenario where someone has access
        # to the RBAC rule share:reset_task_state, but doesn't own the share.
        # Ideally we'd override the default policy, but it's a shared
        # resource and we'll bleed into other tests, so we'll mock the
        # policy check to return False instead
        rbac_checks = [None, None, exception.NotAuthorized]
        with mock.patch.object(policy, 'check_policy',
                               side_effect=rbac_checks):
            self.mock_object(share_api.API, 'get',
                             mock.Mock(return_value=share))
            self.assertRaises(webob.exc.HTTPForbidden,
                              self.controller.reset_task_state,
                              req, share['id'], body)

    def test_reset_task_state_share_has_been_soft_deleted(self):
        share = self.share_in_recycle_bin
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.22')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True
        update = {'task_state': constants.TASK_STATE_MIGRATION_ERROR}
        body = {'reset_task_state': update}
        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=share))

        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.reset_task_state, req, share['id'],
                          body)

    def test_migration_complete(self):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.22')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        body = {'migration_complete': None}

        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=share))

        self.mock_object(share_api.API, 'migration_complete')

        response = self.controller.migration_complete(req, share['id'], body)

        self.assertEqual(202, response.status_int)

        share_api.API.migration_complete.assert_called_once_with(
            utils.IsAMatcher(context.RequestContext), share)

    def test_migration_complete_not_found(self):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.22')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        body = {'migration_complete': None}

        self.mock_object(share_api.API, 'get',
                         mock.Mock(side_effect=exception.NotFound()))
        self.mock_object(share_api.API, 'migration_complete')

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.migration_complete, req, share['id'],
                          body)

    def test_migration_cancel(self):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.22')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        body = {'migration_cancel': None}

        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=share))

        self.mock_object(share_api.API, 'migration_cancel')

        response = self.controller.migration_cancel(req, share['id'], body)

        self.assertEqual(202, response.status_int)

        share_api.API.migration_cancel.assert_called_once_with(
            utils.IsAMatcher(context.RequestContext), share)

    def test_migration_cancel_not_found(self):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.22')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        body = {'migration_cancel': None}

        self.mock_object(share_api.API, 'get',
                         mock.Mock(side_effect=exception.NotFound()))
        self.mock_object(share_api.API, 'migration_cancel')

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.migration_cancel, req, share['id'],
                          body)

    def test_migration_get_progress(self):
        share = db_utils.create_share(
            task_state=constants.TASK_STATE_MIGRATION_SUCCESS)
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.22')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        body = {'migration_get_progress': None}
        expected = {
            'total_progress': 'fake',
            'task_state': constants.TASK_STATE_MIGRATION_SUCCESS,
        }

        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=share))

        self.mock_object(share_api.API, 'migration_get_progress',
                         mock.Mock(return_value=copy.deepcopy(expected)))

        response = self.controller.migration_get_progress(req, share['id'],
                                                          body)

        self.assertEqual(expected, response)

        share_api.API.migration_get_progress.assert_called_once_with(
            utils.IsAMatcher(context.RequestContext), share)

    def test_migration_get_progress_not_found(self):
        share = db_utils.create_share()
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % share['id'],
            use_admin_context=True,
            version='2.22')
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.api_version_request.experimental = True

        body = {'migration_get_progress': None}

        self.mock_object(share_api.API, 'get',
                         mock.Mock(side_effect=exception.NotFound()))
        self.mock_object(share_api.API, 'migration_get_progress')

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.migration_get_progress, req,
                          share['id'], body)

    def test_share_create_from_snapshot_without_share_net_no_parent(self):
        shr = {
            "size": 100,
            "name": "Share Test Name",
            "description": "Share Test Desc",
            "share_proto": "fakeproto",
            "availability_zone": "zone1:host1",
            "snapshot_id": 333,
            "share_network_id": None,
        }
        create_mock = mock.Mock(return_value=stubs.stub_share('1',
                                display_name=shr['name'],
                                display_description=shr['description'],
                                size=shr['size'],
                                share_proto=shr['share_proto'].upper(),
                                snapshot_id=shr['snapshot_id'],
                                instance=dict(
                                    availability_zone=shr['availability_zone'],
                                    share_network_id=shr['share_network_id'])))
        self.mock_object(share_api.API, 'create', create_mock)
        body = {"share": copy.deepcopy(shr)}
        req = fakes.HTTPRequest.blank('/v2/fake/shares', version='2.7')

        res_dict = self.controller.create(req, body)

        expected = self._get_expected_share_detailed_response(
            shr, version='2.7')
        self.assertEqual(expected, res_dict)

    def test_share_create_from_snapshot_without_share_net_parent_exists(self):
        shr = {
            "size": 100,
            "name": "Share Test Name",
            "description": "Share Test Desc",
            "share_proto": "fakeproto",
            "availability_zone": "zone1:host1",
            "snapshot_id": 333,
            "share_network_id": None,
        }
        parent_share_net = 444
        fake_network = {'id': parent_share_net}
        share_net_subnets = [db_utils.create_share_network_subnet(
            id='fake_subnet_id', share_network_id=fake_network['id'])]
        create_mock = mock.Mock(return_value=stubs.stub_share('1',
                                display_name=shr['name'],
                                display_description=shr['description'],
                                size=shr['size'],
                                share_proto=shr['share_proto'].upper(),
                                snapshot_id=shr['snapshot_id'],
                                instance=dict(
                                    availability_zone=shr['availability_zone'],
                                    share_network_id=shr['share_network_id'])))
        self.mock_object(share_api.API, 'create', create_mock)
        self.mock_object(share_api.API, 'get_snapshot',
                         stubs.stub_snapshot_get)
        self.mock_object(common, 'check_share_network_is_active',
                         mock.Mock(return_value=True))
        parent_share = stubs.stub_share(
            '1', instance={'share_network_id': parent_share_net},
            create_share_from_snapshot_support=True)
        self.mock_object(share_api.API, 'get', mock.Mock(
            return_value=parent_share))
        self.mock_object(share_api.API, 'get_share_network', mock.Mock(
            return_value=fake_network))
        self.mock_object(
            db, 'share_network_subnets_get_all_by_availability_zone_id',
            mock.Mock(return_value=share_net_subnets))

        body = {"share": copy.deepcopy(shr)}
        req = fakes.HTTPRequest.blank('/v2/fake/shares', version='2.7')

        res_dict = self.controller.create(req, body)

        expected = self._get_expected_share_detailed_response(
            shr, version='2.7')
        self.assertEqual(expected, res_dict)
        # pylint: disable=unsubscriptable-object
        self.assertEqual(parent_share_net,
                         create_mock.call_args[1]['share_network_id'])
        common.check_share_network_is_active.assert_called_once_with(
            fake_network)

    def test_share_create_from_snapshot_with_share_net_equals_parent(self):
        parent_share_net = 444
        shr = {
            "size": 100,
            "name": "Share Test Name",
            "description": "Share Test Desc",
            "share_proto": "fakeproto",
            "availability_zone": "zone1:host1",
            "snapshot_id": 333,
            "share_network_id": parent_share_net,
        }
        share_net_subnets = [db_utils.create_share_network_subnet(
            id='fake_subnet_id', share_network_id=parent_share_net)]
        create_mock = mock.Mock(return_value=stubs.stub_share('1',
                                display_name=shr['name'],
                                display_description=shr['description'],
                                size=shr['size'],
                                share_proto=shr['share_proto'].upper(),
                                snapshot_id=shr['snapshot_id'],
                                instance=dict(
                                    availability_zone=shr['availability_zone'],
                                    share_network_id=shr['share_network_id'])))
        self.mock_object(share_api.API, 'create', create_mock)
        self.mock_object(share_api.API, 'get_snapshot',
                         stubs.stub_snapshot_get)
        parent_share = stubs.stub_share(
            '1', instance={'share_network_id': parent_share_net},
            create_share_from_snapshot_support=True)
        self.mock_object(share_api.API, 'get', mock.Mock(
            return_value=parent_share))
        self.mock_object(share_api.API, 'get_share_network', mock.Mock(
            return_value={'id': parent_share_net}))
        self.mock_object(common, 'check_share_network_is_active',
                         mock.Mock(return_value=True))
        self.mock_object(
            db, 'share_network_subnets_get_all_by_availability_zone_id',
            mock.Mock(return_value=share_net_subnets))

        body = {"share": copy.deepcopy(shr)}
        req = fakes.HTTPRequest.blank('/v2/fake/shares', version='2.7')
        res_dict = self.controller.create(req, body)
        expected = self._get_expected_share_detailed_response(
            shr, version='2.7')
        self.assertDictEqual(expected, res_dict)
        # pylint: disable=unsubscriptable-object
        self.assertEqual(parent_share_net,
                         create_mock.call_args[1]['share_network_id'])

    def test_share_create_from_snapshot_invalid_share_net(self):
        self.mock_object(share_api.API, 'create')
        shr = {
            "size": 100,
            "name": "Share Test Name",
            "description": "Share Test Desc",
            "share_proto": "fakeproto",
            "availability_zone": "zone1:host1",
            "snapshot_id": 333,
            "share_network_id": 1234,
        }
        body = {"share": shr}
        req = fakes.HTTPRequest.blank('/v2/fake/shares', version='2.7')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.create, req, body)

    def test_share_create_from_snapshot_not_supported(self):
        parent_share_net = 444
        self.mock_object(share_api.API, 'create')
        shr = {
            "size": 100,
            "name": "Share Test Name",
            "description": "Share Test Desc",
            "share_proto": "fakeproto",
            "availability_zone": "zone1:host1",
            "snapshot_id": 333,
            "share_network_id": parent_share_net,
        }
        parent_share = stubs.stub_share(
            '1', instance={'share_network_id': parent_share_net},
            create_share_from_snapshot_support=False)
        self.mock_object(share_api.API, 'get', mock.Mock(
            return_value=parent_share))
        self.mock_object(share_api.API, 'get_share_network', mock.Mock(
            return_value={'id': parent_share_net}))

        body = {"share": shr}
        req = fakes.HTTPRequest.blank('/shares', version='2.24')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.create, req, body)

    def test_share_creation_fails_with_bad_size(self):
        shr = {"size": '',
               "name": "Share Test Name",
               "description": "Share Test Desc",
               "share_proto": "fakeproto",
               "availability_zone": "zone1:host1"}
        body = {"share": shr}
        req = fakes.HTTPRequest.blank('/shares', version='2.7')
        self.assertRaises(exception.InvalidInput,
                          self.controller.create, req, body)

    def test_share_create_no_body(self):
        req = fakes.HTTPRequest.blank('/shares', version='2.7')
        self.assertRaises(webob.exc.HTTPUnprocessableEntity,
                          self.controller.create, req, {})

    def test_share_create_invalid_availability_zone(self):
        self.mock_object(
            db,
            'availability_zone_get',
            mock.Mock(side_effect=exception.AvailabilityZoneNotFound(id='id'))
        )
        body = {"share": copy.deepcopy(self.share)}

        req = fakes.HTTPRequest.blank('/v2/shares', version='2.7')
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.create,
                          req,
                          body)

    def test_share_show(self):
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1')
        expected = self._get_expected_share_detailed_response()

        res_dict = self.controller.show(req, '1')

        self.assertEqual(expected, res_dict)

    def test_share_show_with_share_group(self):
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/1', version='2.31', experimental=True)
        expected = self._get_expected_share_detailed_response(version='2.31')

        res_dict = self.controller.show(req, '1')

        self.assertDictEqual(expected, res_dict)

    def test_share_show_with_share_group_earlier_version(self):
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/1', version='2.23', experimental=True)
        expected = self._get_expected_share_detailed_response(version='2.23')

        res_dict = self.controller.show(req, '1')

        self.assertDictEqual(expected, res_dict)

    def test_share_show_with_share_type_name(self):
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1', version='2.6')

        res_dict = self.controller.show(req, '1')

        expected = self._get_expected_share_detailed_response(version='2.6')
        self.assertEqual(expected, res_dict)

    @ddt.data("2.15", "2.16")
    def test_share_show_with_user_id(self, microversion):
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1',
                                      version=microversion)

        res_dict = self.controller.show(req, '1')

        expected = self._get_expected_share_detailed_response(
            version=microversion)

        self.assertEqual(expected, res_dict)

    def test_share_show_admin(self):
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1',
                                      use_admin_context=True)
        expected = self._get_expected_share_detailed_response(admin=True)

        res_dict = self.controller.show(req, '1')

        self.assertEqual(expected, res_dict)

    def test_share_show_no_share(self):
        self.mock_object(share_api.API, 'get',
                         stubs.stub_share_get_notfound)
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1')
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.show,
                          req, '1')

    def test_share_show_with_replication_type(self):
        api_vers = share_replicas.MIN_SUPPORTED_API_VERSION
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1', version=api_vers)
        res_dict = self.controller.show(req, '1')

        expected = self._get_expected_share_detailed_response(version=api_vers)

        self.assertEqual(expected, res_dict)

    @ddt.data(('2.10', True), ('2.27', True), ('2.28', False))
    @ddt.unpack
    def test_share_show_access_rules_status_translated(self, version,
                                                       translated):
        share = db_utils.create_share(
            access_rules_status=constants.SHARE_INSTANCE_RULES_SYNCING,
            status=constants.STATUS_AVAILABLE)
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s' % share['id'], version=version)

        res_dict = self.controller.show(req, share['id'])

        expected = (constants.STATUS_OUT_OF_SYNC if translated else
                    constants.SHARE_INSTANCE_RULES_SYNCING)

        self.assertEqual(expected, res_dict['share']['access_rules_status'])

    def test_share_soft_delete(self):
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      version='2.69')
        body = {"soft_delete": None}
        resp = self.controller.share_soft_delete(req, 1, body)
        self.assertEqual(202, resp.status_int)

    def test_share_soft_delete_has_been_soft_deleted_already(self):
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      version='2.69')
        body = {"soft_delete": None}
        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=self.share_in_recycle_bin))
        self.mock_object(share_api.API, 'soft_delete',
                         mock.Mock(
                             side_effect=exception.InvalidShare(reason='err')))

        self.assertRaises(
            webob.exc.HTTPForbidden, self.controller.share_soft_delete,
            req, 1, body)

    def test_share_soft_delete_has_replicas(self):
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      version='2.69')
        body = {"soft_delete": None}
        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=self.share))
        self.mock_object(share_api.API, 'soft_delete',
                         mock.Mock(side_effect=exception.Conflict(err='err')))

        self.assertRaises(
            webob.exc.HTTPConflict, self.controller.share_soft_delete,
            req, 1, body)

    def test_share_restore(self):
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      version='2.69')
        body = {"restore": None}
        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=self.share_in_recycle_bin))
        resp = self.controller.share_restore(req, 1, body)
        self.assertEqual(202, resp.status_int)

    def test_share_restore_with_deleting_status(self):
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      version='2.69')
        body = {"restore": None}
        self.mock_object(
            share_api.API, 'get',
            mock.Mock(return_value=self.share_in_recycle_bin_is_deleting))
        self.assertRaises(
            webob.exc.HTTPForbidden, self.controller.share_restore,
            req, 1, body)

    def test_share_delete(self):
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1')
        resp = self.controller.delete(req, 1)
        self.assertEqual(202, resp.status_int)

    def test_share_delete_has_replicas(self):
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1')
        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=self.share))
        self.mock_object(share_api.API, 'delete',
                         mock.Mock(side_effect=exception.Conflict(err='err')))

        self.assertRaises(
            webob.exc.HTTPConflict, self.controller.delete, req, 1)

    def test_share_delete_in_share_group_param_not_provided(self):
        fake_share = stubs.stub_share('fake_share',
                                      share_group_id='fake_group_id')
        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=fake_share))
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.delete, req, 1)

    def test_share_delete_in_share_group(self):
        fake_share = stubs.stub_share('fake_share',
                                      share_group_id='fake_group_id')
        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=fake_share))
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/1?share_group_id=fake_group_id')
        resp = self.controller.delete(req, 1)
        self.assertEqual(202, resp.status_int)

    def test_share_delete_in_share_group_wrong_id(self):
        fake_share = stubs.stub_share('fake_share',
                                      share_group_id='fake_group_id')
        self.mock_object(share_api.API, 'get',
                         mock.Mock(return_value=fake_share))
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/1?share_group_id=not_fake_group_id')
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.delete, req, 1)

    def test_share_update(self):
        shr = self.share
        body = {"share": shr}

        req = fakes.HTTPRequest.blank('/v2/fake/share/1')
        res_dict = self.controller.update(req, 1, body)
        self.assertEqual(shr["display_name"], res_dict['share']["name"])
        self.assertEqual(shr["display_description"],
                         res_dict['share']["description"])
        self.assertEqual(shr['is_public'],
                         res_dict['share']['is_public'])

    def test_share_update_with_share_group(self):
        shr = self.share
        body = {"share": shr}

        req = fakes.HTTPRequest.blank(
            '/v2/fake/share/1', version="2.31", experimental=True)

        res_dict = self.controller.update(req, 1, body)

        self.assertIsNone(res_dict['share']["share_group_id"])
        self.assertIsNone(
            res_dict['share']["source_share_group_snapshot_member_id"])

    def test_share_not_updates_size(self):
        req = fakes.HTTPRequest.blank('/v2/fake/share/1')
        res_dict = self.controller.update(req, 1, {"share": self.share})
        self.assertNotEqual(res_dict['share']["size"], self.share["size"])

    def test_share_delete_no_share(self):
        self.mock_object(share_api.API, 'get',
                         stubs.stub_share_get_notfound)
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1')
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.delete,
                          req,
                          1)

    @ddt.data({'use_admin_context': False, 'version': '2.4'},
              {'use_admin_context': True, 'version': '2.4'},
              {'use_admin_context': True, 'version': '2.35'},
              {'use_admin_context': False, 'version': '2.35'},
              {'use_admin_context': True, 'version': '2.36'},
              {'use_admin_context': False, 'version': '2.36'},
              {'use_admin_context': True, 'version': '2.42'},
              {'use_admin_context': False, 'version': '2.42'},
              {'use_admin_context': False, 'version': '2.69'},
              {'use_admin_context': True, 'version': '2.69'})
    @ddt.unpack
    def test_share_list_summary_with_search_opts(self, use_admin_context,
                                                 version):
        search_opts = {
            'name': 'fake_name',
            'status': constants.STATUS_AVAILABLE,
            'share_server_id': 'fake_share_server_id',
            'share_type_id': 'fake_share_type_id',
            'snapshot_id': 'fake_snapshot_id',
            'share_network_id': 'fake_share_network_id',
            'metadata': '%7B%27k1%27%3A+%27v1%27%7D',  # serialized k1=v1
            'extra_specs': '%7B%27k2%27%3A+%27v2%27%7D',  # serialized k2=v2
            'sort_key': 'fake_sort_key',
            'sort_dir': 'fake_sort_dir',
            'limit': '1',
            'offset': '1',
            'is_public': 'False',
            'export_location_id': 'fake_export_location_id',
            'export_location_path': 'fake_export_location_path',
        }
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.36')):
            search_opts.update(
                {'display_name~': 'fake',
                 'display_description~': 'fake'})
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.69')):
            search_opts.update({'is_soft_deleted': True})
        method = 'get_all'
        shares = [
            {'id': 'id1', 'display_name': 'n1'},
            {'id': 'id2', 'display_name': 'n2'},
            {'id': 'id3', 'display_name': 'n3'},
        ]

        mock_action = {'return_value': [shares[1]]}
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.42')):
            search_opts.update({'with_count': 'true'})
            method = 'get_all_with_count'
            mock_action = {'side_effect': [(1, [shares[1]])]}
        if use_admin_context:
            search_opts['host'] = 'fake_host'
        # fake_key should be filtered for non-admin
        url = '/v2/fake/shares?fake_key=fake_value'
        for k, v in search_opts.items():
            url = url + '&' + k + '=' + str(v)
        req = fakes.HTTPRequest.blank(url, version=version,
                                      use_admin_context=use_admin_context)

        mock_get_all = (
            self.mock_object(share_api.API, method, mock.Mock(**mock_action)))

        result = self.controller.index(req)

        search_opts_expected = {
            'display_name': search_opts['name'],
            'status': search_opts['status'],
            'share_server_id': search_opts['share_server_id'],
            'share_type_id': search_opts['share_type_id'],
            'snapshot_id': search_opts['snapshot_id'],
            'share_network_id': search_opts['share_network_id'],
            'metadata': {'k1': 'v1'},
            'extra_specs': {'k2': 'v2'},
            'is_public': 'False',
            'limit': '1',
            'offset': '1'
        }
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.35')):
            search_opts_expected['export_location_id'] = (
                search_opts['export_location_id'])
            search_opts_expected['export_location_path'] = (
                search_opts['export_location_path'])
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.36')):
            search_opts_expected.update(
                {'display_name~': search_opts['display_name~'],
                 'display_description~': search_opts['display_description~']})
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.69')):
            search_opts_expected['is_soft_deleted'] = (
                search_opts['is_soft_deleted'])

        policy.check_policy.assert_called_once_with(
            req.environ['manila.context'],
            'share',
            'get_all')
        if use_admin_context:
            search_opts_expected.update({'fake_key': 'fake_value'})
            search_opts_expected['host'] = search_opts['host']
        mock_get_all.assert_called_once_with(
            req.environ['manila.context'],
            sort_key=search_opts['sort_key'],
            sort_dir=search_opts['sort_dir'],
            search_opts=search_opts_expected,
        )
        self.assertEqual(1, len(result['shares']))
        self.assertEqual(shares[1]['id'], result['shares'][0]['id'])
        self.assertEqual(
            shares[1]['display_name'], result['shares'][0]['name'])
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.42')):
            self.assertEqual(1, result['count'])

    @ddt.data({'use_admin_context': True, 'version': '2.42'},
              {'use_admin_context': False, 'version': '2.42'})
    @ddt.unpack
    def test_share_list_summary_with_search_opt_count_0(self,
                                                        use_admin_context,
                                                        version):
        search_opts = {
            'sort_key': 'fake_sort_key',
            'sort_dir': 'fake_sort_dir',
            'with_count': 'true'
        }
        if use_admin_context:
            search_opts['host'] = 'fake_host'
        # fake_key should be filtered
        url = '/v2/fake/shares?fake_key=fake_value'
        for k, v in search_opts.items():
            url = url + '&' + k + '=' + v
        req = fakes.HTTPRequest.blank(url, version=version,
                                      use_admin_context=use_admin_context)

        self.mock_object(share_api.API, 'get_all_with_count',
                         mock.Mock(side_effect=[(0, [])]))

        result = self.controller.index(req)

        search_opts_expected = {}

        policy.check_policy.assert_called_once_with(
            req.environ['manila.context'],
            'share',
            'get_all')
        if use_admin_context:
            search_opts_expected.update({'fake_key': 'fake_value'})
            search_opts_expected['host'] = search_opts['host']
        share_api.API.get_all_with_count.assert_called_once_with(
            req.environ['manila.context'],
            sort_key=search_opts['sort_key'],
            sort_dir=search_opts['sort_dir'],
            search_opts=search_opts_expected,
        )
        self.assertEqual(0, len(result['shares']))
        self.assertEqual(0, result['count'])

    def test_share_list_summary(self):
        self.mock_object(share_api.API, 'get_all',
                         stubs.stub_share_get_all_by_project)
        req = fakes.HTTPRequest.blank('/v2/fake/shares')
        res_dict = self.controller.index(req)
        expected = {
            'shares': [
                {
                    'name': 'displayname',
                    'id': '1',
                    'links': [
                        {
                            'href': 'http://localhost/share/v2/fake/shares/1',
                            'rel': 'self'
                        },
                        {
                            'href': 'http://localhost/share/fake/shares/1',
                            'rel': 'bookmark'
                        }
                    ],
                }
            ]
        }
        policy.check_policy.assert_called_once_with(
            req.environ['manila.context'],
            'share',
            'get_all')
        self.assertEqual(expected, res_dict)

    @ddt.data({'use_admin_context': False, 'version': '2.4'},
              {'use_admin_context': True, 'version': '2.4'},
              {'use_admin_context': True, 'version': '2.35'},
              {'use_admin_context': False, 'version': '2.35'},
              {'use_admin_context': True, 'version': '2.42'},
              {'use_admin_context': False, 'version': '2.42'},
              {'use_admin_context': True, 'version': '2.69'},
              {'use_admin_context': False, 'version': '2.69'})
    @ddt.unpack
    def test_share_list_detail_with_search_opts(self, use_admin_context,
                                                version):
        search_opts = {
            'name': 'fake_name',
            'status': constants.STATUS_AVAILABLE,
            'share_server_id': 'fake_share_server_id',
            'share_type_id': 'fake_share_type_id',
            'snapshot_id': 'fake_snapshot_id',
            'share_network_id': 'fake_share_network_id',
            'metadata': '%7B%27k1%27%3A+%27v1%27%7D',  # serialized k1=v1
            'extra_specs': '%7B%27k2%27%3A+%27v2%27%7D',  # serialized k2=v2
            'sort_key': 'fake_sort_key',
            'sort_dir': 'fake_sort_dir',
            'limit': '1',
            'offset': '1',
            'is_public': 'False',
            'export_location_id': 'fake_export_location_id',
            'export_location_path': 'fake_export_location_path',
        }
        shares = [
            {'id': 'id1', 'display_name': 'n1'},
            {
                'id': 'id2',
                'display_name': 'n2',
                'status': constants.STATUS_AVAILABLE,
                'snapshot_id': 'fake_snapshot_id',
                'instance': {
                    'host': 'fake_host',
                    'share_network_id': 'fake_share_network_id',
                    'share_type_id': 'fake_share_type_id',
                },
                'has_replicas': False,
                'is_soft_deleted': True,
                'scheduled_to_be_deleted_at': 'fake_datatime',
            },
            {'id': 'id3', 'display_name': 'n3'},
        ]

        method = 'get_all'
        mock_action = {'return_value': [shares[1]]}
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.42')):
            search_opts.update({'with_count': 'true'})
            method = 'get_all_with_count'
            mock_action = {'side_effect': [(1, [shares[1]])]}
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.69')):
            search_opts.update({'is_soft_deleted': True})
        if use_admin_context:
            search_opts['host'] = 'fake_host'
        # fake_key should be filtered for non-admin
        url = '/v2/fake/shares/detail?fake_key=fake_value'
        for k, v in search_opts.items():
            url = url + '&' + k + '=' + str(v)
        req = fakes.HTTPRequest.blank(url, version=version,
                                      use_admin_context=use_admin_context)

        mock_get_all = self.mock_object(share_api.API, method,
                                        mock.Mock(**mock_action))

        result = self.controller.detail(req)

        search_opts_expected = {
            'display_name': search_opts['name'],
            'status': search_opts['status'],
            'share_server_id': search_opts['share_server_id'],
            'share_type_id': search_opts['share_type_id'],
            'snapshot_id': search_opts['snapshot_id'],
            'share_network_id': search_opts['share_network_id'],
            'metadata': {'k1': 'v1'},
            'extra_specs': {'k2': 'v2'},
            'is_public': 'False',
            'limit': '1',
            'offset': '1'
        }

        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.35')):
            search_opts_expected['export_location_id'] = (
                search_opts['export_location_id'])
            search_opts_expected['export_location_path'] = (
                search_opts['export_location_path'])
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.69')):
            search_opts_expected['is_soft_deleted'] = (
                search_opts['is_soft_deleted'])
        if use_admin_context:
            search_opts_expected.update({'fake_key': 'fake_value'})
            search_opts_expected['host'] = search_opts['host']

        policy.check_policy.assert_called_once_with(
            req.environ['manila.context'],
            'share',
            'get_all')
        mock_get_all.assert_called_once_with(
            req.environ['manila.context'],
            sort_key=search_opts['sort_key'],
            sort_dir=search_opts['sort_dir'],
            search_opts=search_opts_expected,
        )
        self.assertEqual(1, len(result['shares']))
        self.assertEqual(shares[1]['id'], result['shares'][0]['id'])
        self.assertEqual(
            shares[1]['display_name'], result['shares'][0]['name'])
        self.assertEqual(
            shares[1]['snapshot_id'], result['shares'][0]['snapshot_id'])
        self.assertEqual(
            shares[1]['status'], result['shares'][0]['status'])
        self.assertEqual(
            shares[1]['instance']['share_type_id'],
            result['shares'][0]['share_type'])
        self.assertEqual(
            shares[1]['snapshot_id'], result['shares'][0]['snapshot_id'])
        if use_admin_context:
            self.assertEqual(
                shares[1]['instance']['host'], result['shares'][0]['host'])
        self.assertEqual(
            shares[1]['instance']['share_network_id'],
            result['shares'][0]['share_network_id'])
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.42')):
            self.assertEqual(1, result['count'])
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.69')):
            self.assertEqual(
                shares[1]['scheduled_to_be_deleted_at'],
                result['shares'][0]['scheduled_to_be_deleted_at'])

    def _list_detail_common_expected(self, admin=False):
        share_dict = {
            'status': 'fakestatus',
            'description': 'displaydesc',
            'export_location': 'fake_location',
            'export_locations': ['fake_location', 'fake_location2'],
            'availability_zone': 'fakeaz',
            'name': 'displayname',
            'share_proto': 'FAKEPROTO',
            'metadata': {},
            'project_id': 'fakeproject',
            'id': '1',
            'snapshot_id': '2',
            'snapshot_support': True,
            'share_network_id': None,
            'created_at': datetime.datetime(1, 1, 1, 1, 1, 1),
            'size': 1,
            'share_type': '1',
            'volume_type': '1',
            'is_public': False,
            'links': [
                {
                    'href': 'http://localhost/share/v2/fake/shares/1',
                    'rel': 'self'
                },
                {
                    'href': 'http://localhost/share/fake/shares/1',
                    'rel': 'bookmark'
                }
            ],
        }
        if admin:
            share_dict['host'] = 'fakehost'
        return {'shares': [share_dict]}

    def _list_detail_test_common(self, req, expected):
        self.mock_object(share_api.API, 'get_all',
                         stubs.stub_share_get_all_by_project)

        res_dict = self.controller.detail(req)

        policy.check_policy.assert_called_once_with(
            req.environ['manila.context'],
            'share',
            'get_all')
        self.assertDictListMatch(expected['shares'], res_dict['shares'])
        self.assertEqual(res_dict['shares'][0]['volume_type'],
                         res_dict['shares'][0]['share_type'])

    def test_share_list_detail(self):
        env = {'QUERY_STRING': 'name=Share+Test+Name'}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/detail', environ=env)
        expected = self._list_detail_common_expected()
        expected['shares'][0].pop('snapshot_support')
        self._list_detail_test_common(req, expected)

    def test_share_list_detail_with_share_group(self):
        env = {'QUERY_STRING': 'name=Share+Test+Name'}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/detail',
                                      environ=env,
                                      version="2.31",
                                      experimental=True)
        expected = self._list_detail_common_expected()
        expected['shares'][0]['task_state'] = None
        expected['shares'][0]['share_type_name'] = None
        expected['shares'][0].pop('export_location')
        expected['shares'][0].pop('export_locations')
        expected['shares'][0]['access_rules_status'] = 'active'
        expected['shares'][0]['replication_type'] = None
        expected['shares'][0]['has_replicas'] = False
        expected['shares'][0]['user_id'] = 'fakeuser'
        expected['shares'][0]['create_share_from_snapshot_support'] = True
        expected['shares'][0]['revert_to_snapshot_support'] = False
        expected['shares'][0]['share_group_id'] = None
        expected['shares'][0]['source_share_group_snapshot_member_id'] = None
        self._list_detail_test_common(req, expected)

    def test_share_list_detail_with_task_state(self):
        env = {'QUERY_STRING': 'name=Share+Test+Name'}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/detail', environ=env,
                                      version="2.5")
        expected = self._list_detail_common_expected()
        expected['shares'][0]['task_state'] = None
        self._list_detail_test_common(req, expected)

    def test_share_list_detail_without_export_locations(self):
        env = {'QUERY_STRING': 'name=Share+Test+Name'}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/detail', environ=env,
                                      version="2.9")
        expected = self._list_detail_common_expected()
        expected['shares'][0]['task_state'] = None
        expected['shares'][0]['share_type_name'] = None
        expected['shares'][0].pop('export_location')
        expected['shares'][0].pop('export_locations')
        self._list_detail_test_common(req, expected)

    def test_share_list_detail_with_replication_type(self):
        self.mock_object(share_api.API, 'get_all',
                         stubs.stub_share_get_all_by_project)
        env = {'QUERY_STRING': 'name=Share+Test+Name'}
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/detail', environ=env,
            version=share_replicas.MIN_SUPPORTED_API_VERSION)

        res_dict = self.controller.detail(req)

        policy.check_policy.assert_called_once_with(
            req.environ['manila.context'],
            'share',
            'get_all')
        expected = {
            'shares': [
                {
                    'status': 'fakestatus',
                    'description': 'displaydesc',
                    'availability_zone': 'fakeaz',
                    'name': 'displayname',
                    'share_proto': 'FAKEPROTO',
                    'metadata': {},
                    'project_id': 'fakeproject',
                    'access_rules_status': 'active',
                    'id': '1',
                    'snapshot_id': '2',
                    'share_network_id': None,
                    'created_at': datetime.datetime(1, 1, 1, 1, 1, 1),
                    'size': 1,
                    'share_type_name': None,
                    'share_type': '1',
                    'volume_type': '1',
                    'is_public': False,
                    'snapshot_support': True,
                    'has_replicas': False,
                    'replication_type': None,
                    'task_state': None,
                    'links': [
                        {
                            'href': 'http://localhost/share/v2/fake/shares/1',
                            'rel': 'self'
                        },
                        {
                            'href': 'http://localhost/share/fake/shares/1',
                            'rel': 'bookmark'
                        }
                    ],
                }
            ]
        }
        self.assertEqual(expected, res_dict)
        self.assertEqual(res_dict['shares'][0]['volume_type'],
                         res_dict['shares'][0]['share_type'])

    def test_remove_invalid_options(self):
        ctx = context.RequestContext('fakeuser', 'fakeproject', is_admin=False)
        search_opts = {'a': 'a', 'b': 'b', 'c': 'c', 'd': 'd'}
        expected_opts = {'a': 'a', 'c': 'c'}
        allowed_opts = ['a', 'c']
        common.remove_invalid_options(ctx, search_opts, allowed_opts)
        self.assertEqual(expected_opts, search_opts)

    def test_remove_invalid_options_admin(self):
        ctx = context.RequestContext('fakeuser', 'fakeproject', is_admin=True)
        search_opts = {'a': 'a', 'b': 'b', 'c': 'c', 'd': 'd'}
        expected_opts = {'a': 'a', 'b': 'b', 'c': 'c', 'd': 'd'}
        allowed_opts = ['a', 'c']
        common.remove_invalid_options(ctx, search_opts, allowed_opts)
        self.assertEqual(expected_opts, search_opts)

    def test_create_metadata(self):
        id = 'fake_share_id'
        body = {'metadata': {'key1': 'val1', 'key2': 'val2'}}
        mock_validate = self.mock_object(
            self.controller, '_validate_metadata_for_update',
            mock.Mock(return_value=body['metadata']))
        mock_create = self.mock_object(
            self.controller, '_create_metadata',
            mock.Mock(return_value=body))
        self.mock_object(share_api.API, 'update_share_from_metadata')

        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/metadata' % id)

        res = self.controller.create_metadata(req, id, body)
        self.assertEqual(body, res)
        mock_validate.assert_called_once_with(req, id, body['metadata'],
                                              delete=False)
        mock_create.assert_called_once_with(req, id, body)

    def test_update_all_metadata(self):
        id = 'fake_share_id'
        body = {'metadata': {'key1': 'val1', 'key2': 'val2'}}
        mock_validate = self.mock_object(
            self.controller, '_validate_metadata_for_update',
            mock.Mock(return_value=body['metadata']))
        mock_update = self.mock_object(
            self.controller, '_update_all_metadata',
            mock.Mock(return_value=body))
        self.mock_object(share_api.API, 'update_share_from_metadata')

        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/metadata' % id)
        res = self.controller.update_all_metadata(req, id, body)
        self.assertEqual(body, res)
        mock_validate.assert_called_once_with(req, id, body['metadata'])
        mock_update.assert_called_once_with(req, id, body)

    def test_delete_metadata(self):
        mock_delete = self.mock_object(
            self.controller, '_delete_metadata', mock.Mock())

        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/metadata/fake_key' % id)
        self.controller.delete_metadata(req, id, 'fake_key')
        mock_delete.assert_called_once_with(req, id, 'fake_key')


def _fake_access_get(self, ctxt, access_id):

    class Access(object):
        def __init__(self, **kwargs):
            self.STATE_NEW = 'fake_new'
            self.STATE_ACTIVE = 'fake_active'
            self.STATE_ERROR = 'fake_error'
            self.params = kwargs
            self.params['state'] = self.STATE_NEW
            self.share_id = kwargs.get('share_id')
            self.id = access_id

        def __getitem__(self, item):
            return self.params[item]

    access = Access(access_id=access_id, share_id='fake_share_id')
    return access


@ddt.ddt
class ShareActionsTest(test.TestCase):

    def setUp(self):
        super(ShareActionsTest, self).setUp()
        self.controller = shares.ShareController()
        self.mock_object(share_api.API, 'get', stubs.stub_share_get)
        self.mock_object(policy, 'check_policy')

    @ddt.unpack
    @ddt.data(
        {"access": {'access_type': 'ip', 'access_to': '127.0.0.1'},
         "version": "2.7"},
        {"access": {'access_type': 'user', 'access_to': '1' * 4},
         "version": "2.7"},
        {"access": {'access_type': 'user', 'access_to': '1' * 255},
         "version": "2.7"},
        {"access": {'access_type': 'user', 'access_to': 'fake{.-_\'`}'},
         "version": "2.7"},
        {"access": {'access_type': 'user',
                    'access_to': 'MYDOMAIN-Administrator'},
         "version": "2.7"},
        {"access": {'access_type': 'user',
                    'access_to': 'test group name'},
         "version": "2.7"},
        {"access": {'access_type': 'user',
                    'access_to': 'group$.-_\'`{}'},
         "version": "2.7"},
        {"access": {'access_type': 'cert', 'access_to': 'x'},
         "version": "2.7"},
        {"access": {'access_type': 'cert', 'access_to': 'tenant.example.com'},
         "version": "2.7"},
        {"access": {'access_type': 'cert', 'access_to': 'x' * 64},
         "version": "2.7"},
        {"access": {'access_type': 'ip', 'access_to': 'ad80::abaa:0:c2:2'},
         "version": "2.38"},
        {"access": {'access_type': 'ip', 'access_to': 'AD80:ABAA::'},
         "version": "2.38"},
        {"access": {'access_type': 'ip', 'access_to': 'AD80::/36'},
         "version": "2.38"},
        {"access": {'access_type': 'ip', 'access_to': 'AD80:ABAA::/128'},
         "version": "2.38"},
        {"access": {'access_type': 'ip', 'access_to': '127.0.0.1'},
         "version": "2.38"},
        {"access": {'access_type': 'ip', 'access_to': '127.0.0.1',
                    'metadata': {'test_key': 'test_value'}},
         "version": "2.45"},
        {"access": {'access_type': 'ip', 'access_to': '127.0.0.1',
                    'metadata': {'k' * 255: 'v' * 1023}},
         "version": "2.45"},
    )
    def test_allow_access(self, access, version):
        self.mock_object(share_api.API,
                         'allow_access',
                         mock.Mock(return_value={'fake': 'fake'}))
        self.mock_object(self.controller._access_view_builder, 'view',
                         mock.Mock(return_value={'access':
                                                 {'fake': 'fake'}}))
        id = 'fake_share_id'
        body = {'allow_access': access}
        expected = {'access': {'fake': 'fake'}}
        req = fakes.HTTPRequest.blank(
            '/v2/tenant1/shares/%s/action' % id, version=version)

        res = self.controller.allow_access(req, id, body)

        self.assertEqual(expected, res)

    @ddt.unpack
    @ddt.data(
        {"access": {'access_type': 'error_type',
                    'access_to': '127.0.0.1'},
         "version": "2.7"},
        {"access": {'access_type': 'ip', 'access_to': 'localhost'},
         "version": "2.7"},
        {"access": {'access_type': 'ip', 'access_to': '127.0.0.*'},
         "version": "2.7"},
        {"access": {'access_type': 'ip', 'access_to': '127.0.0.0/33'},
         "version": "2.7"},
        {"access": {'access_type': 'ip', 'access_to': '127.0.0.256'},
         "version": "2.7"},
        {"access": {'access_type': 'user', 'access_to': '1'},
         "version": "2.7"},
        {"access": {'access_type': 'user', 'access_to': '1' * 3},
         "version": "2.7"},
        {"access": {'access_type': 'user', 'access_to': '1' * 256},
         "version": "2.7"},
        {"access": {'access_type': 'user', 'access_to': 'root<>'},
         "version": "2.7"},
        {"access": {'access_type': 'user', 'access_to': 'group\\'},
         "version": "2.7"},
        {"access": {'access_type': 'user', 'access_to': '+=*?group'},
         "version": "2.7"},
        {"access": {'access_type': 'cert', 'access_to': ''},
         "version": "2.7"},
        {"access": {'access_type': 'cert', 'access_to': ' '},
         "version": "2.7"},
        {"access": {'access_type': 'cert', 'access_to': 'x' * 65},
         "version": "2.7"},
        {"access": {'access_type': 'ip', 'access_to': 'ad80::abaa:0:c2:2'},
         "version": "2.37"},
        {"access": {'access_type': 'ip', 'access_to': '127.4.0.3/33'},
         "version": "2.38"},
        {"access": {'access_type': 'ip', 'access_to': 'AD80:ABAA::*'},
         "version": "2.38"},
        {"access": {'access_type': 'ip', 'access_to': 'AD80::/129'},
         "version": "2.38"},
        {"access": {'access_type': 'ip', 'access_to': 'ad80::abaa:0:c2:2/64'},
         "version": "2.38"},
        {"access": {'access_type': 'ip', 'access_to': '127.0.0.1',
                    'metadata': {'k' * 256: 'v' * 1024}},
         "version": "2.45"},
        {"access": {'access_type': 'ip', 'access_to': '127.0.0.1',
                    'metadata': {'key': None}},
         "version": "2.45"},
    )
    def test_allow_access_error(self, access, version):
        id = 'fake_share_id'
        body = {'allow_access': access}
        req = fakes.HTTPRequest.blank('/v2/tenant1/shares/%s/action' % id,
                                      version=version)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.allow_access, req, id, body)

    @ddt.unpack
    @ddt.data(
        {'exc': None, 'access_to': 'alice', 'version': '2.13'},
        {'exc': webob.exc.HTTPBadRequest, 'access_to': 'alice',
         'version': '2.11'}
    )
    def test_allow_access_ceph(self, exc, access_to, version):
        share_id = "fake_id"
        self.mock_object(share_api.API,
                         'allow_access',
                         mock.Mock(return_value={'fake': 'fake'}))
        self.mock_object(self.controller._access_view_builder, 'view',
                         mock.Mock(return_value={'access':
                                                 {'fake': 'fake'}}))

        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/action' % share_id, version=version)

        body = {'allow_access':
                {
                    'access_type': 'cephx',
                    'access_to': access_to,
                    'access_level': 'rw'
                }}

        if exc:
            self.assertRaises(exc, self.controller.allow_access, req, share_id,
                              body)
        else:
            expected = {'access': {'fake': 'fake'}}
            res = self.controller.allow_access(req, id, body)
            self.assertEqual(expected, res)

    @ddt.data('2.1', '2.27')
    def test_allow_access_access_rules_status_is_in_error(self, version):
        share = db_utils.create_share(
            access_rules_status=constants.SHARE_INSTANCE_RULES_ERROR)

        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/action' % share['id'], version=version)
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        self.mock_object(share_api.API, 'allow_access')
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.7')):
            key = 'allow_access'
            method = self.controller.allow_access
        else:
            key = 'os-allow_access'
            method = self.controller.allow_access_legacy

        body = {
            key: {
                'access_type': 'user',
                'access_to': 'crimsontide',
                'access_level': 'rw',
            }
        }

        self.assertRaises(webob.exc.HTTPBadRequest,
                          method, req, share['id'], body)
        self.assertFalse(share_api.API.allow_access.called)

    @ddt.data(*itertools.product(
        ('2.1', '2.27'), (constants.SHARE_INSTANCE_RULES_SYNCING,
                          constants.STATUS_ACTIVE)))
    @ddt.unpack
    def test_allow_access_no_transitional_states(self, version, status):
        share = db_utils.create_share(access_rules_status=status,
                                      status=constants.STATUS_AVAILABLE)
        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/action' % share['id'], version=version)
        ctxt = req.environ['manila.context']
        access = {
            'access_type': 'user',
            'access_to': 'clemsontigers',
            'access_level': 'rw',
        }
        expected_mapping = {
            constants.SHARE_INSTANCE_RULES_SYNCING: constants.STATUS_NEW,
            constants.SHARE_INSTANCE_RULES_ERROR:
                constants.ACCESS_STATE_ERROR,
            constants.STATUS_ACTIVE: constants.ACCESS_STATE_ACTIVE,
        }
        share = db.share_get(ctxt, share['id'])
        updated_access = db_utils.create_access(share_id=share['id'], **access)
        expected_access = access
        expected_access.update(
            {
                'id': updated_access['id'],
                'state': expected_mapping[share['access_rules_status']],
                'share_id': updated_access['share_id'],
            })

        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.7')):
            key = 'allow_access'
            method = self.controller.allow_access
        else:
            key = 'os-allow_access'
            method = self.controller.allow_access_legacy
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.13')):
            expected_access['access_key'] = None
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        self.mock_object(share_api.API, 'allow_access',
                         mock.Mock(return_value=updated_access))
        body = {key: access}

        access = method(req, share['id'], body)

        self.assertEqual(expected_access, access['access'])
        share_api.API.allow_access.assert_called_once_with(
            req.environ['manila.context'], share, 'user',
            'clemsontigers', 'rw', None, False)

    @ddt.data(*itertools.product(
        set(['2.28', api_version._MAX_API_VERSION]),
        (constants.SHARE_INSTANCE_RULES_ERROR,
         constants.SHARE_INSTANCE_RULES_SYNCING, constants.STATUS_ACTIVE)))
    @ddt.unpack
    def test_allow_access_access_rules_status_dont_care(self, version, status):
        access = {
            'access_type': 'user',
            'access_to': 'clemsontigers',
            'access_level': 'rw',
        }
        updated_access = db_utils.create_access(**access)
        expected_access = access
        expected_access.update(
            {
                'id': updated_access['id'],
                'state': updated_access['state'],
                'share_id': updated_access['share_id'],
                'access_key': None,
            })

        share = db_utils.create_share(access_rules_status=status)
        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/action' % share['id'], version=version)
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        self.mock_object(share_api.API, 'allow_access',
                         mock.Mock(return_value=updated_access))
        body = {'allow_access': access}

        access = self.controller.allow_access(req, share['id'], body)

        if api_version.APIVersionRequest(version) >= (
                api_version.APIVersionRequest("2.33")):
            expected_access.update(
                {
                    'created_at': updated_access['created_at'],
                    'updated_at': updated_access['updated_at'],
                })

        if api_version.APIVersionRequest(version) >= (
                api_version.APIVersionRequest("2.45")):
            expected_access.update(
                {
                    'metadata': {},
                })

        if api_version.APIVersionRequest(version) >= (
                api_version.APIVersionRequest("2.74")):
            allow_on_error_state = True
        else:
            allow_on_error_state = False

        self.assertEqual(expected_access, access['access'])
        share_api.API.allow_access.assert_called_once_with(
            req.environ['manila.context'], share, 'user',
            'clemsontigers', 'rw', None, allow_on_error_state)

    def test_deny_access(self):
        def _stub_deny_access(*args, **kwargs):
            pass

        self.mock_object(share_api.API, "deny_access", _stub_deny_access)
        self.mock_object(share_api.API, "access_get", _fake_access_get)

        id = 'fake_share_id'
        body = {"os-deny_access": {"access_id": 'fake_acces_id'}}
        req = fakes.HTTPRequest.blank('/v2/tenant1/shares/%s/action' % id)
        res = self.controller._deny_access(req, id, body)
        self.assertEqual(202, res.status_int)

    def test_deny_access_not_found(self):
        def _stub_deny_access(*args, **kwargs):
            pass

        self.mock_object(share_api.API, "deny_access", _stub_deny_access)
        self.mock_object(share_api.API, "access_get", _fake_access_get)

        id = 'super_fake_share_id'
        body = {"os-deny_access": {"access_id": 'fake_acces_id'}}
        req = fakes.HTTPRequest.blank('/v2/tenant1/shares/%s/action' % id)
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller._deny_access,
                          req,
                          id,
                          body)

    def test_access_list(self):
        fake_access_list = [
            {
                "state": "fakestatus",
                "id": "fake_access_id",
                "access_type": "fakeip",
                "access_to": "127.0.0.1",
            }
        ]
        self.mock_object(self.controller._access_view_builder, 'list_view',
                         mock.Mock(return_value={'access_list':
                                                 fake_access_list}))
        id = 'fake_share_id'
        body = {"os-access_list": None}
        req = fakes.HTTPRequest.blank('/v2/tenant1/shares/%s/action' % id)

        res_dict = self.controller._access_list(req, id, body)
        self.assertEqual({'access_list': fake_access_list}, res_dict)

    @ddt.unpack
    @ddt.data(
        {'body': {'os-extend': {'new_size': 2}}, 'version': '2.6'},
        {'body': {'extend': {'new_size': 2}}, 'version': '2.7'},
    )
    def test_extend(self, body, version):
        id = 'fake_share_id'
        share = stubs.stub_share_get(None, None, id)
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        self.mock_object(share_api.API, "extend")

        size = '2'
        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/action' % id, version=version)
        actual_response = self.controller._extend(req, id, body)

        share_api.API.get.assert_called_once_with(mock.ANY, id)
        share_api.API.extend.assert_called_once_with(
            mock.ANY, share, int(size), force=False)
        self.assertEqual(202, actual_response.status_int)

    @ddt.data({"os-extend": ""},
              {"os-extend": {"new_size": "foo"}},
              {"os-extend": {"new_size": {'foo': 'bar'}}})
    def test_extend_invalid_body(self, body):
        id = 'fake_share_id'
        req = fakes.HTTPRequest.blank('/v2/shares/%s/action' % id)

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller._extend, req, id, body)

    @ddt.data({'source': exception.InvalidInput,
               'target': webob.exc.HTTPBadRequest},
              {'source': exception.InvalidShare,
               'target': webob.exc.HTTPBadRequest},
              {'source': exception.ShareSizeExceedsAvailableQuota,
               'target': webob.exc.HTTPForbidden})
    @ddt.unpack
    def test_extend_exception(self, source, target):
        id = 'fake_share_id'
        req = fakes.HTTPRequest.blank('/v2/shares/%s/action' % id)
        body = {"os-extend": {'new_size': '123'}}
        self.mock_object(share_api.API, "extend",
                         mock.Mock(side_effect=source('fake')))

        self.assertRaises(target, self.controller._extend, req, id, body)

    @ddt.unpack
    @ddt.data(
        {'body': {'os-shrink': {'new_size': 1}}, 'version': '2.6'},
        {'body': {'shrink': {'new_size': 1}}, 'version': '2.7'},
    )
    def test_shrink(self, body, version):
        id = 'fake_share_id'
        share = stubs.stub_share_get(None, None, id)
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        self.mock_object(share_api.API, "shrink")

        size = '1'
        req = fakes.HTTPRequest.blank(
            '/v2/shares/%s/action' % id, version=version)
        actual_response = self.controller._shrink(req, id, body)

        share_api.API.get.assert_called_once_with(mock.ANY, id)
        share_api.API.shrink.assert_called_once_with(
            mock.ANY, share, int(size))
        self.assertEqual(202, actual_response.status_int)

    @ddt.data({"os-shrink": ""},
              {"os-shrink": {"new_size": "foo"}},
              {"os-shrink": {"new_size": {'foo': 'bar'}}})
    def test_shrink_invalid_body(self, body):
        id = 'fake_share_id'
        req = fakes.HTTPRequest.blank('/v2/shares/%s/action' % id)

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller._shrink, req, id, body)

    @ddt.data({'source': exception.InvalidInput,
               'target': webob.exc.HTTPBadRequest},
              {'source': exception.InvalidShare,
               'target': webob.exc.HTTPBadRequest})
    @ddt.unpack
    def test_shrink_exception(self, source, target):
        id = 'fake_share_id'
        req = fakes.HTTPRequest.blank('/v2/shares/%s/action' % id)
        body = {"os-shrink": {'new_size': '123'}}
        self.mock_object(share_api.API, "shrink",
                         mock.Mock(side_effect=source('fake')))

        self.assertRaises(target, self.controller._shrink, req, id, body)


@ddt.ddt
class ShareAdminActionsAPITest(test.TestCase):

    def setUp(self):
        super(ShareAdminActionsAPITest, self).setUp()
        CONF.set_default("default_share_type", None)
        self.flags(transport_url='rabbit://fake:fake@mqhost:5672')
        self.share_api = share_api.API()
        self.admin_context = context.RequestContext('admin', 'fake', True)
        self.member_context = context.RequestContext('fake', 'fake')

    def _get_context(self, role):
        return getattr(self, '%s_context' % role)

    def _setup_share_data(self, share=None, version='2.7'):
        if share is None:
            share = db_utils.create_share(status=constants.STATUS_AVAILABLE,
                                          size='1',
                                          override_defaults=True)
        path = '/v2/fake/shares/%s/action' % share['id']
        req = fakes.HTTPRequest.blank(path, script_name=path, version=version)
        return share, req

    def _reset_status(self, ctxt, model, req, db_access_method,
                      valid_code, valid_status=None, body=None, version='2.7'):
        if float(version) > 2.6:
            action_name = 'reset_status'
        else:
            action_name = 'os-reset_status'
        if body is None:
            body = {action_name: {'status': constants.STATUS_ERROR}}
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.headers['X-Openstack-Manila-Api-Version'] = version
        req.body = jsonutils.dumps(body).encode("utf-8")
        req.environ['manila.context'] = ctxt

        resp = req.get_response(fakes.app(), catch_exc_info=True)

        # validate response code and model status
        self.assertEqual(valid_code, resp.status_int)

        if valid_code == 404 and db_access_method is not None:
            self.assertRaises(exception.NotFound,
                              db_access_method,
                              ctxt,
                              model['id'])
        elif db_access_method:
            actual_model = db_access_method(ctxt, model['id'])
            self.assertEqual(valid_status, actual_model['status'])

    @ddt.data(*fakes.fixture_reset_status_with_different_roles)
    @ddt.unpack
    def test_share_reset_status_with_different_roles(self, role, valid_code,
                                                     valid_status, version):
        share, req = self._setup_share_data(version=version)
        ctxt = self._get_context(role)
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))

        self._reset_status(ctxt, share, req, db.share_get, valid_code,
                           valid_status, version=version)

    @ddt.data(*fakes.fixture_invalid_reset_status_body)
    def test_share_invalid_reset_status_body(self, body):
        share, req = self._setup_share_data(version='2.6')
        ctxt = self.admin_context
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))

        self._reset_status(ctxt, share, req, db.share_get, 400,
                           constants.STATUS_AVAILABLE, body, version='2.6')

    @ddt.data('2.6', '2.7')
    def test_share_reset_status_for_missing(self, version):
        fake_share = {'id': 'missing-share-id', 'is_soft_deleted': False}
        req = fakes.HTTPRequest.blank(
            '/v2/fake/shares/%s/action' % fake_share['id'], version=version)

        self._reset_status(self.admin_context, fake_share, req,
                           db.share_get, 404, version=version)

    @ddt.data('2.6', '2.7')
    def test_reset_status_other_project_public_share(self, version):
        # NOTE(gouthamr): we're testing a scenario where someone has access
        # to the RBAC rule share:reset_status, but doesn't own the share.
        # Ideally we'd override the default policy, but it's a shared
        # resource and we'll bleed into other tests, so we'll mock the
        # policy check to return False instead
        share, req = self._setup_share_data(version=version)
        share['is_public'] = True
        rbac_checks = [None, exception.NotAuthorized]
        with mock.patch.object(policy, 'authorize', side_effect=rbac_checks):
            self.mock_object(share_api.API, 'get',
                             mock.Mock(return_value=share))
            self._reset_status(
                self.member_context, share, req, None, 403, version=version)

    def _force_delete(self, ctxt, model, req, db_access_method, valid_code,
                      check_model_in_db=False, version='2.7'):
        if float(version) > 2.6:
            action_name = 'force_delete'
        else:
            action_name = 'os-force_delete'
        req.method = 'POST'
        req.headers['content-type'] = 'application/json'
        req.headers['X-Openstack-Manila-Api-Version'] = version
        req.body = jsonutils.dumps({action_name: {}}).encode("utf-8")
        req.environ['manila.context'] = ctxt

        resp = req.get_response(fakes.app())

        # validate response
        self.assertEqual(valid_code, resp.status_int)

        if valid_code == 202 and check_model_in_db:
            self.assertRaises(exception.NotFound,
                              db_access_method,
                              ctxt,
                              model['id'])

    @ddt.data(*fakes.fixture_force_delete_with_different_roles)
    @ddt.unpack
    def test_share_force_delete_with_different_roles(self, role, resp_code,
                                                     version):
        share, req = self._setup_share_data(version=version)
        ctxt = self._get_context(role)

        self._force_delete(ctxt, share, req, db.share_get, resp_code,
                           check_model_in_db=True, version=version)

    @ddt.data('2.6', '2.7')
    def test_share_force_delete_missing(self, version):
        share, req = self._setup_share_data(
            share={'id': 'fake'}, version=version)
        ctxt = self._get_context('admin')

        self._force_delete(
            ctxt, share, req, db.share_get, 404, version=version)


@ddt.ddt
class ShareUnmanageTest(test.TestCase):

    def setUp(self):
        super(ShareUnmanageTest, self).setUp()
        self.controller = shares.ShareController()
        self.mock_object(share_api.API, 'get_all',
                         stubs.stub_get_all_shares)
        self.mock_object(share_api.API, 'get',
                         stubs.stub_share_get)
        self.mock_object(share_api.API, 'update', stubs.stub_share_update)
        self.mock_object(share_api.API, 'delete', stubs.stub_share_delete)
        self.mock_object(share_api.API, 'get_snapshot',
                         stubs.stub_snapshot_get)
        self.share_id = 'fake'
        self.request = fakes.HTTPRequest.blank(
            '/v2/fake/share/%s/unmanage' % self.share_id,
            use_admin_context=True, version='2.7',
        )

    def test_unmanage_share(self):
        share = dict(status=constants.STATUS_AVAILABLE, id='foo_id',
                     instance={})
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        self.mock_object(share_api.API, 'unmanage', mock.Mock())
        self.mock_object(
            self.controller.share_api.db, 'share_snapshot_get_all_for_share',
            mock.Mock(return_value=[]))

        actual_result = self.controller.unmanage(self.request, share['id'])

        self.assertEqual(202, actual_result.status_int)
        (self.controller.share_api.db.share_snapshot_get_all_for_share.
            assert_called_once_with(
                self.request.environ['manila.context'], share['id']))
        self.controller.share_api.get.assert_called_once_with(
            self.request.environ['manila.context'], share['id'])
        share_api.API.unmanage.assert_called_once_with(
            self.request.environ['manila.context'], share)

    def test__unmanage(self):
        body = {}
        req = fakes.HTTPRequest.blank('/v2/fake/shares/1/action',
                                      use_admin_context=False,
                                      version='2.49')
        share = dict(status=constants.STATUS_AVAILABLE, id='foo_id',
                     instance={})
        mock_unmanage = self.mock_object(self.controller, '_unmanage')

        self.controller.unmanage(req, share['id'], body)

        mock_unmanage.assert_called_once_with(
            req, share['id'], body, allow_dhss_true=True
        )

    def test_unmanage_share_that_has_snapshots(self):
        share = dict(status=constants.STATUS_AVAILABLE, id='foo_id',
                     instance={})
        snapshots = ['foo', 'bar']
        self.mock_object(self.controller.share_api, 'unmanage')
        self.mock_object(
            self.controller.share_api.db, 'share_snapshot_get_all_for_share',
            mock.Mock(return_value=snapshots))
        self.mock_object(
            self.controller.share_api, 'get',
            mock.Mock(return_value=share))

        self.assertRaises(
            webob.exc.HTTPForbidden,
            self.controller.unmanage, self.request, share['id'])

        self.assertFalse(self.controller.share_api.unmanage.called)
        (self.controller.share_api.db.share_snapshot_get_all_for_share.
            assert_called_once_with(
                self.request.environ['manila.context'], share['id']))
        self.controller.share_api.get.assert_called_once_with(
            self.request.environ['manila.context'], share['id'])

    def test_unmanage_share_based_on_share_server(self):
        share = dict(instance=dict(share_server_id='foo_id'), id='bar_id')
        self.mock_object(
            self.controller.share_api, 'get',
            mock.Mock(return_value=share))

        self.assertRaises(
            webob.exc.HTTPForbidden,
            self.controller.unmanage, self.request, share['id'])

        self.controller.share_api.get.assert_called_once_with(
            self.request.environ['manila.context'], share['id'])

    @ddt.data(*constants.TRANSITIONAL_STATUSES)
    def test_unmanage_share_with_transitional_state(self, share_status):
        share = dict(status=share_status, id='foo_id', instance={})
        self.mock_object(
            self.controller.share_api, 'get',
            mock.Mock(return_value=share))

        self.assertRaises(
            webob.exc.HTTPForbidden,
            self.controller.unmanage, self.request, share['id'])

        self.controller.share_api.get.assert_called_once_with(
            self.request.environ['manila.context'], share['id'])

    def test_unmanage_share_not_found(self):
        self.mock_object(share_api.API, 'get', mock.Mock(
            side_effect=exception.NotFound))
        self.mock_object(share_api.API, 'unmanage', mock.Mock())

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.unmanage,
                          self.request, self.share_id)

    @ddt.data(exception.InvalidShare(reason="fake"),
              exception.PolicyNotAuthorized(action="fake"),)
    def test_unmanage_share_invalid(self, side_effect):
        share = dict(status=constants.STATUS_AVAILABLE, id='foo_id',
                     instance={})
        self.mock_object(share_api.API, 'get', mock.Mock(return_value=share))
        self.mock_object(share_api.API, 'unmanage', mock.Mock(
            side_effect=side_effect))

        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.unmanage,
                          self.request, self.share_id)

    def test_wrong_permissions(self):
        share_id = 'fake'
        req = fakes.HTTPRequest.blank('/v2/fake/share/%s/unmanage' % share_id,
                                      use_admin_context=False, version='2.7')

        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.unmanage,
                          req,
                          share_id)

    def test_unsupported_version(self):
        share_id = 'fake'
        req = fakes.HTTPRequest.blank('/v2/fake/share/%s/unmanage' % share_id,
                                      use_admin_context=False, version='2.6')

        self.assertRaises(exception.VersionNotFoundForAPIMethod,
                          self.controller.unmanage,
                          req,
                          share_id)


def get_fake_manage_body(export_path='/fake', service_host='fake@host#POOL',
                         protocol='fake', share_type='fake', **kwargs):
    fake_share = {
        'export_path': export_path,
        'service_host': service_host,
        'protocol': protocol,
        'share_type': share_type,
    }
    fake_share.update(kwargs)
    return {'share': fake_share}


@ddt.ddt
class ShareManageTest(test.TestCase):

    def setUp(self):
        super(ShareManageTest, self).setUp()
        self.controller = shares.ShareController()
        self.resource_name = self.controller.resource_name
        self.request = fakes.HTTPRequest.blank(
            '/v2/shares/manage', use_admin_context=True, version='2.7')
        self.mock_policy_check = self.mock_object(
            policy, 'check_policy', mock.Mock(return_value=True))

    def _setup_manage_mocks(self, service_is_up=True):
        self.mock_object(db, 'service_get_by_host_and_topic', mock.Mock(
            return_value={'host': 'fake'}))
        self.mock_object(share_types, 'get_share_type_by_name_or_id',
                         mock.Mock(return_value={'id': 'fake'}))
        self.mock_object(utils, 'service_is_up', mock.Mock(
            return_value=service_is_up))
        if service_is_up:
            self.mock_object(utils, 'validate_service_host')
        else:
            self.mock_object(
                utils,
                'validate_service_host',
                mock.Mock(side_effect=exception.ServiceIsDown(service='fake')))

    def test__manage(self):
        body = {}
        req = fakes.HTTPRequest.blank(
            '/v2/shares/manage', use_admin_context=True, version='2.49')
        mock_manage = self.mock_object(self.controller, '_manage')

        self.controller.manage(req, body)

        mock_manage.assert_called_once_with(
            req, body, allow_dhss_true=True
        )

    @ddt.data({},
              {'shares': {}},
              {'share': get_fake_manage_body('', None, None)})
    def test_share_manage_invalid_body(self, body):
        self.assertRaises(webob.exc.HTTPUnprocessableEntity,
                          self.controller.manage,
                          self.request,
                          body)

    def test_share_manage_service_not_found(self):
        body = get_fake_manage_body()
        self.mock_object(db, 'service_get_by_host_and_topic', mock.Mock(
            side_effect=exception.ServiceNotFound(service_id='fake')))

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.manage,
                          self.request,
                          body)

    def test_share_manage_share_type_not_found(self):
        body = get_fake_manage_body()
        self.mock_object(db, 'service_get_by_host_and_topic', mock.Mock())
        self.mock_object(utils, 'service_is_up', mock.Mock(return_value=True))
        self.mock_object(db, 'share_type_get_by_name', mock.Mock(
            side_effect=exception.ShareTypeNotFoundByName(
                share_type_name='fake')))

        self.assertRaises(webob.exc.HTTPNotFound,
                          self.controller.manage,
                          self.request,
                          body)

    @ddt.data({'service_is_up': False, 'service_host': 'fake@host#POOL'},
              {'service_is_up': True, 'service_host': 'fake@host'})
    def test_share_manage_bad_request(self, settings):
        body = get_fake_manage_body(service_host=settings.pop('service_host'))
        self._setup_manage_mocks(**settings)

        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.manage,
                          self.request,
                          body)

    def test_share_manage_duplicate_share(self):
        body = get_fake_manage_body()
        exc = exception.InvalidShare(reason="fake")
        self._setup_manage_mocks()
        self.mock_object(share_api.API, 'manage', mock.Mock(side_effect=exc))

        self.assertRaises(webob.exc.HTTPConflict,
                          self.controller.manage,
                          self.request,
                          body)

    def test_share_manage_forbidden_manage(self):
        body = get_fake_manage_body()
        self._setup_manage_mocks()
        error = mock.Mock(side_effect=exception.PolicyNotAuthorized(action=''))
        self.mock_object(share_api.API, 'manage', error)

        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.manage,
                          self.request,
                          body)

    def test_share_manage_forbidden_validate_service_host(self):
        body = get_fake_manage_body()
        self._setup_manage_mocks()
        error = mock.Mock(side_effect=exception.PolicyNotAuthorized(action=''))
        self.mock_object(
            utils, 'validate_service_host', mock.Mock(side_effect=error))

        self.assertRaises(webob.exc.HTTPForbidden,
                          self.controller.manage,
                          self.request,
                          body)

    @ddt.data(
        get_fake_manage_body(name='foo', description='bar'),
        get_fake_manage_body(display_name='foo', description='bar'),
        get_fake_manage_body(name='foo', display_description='bar'),
        get_fake_manage_body(display_name='foo', display_description='bar'),
        get_fake_manage_body(display_name='foo', display_description='bar',
                             driver_options=dict(volume_id='quuz')),
    )
    def test_share_manage(self, data):
        self._test_share_manage(data, "2.7")

    @ddt.data(
        get_fake_manage_body(name='foo', description='bar', is_public=True),
        get_fake_manage_body(name='foo', description='bar', is_public=False)
    )
    def test_share_manage_with_is_public(self, data):
        self._test_share_manage(data, "2.8")

    def test_share_manage_with_user_id(self):
        self._test_share_manage(get_fake_manage_body(
            name='foo', description='bar', is_public=True), "2.16")

    def _test_share_manage(self, data, version):
        expected = {
            'share': {
                'status': 'fakestatus',
                'description': 'displaydesc',
                'availability_zone': 'fakeaz',
                'name': 'displayname',
                'share_proto': 'FAKEPROTO',
                'metadata': {},
                'project_id': 'fakeproject',
                'host': 'fakehost',
                'id': 'fake',
                'snapshot_id': '2',
                'share_network_id': None,
                'created_at': datetime.datetime(1, 1, 1, 1, 1, 1),
                'size': 1,
                'share_type_name': None,
                'share_server_id': 'fake_share_server_id',
                'share_type': '1',
                'volume_type': '1',
                'is_public': False,
                'snapshot_support': True,
                'task_state': None,
                'links': [
                    {
                        'href': 'http://localhost/share/v2/fake/shares/fake',
                        'rel': 'self'
                    },
                    {
                        'href': 'http://localhost/share/fake/shares/fake',
                        'rel': 'bookmark'
                    }
                ],
            }
        }
        self._setup_manage_mocks()
        return_share = mock.Mock(
            return_value=stubs.stub_share(
                'fake',
                instance={
                    'share_type_id': '1',
                })
            )
        self.mock_object(
            share_api.API, 'manage', return_share)
        self.mock_object(
            common, 'validate_public_share_policy',
            mock.Mock(side_effect=lambda *args, **kwargs: args[1]))
        share = {
            'host': data['share']['service_host'],
            'export_location_path': data['share']['export_path'],
            'share_proto': data['share']['protocol'].upper(),
            'share_type_id': 'fake',
            'display_name': 'foo',
            'display_description': 'bar',
        }
        driver_options = data['share'].get('driver_options', {})

        if (api_version.APIVersionRequest(version) <=
                api_version.APIVersionRequest('2.8')):
            expected['share']['export_location'] = 'fake_location'
            expected['share']['export_locations'] = (
                ['fake_location', 'fake_location2'])

        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.10')):
            expected['share']['access_rules_status'] = (
                constants.STATUS_ACTIVE)
        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.11')):
            expected['share']['has_replicas'] = False
            expected['share']['replication_type'] = None

        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.16')):
            expected['share']['user_id'] = 'fakeuser'

        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.8')):
            share['is_public'] = data['share']['is_public']

        if (api_version.APIVersionRequest(version) >=
                api_version.APIVersionRequest('2.80')):
            share['source_backup_id'] = None

        req = fakes.HTTPRequest.blank('/v2/fake/shares/manage',
                                      version=version,
                                      use_admin_context=True)

        actual_result = self.controller.manage(req, data)

        share_api.API.manage.assert_called_once_with(
            mock.ANY, share, driver_options)

        self.assertIsNotNone(actual_result)
        self.assertEqual(expected, actual_result)
        self.mock_policy_check.assert_called_once_with(
            req.environ['manila.context'], self.resource_name, 'manage')

    def test_wrong_permissions(self):
        body = get_fake_manage_body()

        self.assertRaises(
            webob.exc.HTTPForbidden,
            self.controller.manage,
            fakes.HTTPRequest.blank('/v2/fake/share/manage',
                                    use_admin_context=False,
                                    version='2.7'),
            body,
        )

    def test_unsupported_version(self):
        share_id = 'fake'
        req = fakes.HTTPRequest.blank(
            '/v2/fake/share/manage', use_admin_context=False, version='2.6')

        self.assertRaises(exception.VersionNotFoundForAPIMethod,
                          self.controller.manage,
                          req,
                          share_id)

    def test_revert(self):

        mock_revert = self.mock_object(
            self.controller, '_revert',
            mock.Mock(return_value='fake_response'))
        req = fakes.HTTPRequest.blank('/v2/fake/shares/fake_id/action',
                                      use_admin_context=False,
                                      version='2.27')

        result = self.controller.revert(req, 'fake_id', 'fake_body')

        self.assertEqual('fake_response', result)
        mock_revert.assert_called_once_with(
            req, 'fake_id', 'fake_body')

    def test_revert_unsupported(self):

        req = fakes.HTTPRequest.blank('/v2/shares/fake_id/action',
                                      use_admin_context=False,
                                      version='2.24')

        self.assertRaises(exception.VersionNotFoundForAPIMethod,
                          self.controller.revert,
                          req,
                          'fake_id',
                          'fake_body')
