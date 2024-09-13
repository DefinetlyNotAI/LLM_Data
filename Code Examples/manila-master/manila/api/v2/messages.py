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

"""The messages API controller module.

This module handles the following requests:
GET /messages
GET /messages/<message_id>
DELETE /messages/<message_id>
"""

from http import client as http_client

from oslo_utils import timeutils
import webob
from webob import exc

from manila.api import common
from manila.api.openstack import wsgi
from manila.api.schemas import messages as schema
from manila.api import validation
from manila.api.views import messages as messages_view
from manila import exception
from manila.i18n import _
from manila.message import api as message_api

MESSAGES_BASE_MICRO_VERSION = '2.37'
MESSAGES_QUERY_BY_TIMESTAMP = '2.52'


@validation.validated
class MessagesController(wsgi.Controller):
    """The User Messages API controller for the OpenStack API."""
    _view_builder_class = messages_view.ViewBuilder
    resource_name = 'message'

    def __init__(self):
        self.message_api = message_api.API()
        super(MessagesController, self).__init__()

    @wsgi.Controller.api_version(MESSAGES_BASE_MICRO_VERSION)
    @wsgi.Controller.authorize('get')
    @validation.request_query_schema(schema.show_request_query)
    @validation.response_body_schema(schema.show_response_body)
    def show(self, req, id):
        """Return the given message."""
        context = req.environ['manila.context']

        try:
            message = self.message_api.get(context, id)
        except exception.MessageNotFound as error:
            raise exc.HTTPNotFound(explanation=error.msg)

        return self._view_builder.detail(req, message)

    @wsgi.Controller.api_version(MESSAGES_BASE_MICRO_VERSION)
    @wsgi.Controller.authorize
    @wsgi.action("delete")
    @validation.response_body_schema(schema.delete_response_body)
    def delete(self, req, id):
        """Delete a message."""
        context = req.environ['manila.context']

        try:
            message = self.message_api.get(context, id)
            self.message_api.delete(context, message)
        except exception.MessageNotFound as error:
            raise exc.HTTPNotFound(explanation=error.msg)

        return webob.Response(status_int=http_client.NO_CONTENT)

    @wsgi.Controller.api_version(MESSAGES_BASE_MICRO_VERSION, '2.51')
    @wsgi.Controller.authorize('get_all')
    @validation.request_query_schema(schema.index_request_query)
    @validation.response_body_schema(schema.index_response_body)
    def index(self, req):
        """Returns a list of messages, transformed through view builder."""
        context = req.environ['manila.context']
        filters = req.params.copy()

        params = common.get_pagination_params(req)
        limit, offset = [params.get('limit'), params.get('offset')]
        sort_key, sort_dir = common.get_sort_params(filters)
        filters.pop('created_since', None)
        filters.pop('created_before', None)

        messages = self.message_api.get_all(context, search_opts=filters,
                                            limit=limit,
                                            offset=offset,
                                            sort_key=sort_key,
                                            sort_dir=sort_dir)

        return self._view_builder.index(req, messages)

    @wsgi.Controller.api_version(MESSAGES_QUERY_BY_TIMESTAMP)   # noqa: F811
    @wsgi.Controller.authorize('get_all')
    @validation.request_query_schema(schema.index_request_query_v252)
    @validation.response_body_schema(schema.index_response_body)
    def index(self, req):  # pylint: disable=function-redefined  # noqa F811
        """Returns a list of messages, transformed through view builder."""
        context = req.environ['manila.context']
        filters = req.params.copy()

        params = common.get_pagination_params(req)
        limit, offset = [params.get('limit'), params.get('offset')]
        sort_key, sort_dir = common.get_sort_params(filters)

        for time_comparison_filter in ['created_since', 'created_before']:
            if time_comparison_filter in filters:
                time_str = filters.get(time_comparison_filter)
                try:
                    parsed_time = timeutils.parse_isotime(time_str)
                except ValueError:
                    msg = _('Invalid value specified for the query '
                            'key: %s') % time_comparison_filter
                    raise exc.HTTPBadRequest(explanation=msg)

                filters[time_comparison_filter] = parsed_time

        messages = self.message_api.get_all(context, search_opts=filters,
                                            limit=limit,
                                            offset=offset,
                                            sort_key=sort_key,
                                            sort_dir=sort_dir)

        return self._view_builder.index(req, messages)


def create_resource():
    return wsgi.Resource(MessagesController())
