#   Copyright 2013, Red Hat, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.
from http import HTTPStatus

from oslo_log import log as logging
import webob

from cinder.api import extensions
from cinder.api.openstack import wsgi
from cinder.api.schemas import snapshot_actions
from cinder.api import validation
from cinder.i18n import _
from cinder import objects
from cinder.objects import fields
from cinder.policies import snapshot_actions as policy
LOG = logging.getLogger(__name__)


class SnapshotActionsController(wsgi.Controller):
    def __init__(self, *args, **kwargs):
        super(SnapshotActionsController, self).__init__(*args, **kwargs)
        LOG.debug("SnapshotActionsController initialized")

    @wsgi.action('os-update_snapshot_status')
    @validation.schema(snapshot_actions.update_snapshot_status)
    def _update_snapshot_status(self, req, id, body):
        """Update database fields related to status of a snapshot.

           Intended for creation of snapshots, so snapshot state
           must start as 'creating' and be changed to 'available',
           'creating', or 'error'.
        """

        context = req.environ['cinder.context']
        LOG.debug("body: %s", body)

        status = body['os-update_snapshot_status']['status']

        # Allowed state transitions
        status_map = {fields.SnapshotStatus.CREATING:
                      [fields.SnapshotStatus.CREATING,
                       fields.SnapshotStatus.AVAILABLE,
                       fields.SnapshotStatus.ERROR],
                      fields.SnapshotStatus.DELETING:
                      [fields.SnapshotStatus.DELETING,
                       fields.SnapshotStatus.ERROR_DELETING]}

        current_snapshot = objects.Snapshot.get_by_id(context, id)
        context.authorize(policy.UPDATE_STATUS_POLICY,
                          target_obj=current_snapshot)

        if current_snapshot.status not in status_map:
            msg = _("Snapshot status %(cur)s not allowed for "
                    "update_snapshot_status") % {
                        'cur': current_snapshot.status}
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if status not in status_map[current_snapshot.status]:
            msg = _("Provided snapshot status %(provided)s not allowed for "
                    "snapshot with status %(current)s.") % \
                {'provided': status,
                 'current': current_snapshot.status}
            raise webob.exc.HTTPBadRequest(explanation=msg)

        update_dict = {'id': id,
                       'status': status}

        progress = body['os-update_snapshot_status'].get('progress', None)
        if progress:
            update_dict.update({'progress': progress})

        LOG.info("Updating snapshot %(id)s with info %(dict)s",
                 {'id': id, 'dict': update_dict})

        current_snapshot.update(update_dict)
        current_snapshot.save()
        return webob.Response(status_int=HTTPStatus.ACCEPTED)


class Snapshot_actions(extensions.ExtensionDescriptor):
    """Enable snapshot manager actions."""

    name = "SnapshotActions"
    alias = "os-snapshot-actions"
    updated = "2013-07-16T00:00:00+00:00"

    def get_controller_extensions(self):
        controller = SnapshotActionsController()
        extension = extensions.ControllerExtension(self,
                                                   'snapshots',
                                                   controller)
        return [extension]
