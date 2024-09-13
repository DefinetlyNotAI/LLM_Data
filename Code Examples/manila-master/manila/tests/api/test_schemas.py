# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import jsonschema.exceptions

from manila.api.v2 import router
from manila.api.validation import validators
from manila import test


class SchemaTest(test.TestCase):

    def setUp(self):
        super().setUp()
        self.router = router.APIRouter()
        self.meta_schema = validators._SchemaValidator.validator_org

    def test_schemas(self):
        missing_request_schemas = set()
        missing_query_schemas = set()
        missing_response_schemas = set()
        invalid_schemas = set()

        def _validate_schema(func, schema):
            try:
                self.meta_schema.check_schema(schema)
            except jsonschema.exceptions.SchemaError:
                invalid_schemas.add(func.__qualname__)

        def _validate_func(func, method):
            if getattr(func, 'removed', False):
                return

            if method in ("POST", "PUT", "PATCH"):
                # request body validation
                if not hasattr(func, '_request_body_schema'):
                    missing_request_schemas.add(func.__qualname__)
                else:
                    _validate_schema(func, func._request_body_schema)
            elif method in ("GET",):
                # request query string validation
                if not hasattr(func, '_request_query_schema'):
                    missing_query_schemas.add(func.__qualname__)
                else:
                    _validate_schema(func, func._request_query_schema)

            # response body validation
            if not hasattr(func, '_response_body_schema'):
                missing_response_schemas.add(func.__qualname__)
            else:
                _validate_schema(func, func._response_body_schema)

        for route in self.router.map.matchlist:
            if 'controller' not in route.defaults:
                continue

            controller = route.defaults['controller']

            if not getattr(controller.controller, '_validated', False):
                continue

            # NOTE: This is effectively a reimplementation of
            # 'routes.route.Route.make_full_route' that uses OpenAPI-compatible
            # template strings instead of regexes for paramters
            path = ""
            for part in route.routelist:
                if isinstance(part, dict):
                    path += "{" + part["name"] + "}"
                else:
                    path += part

            method = (
                route.conditions.get("method", "GET")[0]
                if route.conditions
                else "GET"
            )
            action = route.defaults["action"]

            if path.endswith('/action'):
                # all actions should use POST
                assert method == 'POST'

                wsgi_actions = [
                    (k, v, controller.controller) for k, v in
                    controller.controller.wsgi_actions.items()
                ]

                for (
                    wsgi_action, wsgi_method, action_controller
                ) in wsgi_actions:
                    versioned_methods = getattr(
                        action_controller, 'versioned_methods', {}
                    )
                    if wsgi_method in versioned_methods:
                        # versioned method
                        for versioned_method in sorted(
                            versioned_methods[action],
                            key=lambda v: v.start_version
                        ):
                            func = versioned_method.func
                            _validate_func(func, method)
                    else:
                        # unversioned method
                        func = controller.wsgi_actions[wsgi_action]
                        _validate_func(func, method)
            else:
                # body validation
                versioned_methods = getattr(
                    controller.controller, 'versioned_methods', {}
                )
                if action in versioned_methods:
                    # versioned method
                    for versioned_method in sorted(
                        versioned_methods[action],
                        key=lambda v: v.start_version
                    ):
                        func = versioned_method.func
                        _validate_func(func, method)
                else:
                    if not hasattr(controller.controller, action):
                        # these are almost certainly because of use of
                        # routes.mapper.Mapper.resource, which we should remove
                        continue

                    # unversioned method
                    func = getattr(controller.controller, action)
                    _validate_func(func, method)

        if missing_request_schemas:
            raise self.failureException(
                f"Found API resources without request body schemas: "
                f"{sorted(missing_request_schemas)}"
            )

        if missing_query_schemas:
            raise self.failureException(
                f"Found API resources without request query schemas: "
                f"{sorted(missing_query_schemas)}"
            )

        if missing_response_schemas:
            raise self.failureException(
                f"Found API resources without response body schemas: "
                f"{sorted(missing_response_schemas)}"
            )
