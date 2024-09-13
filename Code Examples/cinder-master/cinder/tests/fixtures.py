# Copyright 2016 IBM Corp.
# Copyright 2017 Rackspace Australia
# Copyright 2018 Michael Still and Aptira
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

"""Fixtures for Cinder tests."""

import logging as std_logging
import os
import warnings

import fixtures
from oslo_config import cfg
from oslo_policy import policy as oslo_policy
from oslo_privsep import daemon as privsep_daemon
from sqlalchemy import exc as sqla_exc

import cinder.policy

CONF = cfg.CONF
_TRUE_VALUES = ('True', 'true', '1', 'yes')


class NullHandler(std_logging.Handler):
    """custom default NullHandler to attempt to format the record.

    Used in conjunction with
    log_fixture.get_logging_handle_error_fixture to detect formatting errors in
    debug level logs without saving the logs.
    """
    def handle(self, record):
        self.format(record)

    def emit(self, record):
        pass

    def createLock(self):
        self.lock = None


class StandardLogging(fixtures.Fixture):
    """Setup Logging redirection for tests.

    There are a number of things we want to handle with logging in tests:

    * Redirect the logging to somewhere that we can test or dump it later.

    * Ensure that as many DEBUG messages as possible are actually
       executed, to ensure they are actually syntactically valid (they
       often have not been).

    * Ensure that we create useful output for tests that doesn't
      overwhelm the testing system (which means we can't capture the
      100 MB of debug logging on every run).

    To do this we create a logger fixture at the root level, which
    defaults to INFO and create a Null Logger at DEBUG which lets
    us execute log messages at DEBUG but not keep the output.

    To support local debugging OS_DEBUG=True can be set in the
    environment, which will print out the full debug logging.

    There are also a set of overrides for particularly verbose
    modules to be even less than INFO.

    """

    def setUp(self):
        super(StandardLogging, self).setUp()

        # set root logger to debug
        root = std_logging.getLogger()
        root.setLevel(std_logging.INFO)

        # supports collecting debug level for local runs
        if os.environ.get('OS_DEBUG') in _TRUE_VALUES:
            level = std_logging.DEBUG
        else:
            level = std_logging.INFO

        # Collect logs
        fs = '%(asctime)s %(levelname)s [%(name)s] %(message)s'
        self.logger = self.useFixture(
            fixtures.FakeLogger(format=fs, level=None))
        # TODO(sdague): why can't we send level through the fake
        # logger? Tests prove that it breaks, but it's worth getting
        # to the bottom of.
        root.handlers[0].setLevel(level)

        if level > std_logging.DEBUG:
            # Just attempt to format debug level logs, but don't save them
            handler = NullHandler()
            self.useFixture(fixtures.LogHandler(handler, nuke_handlers=False))
            handler.setLevel(std_logging.DEBUG)

            # Don't log every single DB migration step
            std_logging.getLogger(
                'migrate.versioning.api').setLevel(std_logging.WARNING)

        # At times we end up calling back into main() functions in
        # testing. This has the possibility of calling logging.setup
        # again, which completely unwinds the logging capture we've
        # created here. Once we've setup the logging in the way we want,
        # disable the ability for the test to change this.
        def fake_logging_setup(*args):
            pass

        self.useFixture(
            fixtures.MonkeyPatch('oslo_log.log.setup', fake_logging_setup))


class WarningsFixture(fixtures.Fixture):
    """Filters out warnings during test runs."""

    def setUp(self):
        super().setUp()

        self._original_warning_filters = warnings.filters[:]

        # NOTE(sdague): Make deprecation warnings only happen once. Otherwise
        # this gets kind of crazy given the way that upstream python libs use
        # this.
        warnings.simplefilter('once', DeprecationWarning)

        # NOTE(sdague): this remains an unresolved item around the way
        # forward on is_admin, the deprecation is definitely really premature.
        warnings.filterwarnings(
            'ignore',
            message='Policy enforcement is depending on the value of is_admin.'
                    ' This key is deprecated. Please update your policy '
                    'file to use the standard policy values.')

        # We can't do anything about this outside of cinder
        warnings.filterwarnings(
            'ignore',
            message='distutils Version classes are deprecated. .*',
            category=DeprecationWarning,
        )

        warnings.filterwarnings(
            'ignore',
            message='the imp module is deprecated in favour of importlib',
            category=DeprecationWarning,
        )

        warnings.filterwarnings(
            'ignore',
            message='invalid escape sequence',
            category=DeprecationWarning,
        )
        warnings.filterwarnings(
            'error',
            message='invalid escape sequence',
            category=DeprecationWarning,
            module='cinder',
        )

        warnings.filterwarnings(
            'ignore',
            message='Policy ".*":".*" was deprecated in ',
            module='oslo_policy',
            category=UserWarning,
        )

        # Enable deprecation warnings for cinder itself to capture upcoming
        # SQLAlchemy changes

        warnings.filterwarnings(
            'ignore',
            category=sqla_exc.SADeprecationWarning,
        )

        warnings.filterwarnings(
            'error',
            module='cinder',
            category=sqla_exc.SADeprecationWarning,
        )

        # ...but filter everything out until we get around to fixing them
        # TODO: Fix all of these

        warnings.filterwarnings(
            'ignore',
            module='cinder',
            message='The current statement is being autocommitted using ',
            category=sqla_exc.SADeprecationWarning,
        )

        warnings.filterwarnings(
            'ignore',
            module='cinder',
            message='The Session.begin.subtransactions flag is deprecated ',
            category=sqla_exc.SADeprecationWarning,
        )

        self.addCleanup(self._reset_warning_filters)

    def _reset_warning_filters(self):
        warnings.filters[:] = self._original_warning_filters


class UnHelperfulClientChannel(privsep_daemon._ClientChannel):
    def __init__(self, context):
        raise Exception('You have attempted to start a privsep helper. '
                        'This is not allowed in the gate, and '
                        'indicates a failure to have mocked your tests.')


class PrivsepNoHelperFixture(fixtures.Fixture):
    """A fixture to catch failures to mock privsep's rootwrap helper.

    If you fail to mock away a privsep'd method in a unit test, then
    you may well end up accidentally running the privsep rootwrap
    helper. This will fail in the gate, but it fails in a way which
    doesn't identify which test is missing a mock. Instead, we
    raise an exception so that you at least know where you've missed
    something.
    """

    def setUp(self):
        super(PrivsepNoHelperFixture, self).setUp()

        self.useFixture(fixtures.MonkeyPatch(
            'oslo_privsep.daemon.RootwrapClientChannel',
            UnHelperfulClientChannel))


class PolicyFixture(fixtures.Fixture):
    """Load the live policy for tests.

    A base policy fixture that starts with the assumption that you'd
    like to load and enforce the shipped default policy in tests.

    """
    def setUp(self):
        super().setUp()
        cinder.policy.reset()
        # Suppress deprecation warnings for unit tests.
        cinder.policy.init(suppress_deprecation_warnings=True)
        self.addCleanup(cinder.policy.reset)

    def set_rules(self, rules, overwrite=True):
        policy = cinder.policy._ENFORCER
        policy.set_rules(oslo_policy.Rules.from_dict(rules),
                         overwrite=overwrite)
