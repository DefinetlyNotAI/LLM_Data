# Copyright 2022 Infinidat Ltd.
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
INFINIDAT InfiniBox Share Driver
"""

import functools

import ipaddress
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import units
import requests

from manila.common import constants
from manila import exception
from manila.i18n import _
from manila.share import driver
from manila.share import utils
from manila import version

try:
    import capacity
except ImportError:
    capacity = None

try:
    import infinisdk
except ImportError:
    infinisdk = None


LOG = logging.getLogger(__name__)

infinidat_connection_opts = [
    cfg.HostAddressOpt('infinibox_hostname',
                       help='The name (or IP address) for the INFINIDAT '
                       'Infinibox storage system.'),
    cfg.BoolOpt('infinidat_use_ssl',
                help='Use SSL to connect to the INFINIDAT Infinibox storage '
                     'system.',
                default=False),
    cfg.BoolOpt('infinidat_suppress_ssl_warnings',
                help='Suppress requests library SSL certificate warnings.',
                default=False), ]

infinidat_auth_opts = [
    cfg.StrOpt('infinibox_login',
               help=('Administrative user account name used to access the '
                     'INFINIDAT Infinibox storage system.')),
    cfg.StrOpt('infinibox_password',
               help=('Password for the administrative user account '
                     'specified in the infinibox_login option.'),
               secret=True), ]

infinidat_general_opts = [
    cfg.StrOpt('infinidat_pool_name',
               help='Name of the pool from which volumes are allocated.'),
    cfg.StrOpt('infinidat_nas_network_space_name',
               help='Name of the NAS network space on the INFINIDAT '
               'InfiniBox.'),
    cfg.BoolOpt('infinidat_thin_provision', help='Use thin provisioning.',
                default=True),
    cfg.BoolOpt('infinidat_snapdir_accessible',
                help=('Controls access to the .snapshot directory. '
                      'By default, each share allows access to its own '
                      '.snapshot directory, which contains files and '
                      'directories of each snapshot taken. To restrict '
                      'access to the .snapshot directory, this option '
                      'should be set to False.'),
                default=True),
    cfg.BoolOpt('infinidat_snapdir_visible',
                help=('Controls visibility of the .snapshot directory. '
                      'By default, each share contains the .snapshot '
                      'directory, which is hidden on the client side. '
                      'To make the .snapshot directory visible, this '
                      'option should be set to True.'),
                default=False), ]

CONF = cfg.CONF
CONF.register_opts(infinidat_connection_opts)
CONF.register_opts(infinidat_auth_opts)
CONF.register_opts(infinidat_general_opts)

_MANILA_TO_INFINIDAT_ACCESS_LEVEL = {
    constants.ACCESS_LEVEL_RW: 'RW',
    constants.ACCESS_LEVEL_RO: 'RO',
}

# Max retries for the REST API client in case of a failure:
_API_MAX_RETRIES = 5
# Identifier used as the REST API User-Agent string:
_INFINIDAT_MANILA_IDENTIFIER = (
    "manila/%s" % version.version_info.release_string())


def infinisdk_to_manila_exceptions(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except infinisdk.core.exceptions.InfiniSDKException as ex:
            # string formatting of 'ex' includes http code and url
            msg = _('Caught exception from infinisdk: %s') % ex
            LOG.exception(msg)
            raise exception.ShareBackendException(msg=msg)
    return wrapper


class InfiniboxShareDriver(driver.ShareDriver):
    """INFINIDAT InfiniBox Share driver.

    Version history:
        1.0 - initial release
        1.1 - added support for TLS/SSL communication
        1.2 - fixed host assisted migration
    """

    VERSION = '1.2'    # driver version

    def __init__(self, *args, **kwargs):
        super(InfiniboxShareDriver, self).__init__(False, *args, **kwargs)
        self.configuration.append_config_values(infinidat_connection_opts)
        self.configuration.append_config_values(infinidat_auth_opts)
        self.configuration.append_config_values(infinidat_general_opts)

    def _setup_and_get_system_object(self, management_address, auth, use_ssl):
        system = infinisdk.InfiniBox(management_address, auth=auth,
                                     use_ssl=use_ssl)
        system.api.add_auto_retry(
            lambda e: isinstance(
                e, infinisdk.core.exceptions.APITransportFailure) and
            "Interrupted system call" in e.error_desc, _API_MAX_RETRIES)
        system.api.set_source_identifier(_INFINIDAT_MANILA_IDENTIFIER)
        system.login()
        return system

    def do_setup(self, context):
        """Driver initialization"""
        if capacity is None:
            msg = _("Missing 'capacity' python module, ensure the library"
                    " is installed and available.")
            raise exception.ManilaException(message=msg)
        if infinisdk is None:
            msg = _("Missing 'infinisdk' python module, ensure the library"
                    " is installed and available.")
            raise exception.ManilaException(message=msg)

        if self.configuration.safe_get('infinidat_suppress_ssl_warnings'):
            LOG.warning('Suppressing requests library SSL Warnings')
            rpu = requests.packages.urllib3  # pylint: disable=no-member
            rpu.disable_warnings(rpu.exceptions.InsecureRequestWarning)
            rpu.disable_warnings(rpu.exceptions.InsecurePlatformWarning)

        use_ssl = self.configuration.safe_get('infinidat_use_ssl')
        infinibox_login = self._safe_get_from_config_or_fail('infinibox_login')
        infinibox_password = (
            self._safe_get_from_config_or_fail('infinibox_password'))
        auth = (infinibox_login, infinibox_password)

        management_address = (
            self._safe_get_from_config_or_fail('infinibox_hostname'))

        self._pool_name = (
            self._safe_get_from_config_or_fail('infinidat_pool_name'))

        self._network_space_name = (
            self._safe_get_from_config_or_fail(
                'infinidat_nas_network_space_name'))

        self._system = self._setup_and_get_system_object(management_address,
                                                         auth, use_ssl)

        backend_name = self.configuration.safe_get('share_backend_name')
        self._backend_name = backend_name or self.__class__.__name__

        thin_provisioning = self.configuration.infinidat_thin_provision
        self._provtype = "THIN" if thin_provisioning else "THICK"

        LOG.debug('setup complete')

    def _update_share_stats(self):
        """Retrieve stats info from share group."""
        (free_capacity_bytes, physical_capacity_bytes,
         provisioned_capacity_gb) = self._get_available_capacity()

        max_over_subscription_ratio = (
            self.configuration.max_over_subscription_ratio)

        data = dict(
            share_backend_name=self._backend_name,
            vendor_name='INFINIDAT',
            driver_version=self.VERSION,
            storage_protocol='NFS',
            total_capacity_gb=float(physical_capacity_bytes) / units.Gi,
            free_capacity_gb=float(free_capacity_bytes) / units.Gi,
            reserved_percentage=self.configuration.reserved_share_percentage,
            reserved_snapshot_percentage=(
                self.configuration.reserved_share_from_snapshot_percentage
                or self.configuration.reserved_share_percentage),
            reserved_share_extend_percentage=(
                self.configuration.reserved_share_extend_percentage
                or self.configuration.reserved_share_percentage),
            thin_provisioning=self.configuration.infinidat_thin_provision,
            max_over_subscription_ratio=max_over_subscription_ratio,
            provisioned_capacity_gb=provisioned_capacity_gb,
            snapshot_support=True,
            create_share_from_snapshot_support=True,
            mount_snapshot_support=True,
            revert_to_snapshot_support=True)

        super(InfiniboxShareDriver, self)._update_share_stats(data)

    def _get_available_capacity(self):
        # pylint: disable=no-member
        pool = self._get_infinidat_pool()
        free_capacity_bytes = (pool.get_free_physical_capacity() /
                               capacity.byte)
        physical_capacity_bytes = (pool.get_physical_capacity() /
                                   capacity.byte)
        provisioned_capacity_gb = (
            (pool.get_virtual_capacity() - pool.get_free_virtual_capacity()) /
            capacity.GB)
        # pylint: enable=no-member
        return (free_capacity_bytes, physical_capacity_bytes,
                provisioned_capacity_gb)

    def _safe_get_from_config_or_fail(self, config_parameter):
        config_value = self.configuration.safe_get(config_parameter)
        if not config_value:    # None or empty string
            reason = (_("%(config_parameter)s configuration parameter "
                        "must be specified") %
                      {'config_parameter': config_parameter})
            LOG.error(reason)
            raise exception.BadConfigurationException(reason=reason)
        return config_value

    def _verify_share_protocol(self, share):
        if share['share_proto'] != 'NFS':
            reason = (_('Unsupported share protocol: %(proto)s.') %
                      {'proto': share['share_proto']})
            LOG.error(reason)
            raise exception.InvalidShare(reason=reason)

    def _verify_access_type(self, access):
        if access['access_type'] != 'ip':
            reason = _('Only "ip" access type allowed for the NFS protocol.')
            LOG.error(reason)
            raise exception.InvalidShareAccess(reason=reason)
        return True

    def _make_share_name(self, manila_share):
        return 'openstack-shr-%s' % manila_share['id']

    def _make_snapshot_name(self, manila_snapshot):
        return 'openstack-snap-%s' % manila_snapshot['id']

    def _set_manila_object_metadata(self, infinidat_object, manila_object):
        data = {"system": "openstack",
                "openstack_version": version.version_info.release_string(),
                "manila_id": manila_object['id'],
                "manila_name": manila_object['name'],
                "host.created_by": _INFINIDAT_MANILA_IDENTIFIER}
        infinidat_object.set_metadata_from_dict(data)

    @infinisdk_to_manila_exceptions
    def _get_infinidat_pool(self):
        pool = self._system.pools.safe_get(name=self._pool_name)
        if pool is None:
            msg = _('Pool "%s" not found') % self._pool_name
            LOG.error(msg)
            raise exception.ShareBackendException(msg=msg)
        return pool

    @infinisdk_to_manila_exceptions
    def _get_infinidat_nas_network_space_ips(self):
        network_space = self._system.network_spaces.safe_get(
            name=self._network_space_name)
        if network_space is None:
            msg = _('INFINIDAT InfiniBox NAS network space "%s" '
                    'not found') % self._network_space_name
            LOG.error(msg)
            raise exception.ShareBackendException(msg=msg)
        network_space_ips = network_space.get_ips()
        if not network_space_ips:
            msg = _('INFINIDAT InfiniBox NAS network space "%s" has no IP '
                    'addresses defined') % self._network_space_name
            LOG.error(msg)
            raise exception.ShareBackendException(msg=msg)
        ip_addresses = (
            [ip_munch.ip_address for ip_munch in network_space_ips if
             ip_munch.enabled])
        if not ip_addresses:
            msg = _('INFINIDAT InfiniBox NAS network space "%s" has no '
                    'enabled IP addresses') % self._network_space_name
            LOG.error(msg)
            raise exception.ShareBackendException(msg=msg)
        return ip_addresses

    def _get_full_nfs_export_paths(self, export_path):
        network_space_ips = self._get_infinidat_nas_network_space_ips()
        return ['{network_space_ip}:{export_path}'.format(
            network_space_ip=network_space_ip,
            export_path=export_path) for network_space_ip in network_space_ips]

    @infinisdk_to_manila_exceptions
    def _get_infinidat_filesystem_by_name(self, name):
        filesystem = self._system.filesystems.safe_get(name=name)
        if filesystem is None:
            msg = (_('Filesystem not found on the Infinibox by its name: %s') %
                   name)
            LOG.error(msg)
            raise exception.ShareResourceNotFound(share_id=name)
        return filesystem

    def _get_infinidat_filesystem(self, manila_share):
        filesystem_name = self._make_share_name(manila_share)
        return self._get_infinidat_filesystem_by_name(filesystem_name)

    def _get_infinidat_snapshot_by_name(self, name):
        snapshot = self._system.filesystems.safe_get(name=name)
        if snapshot is None:
            msg = (_('Snapshot not found on the Infinibox by its name: %s') %
                   name)
            LOG.error(msg)
            raise exception.ShareSnapshotNotFound(snapshot_id=name)
        return snapshot

    def _get_infinidat_snapshot(self, manila_snapshot):
        snapshot_name = self._make_snapshot_name(manila_snapshot)
        return self._get_infinidat_snapshot_by_name(snapshot_name)

    def _get_infinidat_dataset(self, manila_object, is_snapshot):
        return (self._get_infinidat_snapshot(manila_object) if is_snapshot
                else self._get_infinidat_filesystem(manila_object))

    @infinisdk_to_manila_exceptions
    def _get_export(self, infinidat_filesystem):
        infinidat_exports = infinidat_filesystem.get_exports()
        if len(infinidat_exports) == 0:
            msg = _("Could not find share export")
            raise exception.ShareBackendException(msg=msg)
        elif len(infinidat_exports) > 1:
            msg = _("INFINIDAT filesystem has more than one active export; "
                    "possibly not a Manila share")
            LOG.error(msg)
            raise exception.ShareBackendException(msg=msg)
        return infinidat_exports[0]

    def _get_infinidat_access_level(self, access):
        """Translates between Manila access levels to INFINIDAT API ones"""
        access_level = access['access_level']
        try:
            return _MANILA_TO_INFINIDAT_ACCESS_LEVEL[access_level]
        except KeyError:
            raise exception.InvalidShareAccessLevel(level=access_level)

    def _get_ip_address_range(self, ip_address):
        """Parse single IP address or subnet into a range.

        If the IP address string is in subnet mask format, returns a
        <start ip>-<end-ip> string. If the IP address contains a single IP
        address, returns only that IP address.
        """

        ip_address = str(ip_address)

        # try treating the ip_address parameter as a range of IP addresses:
        ip_network = ipaddress.ip_network(ip_address, strict=False)
        ip_network_hosts = list(ip_network.hosts())
        if len(ip_network_hosts) < 2:    # /32, single IP address
            return ip_address.split('/')[0]
        return "{}-{}".format(ip_network_hosts[0], ip_network_hosts[-1])

    @infinisdk_to_manila_exceptions
    def _create_filesystem_export(self, infinidat_filesystem):
        snapdir_visible = self.configuration.infinidat_snapdir_visible
        infinidat_export = infinidat_filesystem.add_export(
            permissions=[], snapdir_visible=snapdir_visible)
        return self._make_export_locations(infinidat_export)

    @infinisdk_to_manila_exceptions
    def _ensure_filesystem_export(self, infinidat_filesystem):
        try:
            infinidat_export = self._get_export(infinidat_filesystem)
        except exception.ShareBackendException:
            return self._create_filesystem_export(infinidat_filesystem)
        actual = infinidat_export.is_snapdir_visible()
        expected = self.configuration.infinidat_snapdir_visible
        if actual is not expected:
            LOG.debug('Update snapdir_visible for %s: %s -> %s',
                      infinidat_filesystem.get_name(), actual, expected)
            infinidat_export.update_snapdir_visible(expected)
        return self._make_export_locations(infinidat_export)

    @infinisdk_to_manila_exceptions
    def _make_export_locations(self, infinidat_export):
        export_paths = self._get_full_nfs_export_paths(
            infinidat_export.get_export_path())
        export_locations = [{
            'path': export_path,
            'is_admin_only': False,
            'metadata': {},
        } for export_path in export_paths]
        return export_locations

    @infinisdk_to_manila_exceptions
    def _delete_share(self, share, is_snapshot):
        if is_snapshot:
            dataset_name = self._make_snapshot_name(share)
        else:
            dataset_name = self._make_share_name(share)
        try:
            infinidat_filesystem = (
                self._get_infinidat_filesystem_by_name(dataset_name))
        except exception.ShareResourceNotFound:
            message = ("share %(share)s not found on Infinibox, skipping "
                       "delete")
            LOG.warning(message, {"share": share})
            return      # filesystem not found
        try:
            infinidat_export = self._get_export(infinidat_filesystem)
            infinidat_export.safe_delete()
        except exception.ShareBackendException:
            # it is possible that the export has been deleted
            pass
        infinidat_filesystem.safe_delete()

    @infinisdk_to_manila_exceptions
    def _extend_share(self, infinidat_filesystem, share, new_size):
        # pylint: disable=no-member
        new_size_capacity_units = new_size * capacity.GiB
        # pylint: enable=no-member
        old_size = infinidat_filesystem.get_size()
        infinidat_filesystem.resize(new_size_capacity_units - old_size)

    @infinisdk_to_manila_exceptions
    def _update_access(self, manila_object, access_rules, is_snapshot):
        infinidat_filesystem = self._get_infinidat_dataset(
            manila_object, is_snapshot=is_snapshot)
        infinidat_export = self._get_export(infinidat_filesystem)
        permissions = [
            {'access': self._get_infinidat_access_level(access_rule),
             'client': self._get_ip_address_range(access_rule['access_to']),
             'no_root_squash': True} for access_rule in access_rules if
            self._verify_access_type(access_rule)]
        infinidat_export.update_permissions(permissions)

    @infinisdk_to_manila_exceptions
    def create_share(self, context, share, share_server=None):
        self._verify_share_protocol(share)

        pool = self._get_infinidat_pool()
        size = share['size'] * capacity.GiB    # pylint: disable=no-member
        name = self._make_share_name(share)
        snapdir_accessible = self.configuration.infinidat_snapdir_accessible
        infinidat_filesystem = self._system.filesystems.create(
            pool=pool, name=name, size=size, provtype=self._provtype,
            snapdir_accessible=snapdir_accessible)
        self._set_manila_object_metadata(infinidat_filesystem, share)
        return self._create_filesystem_export(infinidat_filesystem)

    @infinisdk_to_manila_exceptions
    def create_share_from_snapshot(self, context, share, snapshot,
                                   share_server=None, parent_share=None):
        name = self._make_share_name(share)
        infinidat_snapshot = self._get_infinidat_snapshot(snapshot)
        snapdir_accessible = self.configuration.infinidat_snapdir_accessible
        infinidat_new_share = infinidat_snapshot.create_snapshot(
            name=name, write_protected=False,
            snapdir_accessible=snapdir_accessible)
        self._extend_share(infinidat_new_share, share, share['size'])
        return self._create_filesystem_export(infinidat_new_share)

    @infinisdk_to_manila_exceptions
    def create_snapshot(self, context, snapshot, share_server=None):
        """Creates a snapshot."""
        share = snapshot['share']
        infinidat_filesystem = self._get_infinidat_filesystem(share)
        name = self._make_snapshot_name(snapshot)
        snapdir_accessible = self.configuration.infinidat_snapdir_accessible
        infinidat_snapshot = infinidat_filesystem.create_snapshot(
            name=name, snapdir_accessible=snapdir_accessible)
        # snapshot is created in the same size as the original share, so no
        # extending is needed
        self._set_manila_object_metadata(infinidat_snapshot, snapshot)
        return {'export_locations':
                self._create_filesystem_export(infinidat_snapshot)}

    def delete_share(self, context, share, share_server=None):
        try:
            self._verify_share_protocol(share)
        except exception.InvalidShare:
            # cleanup shouldn't fail on wrong protocol or missing share:
            message = ("failed to delete share %(share)s; unsupported share "
                       "protocol %(share_proto)s, only NFS is supported")
            LOG.warning(message, {"share": share,
                        "share_proto": share['share_proto']})
            return
        self._delete_share(share, is_snapshot=False)

    def delete_snapshot(self, context, snapshot, share_server=None):
        self._delete_share(snapshot, is_snapshot=True)

    def ensure_share(self, context, share, share_server=None):
        """Ensure that share is properly configured and exported."""
        # will raise ShareResourceNotFound if the share was not found:
        infinidat_filesystem = self._get_infinidat_filesystem(share)
        actual = infinidat_filesystem.is_snapdir_accessible()
        expected = self.configuration.infinidat_snapdir_accessible
        if actual is not expected:
            LOG.debug('Update snapdir_accessible for %s: %s -> %s',
                      infinidat_filesystem.get_name(), actual, expected)
            infinidat_filesystem.update_field('snapdir_accessible', expected)
        return self._ensure_filesystem_export(infinidat_filesystem)

    def ensure_shares(self, context, shares):
        """Invoked to ensure that shares are exported."""
        updates = {}
        for share in shares:
            updates[share['id']] = {
                'export_locations': self.ensure_share(context, share)}
        return updates

    def get_backend_info(self, context):
        snapdir_accessible = self.configuration.infinidat_snapdir_accessible
        snapdir_visible = self.configuration.infinidat_snapdir_visible
        return {
            'snapdir_accessible': snapdir_accessible,
            'snapdir_visible': snapdir_visible
        }

    def update_access(self, context, share, access_rules, add_rules,
                      delete_rules, share_server=None):
        # As the Infinibox API can bulk update export access rules, we will try
        # to use the access_rules list
        self._verify_share_protocol(share)
        self._update_access(share, access_rules, is_snapshot=False)

    def get_network_allocations_number(self):
        return 0

    @infinisdk_to_manila_exceptions
    def revert_to_snapshot(self, context, snapshot, share_access_rules,
                           snapshot_access_rules, share_server=None):
        infinidat_snapshot = self._get_infinidat_snapshot(snapshot)
        infinidat_parent_share = self._get_infinidat_filesystem(
            snapshot['share'])
        infinidat_parent_share.restore(infinidat_snapshot)

    def extend_share(self, share, new_size, share_server=None):
        infinidat_filesystem = self._get_infinidat_filesystem(share)
        self._extend_share(infinidat_filesystem, share, new_size)

    def snapshot_update_access(self, context, snapshot, access_rules,
                               add_rules, delete_rules, share_server=None):
        # snapshots are to be mounted in read-only mode, see:
        # "Add mountable snapshots" on openstack specs.
        access_rules, _, _ = utils.change_rules_to_readonly(
            access_rules, [], [])
        try:
            self._update_access(snapshot, access_rules, is_snapshot=True)
        except exception.InvalidShareAccess as e:
            raise exception.InvalidSnapshotAccess(e)
