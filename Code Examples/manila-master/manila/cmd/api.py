#!/usr/bin/env python3

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

"""Starter script for manila OS API."""

import eventlet
eventlet.monkey_patch()
# Monkey patch the original current_thread to use the up-to-date _active
# global variable. See https://bugs.launchpad.net/bugs/1863021 and
# https://github.com/eventlet/eventlet/issues/592
import __original_module_threading as orig_threading
import threading  # noqa
orig_threading.current_thread.__globals__['_active'] = threading._active

import sys

from oslo_config import cfg
from oslo_log import log
from oslo_reports import guru_meditation_report as gmr
from oslo_reports import opts as gmr_opts

from manila.common import config  # Need to register global_opts  # noqa
from manila import service
from manila import utils
from manila import version

CONF = cfg.CONF


def main():
    log.register_options(CONF)
    gmr_opts.set_defaults(CONF)
    CONF(sys.argv[1:], project='manila',
         version=version.version_string())
    config.verify_share_protocols()
    config.set_lib_defaults()
    log.setup(CONF, "manila")
    utils.monkey_patch()

    gmr.TextGuruMeditation.setup_autorun(version, conf=CONF)
    launcher = service.process_launcher()
    server = service.WSGIService('osapi_share')
    launcher.launch_service(server, workers=server.workers or 1)
    launcher.wait()


if __name__ == '__main__':
    main()
