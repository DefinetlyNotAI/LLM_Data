# Copyright 2011 OpenStack Foundation
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
from oslo_utils import timeutils
import webob

from cinder.api.v3 import types
from cinder.api.v3.views import types as views_types
from cinder import context
from cinder import exception
from cinder.policies import type_extra_specs as extra_specs_policy
from cinder.policies import volume_type as type_policy
from cinder.tests.unit.api import fakes
from cinder.tests.unit import fake_constants as fake
from cinder.tests.unit import test
from cinder.volume import volume_types


def fake_volume_type(id):
    specs = {
        "key1": "value1",
        "key2": "value2",
        "key3": "value3",
        "key4": "value4",
        "key5": "value5"
    }
    return dict(
        id=id,
        name='vol_type_%s' % id,
        description='vol_type_desc_%s' % id,
        extra_specs=specs,
    )


def return_volume_types_get_all_types(context, filters=None, marker=None,
                                      limit=None, sort_keys=None,
                                      sort_dirs=None, offset=None,
                                      list_result=False):
    result = dict(vol_type_1=fake_volume_type(1),
                  vol_type_2=fake_volume_type(2),
                  vol_type_3=fake_volume_type(3)
                  )
    if list_result:
        return list(result.values())
    return result


def return_empty_volume_types_get_all_types(context, filters=None, marker=None,
                                            limit=None, sort_keys=None,
                                            sort_dirs=None, offset=None,
                                            list_result=False):
    if list_result:
        return []
    return {}


def return_volume_types_get_volume_type(context, id):
    if id == fake.WILL_NOT_BE_FOUND_ID:
        raise exception.VolumeTypeNotFound(volume_type_id=id)
    return fake_volume_type(id)


def return_volume_types_get_default(context):
    return fake_volume_type(1)


