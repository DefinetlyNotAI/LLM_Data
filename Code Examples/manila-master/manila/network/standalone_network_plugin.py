# Copyright 2015 Mirantis, Inc.
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

import netaddr
from oslo_config import cfg
from oslo_log import log

from manila.common import constants
from manila import exception
from manila.i18n import _
from manila import network
from manila import utils

standalone_network_plugin_opts = [
    cfg.StrOpt(
        'standalone_network_plugin_gateway',
        help="Gateway address that should be used. Required."),
    cfg.StrOpt(
        'standalone_network_plugin_mask',
        help="Network mask that will be used. Can be either decimal "
             "like '24' or binary like '255.255.255.0'. Required."),
    cfg.StrOpt(
        'standalone_network_plugin_network_type',
        help="Network type, such as 'flat', 'vlan', 'vxlan' or 'gre'. "
             "Empty value is alias for 'flat'. "
             "It will be assigned to share-network and share drivers will be "
             "able to use this for network interfaces within provisioned "
             "share servers. Optional.",
        choices=['flat', 'vlan', 'vxlan', 'gre']),
    cfg.IntOpt(
        'standalone_network_plugin_segmentation_id',
        help="Set it if network has segmentation (VLAN, VXLAN, etc...). "
             "It will be assigned to share-network and share drivers will be "
             "able to use this for network interfaces within provisioned "
             "share servers. Optional. Example: 1001"),
    cfg.ListOpt(
        'standalone_network_plugin_allowed_ip_ranges',
        help="Can be IP address, range of IP addresses or list of addresses "
             "or ranges. Contains addresses from IP network that are allowed "
             "to be used. If empty, then will be assumed that all host "
             "addresses from network can be used. Optional. "
             "Examples: 10.0.0.10 or 10.0.0.10-10.0.0.20 or "
             "10.0.0.10-10.0.0.20,10.0.0.30-10.0.0.40,10.0.0.50"),
    cfg.IntOpt(
        'standalone_network_plugin_mtu',
        default=1500,
        help="Maximum Transmission Unit (MTU) value of the network. Default "
             "value is 1500."),
]

CONF = cfg.CONF
LOG = log.getLogger(__name__)


