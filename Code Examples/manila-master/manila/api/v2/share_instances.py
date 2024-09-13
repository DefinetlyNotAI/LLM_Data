# Copyright 2015 Mirantis Inc.
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

from webob import exc

from manila.api import common
from manila.api.openstack import wsgi
from manila.api.views import share_instance as instance_view
from manila import db
from manila import exception
from manila import share
from manila import utils


class ShareInstancesController(wsgi.Controller, wsgi.AdminActionsMixin):
    """The share instances API controller for the OpenStack API."""

    resource_name = 'share_instance'
    _view_builder_class = instance_view.ViewBuilder

    def __init__(self):
        self.share_api = share.API()
        super(ShareInstancesController, self).__init__()

    def _get(self, *args, **kwargs):
        return db.share_instance_get(*args, **kwargs)

    def _update(self, *args, **kwargs):
        db.share_instance_update(*args, **kwargs)

    def _delete(self, *args, **kwargs):
        return self.share_api.delete_instance(*args, **kwargs)

    @wsgi.Controller.api_version('2.3', '2.6')
    @wsgi.action('os-reset_status')
    def instance_reset_status_legacy(self, req, id, body):
        return self._reset_status(req, id, body)

    @wsgi.Controller.api_version('2.7')
    @wsgi.action('reset_status')
    def instance_reset_status(self, req, id, body):
        return self._reset_status(req, id, body)

    @wsgi.Controller.api_version('2.3', '2.6')
    @wsgi.action('os-force_delete')
    def instance_force_delete_legacy(self, req, id, body):
        return self._force_delete(req, id, body)

    @wsgi.Controller.api_version('2.7')
    @wsgi.action('force_delete')
    def instance_force_delete(self, req, id, body):
        return self._force_delete(req, id, body)

    @wsgi.Controller.api_version("2.3", "2.34")  # noqa
    @wsgi.Controller.authorize
    def index(self, req):  # pylint: disable=function-redefined
        context = req.environ['manila.context']

        req.GET.pop('export_location_id', None)
        req.GET.pop('export_location_path', None)
        instances = db.share_instance_get_all(context)
        return self._view_builder.detail_list(req, instances)

    @wsgi.Controller.api_version("2.35", "2.68")  # noqa
    @wsgi.Controller.authorize
    def index(self, req):  # pylint: disable=function-redefined  # noqa F811
        context = req.environ['manila.context']
        filters = {}
        filters.update(req.GET)
        common.remove_invalid_options(
            context, filters, ('export_location_id', 'export_location_path'))

        instances = db.share_instance_get_all(context, filters)
        return self._view_builder.detail_list(req, instances)

    @wsgi.Controller.api_version("2.69")  # noqa
    @wsgi.Controller.authorize
    def index(self, req):  # pylint: disable=function-redefined  # noqa F811
        context = req.environ['manila.context']
        filters = {}
        filters.update(req.GET)
        common.remove_invalid_options(
            context, filters, ('export_location_id', 'export_location_path',
                               'is_soft_deleted'))
        if 'is_soft_deleted' in filters:
            is_soft_deleted = utils.get_bool_from_api_params(
                'is_soft_deleted', filters)
            filters['is_soft_deleted'] = is_soft_deleted

        instances = db.share_instance_get_all(context, filters)
        return self._view_builder.detail_list(req, instances)

    @wsgi.Controller.api_version("2.3")
    @wsgi.Controller.authorize
    def show(self, req, id):
        context = req.environ['manila.context']

        try:
            instance = db.share_instance_get(context, id)
        except exception.NotFound:
            raise exc.HTTPNotFound()

        return self._view_builder.detail(req, instance)

    @wsgi.Controller.api_version("2.3")
    @wsgi.Controller.authorize('index')
    def get_share_instances(self, req, share_id):
        context = req.environ['manila.context']

        try:
            share = self.share_api.get(context, share_id)
        except exception.NotFound:
            raise exc.HTTPNotFound()

        view = instance_view.ViewBuilder()
        return view.detail_list(req, share.instances)


def create_resource():
    return wsgi.Resource(ShareInstancesController())
