# Copyright 2010 OpenStack LLC.
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
"""
Common Auth Middleware.

"""
import os

from oslo_config import cfg
from oslo_log import log
from oslo_serialization import jsonutils
import webob.dec
import webob.exc

from manila.api.openstack import wsgi
from manila import context
from manila.i18n import _
from manila.wsgi import common as base_wsgi

use_forwarded_for_opt = cfg.BoolOpt(
    'use_forwarded_for',
    default=False,
    deprecated_for_removal=True,
    deprecated_reason='This feature is duplicate of the HTTPProxyToWSGI '
                      'middleware of oslo.middleware.',
    deprecated_since='Zed',
    help='Treat X-Forwarded-For as the canonical remote address. '
         'Only enable this if you have a sanitizing proxy.')

CONF = cfg.CONF
CONF.register_opt(use_forwarded_for_opt)
LOG = log.getLogger(__name__)


def pipeline_factory(loader, global_conf, **local_conf):
    """A paste pipeline replica that keys off of auth_strategy."""
    pipeline = local_conf[CONF.auth_strategy]
    if not CONF.api_rate_limit:
        limit_name = CONF.auth_strategy + '_nolimit'
        pipeline = local_conf.get(limit_name, pipeline)
    pipeline = pipeline.split()
    filters = [loader.get_filter(n) for n in pipeline[:-1]]
    app = loader.get_app(pipeline[-1])
    filters.reverse()
    for filter in filters:
        app = filter(app)
    return app


class InjectContext(base_wsgi.Middleware):
    """Add a 'manila.context' to WSGI environ."""

    def __init__(self, context, *args, **kwargs):
        self.context = context
        super(InjectContext, self).__init__(*args, **kwargs)

    @webob.dec.wsgify(RequestClass=base_wsgi.Request)
    def __call__(self, req):
        req.environ['manila.context'] = self.context
        return self.application


class ManilaKeystoneContext(base_wsgi.Middleware):
    """Make a request context from keystone headers."""

    @webob.dec.wsgify(RequestClass=base_wsgi.Request)
    def __call__(self, req):
        # Build a context, including the auth_token...
        remote_address = req.remote_addr
        if CONF.use_forwarded_for:
            remote_address = req.headers.get('X-Forwarded-For', remote_address)

        service_catalog = None
        if req.headers.get('X_SERVICE_CATALOG') is not None:
            try:
                catalog_header = req.headers.get('X_SERVICE_CATALOG')
                service_catalog = jsonutils.loads(catalog_header)
            except ValueError:
                raise webob.exc.HTTPInternalServerError(
                    _('Invalid service catalog json.'))

        ctx = context.RequestContext.from_environ(
            req.environ,
            remote_address=remote_address,
            service_catalog=service_catalog)

        if ctx.user_id is None:
            LOG.debug("Neither X_USER_ID nor X_USER found in request")
            return webob.exc.HTTPUnauthorized()

        if req.environ.get('X_PROJECT_DOMAIN_ID'):
            ctx.project_domain_id = req.environ['X_PROJECT_DOMAIN_ID']

        if req.environ.get('X_PROJECT_DOMAIN_NAME'):
            ctx.project_domain_name = req.environ['X_PROJECT_DOMAIN_NAME']

        if req.environ.get('X_USER_DOMAIN_ID'):
            ctx.user_domain_id = req.environ['X_USER_DOMAIN_ID']

        if req.environ.get('X_USER_DOMAIN_NAME'):
            ctx.user_domain_name = req.environ['X_USER_DOMAIN_NAME']

        req.environ['manila.context'] = ctx
        return self.application


class NoAuthMiddlewareBase(base_wsgi.Middleware):
    """Return a fake token if one isn't specified."""

    def base_call(self, req, project_id_in_path=False):
        if 'X-Auth-Token' not in req.headers:
            user_id = req.headers.get('X-Auth-User', 'admin')
            project_id = req.headers.get('X-Auth-Project-Id', 'admin')
            if project_id_in_path:
                os_url = os.path.join(req.url.rstrip('/'), project_id)
            else:
                os_url = req.url.rstrip('/')
            res = webob.Response()
            # NOTE(vish): This is expecting and returning Auth(1.1), whereas
            #             keystone uses 2.0 auth.  We should probably allow
            #             2.0 auth here as well.
            res.headers['X-Auth-Token'] = '%s:%s' % (user_id, project_id)
            res.headers['X-Server-Management-Url'] = os_url
            res.content_type = 'text/plain'
            res.status = '204'
            return res

        token = req.headers['X-Auth-Token']
        user_id, _sep, project_id = token.partition(':')
        project_id = project_id or user_id
        remote_address = getattr(req, 'remote_addr', '127.0.0.1')
        if CONF.use_forwarded_for:
            remote_address = req.headers.get('X-Forwarded-For', remote_address)
        ctx = context.RequestContext(user_id,
                                     project_id,
                                     is_admin=True,
                                     remote_address=remote_address)

        req.environ['manila.context'] = ctx
        return self.application


class NoAuthMiddleware(NoAuthMiddlewareBase):
    """Return a fake token if one isn't specified.

    Sets project_id in URLs.
    """

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        return self.base_call(req, project_id_in_path=True)


class NoAuthMiddlewarev2_60(NoAuthMiddlewareBase):
    """Return a fake token if one isn't specified.

    Does not set project_id in URLs.
    """
    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        return self.base_call(req)
