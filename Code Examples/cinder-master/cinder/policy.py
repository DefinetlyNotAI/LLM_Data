# Copyright (c) 2011 OpenStack Foundation
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

"""Policy Engine For Cinder"""

import sys
import typing
from typing import Optional, Type

from oslo_config import cfg
from oslo_log import log as logging
from oslo_policy import opts as policy_opts
from oslo_policy import policy
from oslo_utils import excutils


from cinder import context
from cinder import exception
from cinder import policies

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
# TODO(gmann): Remove overriding the default value of config options:
# - 'policy_file' once oslo_policy change their default value to what is
# overridden here.
# - 'enforce_scope', and 'enforce_new_defaults' once cinder is ready with the
# new RBAC (oslo_policy enable them by default)
DEFAULT_POLICY_FILENAME = 'policy.yaml'
policy_opts.set_defaults(
    cfg.CONF,
    DEFAULT_POLICY_FILENAME,
    enforce_scope=False,
    enforce_new_defaults=False)

_ENFORCER: Optional[policy.Enforcer] = None


def reset() -> None:
    global _ENFORCER
    if _ENFORCER:
        _ENFORCER.clear()
        _ENFORCER = None


def init(use_conf=True,
         suppress_deprecation_warnings: bool = False) -> None:
    """Init an Enforcer class.

    :param use_conf: Whether to load rules from config file.
    """

    global _ENFORCER
    if not _ENFORCER:
        _ENFORCER = policy.Enforcer(
            CONF,
            use_conf=use_conf,
            fallback_to_json_file=False)
        _ENFORCER.suppress_deprecation_warnings = suppress_deprecation_warnings
        register_rules(_ENFORCER)
        _ENFORCER.load_rules()

    _ENFORCER = typing.cast(policy.Enforcer, _ENFORCER)


def enforce(context, action: str, target: dict):
    """Verifies that the action is valid on the target in this context.

    :param context: cinder context
    :param action: string representing the action to be checked
                   this should be colon separated for clarity.
                   i.e. ``compute:create_instance``,
                   ``compute:attach_volume``,
                   ``volume:attach_volume``

    :param target: dictionary representing the object of the action for object
                   creation this should be a dictionary representing the
                   location of the object e.g.
                   ``{'project_id': context.project_id}``

    :raises PolicyNotAuthorized: if verification fails.
    """
    init()
    assert _ENFORCER is not None

    try:
        return _ENFORCER.enforce(action,
                                 target,
                                 context,
                                 do_raise=True,
                                 exc=exception.PolicyNotAuthorized,
                                 action=action)
    except policy.InvalidScope:
        raise exception.PolicyNotAuthorized(action=action)


def set_rules(rules: dict,
              overwrite: bool = True,
              use_conf: bool = False) -> None:
    """Set rules based on the provided dict of rules.

    :param rules: New rules to use. It should be an instance of dict.
    :param overwrite: Whether to overwrite current rules or update them
                      with the new rules.
    :param use_conf: Whether to reload rules from config file.
    """

    init(use_conf=False)
    assert _ENFORCER is not None

    _ENFORCER.set_rules(rules, overwrite, use_conf)


def get_rules():
    if _ENFORCER:
        return _ENFORCER.rules


def register_rules(enforcer):
    enforcer.register_defaults(policies.list_rules())


def get_enforcer() -> policy.Enforcer:
    # This method is for use by oslopolicy CLI scripts. Those scripts need the
    # 'output-file' and 'namespace' options, but having those in sys.argv means
    # loading the Cinder config options will fail as those are not expected to
    # be present. So we pass in an arg list with those stripped out.
    conf_args = []
    # Start at 1 because cfg.CONF expects the equivalent of sys.argv[1:]
    i = 1
    while i < len(sys.argv):
        if sys.argv[i].strip('-') in ['namespace', 'output-file']:
            i += 2
            continue
        conf_args.append(sys.argv[i])
        i += 1

    cfg.CONF(conf_args, project='cinder')
    init()
    assert _ENFORCER is not None
    return _ENFORCER


def authorize(context,
              action: str,
              target: dict,
              do_raise: bool = True,
              exc: Optional[Type[Exception]] = None):
    """Verifies that the action is valid on the target in this context.

    :param context: cinder context
    :param action: string representing the action to be checked
                   this should be colon separated for clarity.
                   i.e. ``compute:create_instance``,
                   ``compute:attach_volume``,
                   ``volume:attach_volume``
    :param target: dictionary representing the object of the action for object
                   creation this should be a dictionary representing the
                   location of the object e.g.
                   ``{'project_id': context.project_id}``
    :param do_raise: if True (the default), raises PolicyNotAuthorized;
                     if False, returns False
    :param exc: Class of the exception to raise if the check fails.
                Any remaining arguments passed to :meth:`authorize` (both
                positional and keyword arguments) will be passed to
                the exception class. If not specified,
                :class:`PolicyNotAuthorized` will be used.

    :raises cinder.exception.PolicyNotAuthorized: if verification fails
           and do_raise is True. Or if 'exc' is specified it will raise an
           exception of that type.

    :return: returns a non-False value (not necessarily "True") if
             authorized, and the exact value False if not authorized and
             do_raise is False.
    """
    init()
    assert _ENFORCER is not None

    if not exc:
        exc = exception.PolicyNotAuthorized
    try:
        result = _ENFORCER.authorize(action, target, context,
                                     do_raise=do_raise, exc=exc, action=action)
    except policy.PolicyNotRegistered:
        with excutils.save_and_reraise_exception():
            LOG.exception('Policy not registered')
    except Exception:
        with excutils.save_and_reraise_exception():
            LOG.debug('Policy check for %(action)s failed with context '
                      '%(credentials)s',
                      {'action': action,
                       'credentials': context.to_policy_values()})
    return result


def check_is_admin(context: 'context.RequestContext'):
    """Whether or not user is admin according to policy setting."""
    init()
    assert _ENFORCER is not None

    # the target is user-self
    credentials = context.to_policy_values()
    target = credentials
    return _ENFORCER.authorize('context_is_admin', target, credentials)
