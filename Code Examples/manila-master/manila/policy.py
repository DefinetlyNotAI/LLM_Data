# Copyright (c) 2011 OpenStack, LLC.
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

"""Policy Engine For Manila"""

import functools
import sys

from oslo_config import cfg
from oslo_log import log as logging
from oslo_policy import opts
from oslo_policy import policy
from oslo_utils import excutils

from manila import exception
from manila import policies

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
_ENFORCER = None


# TODO(gmann): Remove setting the default value of config policy_file
# 'policy_file' once oslo_policy change its default value to what
# is overridden here.
DEFAULT_POLICY_FILE = 'policy.yaml'
opts.set_defaults(CONF, DEFAULT_POLICY_FILE)
opts.set_defaults(
    cfg.CONF,
    DEFAULT_POLICY_FILE)


def reset():
    global _ENFORCER
    if _ENFORCER:
        _ENFORCER.clear()
        _ENFORCER = None


def init(rules=None, use_conf=True, suppress_deprecation_warnings=False):
    """Init an Enforcer class.

        :param policy_file: Custom policy file to use, if none is specified,
                          `CONF.policy_file` will be used.
        :param rules: Default dictionary / Rules to use. It will be
                    considered just in the first instantiation.
        :param use_conf: Whether to load rules from config file.
        :param suppress_deprecation_warnings: Whether to suppress policy
                                            deprecation warnings.
    """

    global _ENFORCER
    if not _ENFORCER:
        _ENFORCER = policy.Enforcer(CONF,
                                    rules=rules,
                                    use_conf=use_conf)

        # NOTE(gouthamr): Explicitly disable the warnings for policies
        # changing their default check_str. During
        # secure-rbac / policy-defaults-refresh work, all the policy
        # defaults have been changed and warning for each policy started
        # filling the log limits for various tools. Once we move to new
        # defaults only world then we can enable these warning again.
        _ENFORCER.suppress_default_change_warnings = True
        # Suppressing deprecation warnings is fine for tests. However we
        # won't do it by default
        _ENFORCER.suppress_deprecation_warnings = suppress_deprecation_warnings

        register_rules(_ENFORCER)


def enforce(context, action, target, do_raise=True):
    """Verifies that the action is valid on the target in this context.

       **IMPORTANT** ONLY for use in API extensions. This method ignores
       unregistered rules and applies a default rule on them; there should
       be no unregistered rules in first party manila APIs.

       :param context: manila context
       :param action: string representing the action to be checked,
           this should be colon separated for clarity.
           i.e. ``share:create``,
       :param target: dictionary representing the object of the action
           for object creation, this should be a dictionary representing the
           location of the object e.g. ``{'project_id': context.project_id}``
       :param do_raise: Whether to raise an exception if check fails.

       :returns: When ``do_raise`` is ``False``, returns a value that
                 evaluates as ``True`` or ``False`` depending on whether
                 the policy allows action on the target.

       :raises: manila.exception.PolicyNotAuthorized if verification fails
                and ``do_raise`` is ``True``.

    """
    init()

    try:
        return _ENFORCER.enforce(action,
                                 target,
                                 context,
                                 do_raise=do_raise,
                                 exc=exception.PolicyNotAuthorized,
                                 action=action)
    except policy.InvalidScope:
        raise exception.PolicyNotAuthorized(action=action)


def set_rules(rules, overwrite=True, use_conf=False):
    """Set rules based on the provided dict of rules.

       :param rules: New rules to use. It should be an instance of dict.
       :param overwrite: Whether to overwrite current rules or update them
                         with the new rules.
       :param use_conf: Whether to reload rules from config file.
    """

    init(use_conf=False)
    _ENFORCER.set_rules(rules, overwrite, use_conf)


def get_rules():
    if _ENFORCER:
        return _ENFORCER.rules


def register_rules(enforcer):
    enforcer.register_defaults(policies.list_rules())


def get_enforcer():
    # This method is for use by oslopolicy CLI scripts. Those scripts need the
    # 'output-file' and 'namespace' options, but having those in sys.argv means
    # loading the Manila config options will fail as those are not expected to
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

    cfg.CONF(conf_args, project='manila')
    init()
    return _ENFORCER


def authorize(context, action, target, do_raise=True, exc=None):
    """Verifies that the action is valid on the target in this context.

       :param context: manila context
       :param action: string representing the action to be checked
           this should be colon separated for clarity.
           i.e. ``share:create``,
       :param target: dictionary representing the object of the action
           for object creation this should be a dictionary representing the
           location of the object e.g. ``{'project_id': context.project_id}``
       :param do_raise: if True (the default), raises PolicyNotAuthorized;
           if False, returns False
       :param exc: Class of the exception to raise if the check fails.
                   Any remaining arguments passed to :meth:`authorize` (both
                   positional and keyword arguments) will be passed to
                   the exception class. If not specified,
                   :class:`PolicyNotAuthorized` will be used.

       :raises manila.exception.PolicyNotAuthorized: if verification fails
           and do_raise is True. Or if 'exc' is specified it will raise an
           exception of that type.

       :return: returns a non-False value (not necessarily "True") if
           authorized, and the exact value False if not authorized and
           do_raise is False.
    """
    init()
    if not exc:
        exc = exception.PolicyNotAuthorized
    target = target or default_target(context)

    try:
        result = _ENFORCER.authorize(action, target, context,
                                     do_raise=do_raise, exc=exc, action=action)
    except policy.PolicyNotRegistered:
        with excutils.save_and_reraise_exception():
            LOG.exception('Policy not registered')
    except policy.InvalidScope:
        if do_raise:
            raise exception.PolicyNotAuthorized(action=action)
        else:
            return False
    except Exception:
        with excutils.save_and_reraise_exception():
            msg_args = {
                'action': action,
                'credentials': context.to_policy_values(),
            }
            LOG.debug('Policy check for %(action)s failed with credentials '
                      '%(credentials)s', msg_args)
    return result


def default_target(context):
    return {'project_id': context.project_id, 'user_id': context.user_id}


def check_is_admin(context):
    """Whether or not user is admin according to policy setting.

    """
    # the target is user-self
    target = default_target(context)
    return authorize(context, 'context_is_admin', target, do_raise=False)


def check_is_host_admin(context):
    """Whether or not user is host admin according to policy setting.

    """
    # the target is user-self
    target = default_target(context)
    return authorize(context, 'context_is_host_admin', target, do_raise=False)


def wrap_check_policy(resource):
    """Check policy corresponding to the wrapped methods prior to execution."""
    def check_policy_wraper(func):
        @functools.wraps(func)
        def wrapped(self, context, target_obj, *args, **kwargs):
            check_policy(context, resource, func.__name__, target_obj)
            return func(self, context, target_obj, *args, **kwargs)

        return wrapped
    return check_policy_wraper


def check_policy(context, resource, action, target_obj=None, do_raise=True):
    target = target_obj or default_target(context)
    _action = '%s:%s' % (resource, action)
    return authorize(context, _action, target, do_raise=do_raise)
