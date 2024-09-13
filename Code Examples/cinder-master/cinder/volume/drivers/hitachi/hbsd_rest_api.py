# Copyright (C) 2020, 2022, Hitachi, Ltd.
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
REST API client class for Hitachi HBSD Driver.

"""

from http import client as httpclient
import socket
import threading

from eventlet import greenthread
from oslo_log import log as logging
from oslo_service import loopingcall
from oslo_utils import timeutils
import requests
from requests.adapters import HTTPAdapter

from cinder import exception
from cinder.i18n import _
from cinder.volume.drivers.hitachi import hbsd_utils as utils
from cinder.volume import volume_utils

_LOCK_TIMEOUT = 2 * 60 * 60
_REST_TIMEOUT = 30
_EXTEND_TIMEOUT = 10 * 60
_EXEC_RETRY_INTERVAL = 5
_DEFAULT_CONNECT_TIMEOUT = 30
_JOB_API_RESPONSE_TIMEOUT = 30 * 60
_GET_API_RESPONSE_TIMEOUT = 30 * 60
_REST_SERVER_BUSY_TIMEOUT = 2 * 60 * 60
_REST_SERVER_RESTART_TIMEOUT = 10 * 60
_REST_SERVER_ERROR_TIMEOUT = 10 * 60
_KEEP_SESSION_LOOP_INTERVAL = 3 * 60
_ANOTHER_LDEV_MAPPED_RETRY_TIMEOUT = 10 * 60
_LOCK_RESOURCE_GROUP_TIMEOUT = 3 * 60

_TCP_KEEPIDLE = 60
_TCP_KEEPINTVL = 15
_TCP_KEEPCNT = 4

_MIRROR_RESERVED_VIRTUAL_LDEV_ID = 65535

_HTTPS = 'https://'

_NOT_SPECIFIED = 'NotSpecified'

_REST_LOCKED_ERRORS = [
    ('2E11', '2205'),
    ('2E11', '2207'),
]
LDEV_ALREADY_DEFINED = ('2E22', '0001')
NO_AVAILABLE_LDEV_ID = ('2E11', '2209')
INVALID_SNAPSHOT_POOL = ('2E30', '600E')
_MSGID_REST_SERVER_BUSY = ('KART00003-E',)
_MSGID_LOCK_FAILURE = ('KART40050-E', 'KART40051-E', 'KART40052-E')
EXCEED_WWN_MAX = ('B957', '4184')
ANOTHER_LDEV_MAPPED = ('B958', '0947')
REST_NO_RETRY_ERRORS = [
    ('2E10', '9705'),
    ('2E10', '9706'),
    ('2E10', '9707'),
    ('2E11', '8303'),
    ('2E30', '0007'),
    ('B956', '3173'),
    ('B956', '31D7'),
    ('B956', '31D9'),
    ('B957', '4188'),
    ('B958', '015A'),
    ('B958', '015E'),
    LDEV_ALREADY_DEFINED,
    NO_AVAILABLE_LDEV_ID,
    EXCEED_WWN_MAX,
    INVALID_SNAPSHOT_POOL,
]
MSGID_SPECIFIED_OBJECT_DOES_NOT_EXIST = 'KART30013-E'
_REST_NO_RETRY_MESSAGEIDS = [
    MSGID_SPECIFIED_OBJECT_DOES_NOT_EXIST
]

LOG = logging.getLogger(__name__)
MSG = utils.HBSDMsg


def _get_device_group_name(remote_client, copy_group_name, is_secondary,
                           is_remote=False):
    if remote_client is None and is_remote:
        return _NOT_SPECIFIED
    return copy_group_name + ('S' if is_secondary ^ is_remote else 'P')


def _build_base_url(ip_addr, ip_port):
    return '%(https)s%(ip)s:%(port)s/ConfigurationManager' % {
        'https': _HTTPS,
        'ip': ip_addr,
        'port': ip_port,
    }


class KeepAliveAdapter(HTTPAdapter):

    def __init__(self, conf):
        self.socket_options = [
            (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
            (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
            (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE,
             conf.hitachi_rest_tcp_keepidle),
            (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL,
             conf.hitachi_rest_tcp_keepintvl),
            (socket.IPPROTO_TCP, socket.TCP_KEEPCNT,
             conf.hitachi_rest_tcp_keepcnt),
        ]

        super(KeepAliveAdapter, self).__init__()

    def init_poolmanager(self, *args, **kwargs):
        kwargs['socket_options'] = self.socket_options
        super(KeepAliveAdapter, self).init_poolmanager(*args, **kwargs)


class ResponseData(dict):

    def is_json(self):
        return (self['rsp'].content and
                'json' in self['rsp'].headers['Content-Type'])

    def _init_content(self):
        """Set response object."""
        if self.is_json():
            self['rsp_body'] = self['rsp'].json()
        elif self['rsp'].content:
            self['rsp_body'] = self['rsp'].text
        else:
            self['rsp_body'] = None

    def _init_error(self):
        """Set error object"""
        if self['rsp_body'] and 'errorSource' in self['rsp_body']:
            self['errobj'] = self['rsp_body']
        elif self['rsp_body'] and 'error' in self['rsp_body']:
            self['errobj'] = self['rsp_body']['error']
        else:
            self['errobj'] = {}

    def __init__(self, rsp):
        """Initialize instance variables."""
        super(ResponseData, self).__init__()
        self['rsp'] = rsp
        self['status_code'] = rsp.status_code
        self._init_content()
        self._init_error()

    def job_succeeded(self):
        return (self.is_json() and
                self['rsp_body'].get('status') == 'Completed' and
                self['rsp_body'].get('state') == 'Succeeded')

    def get_err_code(self):
        return utils.safe_get_err_code(self['errobj'])

    def get_return_code(self):
        return utils.safe_get_return_code(self['errobj'])

    def is_success(self, ignore_error, ignore_message_id,
                   ignore_return_code, ignore_all_errors=False):
        """Check the success or failure of the response."""
        return (ignore_all_errors or
                self['status_code'] == httpclient.OK or
                (self['status_code'] == httpclient.ACCEPTED and
                 self.job_succeeded()) or
                self.get_err_code() in ignore_error or
                self['errobj'].get('messageId') in ignore_message_id or
                self.get_return_code() in ignore_return_code)

    def is_locked(self):
        """Check if a response is the error of the lock factor."""
        if not self['errobj']:
            return False
        message_id = self['errobj'].get('messageId')
        retcode = self['errobj'].get('errorCode', {}).get('errorCode')
        return (message_id in _MSGID_LOCK_FAILURE or
                self.get_err_code() in _REST_LOCKED_ERRORS or
                retcode == 'EX_EACCES')

    def is_auth_fail(self):
        """Check if a response is an authorization error."""
        return self['status_code'] == httpclient.UNAUTHORIZED

    def get_message_id(self):
        return utils.safe_get_message_id(self['errobj'])

    def is_no_retry_error(self, no_retry_error_code):
        """Check if a response is a no retry error."""
        return (not self.is_auth_fail() and
                ((self['status_code'] not in
                  list(range(200, 300)) + list(range(500, 600))) or
                 self.get_err_code() in no_retry_error_code or
                 self.get_message_id() in _REST_NO_RETRY_MESSAGEIDS))

    def is_rest_server_busy(self):
        """Check if a response is a server busy error."""
        if not self['errobj']:
            return False
        message_id = self['errobj'].get('messageId')
        return (message_id in _MSGID_REST_SERVER_BUSY)

    def get_errobj(self):
        return {
            'errorSource': self['errobj'].get('errorSource', ''),
            'messageId': self['errobj'].get('messageId', ''),
            'message': self['errobj'].get('message', ''),
            'cause': self['errobj'].get('cause', ''),
            'solution': self['errobj'].get('solution', ''),
            'errorCode': self['errobj'].get('errorCode', {}),
        }

    def get_job_result(self):
        return {'job_id': self['rsp_body'].get('jobId', ''),
                'status': self['rsp_body'].get('status', ''),
                'state': self['rsp_body'].get('state', '')}


class RestApiClient():

    def __init__(self, conf, ip_addr, ip_port, storage_device_id,
                 user_id, user_pass, driver_prefix, tcp_keepalive=False,
                 verify=False, is_rep=False):
        """Initialize instance variables."""
        self.conf = conf
        self.ip_addr = ip_addr
        self.ip_port = ip_port
        self.storage_id = storage_device_id
        self.storage_info = {}
        self.user_id = user_id
        self.user_pass = user_pass
        self.tcp_keepalive = tcp_keepalive
        self.verify = verify
        self.connect_timeout = self.conf.hitachi_rest_connect_timeout
        self.is_rep = is_rep
        self.login_lock = threading.Lock()
        self.keep_session_loop = loopingcall.FixedIntervalLoopingCall(
            self._keep_session)
        self.nested_count = 0
        self.resource_lock = threading.Lock()

        self.base_url = _build_base_url(ip_addr, self.ip_port)
        self.object_url = '%(base_url)s/v1/objects/storages/%(storage_id)s' % {
            'base_url': self.base_url,
            'storage_id': self.storage_id,
        }
        self.service_url = '%(base_url)s/v1/%(storage_id)s/services' % {
            'base_url': self.base_url,
            'storage_id': self.storage_id,
        }
        self.headers = {"content-type": "application/json",
                        "accept": "application/json"}
        self.driver_prefix = driver_prefix

    class Session(requests.auth.AuthBase):

        def __init__(self, id, token):
            """Initialize instance variables."""
            self.id = id
            self.token = token

        def __call__(self, req):
            req.headers['Authorization'] = 'Session %(token)s' % {
                'token': self.token,
            }
            return req

    @volume_utils.trace
    def _request(self, method, url, params=None, body=None,
                 async_=False, **kwargs):
        """Transmit the request to REST API server."""
        kwargs.setdefault('ignore_error', [])
        kwargs['no_retry_error'] = (kwargs['ignore_error'] +
                                    REST_NO_RETRY_ERRORS)
        kwargs.setdefault('no_retry', False)
        kwargs.setdefault('do_raise', True)
        kwargs.setdefault('ignore_message_id', [])
        kwargs.setdefault('no_relogin', False)
        kwargs.setdefault('ignore_return_code', [])
        kwargs.setdefault('ignore_all_errors', False)
        kwargs.setdefault('timeout_message', None)
        kwargs.setdefault('no_log', False)
        kwargs.setdefault('timeout', self.conf.hitachi_rest_timeout)

        headers = dict(self.headers)
        if async_:
            read_timeout = self.conf.hitachi_rest_job_api_response_timeout
            headers.update({
                "Response-Max-Wait": str(
                    self.conf.hitachi_rest_job_api_response_timeout),
                "Response-Job-Status": "Completed;"})
        else:
            read_timeout = self.conf.hitachi_rest_get_api_response_timeout

        remote_auth = kwargs.get('remote_auth')
        if remote_auth:
            headers["Remote-Authorization"] = 'Session ' + remote_auth.token

        auth_data = kwargs.get('auth', self.get_my_session())

        timeout = (self.connect_timeout, read_timeout)

        interval = kwargs.get(
            'interval', self.conf.hitachi_exec_retry_interval)
        retry = True
        start_time = timeutils.utcnow()
        watch = timeutils.StopWatch()

        while retry:
            watch.restart()
            try:
                with requests.Session() as session:
                    if self.tcp_keepalive:
                        session.mount(_HTTPS, KeepAliveAdapter(self.conf))
                    rsp = session.request(method, url,
                                          params=params,
                                          json=body,
                                          headers=headers,
                                          auth=auth_data,
                                          timeout=timeout,
                                          verify=self.verify)

            except Exception as e:
                msg = self.output_log(
                    MSG.REST_SERVER_CONNECT_FAILED,
                    exception=type(e), message=e,
                    method=method, url=url, params=params, body=body)
                message = _(
                    '%(prefix)s error occurred. %(msg)s' % {
                        'prefix': self.driver_prefix,
                        'msg': msg,
                    }
                )
                raise exception.VolumeDriverException(message)

            response = ResponseData(rsp)
            if (response['status_code'] == httpclient.INTERNAL_SERVER_ERROR and
                    kwargs['timeout'] < _REST_SERVER_RESTART_TIMEOUT):
                kwargs['timeout'] = _REST_SERVER_RESTART_TIMEOUT
            if (response['status_code'] == httpclient.SERVICE_UNAVAILABLE and
                    kwargs['timeout'] < _REST_SERVER_ERROR_TIMEOUT):
                kwargs['timeout'] = _REST_SERVER_ERROR_TIMEOUT
            retry, rsp_data, errobj = self._check_rest_api_response(
                response, start_time,
                method=method, url=url, params=params, body=body, **kwargs)
            if retry:
                watch.stop()
                idle = max(interval - watch.elapsed(), 0)
                greenthread.sleep(idle)
                if not kwargs['no_relogin'] and response.is_auth_fail():
                    auth_data = self.get_my_session()

        return rsp_data, errobj

    def _check_rest_api_response(
            self, response, start_time, method=None,
            url=None, params=None, body=None, **kwargs):
        """Check the response from REST API server."""
        rsp_body = response['rsp_body']
        errobj = response['errobj']
        if response.is_locked():
            if (kwargs['no_retry'] or
                    utils.timed_out(
                        start_time, self.conf.hitachi_lock_timeout)):
                msg = self.output_log(MSG.REST_API_FAILED,
                                      no_log=kwargs['no_log'],
                                      method=method, url=url,
                                      params=params, body=body,
                                      **response.get_errobj())
                if kwargs['do_raise']:
                    message = _(
                        '%(prefix)s error occurred. %(msg)s' % {
                            'prefix': self.driver_prefix,
                            'msg': msg,
                        }
                    )
                    raise exception.VolumeDriverException(
                        message, errobj=errobj)
                return False, rsp_body, errobj
            else:
                LOG.debug("The resource group to which the operation object "
                          "belongs is being locked by other software.")
                return True, rsp_body, errobj

        if response.is_success(kwargs['ignore_error'],
                               kwargs['ignore_message_id'],
                               kwargs['ignore_return_code'],
                               kwargs['ignore_all_errors']):
            return False, rsp_body, errobj

        if (kwargs['no_retry'] and
                response['status_code'] != httpclient.INTERNAL_SERVER_ERROR or
                response.is_no_retry_error(kwargs['no_retry_error'])):
            retry = False
        elif response.is_auth_fail():
            retry = self.relogin(kwargs['no_relogin'])
        else:
            retry = True

        if retry and response.is_rest_server_busy():
            if utils.timed_out(
                    start_time, self.conf.hitachi_rest_server_busy_timeout):
                retry = False
        elif retry and response.get_err_code() in (ANOTHER_LDEV_MAPPED, ):
            if utils.timed_out(
                    start_time,
                    self.conf.hitachi_rest_another_ldev_mapped_retry_timeout):
                LOG.debug(
                    "Another LDEV is already mapped to the specified LUN.")
                retry = False
        elif retry and utils.timed_out(start_time, kwargs['timeout']):
            if kwargs['timeout_message']:
                self.output_log(kwargs['timeout_message'][0],
                                **kwargs['timeout_message'][1])
            if response.is_json():
                msg = self.output_log(MSG.REST_API_TIMEOUT,
                                      no_log=kwargs['no_log'],
                                      method=method, url=url,
                                      params=params, body=body,
                                      **response.get_job_result())
                if errobj:
                    msg = self.output_log(MSG.REST_API_FAILED,
                                          no_log=kwargs['no_log'],
                                          method=method, url=url,
                                          params=params, body=body,
                                          **response.get_errobj())
            else:
                msg = self.output_log(MSG.REST_API_HTTP_ERROR,
                                      no_log=kwargs['no_log'],
                                      status_code=response['status_code'],
                                      response_body=rsp_body,
                                      method=method, url=url,
                                      params=params, body=body)
            if kwargs['do_raise']:
                message = _(
                    '%(prefix)s error occurred. %(msg)s' % {
                        'prefix': self.driver_prefix,
                        'msg': msg,
                    }
                )
                raise exception.VolumeDriverException(
                    message, errobj=errobj)
            return False, rsp_body, errobj

        if errobj:
            LOG.debug('ERROR %s', errobj)
        else:
            LOG.debug('ERROR %s', ' '.join(str(rsp_body).splitlines()))

        if not retry:
            if response.is_json():
                msg = self.output_log(MSG.REST_API_FAILED,
                                      no_log=kwargs['no_log'],
                                      method=method, url=url,
                                      params=params, body=body,
                                      **response.get_errobj())
            else:
                msg = self.output_log(MSG.REST_API_HTTP_ERROR,
                                      no_log=kwargs['no_log'],
                                      status_code=response['status_code'],
                                      response_body=rsp_body,
                                      method=method, url=url,
                                      params=params, body=body)
            if kwargs['do_raise']:
                message = _(
                    '%(prefix)s error occurred. %(msg)s' % {
                        'prefix': self.driver_prefix,
                        'msg': msg,
                    }
                )
                raise exception.VolumeDriverException(
                    message, errobj=errobj)
        return retry, rsp_body, errobj

    def lock_resource_group(self, waittime=_LOCK_RESOURCE_GROUP_TIMEOUT):
        """Lock resources.

        Lock resources of a resource group allocated to the user who
        executes API requests, preventing other users from performing
        operations on the resources.
        """
        with self.resource_lock:
            if self.nested_count <= 0:
                url = '%(url)s/resource-group-service/actions/%(action)s' % {
                    'url': self.service_url,
                    'action': 'lock',
                } + '/invoke'
                if waittime:
                    body = {"parameters": {"waitTime": waittime}}
                    self._invoke(url, body=body, timeout=waittime)
                else:
                    self._invoke(url)
            self.nested_count += 1

    def unlock_resource_group(self):
        """If the lock is already released, there is no need to unlock."""
        with self.resource_lock:
            if self.nested_count == 0:
                return
            self.nested_count -= 1
            if self.nested_count <= 0:
                url = '%(url)s/resource-group-service/actions/%(action)s' % {
                    'url': self.service_url,
                    'action': 'unlock',
                } + '/invoke'
                self._invoke(url)

    def set_my_session(self, session):
        self.session = session

    def get_my_session(self):
        return getattr(self, 'session', None)

    def _login(self, do_raise=True):
        """Establishes a session and manages the session."""
        url = '%(url)s/sessions' % {
            'url': self.object_url,
        }
        auth = (self.user_id, self.user_pass)
        rsp, err = self._request("POST", url, auth=auth, no_relogin=True,
                                 do_raise=do_raise,
                                 timeout=self.conf.hitachi_lock_timeout)
        if not err:
            self.set_my_session(self.Session(rsp["sessionId"], rsp["token"]))
            return True
        else:
            return False

    def login(self):
        """Establishes a session and manages the session."""
        LOG.debug("Trying to login.")
        return self._login()

    def get_session(self, session_id, **kwargs):
        """Get a session information."""
        url = '%(url)s/sessions/%(id)s' % {
            'url': self.object_url,
            'id': session_id,
        }
        return self._get_object(url, **kwargs)

    def _has_session(self):
        """Check if there is a session managing."""
        has_session = False
        try:
            session = self.get_my_session()
            if session is not None:
                self.get_session(session.id, no_retry=True, no_log=True)
                has_session = True
        except exception.VolumeDriverException as ex:
            LOG.debug('Failed to get session info: %s', ex)
        return has_session

    def relogin(self, no_relogin, no_log=False):
        """Establishes a session again."""
        retry = False
        if not no_relogin:
            with self.login_lock:
                retry = self._has_session()
                if not retry:
                    LOG.debug("Trying to re-login.")
                    retry = self._login(do_raise=False)
                if not retry:
                    self.output_log(
                        MSG.REST_LOGIN_FAILED,
                        no_log=no_log, user=self.user_id)
        return retry

    def _keep_session(self):
        """Keep a session."""
        LOG.debug('_keep_session thread is started')
        try:
            self.relogin(False, no_log=True)
        except Exception as ex:
            LOG.debug(
                'relogin() in _keep_session() failed. %s', ex)

    def enter_keep_session(self):
        """Begin the keeping of a session."""
        self.keep_session_loop.start(
            self.conf.hitachi_rest_keep_session_loop_interval)
        LOG.debug('enter_keep_session')

    def _get_object(self, url, params=None, **kwargs):
        """Transmit a GET request that appointed object ID."""
        rsp = self._request("GET", url, params=params, **kwargs)[0]
        return rsp if rsp else None

    def _get_objects(self, url, params=None, **kwargs):
        """Transmit a GET request."""
        rsp = self._request("GET", url, params=params, **kwargs)[0]
        return rsp.get("data") if rsp else None

    def _add_object(self, url, body, **kwargs):
        """Transmit a POST request."""
        rsp, errobj = self._request(
            "POST", url, body=body, async_=True, **kwargs)
        if not rsp:
            return None, errobj
        resources = rsp.get('affectedResources')
        if resources:
            return resources[0].split('/')[-1], errobj
        return None, errobj

    def _delete_object(self, url, params=None, body=None, **kwargs):
        """Transmit a DELETE request."""
        self._request("DELETE", url, params=params, body=body, async_=True,
                      **kwargs)

    def _invoke(self, url, body=None, **kwargs):
        """Transmit a PUT request."""
        self._request("PUT", url, body=body, async_=True, **kwargs)

    def get_pools(self, params=None):
        """Get a list of pool information."""
        url = '%(url)s/pools' % {
            'url': self.object_url,
        }
        return self._get_objects(url, params=params)

    def get_pool(self, pool_id, **kwargs):
        """Get a pool information."""
        url = '%(url)s/pools/%(id)s' % {
            'url': self.object_url,
            'id': pool_id,
        }
        return self._get_object(url, **kwargs)

    def get_ldev(self, ldev_id, **kwargs):
        """Get a ldev information."""
        url = '%(url)s/ldevs/%(id)s' % {
            'url': self.object_url,
            'id': ldev_id,
        }
        return self._get_object(url, **kwargs)

    def get_ldevs(self, params=None, **kwargs):
        """Get a list of ldev information."""
        url = '%(url)s/ldevs' % {
            'url': self.object_url,
        }
        return self._get_objects(url, params=params, **kwargs)

    def add_ldev(self, body, **kwargs):
        """Add a ldev information."""
        url = '%(url)s/ldevs' % {
            'url': self.object_url,
        }
        ldev_id = self._add_object(url, body=body, **kwargs)[0]
        return int(ldev_id) if ldev_id else None

    def delete_ldev(self, ldev_id, body=None, **kwargs):
        """Delete a ldev information."""
        url = '%(url)s/ldevs/%(id)s' % {
            'url': self.object_url,
            'id': ldev_id,
        }
        self._delete_object(url, body=body, **kwargs)

    def modify_ldev(self, ldev_id, body, **kwargs):
        """Modify a ldev information."""
        url = '%(url)s/ldevs/%(id)s' % {
            'url': self.object_url,
            'id': ldev_id,
        }
        self._invoke(url, body=body, **kwargs)

    def extend_ldev(self, ldev_id, body):
        """Expand a ldev size."""
        url = '%(url)s/ldevs/%(id)s/actions/%(action)s/invoke' % {
            'url': self.object_url,
            'id': ldev_id,
            'action': 'expand',
        }
        self._invoke(url, body=body, timeout=self.conf.hitachi_extend_timeout)

    def get_ports(self, params=None):
        """Get a list of port information."""
        url = '%(url)s/ports' % {
            'url': self.object_url,
        }
        return self._get_objects(url, params=params)

    def get_port(self, port_id):
        """Get a port information."""
        url = '%(url)s/ports/%(id)s' % {
            'url': self.object_url,
            'id': port_id,
        }
        return self._get_object(url)

    def get_host_grps(self, params=None):
        """Get a list of host group information."""
        url = '%(url)s/host-groups' % {
            'url': self.object_url,
        }
        return self._get_objects(url, params=params)

    def get_host_grp(self, port_id, host_group_number):
        """Get a host group information."""
        url = '%(url)s/host-groups/%(port)s,%(number)d' % {
            'url': self.object_url,
            'port': port_id,
            'number': host_group_number,
        }
        return self._get_object(url)

    def add_host_grp(self, body, **kwargs):
        """Add a host group information."""
        url = '%(url)s/host-groups' % {
            'url': self.object_url,
        }
        host_group_id = self._add_object(url, body=body, **kwargs)[0]
        return int(host_group_id.split(',')[-1]) if host_group_id else None

    def delete_host_grp(self, port_id, host_group_number):
        """Delete a host group information."""
        url = '%(url)s/host-groups/%(port)s,%(number)d' % {
            'url': self.object_url,
            'port': port_id,
            'number': host_group_number,
        }
        self._delete_object(url)

    def modify_host_grp(self, port_id, host_group_number, body, **kwargs):
        """Modify a host group information."""
        url = '%(url)s/host-groups/%(port)s,%(number)d' % {
            'url': self.object_url,
            'port': port_id,
            'number': host_group_number,
        }
        self._invoke(url, body=body, **kwargs)

    def get_hba_wwns(self, port_id, host_group_number):
        """Get a list of wwn information."""
        url = '%(url)s/host-wwns' % {
            'url': self.object_url,
        }
        params = {"portId": port_id, "hostGroupNumber": host_group_number}
        return self._get_objects(url, params=params)

    def get_hba_wwns_by_name(self, port_id, host_group_name):
        """Get a list of wwn information of the specified name."""
        url = '%(url)s/host-wwns' % {
            'url': self.object_url,
        }
        params = {"portId": port_id, "hostGroupName": host_group_name}
        return self._get_objects(url, params=params)

    def add_hba_wwn(self, port_id, host_group_number, host_wwn, **kwargs):
        """Add a wwn information."""
        url = '%(url)s/host-wwns' % {
            'url': self.object_url,
        }
        body = {"hostWwn": host_wwn, "portId": port_id,
                "hostGroupNumber": host_group_number}
        return self._add_object(url, body=body, **kwargs)[0]

    def get_hba_iscsis(self, port_id, host_group_number):
        """Get a list of ISCSI information."""
        url = '%(url)s/host-iscsis' % {
            'url': self.object_url,
        }
        params = {"portId": port_id, "hostGroupNumber": host_group_number}
        return self._get_objects(url, params=params)

    def get_hba_iscsis_by_name(self, port_id, host_group_name):
        """Get a list of ISCSI information of the specified name."""
        url = '%(url)s/host-iscsis' % {
            'url': self.object_url,
        }
        params = {"portId": port_id, "hostGroupName": host_group_name}
        return self._get_objects(url, params=params)

    def add_hba_iscsi(self, port_id, host_group_number, iscsi_name):
        """Add a ISCSI information."""
        url = '%(url)s/host-iscsis' % {
            'url': self.object_url,
        }
        body = {"iscsiName": iscsi_name, "portId": port_id,
                "hostGroupNumber": host_group_number}
        return self._add_object(url, body=body)[0]

    def get_luns(self, port_id, host_group_number,
                 is_basic_lun_information=False):
        """Get a list of lun information."""
        url = '%(url)s/luns' % {
            'url': self.object_url,
        }
        params = {"portId": port_id, "hostGroupNumber": host_group_number,
                  "isBasicLunInformation": is_basic_lun_information}
        return self._get_objects(url, params=params)

    def add_lun(self, port_id, host_group_number, ldev_id, lun=None, **kwargs):
        """Add a lun information."""
        url = '%(url)s/luns' % {
            'url': self.object_url,
        }
        body = {"portId": port_id, "hostGroupNumber": host_group_number,
                "ldevId": ldev_id}
        if lun is not None:
            body['lun'] = lun
        lun_id, errobj = self._add_object(url, body=body, **kwargs)
        return int(lun_id.split(',')[-1]) if lun_id else None, errobj

    def delete_lun(self, port_id, host_group_number, lun, **kwargs):
        """Delete a lun information."""
        url = '%(url)s/luns/%(port)s,%(number)s,%(lun)d' % {
            'url': self.object_url,
            'port': port_id,
            'number': host_group_number,
            'lun': lun,
        }
        self._delete_object(url, **kwargs)

    def get_snapshots(self, params=None):
        """Get a list of snapshot information."""
        url = '%(url)s/snapshots' % {
            'url': self.object_url,
        }
        return self._get_objects(url, params=params)

    def add_snapshot(self, body, **kwargs):
        """Add a snapshot information."""
        url = '%(url)s/snapshots' % {
            'url': self.object_url,
        }
        return self._add_object(url, body=body, **kwargs)[0]

    def delete_snapshot(self, pvol_ldev_id, mu_number, **kwargs):
        """Delete a snapshot information."""
        url = '%(url)s/snapshots/%(pvol)d,%(mu)d' % {
            'url': self.object_url,
            'pvol': pvol_ldev_id,
            'mu': mu_number,
        }
        self._delete_object(url, **kwargs)

    def unassign_snapshot_volume(self, pvol_ldev_id, mu_number, **kwargs):
        """Unassign a snapshot information."""
        url = '%(url)s/snapshots/%(pvol)d,%(mu)d/actions/%(action)s/invoke' % {
            'url': self.object_url,
            'pvol': pvol_ldev_id,
            'mu': mu_number,
            'action': 'unassign-volume',
        }
        self._invoke(url, **kwargs)

    def restore_snapshot(self, pvol_ldev_id, mu_number, body=None):
        """Restore a snapshot information."""
        url = '%(url)s/snapshots/%(pvol)d,%(mu)d/actions/%(action)s/invoke' % {
            'url': self.object_url,
            'pvol': pvol_ldev_id,
            'mu': mu_number,
            'action': 'restore',
        }
        self._invoke(url, body=body)

    def split_snapshotgroup(self, snapshot_group_id):
        url = '%(url)s/snapshot-groups/%(id)s/actions/%(action)s/invoke' % {
            'url': self.object_url,
            'id': snapshot_group_id,
            'action': 'split',
        }
        self._invoke(url)

    def discard_zero_page(self, ldev_id):
        """Return the ldev's no-data pages to the storage pool."""
        url = '%(url)s/ldevs/%(id)s/actions/%(action)s/invoke' % {
            'url': self.object_url,
            'id': ldev_id,
            'action': 'discard-zero-page',
        }
        self._invoke(url)

    def get_remote_copy_grps(self, remote_client):
        url = '%(url)s/remote-mirror-copygroups' % {
            'url': self.object_url,
        }
        params = {"remoteStorageDeviceId": remote_client.storage_id}
        with RemoteSession(remote_client) as session:
            return self._get_objects(url, params=params, remote_auth=session)

    def get_remote_copy_grp(self, remote_client, copy_group_name, **kwargs):
        url = '%(url)s/remote-mirror-copygroups/%(id)s' % {
            'url': self.object_url,
            'id': self._remote_copygroup_id(remote_client, copy_group_name),
        }
        with RemoteSession(remote_client) as session:
            return self._get_object(url, remote_auth=session, **kwargs)

    def get_remote_copypair(self, remote_client, copy_group_name,
                            pvol_ldev_id, svol_ldev_id, is_secondary=False,
                            **kwargs):
        url = '%(url)s/remote-mirror-copypairs/%(id)s' % {
            'url': self.object_url,
            'id': self._remote_copypair_id(
                remote_client, copy_group_name, pvol_ldev_id, svol_ldev_id,
                is_secondary),
        }
        if remote_client:
            with RemoteSession(remote_client) as session:
                return self._get_object(url, remote_auth=session, **kwargs)
        return self._get_object(url, **kwargs)

    def add_remote_copypair(self, remote_client, body):
        url = '%(url)s/remote-mirror-copypairs' % {
            'url': self.object_url,
        }
        if self.storage_id > remote_client.storage_id:
            client1, client2 = self, remote_client
        else:
            client1, client2 = remote_client, self
        with ResourceGroupLock(client1):
            with ResourceGroupLock(client2):
                session = remote_client.get_my_session()
                return self._add_object(url, body=body,
                                        no_relogin=True,
                                        remote_auth=session,
                                        job_nowait=True)[0]

    @utils.synchronized_on_copy_group()
    def split_remote_copypair(self, remote_client, copy_group_name,
                              pvol_ldev_id, svol_ldev_id, rep_type):
        body = {"parameters": {"replicationType": rep_type}}
        url = '%(url)s/remote-mirror-copypairs/%(id)s/actions/%(action)s' % {
            'url': self.object_url,
            'id': self._remote_copypair_id(remote_client, copy_group_name,
                                           pvol_ldev_id, svol_ldev_id),
            'action': 'split',
        } + '/invoke'
        with RemoteSession(remote_client) as session:
            self._invoke(url, body=body, remote_auth=session, job_nowait=True)

    @utils.synchronized_on_copy_group()
    def resync_remote_copypair(
            self, remote_client, copy_group_name, pvol_ldev_id, svol_ldev_id,
            rep_type, copy_speed=None):
        body = {"parameters": {"replicationType": rep_type}}
        if copy_speed:
            body["parameters"]["copyPace"] = copy_speed
        url = '%(url)s/remote-mirror-copypairs/%(id)s/actions/%(action)s' % {
            'url': self.object_url,
            'id': self._remote_copypair_id(remote_client, copy_group_name,
                                           pvol_ldev_id, svol_ldev_id),
            'action': 'resync',
        } + '/invoke'
        with RemoteSession(remote_client) as session:
            self._invoke(url, body=body, remote_auth=session, job_nowait=True)

    @utils.synchronized_on_copy_group()
    def delete_remote_copypair(self, remote_client, copy_group_name,
                               pvol_ldev_id, svol_ldev_id):
        url = '%(url)s/remote-mirror-copypairs/%(id)s' % {
            'url': self.object_url,
            'id': self._remote_copypair_id(
                remote_client, copy_group_name, pvol_ldev_id, svol_ldev_id),
        }
        if self.storage_id > remote_client.storage_id:
            client1, client2 = self, remote_client
        else:
            client1, client2 = remote_client, self
        with ResourceGroupLock(client1):
            with ResourceGroupLock(client2):
                session = remote_client.get_my_session()
                self._delete_object(
                    url, no_relogin=True, remote_auth=session)

    def _remote_copygroup_id(self, remote_client, copy_group_name,
                             is_secondary=False):
        storage_id = (remote_client.storage_id if remote_client
                      else _NOT_SPECIFIED)
        return "%s,%s,%s,%s" % (
            storage_id,
            copy_group_name,
            _get_device_group_name(remote_client, copy_group_name,
                                   is_secondary),
            _get_device_group_name(remote_client, copy_group_name,
                                   is_secondary, is_remote=True))

    def _remote_copypair_id(self, remote_client, copy_group_name,
                            pvol_ldev_id, svol_ldev_id, is_secondary=False):
        return "%s,HBSD-LDEV-%d-%d" % (
            self._remote_copygroup_id(remote_client, copy_group_name,
                                      is_secondary),
            pvol_ldev_id,
            svol_ldev_id)

    def assign_virtual_ldevid(
            self, ldev_id,
            virtual_ldev_id=_MIRROR_RESERVED_VIRTUAL_LDEV_ID):
        url = '%(url)s/ldevs/%(id)s/actions/%(action)s/invoke' % {
            'url': self.object_url,
            'id': ldev_id,
            'action': 'assign-virtual-ldevid',
        }
        body = {"parameters": {"virtualLdevId": virtual_ldev_id}}
        ignore_error = [('2E21', '9305'), ('2E30', '0088')]
        self._invoke(url, body=body, ignore_error=ignore_error)

    def unassign_virtual_ldevid(
            self, ldev_id,
            virtual_ldev_id=_MIRROR_RESERVED_VIRTUAL_LDEV_ID):
        url = '%(url)s/ldevs/%(id)s/actions/%(action)s/invoke' % {
            'url': self.object_url,
            'id': ldev_id,
            'action': 'unassign-virtual-ldevid',
        }
        body = {"parameters": {"virtualLdevId": virtual_ldev_id}}
        self._invoke(url, body=body)

    def output_log(self, msg_enum, **kwargs):
        if self.is_rep:
            return utils.output_log(
                msg_enum, storage_id=self.storage_id, **kwargs)
        else:
            return utils.output_log(msg_enum, **kwargs)


class RemoteSession(object):

    def __init__(self, remote_client):
        self.remote_client = remote_client

    def __enter__(self):
        return self.remote_client.get_my_session()

    def __exit__(self, exc_type, exc_value, traceback):
        pass


class ResourceGroupLock(object):

    def __init__(self, client):
        self.client = client

    def __enter__(self):
        self.client.lock_resource_group()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.client.unlock_resource_group()
