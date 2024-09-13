# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (c) 2014 TrilioData, Inc
# Copyright (c) 2015 EMC Corporation
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

"""The backups api."""
from http import HTTPStatus

from oslo_log import log as logging
from oslo_utils import strutils
from webob import exc

from cinder.api import api_utils
from cinder.api import common
from cinder.api import extensions
from cinder.api import microversions as mv
from cinder.api.openstack import wsgi
from cinder.api.schemas import backups as backup
from cinder.api import validation
from cinder.api.views import backups as backup_views
from cinder import backup as backupAPI
from cinder import exception
from cinder import utils
from cinder import volume as volumeAPI

LOG = logging.getLogger(__name__)


class BackupsController(wsgi.Controller):
    """The Backups API controller for the OpenStack API."""

    _view_builder_class = backup_views.ViewBuilder

    def __init__(self):
        self.backup_api = backupAPI.API()
        self.volume_api = volumeAPI.API()
        super(BackupsController, self).__init__()

    def show(self, req, id):
        """Return data about the given backup."""
        LOG.debug('Show backup with id: %s.', id)
        context = req.environ['cinder.context']

        # Not found exception will be handled at the wsgi level
        backup = self.backup_api.get(context, backup_id=id)
        req.cache_db_backup(backup)

        return self._view_builder.detail(req, backup)

    @wsgi.response(HTTPStatus.ACCEPTED)
    def delete(self, req, id):
        """Delete a backup."""
        context = req.environ['cinder.context']

        LOG.info('Delete backup with id: %s.', id)

        try:
            backup = self.backup_api.get(context, id)
            self.backup_api.delete(context, backup)
        # Not found exception will be handled at the wsgi level
        except exception.InvalidBackup as error:
            raise exc.HTTPBadRequest(explanation=error.msg)

    def index(self, req):
        """Returns a summary list of backups."""
        return self._get_backups(req, is_detail=False)

    def detail(self, req):
        """Returns a detailed list of backups."""
        return self._get_backups(req, is_detail=True)

    @staticmethod
    def _get_backup_filter_options():
        """Return volume search options allowed by non-admin."""
        return ('name', 'status', 'volume_id')

    @common.process_general_filtering('backup')
    def _process_backup_filtering(self, context=None, filters=None,
                                  req_version=None):
        api_utils.remove_invalid_filter_options(
            context,
            filters,
            self._get_backup_filter_options())

    def _convert_sort_name(self, req_version, sort_keys):
        """Convert sort key "name" to "display_name". """
        pass

    def _get_backups(self, req, is_detail):
        """Returns a list of backups, transformed through view builder."""
        context = req.environ['cinder.context']
        filters = req.params.copy()
        req_version = req.api_version_request
        marker, limit, offset = common.get_pagination_params(filters)
        sort_keys, sort_dirs = common.get_sort_params(filters)

        show_count = False
        if req_version.matches(
                mv.SUPPORT_COUNT_INFO) and 'with_count' in filters:
            show_count = utils.get_bool_param('with_count', filters)
            filters.pop('with_count')
        self._convert_sort_name(req_version, sort_keys)
        self._process_backup_filtering(context=context, filters=filters,
                                       req_version=req_version)

        if 'name' in filters:
            filters['display_name'] = filters.pop('name')

        backups = self.backup_api.get_all(context, search_opts=filters.copy(),
                                          marker=marker,
                                          limit=limit,
                                          offset=offset,
                                          sort_keys=sort_keys,
                                          sort_dirs=sort_dirs,
                                          )

        total_count = None
        if show_count:
            total_count = self.volume_api.calculate_resource_count(
                context, 'backup', filters)
        req.cache_db_backups(backups.objects)

        if is_detail:
            backups = self._view_builder.detail_list(req, backups.objects,
                                                     total_count)
        else:
            backups = self._view_builder.summary_list(req, backups.objects,
                                                      total_count)
        return backups

    # TODO(frankm): Add some checks here including
    # - whether requested volume_id exists so we can return some errors
    #   immediately
    # - maybe also do validation of swift container name
    @wsgi.response(HTTPStatus.ACCEPTED)
    @validation.schema(backup.create, mv.BASE_VERSION,
                       mv.get_prior_version(mv.BACKUP_METADATA))
    @validation.schema(backup.create_backup_v343, mv.BACKUP_METADATA,
                       mv.get_prior_version(mv.BACKUP_AZ))
    @validation.schema(backup.create_backup_v351, mv.BACKUP_AZ)
    def create(self, req, body):
        """Create a new backup."""
        LOG.debug('Creating new backup %s', body)

        context = req.environ['cinder.context']
        req_version = req.api_version_request

        backup = body['backup']
        container = backup.get('container', None)
        volume_id = backup['volume_id']

        self.validate_name_and_description(backup, check_length=False)
        name = backup.get('name', None)
        description = backup.get('description', None)
        incremental = strutils.bool_from_string(backup.get(
            'incremental', False), strict=True)
        force = strutils.bool_from_string(backup.get(
            'force', False), strict=True)
        snapshot_id = backup.get('snapshot_id', None)
        metadata = backup.get('metadata', None) if req_version.matches(
            mv.BACKUP_METADATA) else None

        if req_version.matches(mv.BACKUP_AZ):
            availability_zone = backup.get('availability_zone', None)
        else:
            availability_zone = None
        az_text = ' in az %s' % availability_zone if availability_zone else ''

        LOG.info("Creating backup of volume %(volume_id)s in container"
                 " %(container)s%(az)s",
                 {'volume_id': volume_id, 'container': container,
                  'az': az_text},
                 context=context)

        try:
            new_backup = self.backup_api.create(context, name, description,
                                                volume_id, container,
                                                incremental, availability_zone,
                                                force, snapshot_id, metadata)
        except (exception.InvalidVolume,
                exception.InvalidSnapshot,
                exception.InvalidVolumeMetadata,
                exception.InvalidVolumeMetadataSize) as error:
            raise exc.HTTPBadRequest(explanation=error.msg)
        # Other not found exceptions will be handled at the wsgi level
        except exception.ServiceNotFound as error:
            raise exc.HTTPServiceUnavailable(explanation=error.msg)

        retval = self._view_builder.summary(req, dict(new_backup))
        return retval

    @wsgi.response(HTTPStatus.ACCEPTED)
    @validation.schema(backup.restore)
    def restore(self, req, id, body):
        """Restore an existing backup to a volume."""
        LOG.debug('Restoring backup %(backup_id)s (%(body)s)',
                  {'backup_id': id, 'body': body})

        context = req.environ['cinder.context']
        restore = body['restore']
        volume_id = restore.get('volume_id', None)
        name = restore.get('name', None)

        LOG.info("Restoring backup %(backup_id)s to volume %(volume_id)s.",
                 {'backup_id': id, 'volume_id': volume_id},
                 context=context)

        try:
            new_restore = self.backup_api.restore(context,
                                                  backup_id=id,
                                                  volume_id=volume_id,
                                                  name=name)
        # Not found exception will be handled at the wsgi level
        except (exception.InvalidInput,
                exception.InvalidVolume,
                exception.InvalidBackup) as error:
            raise exc.HTTPBadRequest(explanation=error.msg)
        except (exception.VolumeSizeExceedsAvailableQuota,
                exception.VolumeLimitExceeded) as error:
            raise exc.HTTPRequestEntityTooLarge(
                explanation=error.msg, headers={'Retry-After': '0'})

        retval = self._view_builder.restore_summary(
            req, dict(new_restore))
        return retval

    def export_record(self, req, id):
        """Export a backup."""
        LOG.debug('Export record for backup %s.', id)
        context = req.environ['cinder.context']

        try:
            backup_info = self.backup_api.export_record(context, id)
        # Not found exception will be handled at the wsgi level
        except exception.InvalidBackup as error:
            raise exc.HTTPBadRequest(explanation=error.msg)

        retval = self._view_builder.export_summary(
            req, dict(backup_info))
        LOG.debug('Exported record output: %s.', retval)
        return retval

    @wsgi.response(HTTPStatus.CREATED)
    @validation.schema(backup.import_record)
    def import_record(self, req, body):
        """Import a backup."""
        LOG.debug('Importing record from %s.', body)
        context = req.environ['cinder.context']
        import_data = body['backup-record']
        backup_service = import_data['backup_service']
        backup_url = import_data['backup_url']

        LOG.debug('Importing backup using %(service)s and url %(url)s.',
                  {'service': backup_service, 'url': backup_url})

        try:
            new_backup = self.backup_api.import_record(context,
                                                       backup_service,
                                                       backup_url)
        except exception.InvalidBackup as error:
            raise exc.HTTPBadRequest(explanation=error.msg)
        # Other Not found exceptions will be handled at the wsgi level
        except exception.ServiceNotFound as error:
            raise exc.HTTPServiceUnavailable(explanation=error.msg)

        retval = self._view_builder.summary(req, dict(new_backup))
        LOG.debug('Import record output: %s.', retval)
        return retval


class Backups(extensions.ExtensionDescriptor):
    """Backups support."""

    name = 'Backups'
    alias = 'backups'
    updated = '2012-12-12T00:00:00+00:00'

    def get_resources(self):
        resources = []
        res = extensions.ResourceExtension(
            Backups.alias, BackupsController(),
            collection_actions={'detail': 'GET', 'import_record': 'POST'},
            member_actions={'restore': 'POST', 'export_record': 'GET',
                            'action': 'POST'})
        resources.append(res)
        return resources
