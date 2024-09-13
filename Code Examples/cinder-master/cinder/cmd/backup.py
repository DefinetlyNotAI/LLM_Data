#!/usr/bin/env python

# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
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

"""Starter script for Cinder Volume Backup."""

import logging as python_logging
import shlex
import sys

# NOTE: Monkey patching must go before OSLO.log import, otherwise OSLO.context
# will not use greenthread thread local and all greenthreads will share the
# same context.  It's also a good idea to monkey patch everything before
# loading multiprocessing
import eventlet
eventlet.monkey_patch()
# Monkey patch the original current_thread to use the up-to-date _active
# global variable. See https://bugs.launchpad.net/bugs/1863021 and
# https://github.com/eventlet/eventlet/issues/592
import __original_module_threading as orig_threading  # pylint: disable=E0401
import threading # noqa
orig_threading.current_thread.__globals__['_active'] = \
    threading._active  # type: ignore
import typing
from typing import Union

import os_brick
from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_privsep import priv_context
from oslo_reports import guru_meditation_report as gmr
from oslo_reports import opts as gmr_opts
if typing.TYPE_CHECKING:
    import oslo_service

# Need to register global_opts
from cinder.common import config  # noqa
from cinder.db import api as session
from cinder import i18n
i18n.enable_lazy()
from cinder import objects
from cinder import service
from cinder import utils
from cinder import version


CONF = cfg.CONF

backup_cmd_opts = [
    cfg.IntOpt('backup_workers',
               default=1, min=1, max=processutils.get_worker_count(),
               sample_default=8,
               help='Number of backup processes to launch. '
               'Improves performance with concurrent backups.'),
    cfg.IntOpt('backup_max_operations',
               default=15,
               min=0,
               help='Maximum number of concurrent memory heavy operations: '
                    'backup and restore. Value of 0 means unlimited'),
]
CONF.register_opts(backup_cmd_opts)

LOG = None

# NOTE: The default backup driver uses swift and performs read/write
# operations in a thread. swiftclient will log requests and responses at DEBUG
# level, which can cause a thread switch and break the backup operation. So we
# set a default log level of WARN for swiftclient and boto to try and avoid
# this issue.
_EXTRA_DEFAULT_LOG_LEVELS = ['swiftclient=WARN', 'botocore=WARN']


def _launch_backup_process(launcher: 'oslo_service.ProcessLauncher',
                           num_process: int,
                           _semaphore: Union[eventlet.semaphore.Semaphore,
                                             utils.Semaphore]) -> None:
    try:
        server = service.Service.create(binary='cinder-backup',
                                        coordination=True,
                                        service_name='backup',
                                        process_number=num_process + 1,
                                        semaphore=_semaphore)
    except Exception:
        assert LOG is not None
        LOG.exception('Backup service %s failed to start.', CONF.host)
        sys.exit(1)
    else:
        # Dispose of the whole DB connection pool here before
        # starting another process.  Otherwise we run into cases where
        # child processes share DB connections which results in errors.
        session.dispose_engine()
        launcher.launch_service(server)


def main() -> None:
    objects.register_all()
    gmr_opts.set_defaults(CONF)
    CONF(sys.argv[1:], project='cinder',
         version=version.version_string())
    logging.set_defaults(
        default_log_levels=logging.get_default_log_levels() +
        _EXTRA_DEFAULT_LOG_LEVELS)
    logging.setup(CONF, "cinder")
    python_logging.captureWarnings(True)
    priv_context.init(root_helper=shlex.split(utils.get_root_helper()))
    utils.monkey_patch()
    gmr.TextGuruMeditation.setup_autorun(version, conf=CONF)
    os_brick.setup(CONF)
    global LOG
    LOG = logging.getLogger(__name__)
    semaphore = utils.semaphore_factory(CONF.backup_max_operations,
                                        CONF.backup_workers)

    if CONF.backup_workers > 1:
        LOG.info('Backup running with %s processes.', CONF.backup_workers)
        launcher = service.get_launcher()

        for i in range(CONF.backup_workers):
            _launch_backup_process(launcher, i, semaphore)

        launcher.wait()
    else:
        LOG.info('Backup running in single process mode.')
        server = service.Service.create(binary='cinder-backup',
                                        coordination=True,
                                        service_name='backup',
                                        process_number=1,
                                        semaphore=semaphore)
        service.serve(server)
        service.wait()