class StandaloneNetworkPlugin(network.NetworkBaseAPI):
    """Standalone network plugin for share drivers.

    This network plugin can be used with any network platform.
    It can serve flat networks as well as segmented.
    It does not require some specific network services in OpenStack like
    the Neutron plugin.
    The only thing that plugin does is reservation and release of IP addresses
    from some network.
    """

    def __init__(self, config_group_name=None, db_driver=None, label='user'):
        self.config_group_name = config_group_name or 'DEFAULT'
        super(StandaloneNetworkPlugin,
              self).__init__(config_group_name=self.config_group_name,
                             db_driver=db_driver)
        CONF.register_opts(
            standalone_network_plugin_opts,
            group=self.config_group_name)
        self.configuration = getattr(CONF, self.config_group_name, CONF)
        self._set_persistent_network_data()
        self._label = label
        LOG.debug(
            "\nStandalone network plugin data for config group "
            "'%(config_group)s': \n"
            "IP version - %(ip_version)s\n"
            "Used network - %(net)s\n"
            "Used gateway - %(gateway)s\n"
            "Used network type - %(network_type)s\n"
            "Used segmentation ID - %(segmentation_id)s\n"
            "Allowed CIDRs - %(cidrs)s\n"
            "Original allowed IP ranges - %(ip_ranges)s\n"
            "Reserved IP addresses - %(reserved)s\n",
            dict(
                config_group=self.config_group_name,
                ip_version=self.ip_version,
                net=str(self.net),
                gateway=self.gateway,
                network_type=self.network_type,
                segmentation_id=self.segmentation_id,
                cidrs=self.allowed_cidrs,
                ip_ranges=self.allowed_ip_ranges,
                reserved=self.reserved_addresses))

    @property
    def label(self):
        return self._label

    def _set_persistent_network_data(self):
        """Sets persistent data for whole plugin."""
        # NOTE(tommylikehu): Standalone plugin could only support
        # either IPv4 or IPv6, so if both network_plugin_ipv4_enabled
        # and network_plugin_ipv6_enabled are configured True
        # we would only support IPv6.
        ipv4_enabled = getattr(self.configuration,
                               'network_plugin_ipv4_enabled', None)
        ipv6_enabled = getattr(self.configuration,
                               'network_plugin_ipv6_enabled', None)

        if ipv4_enabled:
            ip_version = 4
        if ipv6_enabled:
            ip_version = 6
        if ipv4_enabled and ipv6_enabled:
            LOG.warning("Only IPv6 is enabled, although both "
                        "'network_plugin_ipv4_enabled' and "
                        "'network_plugin_ipv6_enabled' are "
                        "configured True.")

        self.network_type = (
            self.configuration.standalone_network_plugin_network_type)
        self.segmentation_id = (
            self.configuration.standalone_network_plugin_segmentation_id)
        self.gateway = self.configuration.standalone_network_plugin_gateway
        self.mask = self.configuration.standalone_network_plugin_mask
        self.allowed_ip_ranges = (
            self.configuration.standalone_network_plugin_allowed_ip_ranges)
        self.ip_version = ip_version
        self.net = self._get_network()
        self.allowed_cidrs = self._get_list_of_allowed_addresses()
        self.reserved_addresses = (
            str(self.net.network),
            self.gateway,
            str(self.net.broadcast))
        self.mtu = self.configuration.standalone_network_plugin_mtu

    def _get_network(self):
        """Returns IPNetwork object calculated from gateway and netmask."""
        if not isinstance(self.gateway, str):
            raise exception.NetworkBadConfigurationException(
                _("Configuration option 'standalone_network_plugin_gateway' "
                  "is required and has improper value '%s'.") % self.gateway)
        if not isinstance(self.mask, str):
            raise exception.NetworkBadConfigurationException(
                _("Configuration option 'standalone_network_plugin_mask' is "
                  "required and has improper value '%s'.") % self.mask)
        try:
            return netaddr.IPNetwork(self.gateway + '/' + self.mask)
        except netaddr.AddrFormatError as e:
            raise exception.NetworkBadConfigurationException(
                reason=e)

    def _get_list_of_allowed_addresses(self):
        """Returns list of CIDRs that can be used for getting IP addresses.

        Reads information provided via configuration, such as gateway,
        netmask, segmentation ID and allowed IP ranges, then performs
        validation of provided data.

        :returns: list of CIDRs as text types.
        :raises: exception.NetworkBadConfigurationException
        """
        cidrs = []
        if self.allowed_ip_ranges:
            for ip_range in self.allowed_ip_ranges:
                ip_range_start = ip_range_end = None
                if utils.is_valid_ip_address(ip_range, self.ip_version):
                    ip_range_start = ip_range_end = ip_range
                elif '-' in ip_range:
                    ip_range_list = ip_range.split('-')
                    if len(ip_range_list) == 2:
                        ip_range_start = ip_range_list[0]
                        ip_range_end = ip_range_list[1]
                        for ip in ip_range_list:
                            utils.is_valid_ip_address(ip, self.ip_version)
                    else:
                        msg = _("Wrong value for IP range "
                                "'%s' was provided.") % ip_range
                        raise exception.NetworkBadConfigurationException(
                            reason=msg)
                else:
                    msg = _("Config option "
                            "'standalone_network_plugin_allowed_ip_ranges' "
                            "has incorrect value "
                            "'%s'.") % self.allowed_ip_ranges
                    raise exception.NetworkBadConfigurationException(
                        reason=msg)

                range_instance = netaddr.IPRange(ip_range_start, ip_range_end)

                if range_instance not in self.net:
                    data = dict(
                        range=str(range_instance),
                        net=str(self.net),
                        gateway=self.gateway,
                        netmask=self.net.netmask)
                    msg = _("One of provided allowed IP ranges ('%(range)s') "
                            "does not fit network '%(net)s' combined from "
                            "gateway '%(gateway)s' and netmask "
                            "'%(netmask)s'.") % data
                    raise exception.NetworkBadConfigurationException(
                        reason=msg)

                cidrs.extend(
                    str(cidr) for cidr in range_instance.cidrs())
        else:
            if self.net.version != self.ip_version:
                msg = _("Configured invalid IP version '%(conf_v)s', network "
                        "has version ""'%(net_v)s'") % dict(
                            conf_v=self.ip_version, net_v=self.net.version)
                raise exception.NetworkBadConfigurationException(reason=msg)
            cidrs.append(str(self.net))

        return cidrs

    def _get_available_ips(self, context, amount):
        """Returns IP addresses from allowed IP range if there are unused IPs.

        :returns: IP addresses as list of text types
        :raises: exception.NetworkBadConfigurationException
        """
        ips = []
        if amount < 1:
            return ips
        iterator = netaddr.iter_unique_ips(*self.allowed_cidrs)
        for ip in iterator:
            ip = str(ip)
            if (ip in self.reserved_addresses or
                    self.db.network_allocations_get_by_ip_address(context,
                                                                  ip)):
                continue
            else:
                ips.append(ip)
            if len(ips) == amount:
                return ips
        msg = _("No available IP addresses left in CIDRs %(cidrs)s. "
                "Requested amount of IPs to be provided '%(amount)s', "
                "available only '%(available)s'.") % {
                    'cidrs': self.allowed_cidrs,
                    'amount': amount,
                    'available': len(ips)}
        raise exception.NetworkBadConfigurationException(reason=msg)

    def include_network_info(self, share_network_subnet):
        """Includes share-network-subnet with plugin specific data."""
        self._save_network_info(None, share_network_subnet, save_db=False)

    def _save_network_info(self, context, share_network_subnet, save_db=True):
        """Update share-network-subnet with plugin specific data."""
        data = {
            'network_type': self.network_type,
            'segmentation_id': self.segmentation_id,
            'cidr': str(self.net.cidr),
            'gateway': str(self.gateway),
            'ip_version': self.ip_version,
            'mtu': self.mtu,
        }
        share_network_subnet.update(data)
        if self.label != 'admin' and save_db:
            self.db.share_network_subnet_update(
                context, share_network_subnet['id'], data)

    @utils.synchronized(
        "allocate_network_for_standalone_network_plugin", external=True)
    def allocate_network(self, context, share_server, share_network=None,
                         share_network_subnet=None, **kwargs):
        """Allocate network resources using one dedicated network.

        This one has interprocess lock to avoid concurrency in creation of
        share servers with same IP addresses using different share-networks.
        """
        allocation_count = kwargs.get('count', 1)
        if self.label != 'admin':
            self._verify_share_network(share_server['id'],
                                       share_network_subnet)
        else:
            share_network_subnet = share_network_subnet or {}
        self._save_network_info(context, share_network_subnet)
        allocations = []
        ip_addresses = self._get_available_ips(context, allocation_count)
        for ip_address in ip_addresses:
            data = {
                'share_server_id': share_server['id'],
                'ip_address': ip_address,
                'status': constants.STATUS_ACTIVE,
                'label': self.label,
                'network_type': share_network_subnet['network_type'],
                'segmentation_id': share_network_subnet['segmentation_id'],
                'cidr': share_network_subnet['cidr'],
                'gateway': share_network_subnet['gateway'],
                'ip_version': share_network_subnet['ip_version'],
                'mtu': share_network_subnet['mtu'],
            }
            if self.label != 'admin':
                data['share_network_subnet_id'] = (
                    share_network_subnet['id'])
            allocations.append(
                self.db.network_allocation_create(context, data))
        return allocations

    def deallocate_network(self, context, share_server_id,
                           share_network=None, share_network_subnet=None):
        """Deallocate network resources for share server."""
        allocations = self.db.network_allocations_get_for_share_server(
            context, share_server_id)
        for allocation in allocations:
            self.db.network_allocation_delete(context, allocation['id'])

    def unmanage_network_allocations(self, context, share_server_id):
        self.deallocate_network(context, share_server_id)

    def manage_network_allocations(self, context, allocations, share_server,
                                   share_network=None,
                                   share_network_subnet=None):
        if self.label != 'admin':
            self._verify_share_network_subnet(share_server['id'],
                                              share_network_subnet)
        else:
            share_network_subnet = share_network_subnet or {}
        self._save_network_info(context, share_network_subnet)

        # We begin matching the allocations to known neutron ports and
        # finally return the non-consumed allocations
        remaining_allocations = list(allocations)

        ips = [netaddr.IPAddress(allocation) for allocation
               in remaining_allocations]
        cidrs = [netaddr.IPNetwork(cidr) for cidr in self.allowed_cidrs]
        selected_allocations = []

        for ip in ips:
            if any(ip in cidr for cidr in cidrs):
                allocation = str(ip)
                selected_allocations.append(allocation)

        for allocation in selected_allocations:
            data = {
                'share_server_id': share_server['id'],
                'ip_address': allocation,
                'status': constants.STATUS_ACTIVE,
                'label': self.label,
                'network_type': share_network_subnet['network_type'],
                'segmentation_id': share_network_subnet['segmentation_id'],
                'cidr': share_network_subnet['cidr'],
                'gateway': share_network_subnet['gateway'],
                'ip_version': share_network_subnet['ip_version'],
                'mtu': share_network_subnet['mtu'],
            }
            if self.label != 'admin':
                data['share_network_subnet_id'] = (
                    share_network_subnet['id'])
            self.db.network_allocation_create(context, data)
            remaining_allocations.remove(allocation)

        return remaining_allocations
