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

from keystoneauth1.identity.generic import password
from keystoneauth1 import loading as ks_loading
from keystoneauth1 import service_token

from cinder import context
from cinder import exception
from cinder import service_auth
from cinder.tests.unit import test


class ServiceAuthTestCase(test.TestCase):

    def setUp(self):
        super(ServiceAuthTestCase, self).setUp()
        self.ctx = context.RequestContext('fake', 'fake')
        service_auth.reset_globals()

    @mock.patch.object(ks_loading, 'load_auth_from_conf_options')
    def test_get_auth_plugin_no_wraps(self, mock_load):
        context = mock.MagicMock()
        context.get_auth_plugin.return_value = "fake"

        result = service_auth.get_auth_plugin(context)

        self.assertEqual("fake", result)
        mock_load.assert_not_called()

    @mock.patch.object(ks_loading, 'load_auth_from_conf_options')
    def test_get_auth_plugin_wraps(self, mock_load):
        self.flags(send_service_user_token=True, group='service_user')
        result = service_auth.get_auth_plugin(self.ctx)

        self.assertIsInstance(result, service_token.ServiceTokenAuthWrapper)
        mock_load.assert_called_once_with(mock.ANY, group='service_user')

    def test_service_auth_requested_but_no_auth_given(self):
        self.flags(send_service_user_token=True, group='service_user')

        self.assertRaises(exception.ServiceUserTokenNoAuth,
                          service_auth.get_auth_plugin, self.ctx)

    @mock.patch.object(ks_loading, 'load_auth_from_conf_options')
    def test_get_auth_plugin_with_auth(self, mock_load):
        self.flags(send_service_user_token=True, group='service_user')

        mock_load.return_value = password.Password
        result = service_auth.get_auth_plugin(
            self.ctx, auth=mock_load.return_value)

        self.assertEqual(mock_load.return_value, result.user_auth)
        self.assertIsInstance(result, service_token.ServiceTokenAuthWrapper)
        mock_load.assert_called_once_with(mock.ANY, group='service_user')

    def test_get_auth_plugin_with_auth_and_service_token_false(self):
        self.flags(send_service_user_token=False, group='service_user')

        n_auth = password.Password
        result = service_auth.get_auth_plugin(self.ctx, auth=n_auth)

        self.assertEqual(n_auth, result)
