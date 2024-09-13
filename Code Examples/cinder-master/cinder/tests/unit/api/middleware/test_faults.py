# Copyright 2010 OpenStack Foundation
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

from oslo_i18n import fixture as i18n_fixture
from oslo_serialization import jsonutils
import webob.dec

from cinder.api.middleware import fault
from cinder.api.openstack import wsgi
from cinder.tests.unit import test


class TestFaults(test.TestCase):
    """Tests covering `cinder.api.openstack.faults:Fault` class."""

    def setUp(self):
        super(TestFaults, self).setUp()
        self.useFixture(i18n_fixture.ToggleLazy(True))

    def test_400_fault_json(self):
        """Test fault serialized to JSON via file-extension and/or header."""
        requests = [
            webob.Request.blank('/.json'),
            webob.Request.blank('/', headers={"Accept": "application/json"}),
        ]

        for request in requests:
            fault = wsgi.Fault(webob.exc.HTTPBadRequest(explanation='scram'))
            response = request.get_response(fault)

            expected = {
                "badRequest": {
                    "message": "scram",
                    "code": HTTPStatus.BAD_REQUEST,
                },
            }
            actual = jsonutils.loads(response.body)

            self.assertEqual("application/json", response.content_type)
            self.assertEqual(expected, actual)

    def test_413_fault_json(self):
        """Test fault serialized to JSON via file-extension and/or header."""
        requests = [
            webob.Request.blank('/.json'),
            webob.Request.blank('/', headers={"Accept": "application/json"}),
        ]

        for request in requests:
            exc = webob.exc.HTTPRequestEntityTooLarge
            fault = wsgi.Fault(exc(explanation='sorry',
                                   headers={'Retry-After': '4'}))
            response = request.get_response(fault)

            expected = {
                "overLimit": {
                    "message": "sorry",
                    "code": HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    "retryAfter": "4",
                },
            }
            actual = jsonutils.loads(response.body)

            self.assertEqual("application/json", response.content_type)
            self.assertEqual(expected, actual)

    def test_fault_has_status_int(self):
        """Ensure the status_int is set correctly on faults."""
        fault = wsgi.Fault(webob.exc.HTTPBadRequest(explanation='what?'))
        self.assertEqual(HTTPStatus.BAD_REQUEST, fault.status_int)


class ExceptionTest(test.TestCase):

    def _wsgi_app(self, inner_app):
        return fault.FaultWrapper(inner_app)

    def test_unicode_decode_error(self):
        @webob.dec.wsgify
        def unicode_error(req):
            raise UnicodeDecodeError("ascii", b"", 0, 1, "bad")

        api = self._wsgi_app(unicode_error)
        resp = webob.Request.blank('/').get_response(api)
        self.assertEqual(400, resp.status_int)
