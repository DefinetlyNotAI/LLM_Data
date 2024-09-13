# Copyright 2013 NetApp
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

"""The share snapshots api."""

import ast
from http import client as http_client

from oslo_log import log
import webob
from webob import exc

from manila.api import common
from manila.api.openstack import api_version_request as api_version
from manila.api.openstack import wsgi
from manila.api.views import share_snapshots as snapshot_views
from manila import db
from manila import exception
from manila.i18n import _
from manila import policy
from manila import share
from manila import utils

LOG = log.getLogger(__name__)


class ShareSnapshotMixin(object):
    """Mixin class for Share Snapshot Controllers."""

    def _update(self, *args, **kwargs):
        db.share_snapshot_update(*args, **kwargs)

    def _get(self, *args, **kwargs):
        return self.share_api.get_snapshot(*args, **kwargs)

    def _delete(self, *args, **kwargs):
        return self.share_api.delete_snapshot(*args, **kwargs)

    def show(self, req, id):
        """Return data about the given snapshot."""
        context = req.environ['manila.context']

        try:
            snapshot = self.share_api.get_snapshot(context, id)

            # Snapshot with no instances is filtered out.
            if snapshot.get('status') is None:
                raise exc.HTTPNotFound()
        except exception.NotFound:
            raise exc.HTTPNotFound()

        return self._view_builder.detail(req, snapshot)

    def delete(self, req, id):
        """Delete a snapshot."""
        context = req.environ['manila.context']

        LOG.info("Delete snapshot with id: %s", id, context=context)
        policy.check_policy(context, 'share', 'delete_snapshot')

        try:
            snapshot = self.share_api.get_snapshot(context, id)
            self.share_api.delete_snapshot(context, snapshot)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        return webob.Response(status_int=http_client.ACCEPTED)

    def index(self, req):
        """Returns a summary list of snapshots."""
        req.GET.pop('name~', None)
        req.GET.pop('description~', None)
        req.GET.pop('description', None)
        return self._get_snapshots(req, is_detail=False)

    def detail(self, req):
        """Returns a detailed list of snapshots."""
        req.GET.pop('name~', None)
        req.GET.pop('description~', None)
        req.GET.pop('description', None)
        return self._get_snapshots(req, is_detail=True)

    def _get_snapshots(self, req, is_detail):
        """Returns a list of snapshots."""
        context = req.environ['manila.context']

        search_opts = {}
        search_opts.update(req.GET)
        params = common.get_pagination_params(req)
        limit, offset = [params.get('limit'), params.get('offset')]

        # Remove keys that are not related to share attrs
        search_opts.pop('limit', None)
        search_opts.pop('offset', None)

        show_count = False
        if 'with_count' in search_opts:
            show_count = utils.get_bool_from_api_params(
                'with_count', search_opts)
            search_opts.pop('with_count')

        sort_key, sort_dir = common.get_sort_params(search_opts)
        key_dict = {"name": "display_name",
                    "description": "display_description"}
        for key in key_dict:
            if sort_key == key:
                sort_key = key_dict[key]

        # NOTE(vponomaryov): Manila stores in DB key 'display_name', but
        # allows to use both keys 'name' and 'display_name'. It is leftover
        # from Cinder v1 and v2 APIs.
        if 'name' in search_opts:
            search_opts['display_name'] = search_opts.pop('name')
        if 'description' in search_opts:
            search_opts['display_description'] = search_opts.pop(
                'description')

        # Deserialize dicts
        if req.api_version_request >= api_version.APIVersionRequest("2.73"):
            if 'metadata' in search_opts:
                try:
                    search_opts['metadata'] = ast.literal_eval(
                        search_opts['metadata'])
                except ValueError:
                    msg = _('Invalid value for metadata filter.')
                    raise webob.exc.HTTPBadRequest(explanation=msg)
        else:
            search_opts.pop('metadata', None)

        # like filter
        for key, db_key in (('name~', 'display_name~'),
                            ('description~', 'display_description~')):
            if key in search_opts:
                search_opts[db_key] = search_opts.pop(key)

        common.remove_invalid_options(context, search_opts,
                                      self._get_snapshots_search_options())

        total_count = None
        if show_count:
            count, snapshots = self.share_api.get_all_snapshots_with_count(
                context, search_opts=search_opts, limit=limit, offset=offset,
                sort_key=sort_key, sort_dir=sort_dir)
            total_count = count
        else:
            snapshots = self.share_api.get_all_snapshots(
                context, search_opts=search_opts, limit=limit, offset=offset,
                sort_key=sort_key, sort_dir=sort_dir)

        if is_detail:
            snapshots = self._view_builder.detail_list(
                req, snapshots, total_count)
        else:
            snapshots = self._view_builder.summary_list(
                req, snapshots, total_count)
        return snapshots

    def _get_snapshots_search_options(self):
        """Return share snapshot search options allowed by non-admin."""
        return ('display_name', 'status', 'share_id', 'size', 'display_name~',
                'display_description~', 'display_description', 'metadata')

    def update(self, req, id, body):
        """Update a snapshot."""
        context = req.environ['manila.context']
        policy.check_policy(context, 'share', 'snapshot_update')

        if not body or 'snapshot' not in body:
            raise exc.HTTPUnprocessableEntity()

        snapshot_data = body['snapshot']
        valid_update_keys = (
            'display_name',
            'display_description',
        )

        update_dict = {key: snapshot_data[key]
                       for key in valid_update_keys
                       if key in snapshot_data}

        common.check_display_field_length(
            update_dict.get('display_name'), 'display_name')
        common.check_display_field_length(
            update_dict.get('display_description'), 'display_description')

        try:
            snapshot = self.share_api.get_snapshot(context, id)
        except exception.NotFound:
            raise exc.HTTPNotFound()

        snapshot = self.share_api.snapshot_update(context, snapshot,
                                                  update_dict)
        snapshot.update(update_dict)
        return self._view_builder.detail(req, snapshot)

    @wsgi.response(202)
    def create(self, req, body):
        """Creates a new snapshot."""
        context = req.environ['manila.context']

        if not self.is_valid_body(body, 'snapshot'):
            raise exc.HTTPUnprocessableEntity()

        snapshot = body['snapshot']

        share_id = snapshot['share_id']
        share = self.share_api.get(context, share_id)

        # Verify that share can be snapshotted
        if not share['snapshot_support']:
            msg = _("Snapshots cannot be created for share '%s' "
                    "since it does not have that capability.") % share_id
            LOG.error(msg)
            raise exc.HTTPUnprocessableEntity(explanation=msg)

        # we do not allow soft delete share with snapshot, and also
        # do not allow create snapshot for shares in recycle bin,
        # since it will lead to auto delete share failed.
        if share['is_soft_deleted']:
            msg = _("Snapshots cannot be created for share '%s' "
                    "since it has been soft deleted.") % share_id
            raise exc.HTTPForbidden(explanation=msg)

        LOG.info("Create snapshot from share %s",
                 share_id, context=context)

        # NOTE(rushiagr): v2 API allows name instead of display_name
        if 'name' in snapshot:
            snapshot['display_name'] = snapshot.get('name')
            common.check_display_field_length(
                snapshot['display_name'], 'name')
            del snapshot['name']

        # NOTE(rushiagr): v2 API allows description instead of
        #                display_description
        if 'description' in snapshot:
            snapshot['display_description'] = snapshot.get('description')
            common.check_display_field_length(
                snapshot['display_description'], 'description')
            del snapshot['description']

        kwargs = {}
        if req.api_version_request >= api_version.APIVersionRequest("2.73"):
            if snapshot.get('metadata'):
                metadata = snapshot.get('metadata')
                kwargs.update({
                    'metadata': metadata,
                })

        new_snapshot = self.share_api.create_snapshot(
            context,
            share,
            snapshot.get('display_name'),
            snapshot.get('display_description'),
            **kwargs)
        return self._view_builder.detail(
            req, dict(new_snapshot.items()))


class ShareSnapshotsController(ShareSnapshotMixin, wsgi.Controller,
                               wsgi.AdminActionsMixin):
    """The Share Snapshots API controller for the OpenStack API."""

    resource_name = 'share_snapshot'
    _view_builder_class = snapshot_views.ViewBuilder

    def __init__(self):
        super(ShareSnapshotsController, self).__init__()
        self.share_api = share.API()

    @wsgi.action('os-reset_status')
    def snapshot_reset_status_legacy(self, req, id, body):
        return self._reset_status(req, id, body)

    @wsgi.action('os-force_delete')
    def snapshot_force_delete_legacy(self, req, id, body):
        return self._force_delete(req, id, body)


def create_resource():
    return wsgi.Resource(ShareSnapshotsController())
