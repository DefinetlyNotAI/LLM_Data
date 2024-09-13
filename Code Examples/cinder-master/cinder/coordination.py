# Copyright 2015 Intel
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

"""Coordination and locking utilities."""

import errno
import glob
import inspect
import os
import re
import sys
from typing import Callable, Optional
import uuid

import decorator
from oslo_config import cfg
from oslo_log import log
from oslo_utils import timeutils
from tooz import coordination

from cinder import exception
from cinder.i18n import _
from cinder import utils

LOG = log.getLogger(__name__)

coordination_opts = [
    cfg.StrOpt('backend_url',
               secret=True,
               default='file://$state_path',
               help='The backend URL to use for distributed coordination.'),
]

CONF = cfg.CONF
CONF.register_opts(coordination_opts, group='coordination')


class Coordinator(object):
    """Tooz coordination wrapper.

    Coordination member id is created from concatenated
    `prefix` and `agent_id` parameters.

    :param str agent_id: Agent identifier
    :param str prefix: Used to provide member identifier with a
        meaningful prefix.
    """

    def __init__(self, agent_id: Optional[str] = None, prefix: str = ''):
        self.coordinator = None
        self.agent_id = agent_id or str(uuid.uuid4())
        self.started = False
        self.prefix = prefix
        self._file_path = None

    def _get_file_path(self, backend_url):
        if backend_url.startswith('file://'):
            path = backend_url[7:]
            # Copied from TooZ's _normalize_path to get the same path they use
            if sys.platform == 'win32':
                path = re.sub(r'\\(?=\w:\\)', '', os.path.normpath(path))
            return os.path.abspath(os.path.join(path, self.prefix))
        return None

    def start(self) -> None:
        if self.started:
            return

        backend_url = cfg.CONF.coordination.backend_url

        # NOTE(bluex): Tooz expects member_id as a byte string.
        member_id = (self.prefix + self.agent_id).encode('ascii')
        self.coordinator = coordination.get_coordinator(backend_url, member_id)
        assert self.coordinator is not None
        self.coordinator.start(start_heart=True)
        self._file_path = self._get_file_path(backend_url)
        self.started = True

    def stop(self) -> None:
        """Disconnect from coordination backend and stop heartbeat."""
        if self.started:
            if self.coordinator is not None:
                self.coordinator.stop()
            self.coordinator = None
            self.started = False

    def get_lock(self, name: str):
        """Return a Tooz backend lock.

        :param str name: The lock name that is used to identify it
            across all nodes.
        """
        # NOTE(bluex): Tooz expects lock name as a byte string.
        lock_name = (self.prefix + name).encode('ascii')
        if self.coordinator is not None:
            return self.coordinator.get_lock(lock_name)
        else:
            raise exception.LockCreationFailed(_('Coordinator uninitialized.'))

    def remove_lock(self, glob_name):
        # Most locks clean up on release, but not the file lock, so we manually
        # clean them.

        def _err(file_name: str, exc: Exception) -> None:
            LOG.warning('Failed to cleanup lock %(name)s: %(exc)s',
                        {'name': file_name, 'exc': exc})

        if self._file_path:
            files = glob.glob(self._file_path + glob_name)
            for file_name in files:
                try:
                    os.remove(file_name)
                except OSError as exc:
                    if (exc.errno != errno.ENOENT):
                        _err(file_name, exc)
                except Exception as exc:
                    _err(file_name, exc)


COORDINATOR = Coordinator(prefix='cinder-')


def synchronized_remove(glob_name, coordinator=COORDINATOR):
    coordinator.remove_lock(glob_name)


def __acquire(lock, blocking, f_name):
    """Acquire a lock and return the time when it was acquired."""
    t1 = timeutils.now()
    name = utils.convert_str(lock.name)
    LOG.debug('Acquiring lock "%s" by "%s"', name, f_name)
    lock.acquire(blocking)
    t2 = timeutils.now()
    LOG.debug('Lock "%s" acquired by "%s" :: waited %0.3fs',
              name, f_name, t2 - t1)
    return t2


def __release(lock, acquired_time, f_name):
    """Release a lock ignoring exceptions."""
    name = utils.convert_str(lock.name)
    try:
        lock.release()
        held = timeutils.now() - acquired_time
        LOG.debug('Lock "%s" released by "%s" :: held %0.3fs',
                  name, f_name, held)
    except Exception as e:
        LOG.error('Failed to release lock "%s": %s', name, e)


def synchronized(*lock_names: str,
                 blocking: bool = True,
                 coordinator: Coordinator = COORDINATOR) -> Callable:
    """Synchronization decorator.

    :param str lock_names: Arbitrary number of Lock names.
    :param blocking: If True, blocks until the lock is acquired.
            If False, raises exception when not acquired. Otherwise,
            the value is used as a timeout value and if lock is not acquired
            after this number of seconds exception is raised. This is a keyword
            only argument.
    :param coordinator: Coordinator class to use when creating lock.
        Defaults to the global coordinator.  This is a keyword only argument.
    :raises tooz.coordination.LockAcquireFailed: if lock is not acquired

    Decorating a method like so::

        @synchronized('mylock')
        def foo(self, *args):
           ...

    ensures that only one process will execute the foo method at a time.

    Different methods can share the same lock::

        @synchronized('mylock')
        def foo(self, *args):
           ...

        @synchronized('mylock')
        def bar(self, *args):
           ...

    This way only one of either foo or bar can be executing at a time.

    Lock name can be formatted using Python format string syntax::

        @synchronized('{f_name}-{vol.id}-{snap[name]}')
        def foo(self, vol, snap):
           ...

    Multiple locks can be requested simultaneously and the decorator will
    reorder the names by rendered lock names to prevent potential deadlocks.

        @synchronized('{f_name}-{vol.id}-{snap[name]}',
                      '{f_name}-{vol.id}.delete')
        def foo(self, vol, snap):
           ...

    Available field names are: decorated function parameters and
    `f_name` as a decorated function name.
    """
    @decorator.decorator
    def _synchronized(f, *a, **k) -> Callable:
        call_args = inspect.getcallargs(f, *a, **k)
        call_args['f_name'] = f.__name__

        # Prevent deadlocks not duplicating and sorting them by name to always
        # acquire them in the same order.
        names = sorted(set([name.format(**call_args) for name in lock_names]))
        locks = [coordinator.get_lock(name) for name in names]
        acquired_times = []
        f_name = f.__name__
        t1 = timeutils.now()
        try:
            if len(locks) > 1:  # Don't pollute logs for single locks
                LOG.debug('Acquiring %s locks by %s', len(locks), f_name)

            for lock in locks:
                acquired_times.append(__acquire(lock, blocking, f_name))

            if len(locks) > 1:
                t = timeutils.now() - t1
                LOG.debug('Acquired %s locks by %s in %0.3fs',
                          len(locks), f_name, t)

            return f(*a, **k)
        finally:
            for lock, acquired_time in zip(locks, acquired_times):
                __release(lock, acquired_time, f_name)

    return _synchronized
