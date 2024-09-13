# Copyright 2011 Justin Santa Barbara
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

"""The volumes snapshots api."""
from http import HTTPStatus

from oslo_log import log as logging
from oslo_utils import strutils
import webob

from cinder.api import api_utils
from cinder.api import common
from cinder.api.openstack import wsgi
from cinder.api.schemas import snapshots as snapshot
from cinder.api import validation
from cinder.api.views import snapshots as snapshot_views
from cinder import volume
from cinder.volume import volume_utils


LOG = logging.getLogger(__name__)


class SnapshotsController(wsgi.Controller):
    """The Snapshots API controller for the OpenStack API."""

    _view_builder_class = snapshot_views.ViewBuilder

    def __init__(self, ext_mgr=None):
        self.volume_api = volume.API()
        self.ext_mgr = ext_mgr
        super(SnapshotsController, self).__init__()

    def show(self, req, id):
        """Return data about the given snapshot."""
        context = req.environ['cinder.context']

        # Not found exception will be handled at the wsgi level
        snapshot = self.volume_api.get_snapshot(context, id)
        req.cache_db_snapshot(snapshot)

        return self._view_builder.detail(req, snapshot)

    def delete(self, req, id):
        """Delete a snapshot."""
        context = req.environ['cinder.context']

        LOG.info("Delete snapshot with id: %s", id)

        # Not found exception will be handled at the wsgi level
        snapshot = self.volume_api.get_snapshot(context, id)
        self.volume_api.delete_snapshot(context, snapshot)

        return webob.Response(status_int=HTTPStatus.ACCEPTED)

    def index(self, req):
        """Returns a summary list of snapshots."""
        return self._items(req, is_detail=False)

    def detail(self, req):
        """Returns a detailed list of snapshots."""
        return self._items(req, is_detail=True)

    def _items(self, req, is_detail=True):
        """Returns a list of snapshots, transformed through view builder."""
        context = req.environ['cinder.context']

        # Pop out non search_opts and create local variables
        search_opts = req.GET.copy()
        sort_keys, sort_dirs = common.get_sort_params(search_opts)
        marker, limit, offset = common.get_pagination_params(search_opts)

        # Filter out invalid options
        allowed_search_options = ('status', 'volume_id', 'name')
        api_utils.remove_invalid_filter_options(context, search_opts,
                                                allowed_search_options)

        # NOTE(thingee): v2 API allows name instead of display_name
        if 'name' in search_opts:
            search_opts['display_name'] = search_opts.pop('name')

        snapshots = self.volume_api.get_all_snapshots(context,
                                                      search_opts=search_opts,
                                                      marker=marker,
                                                      limit=limit,
                                                      sort_keys=sort_keys,
                                                      sort_dirs=sort_dirs,
                                                      offset=offset)

        req.cache_db_snapshots(snapshots.objects)

        if is_detail:
            snapshots = self._view_builder.detail_list(req, snapshots.objects)
        else:
            snapshots = self._view_builder.summary_list(req, snapshots.objects)
        return snapshots

    @wsgi.response(HTTPStatus.ACCEPTED)
    @validation.schema(snapshot.create)
    def create(self, req, body):
        """Creates a new snapshot."""
        kwargs = {}
        context = req.environ['cinder.context']
        snapshot = body['snapshot']
        kwargs['metadata'] = snapshot.get('metadata', None)
        volume_id = snapshot['volume_id']
        volume = self.volume_api.get(context, volume_id)
        force = snapshot.get('force', False)
        force = strutils.bool_from_string(force, strict=True)
        LOG.info("Create snapshot from volume %s", volume_id)

        self.validate_name_and_description(snapshot, check_length=False)
        # NOTE(thingee): v2 API allows name instead of display_name
        if 'name' in snapshot:
            snapshot['display_name'] = snapshot.pop('name')

        if force:
            new_snapshot = self.volume_api.create_snapshot_force(
                context,
                volume,
                snapshot.get('display_name'),
                snapshot.get('description'),
                **kwargs)
        else:
            new_snapshot = self.volume_api.create_snapshot(
                context,
                volume,
                snapshot.get('display_name'),
                snapshot.get('description'),
                **kwargs)
        req.cache_db_snapshot(new_snapshot)

        return self._view_builder.detail(req, new_snapshot)

    @validation.schema(snapshot.update)
    def update(self, req, id, body):
        """Update a snapshot."""
        context = req.environ['cinder.context']
        snapshot_body = body['snapshot']
        self.validate_name_and_description(snapshot_body, check_length=False)

        if 'name' in snapshot_body:
            snapshot_body['display_name'] = snapshot_body.pop('name')

        if 'description' in snapshot_body:
            snapshot_body['display_description'] = snapshot_body.pop(
                'description')

        # Not found exception will be handled at the wsgi level
        snapshot = self.volume_api.get_snapshot(context, id)
        volume_utils.notify_about_snapshot_usage(context, snapshot,
                                                 'update.start')
        self.volume_api.update_snapshot(context, snapshot, snapshot_body)

        snapshot.update(snapshot_body)
        req.cache_db_snapshot(snapshot)
        volume_utils.notify_about_snapshot_usage(context, snapshot,
                                                 'update.end')

        return self._view_builder.detail(req, snapshot)


def create_resource(ext_mgr):
    return wsgi.Resource(SnapshotsController(ext_mgr))
