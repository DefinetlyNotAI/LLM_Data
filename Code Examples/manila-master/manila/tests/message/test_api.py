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

import datetime
from unittest import mock

from oslo_config import cfg
from oslo_utils import timeutils

from manila import context
from manila.message import api as message_api
from manila.message.message_field import Action as MsgAction
from manila.message.message_field import Detail as MsgDetail
from manila.message import message_levels
from manila import test

CONF = cfg.CONF


class MessageApiTest(test.TestCase):
    def setUp(self):
        super(MessageApiTest, self).setUp()
        self.message_api = message_api.API()
        self.mock_object(self.message_api, 'db')
        self.ctxt = context.RequestContext('admin', 'fakeproject', True)
        self.ctxt.request_id = 'fakerequestid'

    @mock.patch.object(timeutils, 'utcnow')
    def test_create(self, mock_utcnow):
        CONF.set_override('message_ttl', 300)
        now = datetime.datetime.utcnow()
        mock_utcnow.return_value = now
        expected_expires_at = now + datetime.timedelta(
            seconds=300)
        expected_message_record = {
            'project_id': 'fakeproject',
            'request_id': 'fakerequestid',
            'resource_type': 'fake_resource_type',
            'resource_id': None,
            'action_id': MsgAction.ALLOCATE_HOST[0],
            'detail_id': MsgDetail.NO_VALID_HOST[0],
            'message_level': message_levels.ERROR,
            'expires_at': expected_expires_at,
        }

        self.message_api.create(self.ctxt,
                                MsgAction.ALLOCATE_HOST,
                                "fakeproject",
                                detail=MsgDetail.NO_VALID_HOST,
                                resource_type="fake_resource_type")

        self.message_api.db.message_create.assert_called_once_with(
            self.ctxt, expected_message_record)

    def test_create_swallows_exception(self):
        self.mock_object(self.message_api.db, 'message_create',
                         mock.Mock(side_effect=Exception()))
        exception_log = self.mock_object(message_api.LOG, 'exception')
        self.message_api.create(self.ctxt,
                                MsgAction.ALLOCATE_HOST,
                                'fakeproject',
                                'fake_resource')

        self.message_api.db.message_create.assert_called_once_with(
            self.ctxt, mock.ANY)
        exception_log.assert_called_once_with(
            'Failed to create message record for request_id %s',
            self.ctxt.request_id)

    def test_get(self):
        self.message_api.get(self.ctxt, 'fake_id')

        self.message_api.db.message_get.assert_called_once_with(self.ctxt,
                                                                'fake_id')

    def test_get_all(self):
        self.message_api.get_all(self.ctxt)

        self.message_api.db.message_get_all.assert_called_once_with(
            self.ctxt, filters={}, limit=None, offset=None,
            sort_dir=None, sort_key=None)

    def test_delete(self):
        self.message_api.delete(self.ctxt, 'fake_id')

        self.message_api.db.message_destroy.assert_called_once_with(
            self.ctxt, 'fake_id')

    def test_cleanup_expired_messages(self):
        admin_context = mock.Mock()
        self.mock_object(self.ctxt, 'elevated',
                         mock.Mock(return_value=admin_context))
        self.message_api.cleanup_expired_messages(self.ctxt)
        self.message_api.db.cleanup_expired_messages.assert_called_once_with(
            admin_context)
