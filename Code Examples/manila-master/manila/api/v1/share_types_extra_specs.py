# Copyright (c) 2011 Zadara Storage Inc.
# Copyright (c) 2011 OpenStack Foundation
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

from http import client as http_client

import webob

from manila.api import common
from manila.api.openstack import wsgi
from manila.common import constants
from manila import db
from manila import exception
from manila.i18n import _
from manila import rpc
from manila.share import share_types


class ShareTypeExtraSpecsController(wsgi.Controller):
    """The share type extra specs API controller for the OpenStack API."""

    resource_name = 'share_types_extra_spec'

    def _get_extra_specs(self, context, type_id):
        extra_specs = db.share_type_extra_specs_get(context, type_id)
        specs_dict = {}
        for key, value in extra_specs.items():
            specs_dict[key] = value
        return dict(extra_specs=specs_dict)

    def _check_type(self, context, type_id):
        try:
            share_types.get_share_type(context, type_id)
        except exception.NotFound as ex:
            raise webob.exc.HTTPNotFound(explanation=ex.msg)

    def _verify_extra_specs(self, extra_specs, verify_all_required=True):
        if verify_all_required:
            try:
                share_types.get_valid_required_extra_specs(extra_specs)
            except exception.InvalidExtraSpec as e:
                raise webob.exc.HTTPBadRequest(explanation=e.msg)

        def is_valid_string(v):
            return isinstance(v, str) and len(v) in range(1, 256)

        def is_valid_extra_spec(k, v):
            valid_extra_spec_key = is_valid_string(k)
            valid_type = is_valid_string(v) or isinstance(v, bool)
            valid_required_extra_spec = (
                share_types.is_valid_required_extra_spec(k, v) in (None, True))
            valid_optional_extra_spec = (
                share_types.is_valid_optional_extra_spec(k, v) in (None, True))
            return (valid_extra_spec_key
                    and valid_type
                    and valid_required_extra_spec
                    and valid_optional_extra_spec)

        for k, v in extra_specs.items():
            if is_valid_string(k) and isinstance(v, dict):
                self._verify_extra_specs(
                    v, verify_all_required=verify_all_required)
            elif not is_valid_extra_spec(k, v):
                expl = _('Invalid extra_spec: %(key)s: %(value)s') % {
                    'key': k, 'value': v
                }
                raise webob.exc.HTTPBadRequest(explanation=expl)

    @wsgi.Controller.authorize
    def index(self, req, type_id):
        """Returns the list of extra specs for a given share type."""
        context = req.environ['manila.context']
        self._check_type(context, type_id)
        return self._get_extra_specs(context, type_id)

    @wsgi.Controller.authorize
    def create(self, req, type_id, body=None):
        context = req.environ['manila.context']

        if not self.is_valid_body(body, 'extra_specs'):
            raise webob.exc.HTTPBadRequest()

        self._check_type(context, type_id)
        specs = body['extra_specs']
        try:
            self._verify_extra_specs(specs, False)
        except exception.InvalidExtraSpec as e:
            raise webob.exc.HTTPBadRequest(e.msg)

        self._check_key_names(specs.keys())
        specs = share_types.sanitize_extra_specs(specs)
        db.share_type_extra_specs_update_or_create(context, type_id, specs)
        notifier_info = dict(type_id=type_id, specs=specs)
        notifier = rpc.get_notifier('shareTypeExtraSpecs')
        notifier.info(context, 'share_type_extra_specs.create', notifier_info)
        return body

    @wsgi.Controller.authorize
    def update(self, req, type_id, id, body=None):
        context = req.environ['manila.context']
        if not body:
            expl = _('Request body empty')
            raise webob.exc.HTTPBadRequest(explanation=expl)
        self._check_type(context, type_id)
        if id not in body:
            expl = _('Request body and URI mismatch')
            raise webob.exc.HTTPBadRequest(explanation=expl)
        if len(body) > 1:
            expl = _('Request body contains too many items')
            raise webob.exc.HTTPBadRequest(explanation=expl)
        self._verify_extra_specs(body, False)
        specs = share_types.sanitize_extra_specs(body)
        db.share_type_extra_specs_update_or_create(context, type_id, specs)
        notifier_info = dict(type_id=type_id, id=id)
        notifier = rpc.get_notifier('shareTypeExtraSpecs')
        notifier.info(context, 'share_type_extra_specs.update', notifier_info)
        return specs

    @wsgi.Controller.authorize
    def show(self, req, type_id, id):
        """Return a single extra spec item."""
        context = req.environ['manila.context']
        self._check_type(context, type_id)
        specs = self._get_extra_specs(context, type_id)
        if id in specs['extra_specs']:
            return {id: specs['extra_specs'][id]}
        else:
            raise webob.exc.HTTPNotFound()

    @wsgi.Controller.api_version('1.0', '2.23')
    @wsgi.Controller.authorize
    def delete(self, req, type_id, id):
        """Deletes an existing extra spec."""
        context = req.environ['manila.context']
        self._check_type(context, type_id)

        if id == constants.ExtraSpecs.SNAPSHOT_SUPPORT:
            msg = _("Extra spec '%s' can't be deleted.") % id
            raise webob.exc.HTTPForbidden(explanation=msg)

        return self._delete(req, type_id, id)

    @wsgi.Controller.api_version('2.24')  # noqa
    @wsgi.Controller.authorize
    def delete(self, req, type_id, id):  # pylint: disable=function-redefined  # noqa F811
        """Deletes an existing extra spec."""
        context = req.environ['manila.context']
        self._check_type(context, type_id)

        return self._delete(req, type_id, id)

    def _delete(self, req, type_id, id):
        """Deletes an existing extra spec."""
        context = req.environ['manila.context']

        if id in share_types.get_required_extra_specs():
            msg = _("Extra spec '%s' can't be deleted.") % id
            raise webob.exc.HTTPForbidden(explanation=msg)

        try:
            db.share_type_extra_specs_delete(context, type_id, id)
        except exception.ShareTypeExtraSpecsNotFound as error:
            raise webob.exc.HTTPNotFound(explanation=error.msg)

        notifier_info = dict(type_id=type_id, id=id)
        notifier = rpc.get_notifier('shareTypeExtraSpecs')
        notifier.info(context, 'share_type_extra_specs.delete', notifier_info)
        return webob.Response(status_int=http_client.ACCEPTED)

    def _check_key_names(self, keys):
        if not common.validate_key_names(keys):
            expl = _('Key names can only contain alphanumeric characters, '
                     'underscores, periods, colons and hyphens.')

            raise webob.exc.HTTPBadRequest(explanation=expl)


def create_resource():
    return wsgi.Resource(ShareTypeExtraSpecsController())