@ddt.ddt
class VolumeTypesApiTest(test.TestCase):

    def _create_volume_type(self, volume_type_name, extra_specs=None,
                            is_public=True, projects=None):
        return volume_types.create(self.ctxt, volume_type_name, extra_specs,
                                   is_public, projects).get('id')

    def setUp(self):
        super(VolumeTypesApiTest, self).setUp()
        self.controller = types.VolumeTypesController()
        self.ctxt = context.RequestContext(user_id=fake.USER_ID,
                                           project_id=fake.PROJECT_ID,
                                           is_admin=True)
        self.mock_authorize = self.patch(
            'cinder.context.RequestContext.authorize')
        # since __DEFAULT__ type always exists, total number of volume types
        # is total_types_created + 1. In this case it's 4
        self.type_id1 = self._create_volume_type('volume_type1',
                                                 {'key1': 'value1'})
        self.type_id2 = self._create_volume_type('volume_type2',
                                                 {'key2': 'value2'})
        self.type_id3 = self._create_volume_type('volume_type3',
                                                 {'key3': 'value3'}, False,
                                                 [fake.PROJECT_ID])
        self.default_type = volume_types.get_default_volume_type()['id']
        self.vol_type = volume_types.get_by_name_or_id(
            context.get_admin_context(), '__DEFAULT__')['id']

    def test_volume_types_index(self):
        self.mock_object(volume_types, 'get_all_types',
                         return_volume_types_get_all_types)

        req = fakes.HTTPRequest.blank('/v3/%s/types' % fake.PROJECT_ID,
                                      use_admin_context=True)
        res_dict = self.controller.index(req)

        self.assertEqual(3, len(res_dict['volume_types']))

        expected_names = ['vol_type_1', 'vol_type_2', 'vol_type_3']
        actual_names = map(lambda e: e['name'], res_dict['volume_types'])
        self.assertEqual(set(expected_names), set(actual_names))
        for entry in res_dict['volume_types']:
            self.assertEqual('value1', entry['extra_specs']['key1'])
        self.mock_authorize.assert_any_call(type_policy.GET_ALL_POLICY)

    def test_volume_types_index_no_data(self):
        self.mock_object(volume_types, 'get_all_types',
                         return_empty_volume_types_get_all_types)

        req = fakes.HTTPRequest.blank('/v3/%s/types' % fake.PROJECT_ID)
        res_dict = self.controller.index(req)

        self.assertEqual(0, len(res_dict['volume_types']))

    def test_volume_types_index_with_limit(self):
        req = fakes.HTTPRequest.blank('/v3/%s/types?limit=1' % fake.PROJECT_ID)
        req.environ['cinder.context'] = self.ctxt
        res = self.controller.index(req)

        self.assertEqual(1, len(res['volume_types']))
        self.assertEqual(self.type_id3, res['volume_types'][0]['id'])

        expect_next_link = ('http://localhost/v3/%s/types?limit=1'
                            '&marker=%s' %
                            (fake.PROJECT_ID, res['volume_types'][0]['id']))
        self.assertEqual(expect_next_link, res['volume_type_links'][0]['href'])

    def test_volume_types_index_with_offset(self):
        req = fakes.HTTPRequest.blank(
            '/v3/%s/types?offset=1' % fake.PROJECT_ID)
        req.environ['cinder.context'] = self.ctxt
        res = self.controller.index(req)

        self.assertEqual(3, len(res['volume_types']))

    def test_volume_types_index_with_offset_out_of_range(self):
        url = '/v3/%s/types?offset=424366766556787' % fake.PROJECT_ID
        req = fakes.HTTPRequest.blank(url)
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.controller.index, req)

    def test_volume_types_index_with_limit_and_offset(self):
        req = fakes.HTTPRequest.blank(
            '/v3/%s/types?limit=2&offset=1' % fake.PROJECT_ID)
        req.environ['cinder.context'] = self.ctxt
        res = self.controller.index(req)

        self.assertEqual(2, len(res['volume_types']))
        self.assertEqual(self.type_id2, res['volume_types'][0]['id'])
        self.assertEqual(self.type_id1, res['volume_types'][1]['id'])

    def test_volume_types_index_with_limit_and_marker(self):
        req = fakes.HTTPRequest.blank('/v3/%s/types?limit=1'
                                      '&marker=%s' %
                                      (fake.PROJECT_ID,
                                       self.type_id2))
        req.environ['cinder.context'] = self.ctxt
        res = self.controller.index(req)

        self.assertEqual(1, len(res['volume_types']))
        self.assertEqual(self.type_id1, res['volume_types'][0]['id'])

    def test_volume_types_index_with_valid_filter(self):
        req = fakes.HTTPRequest.blank(
            '/v3/%s/types?is_public=True' % fake.PROJECT_ID)
        req.environ['cinder.context'] = self.ctxt
        res = self.controller.index(req)

        self.assertEqual(4, len(res['volume_types']))
        self.assertEqual(self.type_id3, res['volume_types'][0]['id'])
        self.assertEqual(self.type_id2, res['volume_types'][1]['id'])
        self.assertEqual(self.type_id1, res['volume_types'][2]['id'])

    def test_volume_types_index_with_invalid_filter(self):
        req = fakes.HTTPRequest.blank(
            '/v3/%s/types?id=%s' % (fake.PROJECT_ID, self.type_id1))
        req.environ['cinder.context'] = context.RequestContext(
            user_id=fake.USER_ID, project_id=fake.PROJECT_ID, is_admin=False)
        res = self.controller.index(req)

        self.assertEqual(4, len(res['volume_types']))

    def test_volume_types_index_with_sort_keys(self):
        req = fakes.HTTPRequest.blank('/v3/%s/types?sort=id' % fake.PROJECT_ID)
        req.environ['cinder.context'] = self.ctxt
        res = self.controller.index(req)
        expect_result = [self.default_type, self.type_id1,
                         self.type_id2, self.type_id3]
        expect_result.sort(reverse=True)

        self.assertEqual(4, len(res['volume_types']))
        self.assertEqual(expect_result[0], res['volume_types'][0]['id'])
        self.assertEqual(expect_result[1], res['volume_types'][1]['id'])
        self.assertEqual(expect_result[2], res['volume_types'][2]['id'])
        self.assertEqual(expect_result[3], res['volume_types'][3]['id'])

    def test_volume_types_index_with_sort_and_limit(self):
        req = fakes.HTTPRequest.blank(
            '/v3/%s/types?sort=id&limit=2' % fake.PROJECT_ID)
        req.environ['cinder.context'] = self.ctxt
        res = self.controller.index(req)

        expect_result = [self.default_type, self.type_id1,
                         self.type_id2, self.type_id3]
        expect_result.sort(reverse=True)

        self.assertEqual(2, len(res['volume_types']))
        self.assertEqual(expect_result[0], res['volume_types'][0]['id'])
        self.assertEqual(expect_result[1], res['volume_types'][1]['id'])

    def test_volume_types_index_with_sort_keys_and_sort_dirs(self):
        req = fakes.HTTPRequest.blank(
            '/v3/%s/types?sort=id:asc' % fake.PROJECT_ID)
        req.environ['cinder.context'] = self.ctxt
        res = self.controller.index(req)
        expect_result = [self.default_type, self.type_id1,
                         self.type_id2, self.type_id3]
        expect_result.sort()

        self.assertEqual(4, len(res['volume_types']))
        self.assertEqual(expect_result[0], res['volume_types'][0]['id'])
        self.assertEqual(expect_result[1], res['volume_types'][1]['id'])
        self.assertEqual(expect_result[2], res['volume_types'][2]['id'])
        self.assertEqual(expect_result[3], res['volume_types'][3]['id'])

    def test_volume_types_show(self):
        self.mock_object(volume_types, 'get_volume_type',
                         return_volume_types_get_volume_type)

        type_id = fake.VOLUME_TYPE_ID
        req = fakes.HTTPRequest.blank('/v3/%s/types/' % fake.PROJECT_ID
                                      + type_id)
        res_dict = self.controller.show(req, type_id)

        self.assertEqual(1, len(res_dict))
        self.assertEqual(type_id, res_dict['volume_type']['id'])
        type_name = 'vol_type_' + type_id
        self.assertEqual(type_name, res_dict['volume_type']['name'])
        self.mock_authorize.assert_any_call(
            type_policy.GET_POLICY, target_obj=mock.ANY)

    def test_volume_types_show_not_found(self):
        self.mock_object(volume_types, 'get_volume_type',
                         return_volume_types_get_volume_type)

        req = fakes.HTTPRequest.blank('/v3/%s/types/%s' %
                                      (fake.PROJECT_ID,
                                       fake.WILL_NOT_BE_FOUND_ID))
        self.assertRaises(exception.VolumeTypeNotFound, self.controller.show,
                          req, fake.WILL_NOT_BE_FOUND_ID)

    def test_get_default(self):
        self.mock_object(volume_types, 'get_default_volume_type',
                         return_volume_types_get_default)
        req = fakes.HTTPRequest.blank('/v3/%s/types/default' % fake.PROJECT_ID)
        req.method = 'GET'
        res_dict = self.controller.show(req, 'default')
        self.assertEqual(1, len(res_dict))
        self.assertEqual('vol_type_1', res_dict['volume_type']['name'])
        self.assertEqual('vol_type_desc_1',
                         res_dict['volume_type']['description'])

    def test_get_default_not_found(self):
        self.mock_object(volume_types, 'get_default_volume_type',
                         return_value={})
        req = fakes.HTTPRequest.blank('/v3/%s/types/default' % fake.PROJECT_ID)
        req.method = 'GET'

        self.assertRaises(exception.VolumeTypeNotFound,
                          self.controller.show, req, 'default')

    @ddt.data(
        {
            'extra_spec_policy': False,
            'read_sensitive_policy': False,
            'qos_policy': False,
        },
        {
            'extra_spec_policy': True,
            'read_sensitive_policy': False,
            'qos_policy': False,
        },
        {
            'extra_spec_policy': True,
            'read_sensitive_policy': True,
            'qos_policy': False,
        },
        {
            'extra_spec_policy': False,
            'read_sensitive_policy': False,
            'qos_policy': True,
        },
        {
            'extra_spec_policy': True,
            'read_sensitive_policy': True,
            'qos_policy': True,
        },
    )
    @ddt.unpack
    def test_view_builder_show(self,
                               extra_spec_policy,
                               read_sensitive_policy,
                               qos_policy):
        # This function returns the authorization result supplied by the
        # DDT data for the associated policy.
        def authorize(policy, fatal):
            policy_data = {
                type_policy.EXTRA_SPEC_POLICY: extra_spec_policy,
                extra_specs_policy.READ_SENSITIVE_POLICY: (
                    read_sensitive_policy),
                type_policy.QOS_POLICY: qos_policy,
            }
            return policy_data[policy]

        view_builder = views_types.ViewBuilder()
        now = timeutils.utcnow().isoformat()
        raw_volume_type = dict(
            name='new_type',
            description='new_type_desc',
            qos_specs_id='new_id',
            is_public=True,
            deleted=False,
            created_at=now,
            updated_at=now,
            extra_specs={'multiattach': True, 'sensitive': 'secret'},
            deleted_at=None,
            id=42,
        )

        request = fakes.HTTPRequest.blank("/v3")
        with mock.patch('cinder.context.RequestContext.authorize',
                        side_effect=authorize):
            output = view_builder.show(request, raw_volume_type)

        self.assertIn('volume_type', output)
        expected_volume_type = dict(
            name='new_type',
            description='new_type_desc',
            is_public=True,
            id=42,
        )
        if extra_spec_policy:
            expected_volume_type['extra_specs'] = {'multiattach': True}
            if read_sensitive_policy:
                expected_volume_type['extra_specs']['sensitive'] = 'secret'
        if qos_policy:
            expected_volume_type['qos_specs_id'] = 'new_id'

        self.assertDictEqual(expected_volume_type, output['volume_type'])

    @ddt.data(False, True)
    def test_view_builder_list(self, is_admin):
        view_builder = views_types.ViewBuilder()
        self.mock_authorize.return_value = is_admin
        now = timeutils.utcnow().isoformat()
        raw_volume_types = []
        for i in range(0, 10):
            raw_volume_types.append(
                dict(
                    name='new_type',
                    description='new_type_desc',
                    qos_specs_id='new_id',
                    is_public=True,
                    deleted=False,
                    created_at=now,
                    updated_at=now,
                    extra_specs={'multiattach': True, 'sensitive': 'secret'},
                    deleted_at=None,
                    id=42 + i
                )
            )

        request = fakes.HTTPRequest.blank("/v3")
        output = view_builder.index(request, raw_volume_types)

        self.assertIn('volume_types', output)
        for i in range(0, 10):
            expected_volume_type = dict(
                name='new_type',
                description='new_type_desc',
                is_public=True,
                id=42 + i
            )
            if is_admin:
                expected_volume_type['qos_specs_id'] = 'new_id'
                expected_volume_type['extra_specs'] = {'multiattach': True,
                                                       'sensitive': 'secret'}
            self.assertDictEqual(expected_volume_type,
                                 output['volume_types'][i])
