# Copyright 2015 IBM Corp.
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
#

import math
import random
import re
import time
import unicodedata

from eventlet import greenthread
from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils as json
from oslo_service import loopingcall
from oslo_utils import encodeutils
from oslo_utils import excutils
from oslo_utils import strutils
from oslo_utils import units
import paramiko

from cinder import context
from cinder import exception
from cinder.i18n import _
from cinder import objects
from cinder.objects import fields
from cinder import ssh_utils
from cinder import utils as cinder_utils
from cinder.volume import configuration
from cinder.volume import driver
from cinder.volume.drivers.ibm.storwize_svc import (
    replication as storwize_rep)
from cinder.volume.drivers.ibm.storwize_svc import storwize_const
from cinder.volume.drivers.san import san
from cinder.volume import qos_specs
from cinder.volume import volume_types
from cinder.volume import volume_utils


INTERVAL_1_SEC = 1
DEFAULT_TIMEOUT = 15
CMMVC5753E = "CMMVC5753E"
LOG = logging.getLogger(__name__)

storwize_svc_opts = [
    cfg.ListOpt('storwize_svc_volpool_name',
                default=['volpool'],
                help='Comma separated list of storage system storage '
                     'pools for volumes.'),
    cfg.IntOpt('storwize_svc_vol_rsize',
               default=2,
               min=-1, max=100,
               help='Storage system space-efficiency parameter for volumes '
                    '(percentage)'),
    cfg.IntOpt('storwize_svc_vol_warning',
               default=0,
               min=-1, max=100,
               help='Storage system threshold for volume capacity warnings '
                    '(percentage)'),
    cfg.BoolOpt('storwize_svc_vol_autoexpand',
                default=True,
                help='Storage system autoexpand parameter for volumes '
                     '(True/False)'),
    cfg.IntOpt('storwize_svc_vol_grainsize',
               default=256,
               help='Storage system grain size parameter for volumes '
                    '(8/32/64/128/256)'),
    cfg.BoolOpt('storwize_svc_vol_compression',
                default=False,
                help='Storage system compression option for volumes'),
    cfg.BoolOpt('storwize_svc_vol_easytier',
                default=True,
                help='Enable Easy Tier for volumes'),
    cfg.StrOpt('storwize_svc_vol_iogrp',
               default='0',
               help='The I/O group in which to allocate volumes. It can be a '
               'comma-separated list in which case the driver will select an '
               'io_group based on least number of volumes associated with the '
               'io_group.'),
    cfg.IntOpt('storwize_svc_flashcopy_timeout',
               default=120,
               min=1, max=600,
               help='Maximum number of seconds to wait for FlashCopy to be '
                    'prepared.'),
    cfg.BoolOpt('storwize_svc_multihostmap_enabled',
                default=True,
                help='This option no longer has any affect. It is deprecated '
                     'and will be removed in the next release.',
                deprecated_for_removal=True),
    cfg.BoolOpt('storwize_svc_allow_tenant_qos',
                default=False,
                help='Allow tenants to specify QOS on create'),
    cfg.StrOpt('storwize_svc_stretched_cluster_partner',
               default=None,
               help='If operating in stretched cluster mode, specify the '
                    'name of the pool in which mirrored copies are stored.'
                    'Example: "pool2"'),
    cfg.StrOpt('storwize_san_secondary_ip',
               default=None,
               help='Specifies secondary management IP or hostname to be '
                    'used if san_ip is invalid or becomes inaccessible.'),
    cfg.BoolOpt('storwize_svc_vol_nofmtdisk',
                default=False,
                help='Specifies that the volume not be formatted during '
                     'creation.'),
    cfg.IntOpt('storwize_svc_flashcopy_rate',
               default=50,
               min=1, max=150,
               help='Specifies the Storwize FlashCopy copy rate to be used '
               'when creating a full volume copy. The default is rate '
               'is 50, and the valid rates are 1-150.'),
    cfg.IntOpt('storwize_svc_clean_rate',
               default=50,
               min=0, max=150,
               help='Specifies the Storwize cleaning rate for the mapping. '
                    'The default rate is 50, and the valid rates are '
                    '0-150.'),
    cfg.StrOpt('storwize_svc_mirror_pool',
               default=None,
               help='Specifies the name of the pool in which mirrored copy '
                    'is stored. Example: "pool2"'),
    cfg.StrOpt('storwize_portset',
               default=None,
               help='Specifies the name of the portset in which '
                    'the host is to be created.'),
    cfg.StrOpt('storwize_svc_src_child_pool',
               default=None,
               help='Specifies the name of the source child pool in which '
                    'global mirror source change volume is stored.'),
    cfg.StrOpt('storwize_svc_target_child_pool',
               default=None,
               help='Specifies the name of the target child pool in which '
                    'global mirror auxiliary change volume is stored.'),
    cfg.StrOpt('storwize_peer_pool',
               default=None,
               help='Specifies the name of the peer pool for hyperswap '
                    'volume, the peer pool must exist on the other site.'),
    cfg.DictOpt('storwize_preferred_host_site',
                default={},
                help='Specifies the site information for host. '
                     'One WWPN or multi WWPNs used in the host can be '
                     'specified. For example: '
                     'storwize_preferred_host_site=site1:wwpn1,'
                     'site2:wwpn2&wwpn3 or '
                     'storwize_preferred_host_site=site1:iqn1,site2:iqn2'),
    cfg.IntOpt('cycle_period_seconds',
               default=300,
               min=60, max=86400,
               help='This defines an optional cycle period that applies to '
               'Global Mirror relationships with a cycling mode of multi. '
               'A Global Mirror relationship using the multi cycling_mode '
               'performs a complete cycle at most once each period. '
               'The default is 300 seconds, and the valid seconds '
               'are 60-86400.'),
    cfg.BoolOpt('storwize_svc_retain_aux_volume',
                default=False,
                help='Enable or disable retaining of aux volume on secondary '
                     'storage during delete of the volume on primary storage '
                     'or moving the primary volume from mirror to non-mirror '
                     'with replication enabled. This option is valid for '
                     'Storage Virtualize Family.'),
    cfg.BoolOpt('storwize_volume_group',
                default=False,
                help='Parameter to enable or disable Volume Group'
                     '(True/False)'),
]

CONF = cfg.CONF
CONF.register_opts(storwize_svc_opts, group=configuration.SHARED_CONF_GROUP)


class StorwizeSSH(object):
    """SSH interface to IBM Storwize family and SVC storage systems."""
    def __init__(self, run_ssh):
        self._ssh = run_ssh

    def _run_ssh(self, ssh_cmd):
        try:
            return self._ssh(ssh_cmd)
        except processutils.ProcessExecutionError as e:
            msg = (_('CLI Exception output:\n command: %(cmd)s\n '
                     'stdout: %(out)s\n stderr: %(err)s.') %
                   {'cmd': ssh_cmd,
                    'out': e.stdout,
                    'err': e.stderr})
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def run_ssh_info(self, ssh_cmd, delim='!', with_header=False):
        """Run an SSH command and return parsed output."""
        raw = self._run_ssh(ssh_cmd)
        return CLIResponse(raw, ssh_cmd=ssh_cmd, delim=delim,
                           with_header=with_header)

    def run_ssh_assert_no_output(self, ssh_cmd, log_cmd=None):
        """Run an SSH command and assert no output returned."""
        out, err = self._run_ssh(ssh_cmd)
        if len(out.strip()) != 0:
            if not log_cmd:
                log_cmd = ' '.join(ssh_cmd)
            msg = (_('Expected no output from CLI command %(cmd)s, '
                     'got %(out)s.') % {'cmd': log_cmd, 'out': out})
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def run_ssh_check_created(self, ssh_cmd):
        """Run an SSH command and return the ID of the created object."""
        out, err = self._run_ssh(ssh_cmd)
        try:
            match_obj = re.search(r'\[([0-9]+)\],? successfully created', out)
            return match_obj.group(1)
        except (AttributeError, IndexError):
            msg = (_('Failed to parse CLI output:\n command: %(cmd)s\n '
                     'stdout: %(out)s\n stderr: %(err)s.') %
                   {'cmd': ssh_cmd,
                    'out': out,
                    'err': err})
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def lsnode(self, node_id=None):
        with_header = True
        ssh_cmd = ['svcinfo', 'lsnode', '-delim', '!']
        if node_id:
            with_header = False
            ssh_cmd.append(node_id)
        return self.run_ssh_info(ssh_cmd, with_header=with_header)

    def lslicense(self):
        ssh_cmd = ['svcinfo', 'lslicense', '-delim', '!']
        return self.run_ssh_info(ssh_cmd)[0]

    def lsguicapabilities(self):
        ssh_cmd = ['svcinfo', 'lsguicapabilities', '-delim', '!']
        return self.run_ssh_info(ssh_cmd)[0]

    def lssystem(self):
        ssh_cmd = ['svcinfo', 'lssystem', '-delim', '!']
        return self.run_ssh_info(ssh_cmd)[0]

    def lsmdiskgrp(self, pool):
        ssh_cmd = ['svcinfo', 'lsmdiskgrp', '-bytes', '-delim', '!',
                   '"%s"' % pool]
        try:
            return self.run_ssh_info(ssh_cmd)[0]
        except exception.VolumeBackendAPIException as ex:
            LOG.warning("Failed to get pool %(pool)s info. "
                        "Exception: %(ex)s.", {'pool': pool,
                                               'ex': ex})
            return None

    def lsiogrp(self):
        ssh_cmd = ['svcinfo', 'lsiogrp', '-delim', '!']
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def lsportip(self):
        ssh_cmd = ['svcinfo', 'lsportip', '-delim', '!']
        return self.run_ssh_info(ssh_cmd, with_header=True)

    @staticmethod
    def _create_port_arg(port_type, port_name):
        if port_type == 'initiator':
            port = ['-iscsiname']
        else:
            port = ['-hbawwpn']
        port.append(port_name)
        return port

    def mkhost(self, host_name, port_type, port_name, site=None, portset=None):
        port = self._create_port_arg(port_type, port_name)
        ssh_cmd = ['svctask', 'mkhost', '-force'] + port
        if site:
            ssh_cmd += ['-site', '"%s"' % site]
        if portset:
            ssh_cmd += ['-portset', '"%s"' % portset]
        ssh_cmd += ['-name', '"%s"' % host_name]
        return self.run_ssh_check_created(ssh_cmd)

    def addhostport(self, host, port_type, port_name):
        port = self._create_port_arg(port_type, port_name)
        ssh_cmd = ['svctask', 'addhostport', '-force'] + port + ['"%s"' % host]
        self.run_ssh_assert_no_output(ssh_cmd)

    def addhostiogrp(self, host, iogrplist='all'):
        ssh_cmd = ['svctask', 'addhostiogrp']
        if iogrplist == 'all':
            ssh_cmd += ['-iogrpall', '"%s"' % host]
        else:
            ssh_cmd += ['-iogrp', ':'.join(iogrplist), '"%s"' % host]
        self.run_ssh_assert_no_output(ssh_cmd)

    def lshost(self, host=None):
        with_header = True
        ssh_cmd = ['svcinfo', 'lshost', '-delim', '!']
        if host:
            with_header = False
            ssh_cmd.append('"%s"' % host)
        return self.run_ssh_info(ssh_cmd, with_header=with_header)

    def add_chap_secret(self, secret, host):
        ssh_cmd = ['svctask', 'chhost', '-chapsecret', secret, '"%s"' % host]
        log_cmd = 'svctask chhost -chapsecret *** %s' % host
        self.run_ssh_assert_no_output(ssh_cmd, log_cmd)

    def chhost(self, host, site):
        ssh_cmd = ['svctask', 'chhost']
        if site:
            ssh_cmd += ['-site', '"%s"' % site, '"%s"' % host]
        else:
            ssh_cmd += ['-nosite', '"%s"' % host]
        self.run_ssh_assert_no_output(ssh_cmd)

    def lsiscsiauth(self):
        ssh_cmd = ['svcinfo', 'lsiscsiauth', '-delim', '!']
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def lsip(self, portset=None):
        ssh_cmd = ['svcinfo', 'lsip', '-delim', '!']
        if portset:
            ssh_cmd += ['-filtervalue', 'portset_name=%s' % portset]
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def lsfabric(self, wwpn=None, host=None):
        ssh_cmd = ['svcinfo', 'lsfabric', '-delim', '!']
        if wwpn:
            ssh_cmd.extend(['-wwpn', wwpn])
        elif host:
            ssh_cmd.extend(['-host', '"%s"' % host])
        else:
            msg = (_('Must pass wwpn or host to lsfabric.'))
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def mkvdiskhostmap(self, host, vdisk, lun, multihostmap):
        """Map vdisk to host.

        If vdisk already mapped and multihostmap is True, use the force flag.
        """
        ssh_cmd = ['svctask', 'mkvdiskhostmap', '-host', '"%s"' % host,
                   '-scsi', lun, '"%s"' % vdisk]

        if multihostmap:
            ssh_cmd.insert(ssh_cmd.index('mkvdiskhostmap') + 1, '-force')
        self.run_ssh_check_created(ssh_cmd)

    def mkrcrelationship(self, master, aux, system, asyncmirror,
                         cyclingmode=False):
        ssh_cmd = ['svctask', 'mkrcrelationship', '-master', master,
                   '-aux', aux, '-cluster', system]
        if asyncmirror:
            ssh_cmd.append('-global')
        if cyclingmode:
            ssh_cmd.extend(['-cyclingmode', 'multi'])
        return self.run_ssh_check_created(ssh_cmd)

    def rmrcrelationship(self, relationship, force=False):
        ssh_cmd = ['svctask', 'rmrcrelationship']
        if force:
            ssh_cmd += ['-force']
        ssh_cmd += [relationship]
        self.run_ssh_assert_no_output(ssh_cmd)

    def switchrelationship(self, relationship, aux=True):
        primary = 'aux' if aux else 'master'
        ssh_cmd = ['svctask', 'switchrcrelationship', '-primary',
                   primary, relationship]
        self.run_ssh_assert_no_output(ssh_cmd)

    def startrcrelationship(self, rc_rel, primary=None):
        ssh_cmd = ['svctask', 'startrcrelationship', '-force']
        if primary:
            ssh_cmd.extend(['-primary', primary])
        ssh_cmd.append(rc_rel)
        self.run_ssh_assert_no_output(ssh_cmd)

    def ch_rcconsistgrp_cyclingmode(self, consistgrp,
                                    cyclingmode='none'):
        ssh_cmd = ['svctask', 'chrcconsistgrp',
                   '-cyclingmode', cyclingmode, consistgrp]
        self.run_ssh_assert_no_output(ssh_cmd)

    def ch_rcrelationship_cyclingmode(self, relationship,
                                      cyclingmode='none'):
        # Note: Can only change one attribute at a time,
        # so define three ch_rcrelationship_xxx here
        ssh_cmd = ['svctask', 'chrcrelationship',
                   '-cyclingmode', cyclingmode, relationship]
        self.run_ssh_assert_no_output(ssh_cmd)

    def ch_rcrelationship_cycleperiod(self, relationship,
                                      cycle_period_seconds):
        # Note: Can only change one attribute at a time,
        # so define three ch_rcrelationship_xxx here
        if cycle_period_seconds:
            ssh_cmd = ['svctask', 'chrcrelationship']
            ssh_cmd.extend(['-cycleperiodseconds',
                            str(cycle_period_seconds)])
            ssh_cmd.append(relationship)
            self.run_ssh_assert_no_output(ssh_cmd)

    def ch_rcrelationship_changevolume(self, relationship,
                                       changevolume, master):
        # Note: Can only change one attribute at a time,
        # so define three ch_rcrelationship_xxx here
        if changevolume:
            ssh_cmd = ['svctask', 'chrcrelationship']
            if master:
                ssh_cmd.extend(['-masterchange', changevolume])
            else:
                ssh_cmd.extend(['-auxchange', changevolume])
            ssh_cmd.append(relationship)
            self.run_ssh_assert_no_output(ssh_cmd)

    def stoprcrelationship(self, relationship, access=False):
        ssh_cmd = ['svctask', 'stoprcrelationship']
        if access:
            ssh_cmd.append('-access')
        ssh_cmd.append(relationship)
        self.run_ssh_assert_no_output(ssh_cmd)

    def lsrcrelationship(self, rc_rel):
        ssh_cmd = ['svcinfo', 'lsrcrelationship', '-delim', '!', rc_rel]
        return self.run_ssh_info(ssh_cmd)

    # replication cg
    def chrcrelationship(self, relationship, rccg=None):
        ssh_cmd = ['svctask', 'chrcrelationship']
        if rccg:
            ssh_cmd.extend(['-consistgrp', rccg])
        else:
            ssh_cmd.extend(['-noconsistgrp'])
        ssh_cmd.append(relationship)
        self.run_ssh_assert_no_output(ssh_cmd)

    def lsrcconsistgrp(self, rccg):
        ssh_cmd = ['svcinfo', 'lsrcconsistgrp', '-delim', '!', rccg]
        try:
            return self.run_ssh_info(ssh_cmd)[0]
        except exception.VolumeBackendAPIException as ex:
            LOG.warning("Failed to get rcconsistgrp %(rccg)s info. "
                        "Exception: %(ex)s.", {'rccg': rccg,
                                               'ex': ex})
            return None

    def mkrcconsistgrp(self, rccg, system):
        ssh_cmd = ['svctask', 'mkrcconsistgrp', '-name', rccg,
                   '-cluster', system]
        return self.run_ssh_check_created(ssh_cmd)

    def rmrcconsistgrp(self, rccg, force=True):
        ssh_cmd = ['svctask', 'rmrcconsistgrp']
        if force:
            ssh_cmd += ['-force']
        ssh_cmd += ['"%s"' % rccg]
        return self.run_ssh_assert_no_output(ssh_cmd)

    def startrcconsistgrp(self, rccg, primary=None):
        ssh_cmd = ['svctask', 'startrcconsistgrp', '-force']
        if primary:
            ssh_cmd.extend(['-primary', primary])
        ssh_cmd.append(rccg)
        self.run_ssh_assert_no_output(ssh_cmd)

    def stoprcconsistgrp(self, rccg, access=False):
        ssh_cmd = ['svctask', 'stoprcconsistgrp']
        if access:
            ssh_cmd.append('-access')
        ssh_cmd.append(rccg)
        self.run_ssh_assert_no_output(ssh_cmd)

    def switchrcconsistgrp(self, rccg, aux=True):
        primary = 'aux' if aux else 'master'
        ssh_cmd = ['svctask', 'switchrcconsistgrp', '-primary',
                   primary, rccg]
        self.run_ssh_assert_no_output(ssh_cmd)

    def lspartnership(self, system_name):
        key_value = 'name=%s' % system_name
        ssh_cmd = ['svcinfo', 'lspartnership', '-filtervalue',
                   key_value, '-delim', '!']
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def lspartnershipcandidate(self):
        ssh_cmd = ['svcinfo', 'lspartnershipcandidate', '-delim', '!']
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def mkippartnership(self, ip_v4, bandwidth=1000, backgroundcopyrate=50):
        ssh_cmd = ['svctask', 'mkippartnership', '-type', 'ipv4',
                   '-clusterip', ip_v4, '-linkbandwidthmbits', str(bandwidth),
                   '-backgroundcopyrate', str(backgroundcopyrate)]
        return self.run_ssh_assert_no_output(ssh_cmd)

    def mkfcpartnership(self, system_name, bandwidth=1000,
                        backgroundcopyrate=50):
        ssh_cmd = ['svctask', 'mkfcpartnership', '-linkbandwidthmbits',
                   str(bandwidth),
                   '-backgroundcopyrate', str(backgroundcopyrate),
                   system_name]
        return self.run_ssh_assert_no_output(ssh_cmd)

    def chpartnership(self, partnership_id, start=True):
        action = '-start' if start else '-stop'
        ssh_cmd = ['svctask', 'chpartnership', action, partnership_id]
        return self.run_ssh_assert_no_output(ssh_cmd)

    def rmvdiskhostmap(self, host, vdisk):
        ssh_cmd = ['svctask', 'rmvdiskhostmap', '-host', '"%s"' % host,
                   '"%s"' % vdisk]
        self.run_ssh_assert_no_output(ssh_cmd)

    def lsvdiskhostmap(self, vdisk):
        ssh_cmd = ['svcinfo', 'lsvdiskhostmap', '-delim', '!', '"%s"' % vdisk]
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def lshostvdiskmap(self, host):
        ssh_cmd = ['svcinfo', 'lshostvdiskmap', '-delim', '!', '"%s"' % host]
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def get_vdiskhostmapid(self, vdisk, host):
        resp = self.lsvdiskhostmap(vdisk)
        for mapping_info in resp:
            if mapping_info['host_name'] == host:
                lun_id = mapping_info['SCSI_id']
                return lun_id
        return None

    def rmhost(self, host):
        ssh_cmd = ['svctask', 'rmhost', '"%s"' % host]
        self.run_ssh_assert_no_output(ssh_cmd)

    def mkvolumegroup(self, volumegroup_name):
        """Create a volume group(VG)."""
        ssh_cmd = ['svctask', 'mkvolumegroup', '-name', '"%s"'
                   % volumegroup_name]
        try:
            return self.run_ssh_check_created(ssh_cmd)
        except Exception as ex:
            if hasattr(ex, 'msg') and 'CMMVC6035E' in ex.msg:
                msg = (_('CMMVC6372W Action failed because volume group '
                         'with the name provided already exists.'))
                LOG.error(msg)
                raise exception.VolumeBackendAPIException(data=msg)
            with excutils.save_and_reraise_exception():
                LOG.exception('Failed to create volumegroup.')

    def lsvolumegroup(self, volumegroup_id_or_name):
        """Return volume group attributes or None if it doesn't exist."""
        ssh_cmd = ['svcinfo', 'lsvolumegroup', '-bytes', '-delim', '!',
                   '"%s"' % volumegroup_id_or_name]
        out, err = self._ssh(ssh_cmd, check_exit_code=False)
        if not err:
            return CLIResponse((out, err), ssh_cmd=ssh_cmd, delim='!',
                               with_header=False)[0]
        if 'CMMVC5804E' in err:
            return None
        msg = (_('CLI Exception output:\n command: %(cmd)s\n '
                 'stdout: %(out)s\n stderr: %(err)s.') %
               {'cmd': ssh_cmd,
                'out': out,
                'err': err})
        LOG.error(msg)
        raise exception.VolumeBackendAPIException(data=msg)

    def rmvolumegroup(self, volumegroup_name_or_id):
        """Delete a volume group"""
        ssh_cmd = ['svctask', 'rmvolumegroup', '"%s"' % volumegroup_name_or_id]
        try:
            self.run_ssh_assert_no_output(ssh_cmd)
        except Exception as ex:
            if hasattr(ex, 'msg') and 'CMMVC8749E' in ex.msg:
                msg = _('rmvolumegroup: specified volume group is not empty.')
                LOG.error(msg)
                raise exception.VolumeDriverException(message=msg)
            with excutils.save_and_reraise_exception():
                LOG.exception('Failed to delete volumegroup.')

    def lsvolumegroupsnapshot(self, params):
        """Return volumegroup-snapshot attributes.

        Return None if it doesn't exists
        """

        ssh_cmd = ['svcinfo', 'lsvolumegroupsnapshot']
        if "id" in params:
            ssh_cmd.append(params["id"])
        elif "name" and "volumegroup" in params:
            ssh_cmd.extend(['-snapshot', params["name"], '-volumegroup',
                            params["volumegroup"]])
        # Add delimiter to parse the output
        ssh_cmd.extend(['-delim', ':'])
        out, err = self._ssh(ssh_cmd, check_exit_code=False)
        if not err:
            if not out:
                return None
            # Parse the lsvolumegroupsnapshot output
            output = out.split('\n')
            attributes = output[0].split(":")
            attribute_values = output[1].split(":")
            attrs = {key: val for key, val in zip(attributes,
                                                  attribute_values)}
            return attrs
        # CMMVC5804E implies volumegroup-snapshot or volumegroup specified
        # does not exist in the SVC storage.
        if 'CMMVC5804E' in err:
            return None
        msg = (_('CLI Exception output:\n command: %(cmd)s\n '
                 'stdout: %(out)s\n stderr: %(err)s.') %
               {'cmd': ssh_cmd,
                'out': out,
                'err': err})
        LOG.error(msg)
        raise exception.VolumeBackendAPIException(data=msg)

    def addsnapshot(self, params):
        ssh_cmd = ['svctask', 'addsnapshot', '-ignorelegacy']
        if "volumegroup" in params:
            ssh_cmd.extend(['-volumegroup', params["volumegroup"]])
        if "name" in params:
            ssh_cmd.extend(['-name', params["name"]])
        try:
            return self.run_ssh_check_created(ssh_cmd)
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.exception('Failed to create volumegroup snapshot.')

    def rmsnapshot(self, params):
        ssh_cmd = ['svctask', 'rmsnapshot']
        if "id" in params:
            ssh_cmd.extend(['-snapshotid', params["id"]])
        elif "name" and "volumegroup" in params:
            ssh_cmd.extend(['-snapshot', params["name"], '-volumegroup',
                            params["volumegroup"]])
        self.run_ssh_assert_no_output(ssh_cmd)

    def mkvdisk(self, name, size, units, pool, opts, params):
        ssh_cmd = ['svctask', 'mkvdisk', '-name', '"%s"' % name, '-mdiskgrp',
                   '"%s"' % pool, '-iogrp', str(opts['iogrp']),
                   '-size', size, '-unit', units] + params
        try:
            return self.run_ssh_check_created(ssh_cmd)
        except Exception as ex:
            # pylint: disable=E1101
            if hasattr(ex, 'msg') and 'CMMVC6372W' in ex.msg:
                vdisk = self.lsvdisk(name)
                if vdisk:
                    LOG.warning('CMMVC6372W The virtualized storage '
                                'capacity that the cluster is using is '
                                'approaching the virtualized storage '
                                'capacity that is licensed.')
                    return vdisk['id']
            with excutils.save_and_reraise_exception():
                LOG.exception('Failed to create vdisk %(vol)s.',
                              {'vol': name})

    def rmvdisk(self, vdisk, force_unmap=True, force_delete=True):
        ssh_cmd = ['svctask', 'rmvdisk']
        if force_unmap and not force_delete:
            ssh_cmd += ['-removehostmappings']
        if force_delete:
            ssh_cmd += ['-force']
        ssh_cmd += ['"%s"' % vdisk]
        self.run_ssh_assert_no_output(ssh_cmd)

    def lsvdisk(self, vdisk):
        """Return vdisk attributes or None if it doesn't exist."""
        ssh_cmd = ['svcinfo', 'lsvdisk', '-bytes', '-delim', '!',
                   '"%s"' % vdisk]
        out, err = self._ssh(ssh_cmd, check_exit_code=False)
        if not err:
            return CLIResponse((out, err), ssh_cmd=ssh_cmd, delim='!',
                               with_header=False)[0]
        if 'CMMVC5754E' in err:
            return None
        msg = (_('CLI Exception output:\n command: %(cmd)s\n '
                 'stdout: %(out)s\n stderr: %(err)s.') %
               {'cmd': ssh_cmd,
                'out': out,
                'err': err})
        LOG.error(msg)
        raise exception.VolumeBackendAPIException(data=msg)

    def lsvdisks_from_filter(self, filter_name, value):
        """Performs an lsvdisk command, filtering the results as specified.

        Returns an iterable for all matching vdisks.
        """
        ssh_cmd = ['svcinfo', 'lsvdisk', '-bytes', '-delim', '!',
                   '-filtervalue', '%s=%s' % (filter_name, value)]
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def lsthrottle(self):
        """Returns throttle objects for all vdisks."""
        ssh_cmd = ['svcinfo', 'lsthrottle', '-delim', '!', '-filtervalue',
                   'throttle_type=vdisk']
        throttles = self.run_ssh_info(ssh_cmd, with_header=True)
        return throttles.result

    def chvdisk(self, vdisk, params):
        ssh_cmd = ['svctask', 'chvdisk'] + params + ['"%s"' % vdisk]
        self.run_ssh_assert_no_output(ssh_cmd)

    def movevdisk(self, vdisk, iogrp):
        ssh_cmd = ['svctask', 'movevdisk', '-iogrp', iogrp, '"%s"' % vdisk]
        self.run_ssh_assert_no_output(ssh_cmd)

    def expandvdisksize(self, vdisk, amount):
        ssh_cmd = (
            ['svctask', 'expandvdisksize', '-size', str(amount),
             '-unit', 'gb', '"%s"' % vdisk])
        self.run_ssh_assert_no_output(ssh_cmd)

    def mkfcmap(self, source, target, full_copy, copy_rate, clean_rate,
                consistgrp=None):
        ssh_cmd = ['svctask', 'mkfcmap', '-source', '"%s"' % source, '-target',
                   '"%s"' % target]
        if not full_copy:
            ssh_cmd.extend(['-copyrate', '0'])
        else:
            ssh_cmd.extend(['-copyrate', str(copy_rate)])
            ssh_cmd.append('-autodelete')
        if consistgrp:
            ssh_cmd.extend(['-consistgrp', consistgrp])
        if clean_rate is not None:
            ssh_cmd.extend(['-cleanrate', str(int(clean_rate))])
        out, err = self._ssh(ssh_cmd, check_exit_code=False)
        if 'successfully created' not in out:
            msg = (_('CLI Exception output:\n command: %(cmd)s\n '
                     'stdout: %(out)s\n stderr: %(err)s.') %
                   {'cmd': ssh_cmd,
                    'out': out,
                    'err': err})
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        try:
            match_obj = re.search(r'FlashCopy Mapping, id \[([0-9]+)\], '
                                  'successfully created', out)
            fc_map_id = match_obj.group(1)
        except (AttributeError, IndexError):
            msg = (_('Failed to parse CLI output:\n command: %(cmd)s\n '
                     'stdout: %(out)s\n stderr: %(err)s.') %
                   {'cmd': ssh_cmd,
                    'out': out,
                    'err': err})
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        return fc_map_id

    def prestartfcmap(self, fc_map_id, restore=False):
        ssh_cmd = ['svctask', 'prestartfcmap']
        if restore:
            ssh_cmd.append('-restore')
        ssh_cmd.append(fc_map_id)
        self.run_ssh_assert_no_output(ssh_cmd)

    def startfcmap(self, fc_map_id, restore=False):
        ssh_cmd = ['svctask', 'startfcmap']
        if restore:
            ssh_cmd.append('-restore')
        ssh_cmd.append(fc_map_id)
        self.run_ssh_assert_no_output(ssh_cmd)

    def prestartfcconsistgrp(self, fc_consist_group):
        ssh_cmd = ['svctask', 'prestartfcconsistgrp', fc_consist_group]
        self.run_ssh_assert_no_output(ssh_cmd)

    def startfcconsistgrp(self, fc_consist_group):
        ssh_cmd = ['svctask', 'startfcconsistgrp', fc_consist_group]
        self.run_ssh_assert_no_output(ssh_cmd)

    def stopfcconsistgrp(self, fc_consist_group):
        ssh_cmd = ['svctask', 'stopfcconsistgrp', fc_consist_group]
        self.run_ssh_assert_no_output(ssh_cmd)

    def chfcmap(self, fc_map_id, copyrate=None, clean_rate=None,
                autodel='on'):
        ssh_cmd = ['svctask', 'chfcmap']
        if clean_rate is not None:
            ssh_cmd += ['-cleanrate', clean_rate]
        if copyrate is not None:
            ssh_cmd += ['-copyrate', copyrate]
        ssh_cmd += ['-autodelete', autodel, fc_map_id]
        self.run_ssh_assert_no_output(ssh_cmd)

    def stopfcmap(self, fc_map_id, force=False, split=False):
        ssh_cmd = ['svctask', 'stopfcmap']
        if force:
            ssh_cmd += ['-force']
        if split:
            ssh_cmd += ['-split']
        ssh_cmd += [fc_map_id]
        self.run_ssh_assert_no_output(ssh_cmd)

    def rmfcmap(self, fc_map_id):
        ssh_cmd = ['svctask', 'rmfcmap', '-force', fc_map_id]
        self.run_ssh_assert_no_output(ssh_cmd)

    def lsvdiskfcmappings(self, vdisk):
        ssh_cmd = ['svcinfo', 'lsvdiskfcmappings', '-delim', '!',
                   '"%s"' % vdisk]
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def lsfcmap(self, fc_map_id):
        ssh_cmd = ['svcinfo', 'lsfcmap', '-filtervalue',
                   'id=%s' % fc_map_id, '-delim', '!']
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def lsfcconsistgrp(self, fc_consistgrp):
        ssh_cmd = ['svcinfo', 'lsfcconsistgrp', '-delim', '!', fc_consistgrp]
        out, err = self._ssh(ssh_cmd)
        return CLIResponse((out, err), ssh_cmd=ssh_cmd, delim='!',
                           with_header=False)

    def mkfcconsistgrp(self, fc_consist_group):
        ssh_cmd = ['svctask', 'mkfcconsistgrp', '-name', fc_consist_group]
        return self.run_ssh_check_created(ssh_cmd)

    def rmfcconsistgrp(self, fc_consist_group):
        ssh_cmd = ['svctask', 'rmfcconsistgrp', '-force', fc_consist_group]
        return self.run_ssh_assert_no_output(ssh_cmd)

    def addvdiskcopy(self, vdisk, dest_pool, params, auto_delete):
        ssh_cmd = (['svctask', 'addvdiskcopy'] + params + ['-mdiskgrp',
                   '"%s"' % dest_pool])
        if auto_delete:
            ssh_cmd += ['-autodelete']
        ssh_cmd += ['"%s"' % vdisk]
        return self.run_ssh_check_created(ssh_cmd)

    def lsvdiskcopy(self, vdisk, copy_id=None):
        ssh_cmd = ['svcinfo', 'lsvdiskcopy', '-delim', '!']
        with_header = True
        if copy_id:
            ssh_cmd += ['-copy', copy_id]
            with_header = False
        ssh_cmd += ['"%s"' % vdisk]
        return self.run_ssh_info(ssh_cmd, with_header=with_header)

    def lsvdisksyncprogress(self, vdisk, copy_id):
        ssh_cmd = ['svcinfo', 'lsvdisksyncprogress', '-delim', '!',
                   '-copy', copy_id, '"%s"' % vdisk]
        return self.run_ssh_info(ssh_cmd, with_header=True)[0]

    def rmvdiskcopy(self, vdisk, copy_id):
        ssh_cmd = ['svctask', 'rmvdiskcopy', '-copy', copy_id, '"%s"' % vdisk]
        self.run_ssh_assert_no_output(ssh_cmd)

    def addvdiskaccess(self, vdisk, iogrp):
        ssh_cmd = ['svctask', 'addvdiskaccess', '-iogrp', iogrp,
                   '"%s"' % vdisk]
        self.run_ssh_assert_no_output(ssh_cmd)

    def rmvdiskaccess(self, vdisk, iogrp):
        ssh_cmd = ['svctask', 'rmvdiskaccess', '-iogrp', iogrp, '"%s"' % vdisk]
        self.run_ssh_assert_no_output(ssh_cmd)

    def lsvdiskaccess(self, vdisk):
        ssh_cmd = ['svcinfo', 'lsvdiskaccess', '-delim', '!', '"%s"' % vdisk]
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def lsportfc(self, node_id):
        ssh_cmd = ['svcinfo', 'lsportfc', '-delim', '!',
                   '-filtervalue', 'node_id=%s' % node_id]
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def lstargetportfc(self, current_node_id=None, host_io_permitted=None):
        ssh_cmd = ['svcinfo', 'lstargetportfc', '-delim', '!']
        if current_node_id and host_io_permitted:
            ssh_cmd += ['-filtervalue', '%s:%s' % (
                'current_node_id=%s' % current_node_id,
                'host_io_permitted=%s' % host_io_permitted)]
        elif current_node_id:
            ssh_cmd += ['-filtervalue', 'current_node_id=%s' % current_node_id]
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def lsfcportsetmember(self):
        ssh_cmd = ['svcinfo', 'lsfcportsetmember', '-delim', '!']
        return self.run_ssh_info(ssh_cmd, with_header=True)

    def migratevdisk(self, vdisk, dest_pool, copy_id='0'):
        ssh_cmd = ['svctask', 'migratevdisk', '-mdiskgrp', dest_pool, '-copy',
                   copy_id, '-vdisk', vdisk]
        self.run_ssh_assert_no_output(ssh_cmd)

    def mkvolume(self, name, size, units, pool, params):
        ssh_cmd = ['svctask', 'mkvolume', '-name', name, '-pool',
                   '"%s"' % pool, '-size', size, '-unit', units] + params
        return self.run_ssh_check_created(ssh_cmd)

    def rmvolume(self, volume, force_unmap=True, force_delete=True):
        ssh_cmd = ['svctask', 'rmvolume']
        if force_delete:
            ssh_cmd += ['-removehostmappings', '-removefcmaps',
                        '-removercrelationships']
        elif force_unmap:
            ssh_cmd += ['-removehostmappings']
        ssh_cmd += ['"%s"' % volume]
        self.run_ssh_assert_no_output(ssh_cmd)

    def addvolumecopy(self, name, pool, params):
        ssh_cmd = ['svctask', 'addvolumecopy', '-pool',
                   '"%s"' % pool] + params + ['"%s"' % name]
        self.run_ssh_assert_no_output(ssh_cmd)

    def rmvolumecopy(self, name, pool):
        ssh_cmd = ['svctask', 'rmvolumecopy', '-pool',
                   '"%s"' % pool, '"%s"' % name]
        self.run_ssh_assert_no_output(ssh_cmd)


class StorwizeHelpers(object):

    # All the supported QoS key are saved in this dict. When a new
    # key is going to add, four values MUST be set:
    # 'default': to indicate the value, when the parameter is disabled.
    # 'param': to indicate the corresponding parameter in the command.
    # 'type': to indicate the type of this value.
    # 'unit': to indicate the string, a supported QoS parameter.
    WAIT_TIME = 5
    svc_qos = {'IOThrottling': {'default': '0',
                                'param': 'rate',
                                'type': float,
                                'unit': 'IOThrottling_unit'},
               'IOThrottling_unit': {'default': 'iops',
                                     'enum': ['iops', 'mbps', 'iops_per_gb'],
                                     'type': str,
                                     'mbps': 'unitmb',
                                     'iops': 'rate',
                                     'iops_per_gb': 'rate'}}

    def __init__(self, run_ssh):
        self.ssh = StorwizeSSH(run_ssh)
        self.check_fcmapping_interval = 3
        self.code_level = None
        self.stats = {}
        self.Host_connector_info = {"FC": {}, "ISCSI": {}}

    @staticmethod
    def handle_keyerror(cmd, out):
        msg = (_('Could not find key in output of command %(cmd)s: %(out)s.')
               % {'out': out, 'cmd': cmd})
        raise exception.VolumeBackendAPIException(data=msg)

    def compression_enabled(self):
        """Return whether or not compression is enabled for this system."""
        resp = self.ssh.lslicense()
        keys = ['license_compression_enclosures',
                'license_compression_capacity']
        for key in keys:
            if resp.get(key, '0') != '0':
                return True

        # lslicense is not used for V9000 compression check
        # compression_enclosures and compression_capacity are
        # always 0. V9000 uses license_scheme 9846 as an
        # indicator and can always do compression
        try:
            resp = self.ssh.lsguicapabilities()
            if resp.get('license_scheme', '0') == '9846':
                return True
            if resp.get('license_scheme', '0') == 'flex':
                return True
        except exception.VolumeBackendAPIException:
            LOG.exception("Failed to fetch licensing scheme.")
        return False

    def replication_licensed(self):
        """Return whether or not replication is enabled for this system."""
        # Uses product_key as an indicator to check
        # whether replication is supported in storage.
        try:
            resp = self.ssh.lsguicapabilities()
            product_key = resp.get('product_key', '0')
            if product_key in storwize_const.REP_CAP_DEVS:
                return True
        except exception.VolumeBackendAPIException as war:
            LOG.warning("Failed to run lsguicapability. Exception: %s.", war)
        return False

    def get_system_info(self):
        """Return system's name, ID, and code level."""
        resp = self.ssh.lssystem()
        level = resp['code_level']
        match_obj = re.search('([0-9].){3}[0-9]', level)
        if match_obj is None:
            msg = _('Failed to get code level (%s).') % level
            raise exception.VolumeBackendAPIException(data=msg)
        code_level = match_obj.group().split('.')
        LOG.info("code_level is: %s.", level)
        return {'code_level': tuple([int(x) for x in code_level]),
                'topology': resp['topology'],
                'system_name': resp['name'],
                'system_id': resp['id']}

    def get_pool_attrs(self, pool):
        """Return attributes for the specified pool."""
        return self.ssh.lsmdiskgrp(pool)

    def is_pool_defined(self, pool_name):
        """Check if vdisk is defined."""
        attrs = self.get_pool_attrs(pool_name)
        return attrs is not None

    def is_data_reduction_pool(self, pool_name):
        """Check if pool is data reduction pool."""
        # Check pool is data reduction pool or not from pool information
        # saved in stats.
        for pool in self.stats.get('pools', []):
            if pool['pool_name'] == pool_name:
                return pool['data_reduction']

        pool_data = self.get_pool_attrs(pool_name)
        if (pool_data and 'data_reduction' in pool_data and
                pool_data['data_reduction'] == 'yes'):
            return True
        return False

    def get_pool_volumes(self, pool):
        """Return volumes for the specified pool."""
        vdisks = self.ssh.lsvdisks_from_filter('mdisk_grp_name', pool)
        return vdisks.result

    def get_available_io_groups(self):
        """Return list of available IO groups."""
        iogrps = []
        resp = self.ssh.lsiogrp()
        for iogrp in resp:
            try:
                if int(iogrp['node_count']) > 0:
                    iogrps.append(int(iogrp['id']))
            except KeyError:
                self.handle_keyerror('lsiogrp', iogrp)
            except ValueError:
                msg = (_('Expected integer for node_count, '
                         'svcinfo lsiogrp returned: %(node)s.') %
                       {'node': iogrp['node_count']})
                raise exception.VolumeBackendAPIException(data=msg)
        return iogrps

    def get_vdisk_count_by_io_group(self):
        res = {}
        resp = self.ssh.lsiogrp()
        for iogrp in resp:
            try:
                if int(iogrp['node_count']) > 0:
                    res[int(iogrp['id'])] = int(iogrp['vdisk_count'])
            except KeyError:
                self.handle_keyerror('lsiogrp', iogrp)
            except ValueError:
                msg = (_('Expected integer for node_count, '
                         'svcinfo lsiogrp returned: %(node)s') %
                       {'node': iogrp['node_count']})
                raise exception.VolumeBackendAPIException(data=msg)
        return res

    def get_hyperswap_pool_io_grp(self, state, pool, peer_pool):
        if not peer_pool or not pool:
            raise exception.InvalidInput(
                reason=_('The pool and peer pool is necessary for hyperswap '
                         'volume, please configure the pool and peer pool.'))
        pool_data = None
        peer_pool_data = None
        for stat_pool in self.stats.get('pools', []):
            if stat_pool['pool_name'] == pool:
                pool_data = stat_pool
            elif stat_pool['pool_name'] == peer_pool:
                peer_pool_data = stat_pool

        if pool_data is None or pool_data.get("site_id") is None:
            pool_data = self.get_pool_attrs(pool)
            if not pool_data['site_id']:
                raise exception.InvalidInput(
                    reason=_('The pool with site is necessary for hyperswap '
                             'volume, please configure the pool with site.'))

        if peer_pool_data is None or peer_pool_data.get("site_id") is None:
            peer_pool_data = self.get_pool_attrs(peer_pool)
            if not peer_pool_data['site_id']:
                raise exception.InvalidInput(
                    reason=_('The peer pool with site is necessary for '
                             'hyperswap volume, please configure the peer '
                             'pool with site.'))

        iogrp_list = []
        for node in state['storage_nodes'].values():
            if ((pool_data['site_id'] == node['site_id']) or
                    (peer_pool_data['site_id'] == node['site_id'])):
                if node['IO_group'] not in iogrp_list:
                    iogrp_list.append(node['IO_group'])

        return iogrp_list

    def select_io_group(self, state, opts, pool):
        selected_iog = 0
        iog_list = StorwizeHelpers._get_valid_requested_io_groups(state, opts)
        if len(iog_list) == 0:
            raise exception.InvalidInput(
                reason=_('Given I/O group(s) %(iogrp)s not valid; available '
                         'I/O groups are %(avail)s.')
                % {'iogrp': opts['iogrp'],
                   'avail': state['available_iogrps']})

        site_iogrp = []
        hyperswap = opts['volume_topology'] == 'hyperswap'
        if hyperswap:
            pool_data = self.get_pool_attrs(pool)
            if pool_data is None:
                msg = (_('Failed getting details for pool %s.') % pool)
                LOG.error(msg)
                raise exception.InvalidConfigurationValue(message=msg)
        if hyperswap and pool_data.get('site_id'):
            for node in state['storage_nodes'].values():
                if pool_data['site_id'] == node['site_id']:
                    site_iogrp.append(node['IO_group'])
            site_iogrp = list(map(int, site_iogrp))
            iogroup_list = list(set(site_iogrp).intersection(iog_list))
            if len(iogroup_list) == 0:
                LOG.warning('The storage system topology is hyperswap or '
                            'stretched, The site_id of pool %(pool)s is '
                            '%(site_id)s, the available I/O groups on this '
                            'site is %(site_iogrp)s, but the given I/O'
                            ' group(s) is %(iogrp)s.',
                            {'pool': pool, 'site_id': pool_data['site_id'],
                             'site_iogrp': site_iogrp, 'iogrp': opts['iogrp']})
                iogroup_list = iog_list
        else:
            iogroup_list = iog_list
        iog_vdc = self.get_vdisk_count_by_io_group()
        LOG.debug("IO group current balance %s", iog_vdc)
        min_vdisk_count = iog_vdc[iogroup_list[0]]
        selected_iog = iogroup_list[0]
        for iog in iogroup_list:
            if iog_vdc[iog] < min_vdisk_count:
                min_vdisk_count = iog_vdc[iog]
                selected_iog = iog
        LOG.debug("Selected io_group is %d", selected_iog)
        return selected_iog

    def get_pool_max_throttle_rate_vdisk(self, pool, throttle_rate_type):
        """Returns the IOPs or Bandwidth throttle rate.

        Throttle rate of all vdisks for the specified pool.
        """
        max_throttle_rate_vdisk = 0
        vdisks = self.get_pool_volumes(pool)
        if vdisks:
            throttles = self.ssh.lsthrottle()
            if throttles:
                vdisk_names = [
                    vdisk['name'] for vdisk in vdisks if vdisk['name']]
                for throttle in throttles:
                    if (throttle['object_name'] in vdisk_names and
                            throttle[throttle_rate_type]):
                        max_throttle_rate_vdisk += int(
                            throttle[throttle_rate_type])
        return max_throttle_rate_vdisk

    def get_volume_io_group(self, vol_name):
        vdisk = self.ssh.lsvdisk(vol_name)
        if vdisk:
            resp = self.ssh.lsiogrp()
            for iogrp in resp:
                if iogrp['name'] == vdisk['IO_group_name']:
                    return int(iogrp['id'])
        return None

    def get_node_info(self, online_node=True):
        """Return dictionary containing information on system's nodes."""
        nodes = {}
        resp = self.ssh.lsnode()
        for node_data in resp:
            try:
                if online_node and node_data['status'] != 'online':
                    continue
                node = {}
                node['id'] = node_data['id']
                node['name'] = node_data['name']
                node['IO_group'] = node_data['IO_group_id']
                node['iscsi_name'] = node_data['iscsi_name']
                node['WWNN'] = node_data['WWNN']
                node['status'] = node_data['status']
                node['WWPN'] = []
                node['ipv4'] = []
                node['ipv6'] = []
                node['IP_address'] = []
                node['enabled_protocols'] = []
                nodes[node['id']] = node
                node['site_id'] = (node_data['site_id']
                                   if 'site_id' in node_data else None)
                node['site_name'] = (node_data['site_name']
                                     if 'site_name' in node_data else None)
            except KeyError:
                self.handle_keyerror('lsnode', node_data)
        return nodes

    def add_iscsi_ip_addrs(self, storage_nodes, code_level, portset=None):
        """Add iSCSI IP addresses to system node information."""
        if code_level >= (8, 4, 2, 0):
            portset_name = portset if portset else 'portset0'
            lsip_resp = self.ssh.lsip(portset=portset_name)
            # For every node_id there is one IP address in a particular
            # portset_name. Hence storing that one IP address of the
            # corresponding node_id in storage_node list.
            for node_data in storage_nodes:
                try:
                    for ip_data in lsip_resp:
                        if ip_data['node_id'] in node_data:
                            if ip_data['IP_address']:
                                (storage_nodes[ip_data['node_id']]
                                    ['IP_address']) = (
                                        [ip_data['IP_address']])
                except KeyError:
                    self.handle_keyerror('lsip', ip_data)
        else:
            lsportip_resp = self.ssh.lsportip()
            for ip_data in lsportip_resp:
                try:
                    state = ip_data['state']
                    if ip_data['node_id'] in storage_nodes and (
                            state == 'configured' or state == 'online'):
                        node = storage_nodes[ip_data['node_id']]
                        if len(ip_data['IP_address']):
                            node['ipv4'].append(ip_data['IP_address'])
                        if len(ip_data['IP_address_6']):
                            node['ipv6'].append(ip_data['IP_address_6'])
                except KeyError:
                    self.handle_keyerror('lsportip', ip_data)

    def add_fc_wwpns(self, storage_nodes, code_level):
        """Add FC WWPNs to system node information."""
        for key in storage_nodes:
            node = storage_nodes[key]
            wwpns = set(node['WWPN'])
            # The Storwize/svc release 7.7.0.0 introduced NPIV feature.
            # The virtual wwpns will be included in cli lstargetportfc
            if code_level < (7, 7, 0, 0):
                resp = self.ssh.lsportfc(node_id=node['id'])
                for port_info in resp:
                    if (port_info['type'] == 'fc' and
                            port_info['status'] == 'active'):
                        wwpns.add(port_info['WWPN'])
            else:
                npiv_wwpns = self.get_npiv_wwpns(code_level,
                                                 node_id=node['id'])
                wwpns.update(npiv_wwpns)
            node['WWPN'] = list(wwpns)
            LOG.info('WWPN on node %(node)s: %(wwpn)s.',
                     {'node': node['id'], 'wwpn': node['WWPN']})

    def get_npiv_wwpns(self, code_level, node_id=None, host_io=None,
                       portset=None):
        wwpns = set()
        # In the response of lstargetportfc, the host_io_permitted
        # indicates whether the port can be used for host I/O
        targetportfc_resp = self.ssh.lstargetportfc(current_node_id=node_id,
                                                    host_io_permitted=host_io)
        if code_level >= (8, 5, 0, 0):
            portset_name = portset if portset else 'portset64'
            port_ids = set()
            fcportsetmember_resp = self.ssh.lsfcportsetmember()
            for portset_member in fcportsetmember_resp:
                if portset_member['portset_name'] == portset_name:
                    port_ids.add(portset_member['fc_io_port_id'])

            for port_info in targetportfc_resp:
                for port_id in port_ids:
                    if port_id == port_info['fc_io_port_id']:
                        wwpns.add(port_info['WWPN'])
                        break
        else:
            for port_info in targetportfc_resp:
                wwpns.add(port_info['WWPN'])
        return list(wwpns)

    def add_chap_secret_to_host(self, host_name):
        """Generate and store a randomly-generated CHAP secret for the host."""
        chap_secret = volume_utils.generate_password()
        self.ssh.add_chap_secret(chap_secret, host_name)
        return chap_secret

    def get_chap_secret_for_host(self, host_name):
        """Generate and store a randomly-generated CHAP secret for the host."""
        resp = self.ssh.lsiscsiauth()
        host_found = False
        for host_data in resp:
            try:
                if host_data['name'] == host_name:
                    host_found = True
                    if host_data['iscsi_auth_method'] == 'chap':
                        return host_data['iscsi_chap_secret']
            except KeyError:
                self.handle_keyerror('lsiscsiauth', host_data)
        if not host_found:
            msg = _('Failed to find host %s.') % host_name
            raise exception.VolumeBackendAPIException(data=msg)
        return None

    def get_conn_fc_wwpns(self, host):
        wwpns = set()
        resp = self.ssh.lsfabric(host=host)
        for wwpn in resp.select('local_wwpn'):
            if wwpn is not None:
                wwpns.add(wwpn)
        return list(wwpns)

    def initialize_host_info(self):
        """Get the host,wwpn,iscsi and store in Host_connector_info."""
        if (not self.Host_connector_info['FC'] and
                not self.Host_connector_info['ISCSI']):
            hosts_info = self.ssh.lshost()
            host_list = list(hosts_info.select('name'))
            for eachhost in host_list:
                resp = self.ssh.lshost(host=eachhost)
                if list(resp.select("WWPN")) != [None]:
                    for wwpn in resp.select('WWPN'):
                        if wwpn not in self.Host_connector_info['FC'].keys():
                            self.Host_connector_info['FC'][wwpn] = eachhost
                elif list(resp.select('iscsi_name')) != [None]:
                    for iscsi_name in resp.select('iscsi_name'):
                        if (iscsi_name not in
                                self.Host_connector_info['ISCSI'].keys()):
                            self.Host_connector_info['ISCSI'][iscsi_name] = (
                                eachhost)

    def get_host_from_host_info(self, connector, iscsi=False):
        host_name = None
        new_wwpn = []
        if iscsi and 'initiator' in connector:
            if connector['initiator'] in self.Host_connector_info['ISCSI']:
                iqn = connector['initiator']
                host_name = self.Host_connector_info['ISCSI'][iqn]
        elif 'wwpns' in connector:
            for wwpn in connector['wwpns']:
                if wwpn.upper() in self.Host_connector_info['FC']:
                    host_name = self.Host_connector_info['FC'][wwpn.upper()]
                else:
                    new_wwpn.append(['wwpn', '%s' % wwpn])

        return host_name, new_wwpn

    def get_host_from_connector(self, connector, volume_name=None,
                                iscsi=False):
        """Return the Storwize host described by the connector."""
        LOG.debug('Enter: get_host_from_connector: %s.', connector)

        # If we have FC information, we have a faster lookup option
        host_name, new_wwpn = self.get_host_from_host_info(connector, iscsi)

        if host_name and volume_name:
            hosts_map_info = self.ssh.lsvdiskhostmap(volume_name)
            hosts_map_info_list = list(hosts_map_info.select('host_name'))
            if host_name in hosts_map_info_list:
                LOG.debug("get_host_from_connector: hosts_map_info:"
                          " %s", hosts_map_info_list)
                LOG.debug('Leave: get_host_from_connector host %s', host_name)
                return host_name
            else:
                LOG.debug('get_host_from_connector: host %s not mapped '
                          'to volume', host_name)
                host_name = None

        if host_name:
            for port in new_wwpn:
                LOG.debug('update wwpn %(wwpn)s to  host %(host)s.',
                          {'wwpn': port, 'host': host_name})
                self.ssh.addhostport(host_name, port[0], port[1])

            LOG.debug('Leave: get_host_from_connector: host %s.', host_name)
            return host_name

        def update_host_list(host, host_list):
            idx = host_list.index(host)
            del host_list[idx]
            host_list.insert(0, host)

        # That didn't work, so try exhaustive search
        hosts_info = self.ssh.lshost()
        host_list = list(hosts_info.select('name'))
        # If we have a "real" connector, we might be able to find the
        # host entry with fewer queries if we move the host entries
        # that contain the connector's host property value to the front
        # of the list
        if 'host' in connector:
            # order host_list such that the host entries that
            # contain the connector's host name are at the
            # beginning of the list
            for host in host_list:
                if re.search(connector['host'], host):
                    update_host_list(host, host_list)
        # If we have a volume name we have a potential fast path
        # for finding the matching host for that volume.
        # Add the host_names that have mappings for our volume to the
        # head of the list of host names to search them first
        if volume_name:
            hosts_map_info = self.ssh.lsvdiskhostmap(volume_name)
            hosts_map_info_list = list(hosts_map_info.select('host_name'))
            # remove the fast path host names from the end of the list
            # and move to the front so they are only searched for once.
            for host in hosts_map_info_list:
                update_host_list(host, host_list)
        found = False
        for name in host_list:
            try:
                resp = self.ssh.lshost(host=name)
            except exception.VolumeBackendAPIException as ex:
                LOG.debug("Exception message: %s", ex.msg)
                if 'CMMVC5754E' in ex.msg:
                    LOG.debug("CMMVC5754E found in CLI exception.")
                    # CMMVC5754E: The specified object does not exist
                    # The host has been deleted while walking the list.
                    # This is a result of a host change on the SVC that
                    # is out of band to this request.
                    continue
                # unexpected error so reraise it
                with excutils.save_and_reraise_exception():
                    pass
            if iscsi:
                if 'initiator' in connector:
                    for iscsi_name in resp.select('iscsi_name'):
                        if iscsi_name == connector['initiator']:
                            host_name = name
                            found = True
                            break
            elif 'wwpns' in connector and len(connector['wwpns']):
                connector_wwpns = [str(x).lower() for x in connector['wwpns']]
                for wwpn in resp.select('WWPN'):
                    if wwpn and wwpn.lower() in connector_wwpns:
                        host_name = name
                        found = True
                        break
            if found:
                break

        LOG.debug('Leave: get_host_from_connector: host %s.', host_name)
        return host_name

    def create_host(self, connector, iscsi=False, site=None, portset=None):
        """Create a new host on the storage system.

        We create a host name and associate it with the given connection
        information.  The host name will be a cleaned up version of the given
        host name (at most 55 characters), plus a random 8-character suffix to
        avoid collisions. The total length should be at most 63 characters.
        """
        LOG.debug('Enter: create_host: host %s.', connector['host'])

        # Before we start, make sure host name is a string and that we have at
        # least one port.
        host_name = connector['host']
        if not isinstance(host_name, str):
            msg = _('create_host: Host name is not a string.')
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

        ports = []
        if iscsi:
            if 'initiator' in connector:
                ports.append(['initiator', '%s' % connector['initiator']])
            else:
                msg = _('create_host: No initiators supplied.')
        else:
            if 'wwpns' in connector:
                for wwpn in connector['wwpns']:
                    ports.append(['wwpn', '%s' % wwpn])
            else:
                msg = _('create_host: No wwpns supplied.')
        if not len(ports):
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

        # Build a host name for the Storwize host - first clean up the name
        if isinstance(host_name, str):
            host_name = unicodedata.normalize('NFKD', host_name).encode(
                'ascii', 'replace').decode('ascii')

        for num in range(0, 128):
            ch = str(chr(num))
            if not ch.isalnum() and ch not in [' ', '.', '-', '_']:
                host_name = host_name.replace(ch, '-')

        # Storwize doesn't like hostname that doesn't starts with letter or _.
        if not re.match('^[A-Za-z]', host_name):
            host_name = '_' + host_name

        # Add a random 8-character suffix to avoid collisions
        rand_id = str(random.randint(0, 99999999)).zfill(8)
        host_name = '%s-%s' % (host_name[:55], rand_id)

        # Create a host with one port
        port = ports.pop(0)
        # Host site_id is necessary for hyperswap volume.
        self.ssh.mkhost(host_name, port[0], port[1], site, portset)

        # Add any additional ports to the host
        for port in ports:
            self.ssh.addhostport(host_name, port[0], port[1])

        if iscsi and 'initiator' in connector:
            iqn = connector['initiator']
            self.Host_connector_info['ISCSI'][iqn] = host_name
        elif 'wwpns' in connector:
            for wwpn in connector['wwpns']:
                self.Host_connector_info['FC'][wwpn.upper()] = host_name

        LOG.debug('Leave: create_host: host %(host)s - %(host_name)s.',
                  {'host': connector['host'], 'host_name': host_name})
        return host_name

    def update_host(self, host_name, site_name):
        self.ssh.chhost(host_name, site=site_name)

    def delete_host(self, host_name):
        self.ssh.rmhost(host_name)

        if host_name in self.Host_connector_info['ISCSI'].values():
            host_iqn = None
            for iqn, host in self.Host_connector_info['ISCSI'].items():
                if host == host_name:
                    host_iqn = iqn
                    break
            if host_iqn:
                self.Host_connector_info['ISCSI'].pop(host_iqn)
        elif host_name in self.Host_connector_info['FC'].values():
            host_wwpn = []
            for wwpn, host in self.Host_connector_info['FC'].items():
                if host == host_name:
                    host_wwpn.append(wwpn)

            for wwpn in host_wwpn:
                self.Host_connector_info['FC'].pop(wwpn)

    def _get_unused_lun_id(self, host_name):
        luns_used = []
        result_lun = '-1'
        resp = self.ssh.lshostvdiskmap(host_name)
        for mapping_info in resp:
            luns_used.append(int(mapping_info['SCSI_id']))

        luns_used.sort()
        result_lun = str(len(luns_used))
        for index, n in enumerate(luns_used):
            if n > index:
                result_lun = str(index)
                break

        return result_lun

    @volume_utils.trace
    def map_vol_to_host(self, volume_name, host_name, multihostmap):
        """Create a mapping between a volume to a host."""

        # Check if this volume is already mapped to this host
        result_lun = self.ssh.get_vdiskhostmapid(volume_name, host_name)
        if result_lun:
            LOG.debug('volume %(volume_name)s is already mapped to the host '
                      '%(host_name)s.',
                      {'volume_name': volume_name, 'host_name': host_name})
            return int(result_lun)

        class _RetryableVolumeDriverException(
                exception.VolumeBackendAPIException):
            """Exception to identify which types of errors to retry."""
            pass

        @cinder_utils.retry(_RetryableVolumeDriverException,
                            interval=2,
                            retries=3,
                            wait_random=True)
        def make_vdisk_host_map():
            try:
                result_lun = self._get_unused_lun_id(host_name)
                self.ssh.mkvdiskhostmap(host_name, volume_name, result_lun,
                                        multihostmap)
                return int(result_lun)
            except Exception as ex:
                # pylint: disable=E1101
                if (not multihostmap and hasattr(ex, 'msg') and
                        'CMMVC6071E' in ex.msg):
                    LOG.warning('storwize_svc_multihostmap_enabled is set '
                                'to False, not allowing multi host mapping.')
                    raise exception.VolumeDriverException(
                        message=_('CMMVC6071E The VDisk-to-host mapping was '
                                  'not created because the VDisk is already '
                                  'mapped to a host.'))
                if hasattr(ex, 'msg') and 'CMMVC5879E' in ex.msg:
                    raise _RetryableVolumeDriverException(ex)
                with excutils.save_and_reraise_exception():
                    LOG.error('Error mapping VDisk-to-host.')

        return make_vdisk_host_map()

    def unmap_vol_from_host(self, volume_name, host_name):
        """Unmap the volume and delete the host if it has no more mappings."""

        LOG.debug('Enter: unmap_vol_from_host: volume %(volume_name)s from '
                  'host %(host_name)s.',
                  {'volume_name': volume_name, 'host_name': host_name})

        # Check if the mapping exists
        resp = self.ssh.lsvdiskhostmap(volume_name)
        if not len(resp):
            LOG.warning('unmap_vol_from_host: No mapping of volume '
                        '%(vol_name)s to any host found.',
                        {'vol_name': volume_name})
            return host_name
        if host_name is None:
            if len(resp) > 1:
                LOG.warning('unmap_vol_from_host: Multiple mappings of '
                            'volume %(vol_name)s found, no host '
                            'specified.', {'vol_name': volume_name})
                return
            else:
                host_name = resp[0]['host_name']
        else:
            found = False
            for h in resp.select('host_name'):
                if h == host_name:
                    found = True
            if not found:
                LOG.warning('unmap_vol_from_host: No mapping of volume '
                            '%(vol_name)s to host %(host)s found.',
                            {'vol_name': volume_name, 'host': host_name})
                return host_name
        # We now know that the mapping exists
        self.ssh.rmvdiskhostmap(host_name, volume_name)

        LOG.debug('Leave: unmap_vol_from_host: volume %(volume_name)s from '
                  'host %(host_name)s.',
                  {'volume_name': volume_name, 'host_name': host_name})
        return host_name

    def check_host_mapped_vols(self, host_name):
        return self.ssh.lshostvdiskmap(host_name)

    def check_vol_mapped_to_host(self, vol_name, host_name):
        resp = self.ssh.lsvdiskhostmap(vol_name)
        for mapping_info in resp:
            if mapping_info['host_name'] == host_name:
                return True
        return False

    @staticmethod
    def build_default_opts(config):
        # Ignore capitalization

        cluster_partner = config.storwize_svc_stretched_cluster_partner
        opt = {'rsize': config.storwize_svc_vol_rsize,
               'warning': config.storwize_svc_vol_warning,
               'autoexpand': config.storwize_svc_vol_autoexpand,
               'grainsize': config.storwize_svc_vol_grainsize,
               'compression': config.storwize_svc_vol_compression,
               'easytier': config.storwize_svc_vol_easytier,
               'iogrp': config.storwize_svc_vol_iogrp,
               'qos': None,
               'stretched_cluster': cluster_partner,
               'replication': False,
               'nofmtdisk': config.storwize_svc_vol_nofmtdisk,
               'flashcopy_rate': config.storwize_svc_flashcopy_rate,
               'clean_rate': config.storwize_svc_clean_rate,
               'mirror_pool': config.storwize_svc_mirror_pool,
               'volume_topology': None,
               'peer_pool': config.storwize_peer_pool,
               'storwize_portset': config.storwize_portset,
               'storwize_svc_src_child_pool':
                   config.storwize_svc_src_child_pool,
               'storwize_svc_target_child_pool':
                   config.storwize_svc_target_child_pool,
               'cycle_period_seconds': config.cycle_period_seconds}
        return opt

    @staticmethod
    def check_vdisk_opts(state, opts):
        # Check that grainsize is 32/64/128/256
        if opts['grainsize'] not in [8, 32, 64, 128, 256]:
            raise exception.InvalidInput(
                reason=_('Illegal value specified for '
                         'storwize_svc_vol_grainsize: set to either '
                         '32, 64, 128, or 256.'))

        # Check that compression is supported
        if opts['compression'] and not state['compression_enabled']:
            raise exception.InvalidInput(
                reason=_('System does not support compression.'))

        # Check that rsize is set if compression is set
        if opts['compression'] and opts['rsize'] == -1:
            raise exception.InvalidInput(
                reason=_('If compression is set to True, rsize must '
                         'also be set (not equal to -1).'))

        # Check cycle_period_seconds are in 60-86400
        if opts['cycle_period_seconds'] not in range(60, 86401):
            raise exception.InvalidInput(
                reason=_('cycle_period_seconds should be integer '
                         'between 60 and 86400.'))

        iogs = StorwizeHelpers._get_valid_requested_io_groups(state, opts)

        if len(iogs) == 0:
            raise exception.InvalidInput(
                reason=_('Given I/O group(s) %(iogrp)s not valid; available '
                         'I/O groups are %(avail)s.')
                % {'iogrp': opts['iogrp'],
                   'avail': state['available_iogrps']})

        if opts['nofmtdisk'] and opts['rsize'] != -1:
            raise exception.InvalidInput(
                reason=_('If nofmtdisk is set to True, rsize must '
                         'also be set to -1.'))

    @staticmethod
    def _get_valid_requested_io_groups(state, opts):
        given_iogs = str(opts['iogrp'])
        iog_list = given_iogs.split(',')
        # convert to int
        iog_list = list(map(int, iog_list))
        LOG.debug("Requested iogroups %s", iog_list)
        LOG.debug("Available iogroups %s", state['available_iogrps'])
        filtiog = set(iog_list).intersection(state['available_iogrps'])
        iog_list = list(filtiog)
        LOG.debug("Filtered (valid) requested iogroups %s", iog_list)
        return iog_list

    def _get_opts_from_specs(self, opts, specs):
        qos = {}
        for k, value in specs.items():
            # Get the scope, if using scope format
            key_split = k.split(':')
            if len(key_split) == 1:
                scope = None
                key = key_split[0]
            else:
                scope = key_split[0]
                key = key_split[1]
            # We generally do not look at capabilities in the driver, but
            # replication is a special case where the user asks for
            # a volume to be replicated, and we want both the scheduler and
            # the driver to act on the value.
            if ((not scope or scope == 'capabilities') and
               key == 'replication'):
                scope = None
                key = 'replication'
                words = value.split()
                if not (words and len(words) == 2 and words[0] == '<is>'):
                    LOG.error('Replication must be specified as '
                              '\'<is> True\' or \'<is> False\'.')
                del words[0]
                value = words[0]

            # Add the QoS.
            if scope and scope == 'qos':
                if key in self.svc_qos:
                    try:
                        type_fn = self.svc_qos[key]['type']
                        value = type_fn(value)
                        qos[key] = value
                    except ValueError:
                        continue

            # Any keys that the driver should look at should have the
            # 'drivers' scope.
            if scope and scope != 'drivers':
                continue

            if key in opts:
                this_type = type(opts[key]).__name__
                if this_type == 'int':
                    value = int(value)
                elif this_type == 'bool':
                    value = strutils.bool_from_string(value)
                opts[key] = value
        if len(qos):
            opts['qos'] = qos
            opts = self._validate_qos_opts(opts)
        return opts

    def _validate_qos_opts(self, opts):
        """Override to add IOThrottling_unit to qos from extra_specs"""
        qos = {}
        for key, value in opts['qos'].items():
            # Validate IOThrottle rate value
            if key in self.svc_qos and key == "IOThrottling":
                if int(value) >= 0:
                    qos[key] = value
                else:
                    msg = (_("I/O Throttle rate cannot be negative or Zero. "
                             "So skipping setting of I/O Throttle rate on "
                             "volumes."))
                    LOG.warning(msg)
                    continue

            # Validate IOThrottle Unit
            if key in self.svc_qos and key == 'IOThrottling_unit':
                if value:
                    enum_values = self.svc_qos[key]['enum']
                    if value in enum_values:
                        qos[key] = value
                    else:
                        msg = (_("An invalid '%(actual)s' unit was configured "
                                 "for IOThrottling_unit on Storage Template. "
                                 "It should be one of the values: "
                                 "%(expected)s. So skipping setting of I/O "
                                 "Throttle rate on volumes.") %
                               dict(actual=value, expected=enum_values))
                        LOG.warning(msg)
                        continue
        if len(qos) != 2:
            opts['qos'] = {}
        return opts

    def _get_qos_from_volume_metadata(self, volume_metadata):
        """Return the QoS information from the volume metadata."""
        qos = {}
        for i in volume_metadata:
            k = i.get('key', None)
            value = i.get('value', None)
            key_split = k.split(':')
            if len(key_split) == 1:
                scope = None
                key = key_split[0]
            else:
                scope = key_split[0]
                key = key_split[1]
            # Add the QoS.
            if scope and scope == 'qos':
                if key in self.svc_qos:
                    try:
                        type_fn = self.svc_qos[key]['type']
                        value = type_fn(value)
                        qos[key] = value
                    except ValueError:
                        continue
        return qos

    def _wait_for_a_condition(self, testmethod, timeout=None,
                              interval=INTERVAL_1_SEC,
                              raise_exception=False):
        start_time = time.time()
        if timeout is None:
            timeout = DEFAULT_TIMEOUT

        def _inner():
            try:
                testValue = testmethod()
            except Exception as ex:
                if raise_exception:
                    LOG.exception("_wait_for_a_condition: %s"
                                  " execution failed.",
                                  testmethod.__name__)
                    raise exception.VolumeBackendAPIException(data=ex)
                else:
                    testValue = False
                    # pylint: disable=E1101
                    LOG.debug('Helper.'
                              '_wait_for_condition: %(method_name)s '
                              'execution failed for %(exception)s.',
                              {'method_name': testmethod.__name__,
                               'exception': ex.message})
            if testValue:
                raise loopingcall.LoopingCallDone()

            if int(time.time()) - start_time > timeout:
                msg = (_('CommandLineHelper._wait_for_condition: %s timeout.')
                       % testmethod.__name__)
                LOG.error(msg)
                raise exception.VolumeBackendAPIException(data=msg)

        timer = loopingcall.FixedIntervalLoopingCall(_inner)
        timer.start(interval=interval).wait()

    def get_vdisk_params(self, config, state, type_id,
                         volume_type=None, volume_metadata=None):
        """Return the parameters for creating the vdisk.

        Takes volume type and defaults from config options into account.
        """
        opts = self.build_default_opts(config)
        ctxt = context.get_admin_context()
        if volume_type is None and type_id is not None:
            volume_type = volume_types.get_volume_type(ctxt, type_id)
        if volume_type:
            qos_specs_id = volume_type.get('qos_specs_id')
            specs = dict(volume_type).get('extra_specs')

            # NOTE(vhou): We prefer the qos_specs association
            # and over-ride any existing
            # extra-specs settings if present
            if qos_specs_id is not None:
                kvs = qos_specs.get_qos_specs(ctxt, qos_specs_id)['specs']
                # Merge the qos_specs into extra_specs and qos_specs has higher
                # priority than extra_specs if they have different values for
                # the same key.
                specs.update(kvs)
            opts = self._get_opts_from_specs(opts, specs)
        if (opts['qos'] is None and config.storwize_svc_allow_tenant_qos and
                volume_metadata):
            qos = self._get_qos_from_volume_metadata(volume_metadata)
            if len(qos) != 0:
                opts['qos'] = qos

        self.check_vdisk_opts(state, opts)
        return opts

    def check_data_reduction_pool_params(self, opts):
        """Check the configured parameters if vol in data reduction pool."""
        if opts['warning'] != 0:
            msg = (_('You cannot specify -warning for thin-provisioned or '
                     'compressed volumes that are in data reduction '
                     'pools. The configured warning is '
                     '%s.') % opts['warning'])
            raise exception.VolumeDriverException(message=msg)
        if not opts['easytier']:
            msg = (_('You cannot specify -easytier for thin-provisioned '
                     'or compressed volumes that are in data reduction '
                     'pools. The configured easytier is '
                     '%s') % opts['easytier'])
            raise exception.VolumeDriverException(message=msg)
        if opts['grainsize'] != 256 and opts['grainsize'] != 8:
            msg = (_('You cannot specify -grainsize for thin-provisioned '
                     'or compressed volumes that are in data reduction '
                     'pools. This type of volume will be created with a '
                     'grainsize of 8 KB. The configured grainsize is '
                     '%s.') % opts['grainsize'])
            raise exception.VolumeDriverException(message=msg)
        if opts['rsize'] != 2:
            if opts['volume_topology'] == 'hyperswap':
                msg = (_('You cannot specify -buffersize for Hyperswap volumes'
                         ' that are in data reduction pools, The configured '
                         'buffersize is %s.') % opts['rsize'])
                raise exception.VolumeDriverException(message=msg)
            else:
                msg = (_('You cannot specify -rsize for thin-provisioned '
                         'or compressed volumes that are in data reduction '
                         'pools. The -rsize parameter will be ignored in '
                         'mkvdisk. Only its presence or absence is used to '
                         'determine if the disk is a data reduction volume '
                         'copy or a thick volume copy. The '
                         'configured rsize is %s.') % opts['rsize'])
                raise exception.VolumeDriverException(message=msg)
        if not opts['autoexpand']:
            msg = (_('You cannot set the autoexpand to disable for '
                     'thin-provisioned or compressed volumes that are in data '
                     'reduction pool. The configured'
                     ' autoexpand is %s.') % opts['autoexpand'])
            raise exception.VolumeDriverException(message=msg)
        else:
            LOG.info('You cannot specify warning, grainsize and '
                     'easytier for thin-provisioned or compressed'
                     ' volumes that are in data reduction pools. '
                     'The rsize parameter will be ignored, the '
                     'autoexpand must be enabled.')

    def is_volume_type_dr_pools(self, pool, opts, rep_type=None,
                                rep_target_pool=None):
        """Check every configured pools is data reduction pool."""
        if self.is_data_reduction_pool(pool):
            LOG.debug('The configured pool %s is a data reduction pool.', pool)
            return True

        if opts['mirror_pool'] and self.is_data_reduction_pool(
                opts['mirror_pool']):
            LOG.debug('The mirror_pool %s is a data reduction pool.',
                      opts['mirror_pool'])
            return True

        if (opts['volume_topology'] == 'hyperswap' and
                self.is_data_reduction_pool(opts['peer_pool'])):
            LOG.debug('The peer_pool %s is a data reduction pool.',
                      opts['peer_pool'])
            return True

        if rep_type and self.is_data_reduction_pool(rep_target_pool):
            LOG.debug('The replica target pool %s is a data reduction pool.',
                      rep_target_pool)
            return True

        return False

    @staticmethod
    def _get_vdisk_create_params(opts, is_dr_pool, add_copies=False):
        easytier = 'on' if opts['easytier'] else 'off'
        if opts['rsize'] == -1:
            params = []
            if opts['nofmtdisk']:
                params.append('-nofmtdisk')
        else:
            if is_dr_pool:
                params = ['-rsize', '%s%%' % str(opts['rsize']), '-autoexpand']
                if opts['compression']:
                    params.append('-compressed')
            else:
                params = ['-rsize', '%s%%' % str(opts['rsize']),
                          '-autoexpand', '-warning',
                          '%s%%' % str(opts['warning'])]
                if not opts['autoexpand']:
                    params.remove('-autoexpand')

                if opts['compression']:
                    params.append('-compressed')
                else:
                    params.extend(['-grainsize', str(opts['grainsize'])])

        if add_copies and opts['mirror_pool']:
            params.extend(['-copies', '2'])

        if not is_dr_pool:
            params.extend(['-easytier', easytier])
        return params

    def create_vdisk(self, name, size, units, pool, opts):
        LOG.debug('Enter: create_vdisk: vdisk %s.', name)
        mdiskgrp = pool
        if opts['mirror_pool']:
            if not self.is_pool_defined(opts['mirror_pool']):
                raise exception.InvalidInput(
                    reason=_('The pool %s in which mirrored copy is stored '
                             'is invalid') % opts['mirror_pool'])
            # The syntax of pool SVC expects is pool:mirror_pool in
            # mdiskgrp for mirror volume
            mdiskgrp = '%s:%s' % (pool, opts['mirror_pool'])

        is_dr_pool = False
        if opts['rsize'] != -1:
            is_dr_pool = self.is_volume_type_dr_pools(pool, opts)
            if is_dr_pool:
                self.check_data_reduction_pool_params(opts)
        params = self._get_vdisk_create_params(
            opts, is_dr_pool,
            add_copies=True if opts['mirror_pool'] else False)
        self.ssh.mkvdisk(name, size, units, mdiskgrp, opts, params)
        LOG.debug('Leave: _create_vdisk: volume %s.', name)

    def _get_hyperswap_volume_create_params(self, opts, is_dr_pool):
        # Storwize/svc use cli command mkvolume to create hyperswap volume.
        # You must specify -thin with grainsize.
        # You must specify either -thin or -compressed with warning.
        params = []
        LOG.debug('The I/O groups of a hyperswap volume will be selected by '
                  'storage.')
        if is_dr_pool:
            if opts['compression']:
                params.append('-compressed')
            else:
                params.append('-thin')
        else:
            params.extend(['-buffersize', '%s%%' % str(opts['rsize']),
                           '-warning',
                           '%s%%' % str(opts['warning'])])
            if not opts['autoexpand']:
                params.append('-noautoexpand')
            if opts['compression']:
                params.append('-compressed')
            else:
                params.append('-thin')
                params.extend(['-grainsize',
                               str(opts['grainsize'])])
        return params

    def create_hyperswap_volume(self, vol_name, size, units, pool, opts):
        vol_name = '"%s"' % vol_name
        params = []
        if opts['rsize'] != -1:
            is_dr_pool = self.is_volume_type_dr_pools(pool, opts)
            if is_dr_pool:
                self.check_data_reduction_pool_params(opts)
            params = self._get_hyperswap_volume_create_params(opts, is_dr_pool)
        hyperpool = '%s:%s' % (pool, opts['peer_pool'])
        self.ssh.mkvolume(vol_name, str(size), units, hyperpool, params)

    def convert_volume_to_hyperswap(self, vol_name, opts, state):
        vol_name = '%s' % vol_name
        if not self.is_system_topology_hyperswap(state):
            msg = _('Convert volume to hyperswap failed, the system is '
                    'below release 7.6.0.0 or it is not hyperswap '
                    'topology.')
            raise exception.VolumeDriverException(message=msg)
        else:
            attr = self.get_vdisk_attributes(vol_name)
            if attr is None:
                msg = (_('convert_volume_to_hyperswap: Failed to get '
                         'attributes for volume %s.') % vol_name)
                LOG.error(msg)
                raise exception.VolumeDriverException(message=msg)
            pool = attr['mdisk_grp_name']
            self.check_hyperswap_pool(pool, opts['peer_pool'])
            hyper_pool = '%s' % opts['peer_pool']
            params = []
            if opts['rsize'] != -1:
                is_dr_pool = self.is_volume_type_dr_pools(pool, opts)
                if is_dr_pool:
                    self.check_data_reduction_pool_params(opts)
                params = self._get_hyperswap_volume_create_params(opts,
                                                                  is_dr_pool)
            self.ssh.addvolumecopy(vol_name, hyper_pool, params)

    def convert_extended_volume_to_hyperswap(self, vol_name, opts, state):
        vol_name = '%s' % vol_name
        attr = self.get_vdisk_attributes(vol_name)
        if attr is None:
            msg = (_('convert_volume_to_hyperswap: Failed to get '
                     'attributes for volume %s.') % vol_name)
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)
        hyper_pool = '%s' % opts['peer_pool']
        params = []
        if opts['rsize'] != -1:
            is_dr_pool = self.is_volume_type_dr_pools(attr['mdisk_grp_name'],
                                                      opts)
            if is_dr_pool:
                self.check_data_reduction_pool_params(opts)
            params = self._get_hyperswap_volume_create_params(opts, is_dr_pool)
        self.ssh.addvolumecopy(vol_name, hyper_pool, params)

    def convert_hyperswap_volume_to_normal(self, vol_name, peer_pool):
        vol_name = '%s' % vol_name
        hyper_pool = '%s' % peer_pool
        self.ssh.rmvolumecopy(vol_name, hyper_pool)

    def delete_hyperswap_volume(self, volume, force_unmap, force_delete):
        """Ensures that vdisk is not part of FC mapping and deletes it."""
        if not self.is_vdisk_defined(volume):
            LOG.warning('Tried to delete non-existent volume %s.', volume)
            return
        self.ensure_vdisk_no_fc_mappings(volume, allow_snaps=True,
                                         allow_fctgt=True)
        self.ssh.rmvolume(volume,
                          force_unmap=force_unmap,
                          force_delete=force_delete)

    def get_vdisk_attributes(self, vdisk):
        attrs = self.ssh.lsvdisk(vdisk)
        return attrs

    def is_vdisk_defined(self, vdisk_name):
        """Check if vdisk is defined."""
        attrs = self.get_vdisk_attributes(vdisk_name)
        return attrs is not None

    def get_vdisk_copy_attrs(self, vdisk, copy_id):
        return self.ssh.lsvdiskcopy(vdisk, copy_id=copy_id)[0]

    def get_vdisk_copies(self, vdisk):
        copies = {'primary': None,
                  'secondary': None}

        resp = self.ssh.lsvdiskcopy(vdisk)
        for copy_id, status, sync, primary, mdisk_grp in (
            resp.select('copy_id', 'status', 'sync',
                        'primary', 'mdisk_grp_name')):
            copy = {'copy_id': copy_id,
                    'status': status,
                    'sync': sync,
                    'primary': primary,
                    'mdisk_grp_name': mdisk_grp,
                    'sync_progress': None}
            if copy['sync'] != 'yes':
                progress_info = self.ssh.lsvdisksyncprogress(vdisk, copy_id)
                copy['sync_progress'] = progress_info['progress']
            if copy['primary'] == 'yes':
                copies['primary'] = copy
            else:
                copies['secondary'] = copy
        return copies

    def _prepare_fc_map(self, fc_map_id, timeout, restore):
        self.ssh.prestartfcmap(fc_map_id, restore)
        mapping_ready = False
        max_retries = (timeout // self.WAIT_TIME) + 1
        for try_number in range(1, max_retries):
            mapping_attrs = self._get_flashcopy_mapping_attributes(fc_map_id)
            if (mapping_attrs is None or
                    'status' not in mapping_attrs):
                break
            if mapping_attrs['status'] == 'prepared':
                mapping_ready = True
                break
            elif mapping_attrs['status'] == 'stopped':
                self.ssh.prestartfcmap(fc_map_id, restore)
            elif mapping_attrs['status'] != 'preparing':
                msg = (_('Unexecpted mapping status %(status)s for mapping '
                         '%(id)s. Attributes: %(attr)s.')
                       % {'status': mapping_attrs['status'],
                          'id': fc_map_id,
                          'attr': mapping_attrs})
                LOG.error(msg)
                raise exception.VolumeBackendAPIException(data=msg)
            greenthread.sleep(self.WAIT_TIME)

        if not mapping_ready:
            msg = (_('Mapping %(id)s prepare failed to complete within the '
                     'allotted %(to)d seconds timeout. Terminating.')
                   % {'id': fc_map_id,
                      'to': timeout})
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

    def start_fc_consistgrp(self, fc_consistgrp):
        self.ssh.startfcconsistgrp(fc_consistgrp)

    def create_fc_consistgrp(self, fc_consistgrp):
        self.ssh.mkfcconsistgrp(fc_consistgrp)

    def delete_fc_consistgrp(self, fc_consistgrp):
        self.ssh.rmfcconsistgrp(fc_consistgrp)

    def stop_fc_consistgrp(self, fc_consistgrp):
        self.ssh.stopfcconsistgrp(fc_consistgrp)

    def run_consistgrp_snapshots(self, fc_consistgrp, snapshots, state,
                                 config, timeout):
        model_update = {'status': fields.GroupSnapshotStatus.AVAILABLE}
        snapshots_model_update = []
        try:
            for snapshot in snapshots:
                opts = self.get_vdisk_params(config, state,
                                             snapshot['volume_type_id'])
                volume = snapshot.volume
                if not volume:
                    msg = (_("Can't get volume from snapshot: %(id)s")
                           % {"id": snapshot.id})
                    LOG.error(msg)
                    raise exception.VolumeBackendAPIException(data=msg)
                vhost = volume.host
                if '#' not in vhost:
                    attrs = self.get_vdisk_attributes(volume['name'])
                    pool = self._get_pool(attrs)
                else:
                    pool = volume_utils.extract_host(volume.host, 'pool')
                self.create_flashcopy_to_consistgrp(snapshot['volume_name'],
                                                    snapshot['name'],
                                                    fc_consistgrp,
                                                    config, opts, False,
                                                    pool=pool)

            self.prepare_fc_consistgrp(fc_consistgrp, timeout)
            self.start_fc_consistgrp(fc_consistgrp)
            # There is CG limitation that could not create more than 128 CGs.
            # After start CG, we delete CG to avoid CG limitation.
            # Cinder general will maintain the CG and snapshots relationship.
            self.delete_fc_consistgrp(fc_consistgrp)
        except exception.VolumeBackendAPIException as err:
            model_update['status'] = fields.GroupSnapshotStatus.ERROR
            # Release cg
            self.delete_fc_consistgrp(fc_consistgrp)
            LOG.error("Failed to create CGSnapshot. "
                      "Exception: %s.", err)

        for snapshot in snapshots:
            snapshots_model_update.append(
                {'id': snapshot['id'],
                 'status': model_update['status'],
                 'replication_status': fields.ReplicationStatus.NOT_CAPABLE})
        return model_update, snapshots_model_update

    def delete_consistgrp_snapshots(self, fc_consistgrp, snapshots):
        """Delete flashcopy maps and consistent group."""
        model_update = {'status': fields.GroupSnapshotStatus.DELETED}
        snapshots_model_update = []

        try:
            self.delete_fc_consistgrp(fc_consistgrp)
        except exception.VolumeBackendAPIException as err:
            if CMMVC5753E in err.msg:
                LOG.warning('Failed to delete as flash copy consistency '
                            'group %s does not exist,ignoring err: %s',
                            fc_consistgrp, err)

        for snapshot in snapshots:
            try:
                self.delete_vdisk(snapshot['name'],
                                  force_unmap=False,
                                  force_delete=True)
                snapshots_model_update.append(
                    {'id': snapshot['id'],
                     'status': fields.GroupSnapshotStatus.DELETED})
            except exception.VolumeBackendAPIException as err:
                model_update['status'] = (
                    fields.GroupSnapshotStatus.ERROR_DELETING)
                snapshots_model_update.append(
                    {'id': snapshot['id'],
                     'status': fields.GroupSnapshotStatus.ERROR_DELETING})
                LOG.error("Failed to delete the snapshot %(snap)s of "
                          "CGSnapshot. Exception: %(exception)s.",
                          {'snap': snapshot['name'], 'exception': err})

        return model_update, snapshots_model_update

    def prepare_fc_consistgrp(self, fc_consistgrp, timeout):
        """Prepare FC Consistency Group."""
        self.ssh.prestartfcconsistgrp(fc_consistgrp)

        def prepare_fc_consistgrp_success():
            mapping_ready = False
            mapping_attrs = self._get_flashcopy_consistgrp_attr(fc_consistgrp)
            if (mapping_attrs is None or
                    'status' not in mapping_attrs):
                pass
            if mapping_attrs['status'] == 'prepared':
                mapping_ready = True
            elif mapping_attrs['status'] == 'stopped':
                self.ssh.prestartfcconsistgrp(fc_consistgrp)
            elif mapping_attrs['status'] != 'preparing':
                msg = (_('Unexpected mapping status %(status)s for mapping '
                         '%(id)s. Attributes: %(attr)s.') %
                       {'status': mapping_attrs['status'],
                        'id': fc_consistgrp,
                        'attr': mapping_attrs})
                LOG.error(msg)
                raise exception.VolumeBackendAPIException(data=msg)
            return mapping_ready
        self._wait_for_a_condition(prepare_fc_consistgrp_success, timeout)

    def create_cg_from_source(self, group, fc_consistgrp,
                              sources, targets, state,
                              config, timeout):
        """Create consistence group from source"""
        LOG.debug('Enter: create_cg_from_source: cg %(cg)s'
                  ' source %(source)s, target %(target)s',
                  {'cg': fc_consistgrp, 'source': sources, 'target': targets})
        model_update = {'status': fields.GroupStatus.AVAILABLE}
        ctxt = context.get_admin_context()
        try:
            for source, target in zip(sources, targets):
                opts = self.get_vdisk_params(config, state,
                                             source['volume_type_id'])
                vhost = target['host']
                if '#' not in vhost:
                    pool = opts.get('storage_pool')
                else:
                    pool = volume_utils.extract_host(target['host'], 'pool')
                self.create_flashcopy_to_consistgrp(source['name'],
                                                    target['name'],
                                                    fc_consistgrp,
                                                    config, opts,
                                                    True, pool=pool)
            self.prepare_fc_consistgrp(fc_consistgrp, timeout)
            self.start_fc_consistgrp(fc_consistgrp)
            self.delete_fc_consistgrp(fc_consistgrp)
            volumes_model_update = self._get_volume_model_updates(
                ctxt, targets, group['id'], model_update['status'])
        except exception.VolumeBackendAPIException as err:
            model_update['status'] = fields.GroupStatus.ERROR
            volumes_model_update = self._get_volume_model_updates(
                ctxt, targets, group['id'], model_update['status'])
            with excutils.save_and_reraise_exception():
                # Release cg
                self.delete_fc_consistgrp(fc_consistgrp)
                LOG.error("Failed to create CG from CGsnapshot. "
                          "Exception: %s", err)
            return model_update, volumes_model_update

        LOG.debug('Leave: create_cg_from_source.')
        return model_update, volumes_model_update

    def _get_volume_model_updates(self, ctxt, volumes, cgId,
                                  status='available'):
        """Update the volume model's status and return it."""
        volume_model_updates = []
        LOG.info("Updating status for CG: %(id)s.",
                 {'id': cgId})
        if volumes:
            for volume in volumes:
                volume_model_updates.append({
                    'id': volume['id'],
                    'status': status,
                    'replication_status':
                        fields.ReplicationStatus.NOT_CAPABLE})
        else:
            LOG.info("No volume found for CG: %(cg)s.",
                     {'cg': cgId})
        return volume_model_updates

    def update_clean_rate(self, volume_name, new_clean_rate):
        mapping_ids = self._get_vdisk_fc_mappings(volume_name)
        for map_id in mapping_ids:
            attrs = self._get_flashcopy_mapping_attributes(map_id)
            # chfcmap should not be called for rc_controlled fcmap
            if attrs is not None and attrs['rc_controlled'] != 'yes':
                self.ssh.chfcmap(map_id,
                                 clean_rate=str(new_clean_rate))

    def check_flashcopy_rate(self, flashcopy_rate):
        if not self.code_level:
            sys_info = self.get_system_info()
            self.code_level = sys_info['code_level']

        if flashcopy_rate not in range(1, 151):
            raise exception.InvalidInput(
                reason=_('The configured flashcopy rate should be '
                         'between 1 and 150.'))
        elif self.code_level < (7, 8, 1, 0) and flashcopy_rate > 100:
            msg = (_('The configured flashcopy rate is %(fc_rate)s, The '
                     'storage code level is %(code_level)s, the flashcopy_rate'
                     ' range is 1-100 if the storwize code level '
                     'below 7.8.1.') % {'fc_rate': flashcopy_rate,
                                        'code_level': self.code_level})
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

    def update_flashcopy_rate(self, volume_name, new_flashcopy_rate):
        mapping_ids = self._get_vdisk_fc_mappings(volume_name)
        for map_id in mapping_ids:
            attrs = self._get_flashcopy_mapping_attributes(map_id)
            copy_rate = attrs['copy_rate']
            # update flashcopy rate for clone volume
            if copy_rate != '0' and attrs['rc_controlled'] != 'yes':
                self.ssh.chfcmap(map_id,
                                 copyrate=str(new_flashcopy_rate))

    def run_flashcopy(self, source, target, timeout, copy_rate,
                      clean_rate, full_copy=True, restore=False):
        """Create a FlashCopy mapping from the source to the target."""
        LOG.debug('Enter: run_flashcopy: execute FlashCopy from source '
                  '%(source)s to target %(target)s.',
                  {'source': source, 'target': target})
        self.check_flashcopy_rate(copy_rate)
        fc_map_id = self.ssh.mkfcmap(source, target, full_copy, copy_rate,
                                     clean_rate)
        self._prepare_fc_map(fc_map_id, timeout, restore)
        self.ssh.startfcmap(fc_map_id, restore)

        LOG.debug('Leave: run_flashcopy: FlashCopy started from '
                  '%(source)s to %(target)s.',
                  {'source': source, 'target': target})

    def create_flashcopy_to_consistgrp(self, source, target, consistgrp,
                                       config, opts, full_copy=False,
                                       pool=None):
        """Create a FlashCopy mapping and add to consistent group."""
        LOG.debug('Enter: create_flashcopy_to_consistgrp: create FlashCopy'
                  ' from source %(source)s to target %(target)s. '
                  'Then add the flashcopy to %(cg)s.',
                  {'source': source, 'target': target, 'cg': consistgrp})

        src_attrs = self.get_vdisk_attributes(source)
        if src_attrs is None:
            msg = (_('create_copy: Source vdisk %(src)s '
                     'does not exist.') % {'src': source})
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

        src_size = src_attrs['capacity']
        # In case we need to use a specific pool
        if not pool:
            pool = self._get_pool(src_attrs)
        if not full_copy:
            opts['rsize'] = config.storwize_svc_vol_rsize
            opts['autoexpand'] = True
        if opts and opts.get('iogrp') is None:
            opts['iogrp'] = src_attrs['IO_group_id']
        self.create_vdisk(target, src_size, 'b', pool, opts)
        if opts['qos']:
            vdisk_size = int(float(src_size) / (1 << 30))
            self.add_vdisk_qos(target, opts['qos'], vdisk_size)
        self.check_flashcopy_rate(opts['flashcopy_rate'])
        self.ssh.mkfcmap(source, target, full_copy,
                         opts['flashcopy_rate'],
                         opts['clean_rate'],
                         consistgrp=consistgrp)

        LOG.debug('Leave: create_flashcopy_to_consistgrp: '
                  'FlashCopy started from  %(source)s to %(target)s.',
                  {'source': source, 'target': target})

    def _get_pool(self, volume):
        pool = volume['mdisk_grp_name']
        if 'many' in pool:
            LOG.info("Mirror volume copy found %s: Getting volume "
                     "copies", volume['name'])
            copies = self.get_vdisk_copies(volume['name'])
            if 'primary' in copies:
                pool = copies['primary']['mdisk_grp_name']
        return pool

    def _get_vdisk_fc_mappings(self, vdisk):
        """Return FlashCopy mappings that this vdisk is associated with."""
        mapping_ids = []
        resp = self.ssh.lsvdiskfcmappings(vdisk)
        for id in resp.select('id'):
            mapping_ids.append(id)
        return mapping_ids

    def _get_flashcopy_mapping_attributes(self, fc_map_id):
        try:
            resp = self.ssh.lsfcmap(fc_map_id)
            return resp[0] if len(resp) else None
        except exception.VolumeBackendAPIException as ex:
            LOG.warning("Failed to get fcmap %(fcmap)s info. "
                        "Exception: %(ex)s.", {'fcmap': fc_map_id,
                                               'ex': ex})
            return None

    def _get_flashcopy_consistgrp_attr(self, fc_map_id):
        resp = self.ssh.lsfcconsistgrp(fc_map_id)
        if not len(resp):
            return None
        return resp[0]

    @volume_utils.trace
    def _check_delete_vdisk_fc_mappings(self, name, allow_snaps=True,
                                        allow_fctgt=False, rel_info=None):
        """FlashCopy mapping check helper."""
        mapping_ids = self._get_vdisk_fc_mappings(name)
        wait_for_copy = False
        for map_id in mapping_ids:
            attrs = self._get_flashcopy_mapping_attributes(map_id)
            # We should ignore GMCV flash copies
            # Hyperswap flash copies are also ignored.
            if not attrs or 'yes' == attrs['rc_controlled']:
                continue
            source = attrs['source_vdisk_name']
            target = attrs['target_vdisk_name']
            copy_rate = attrs['copy_rate']
            status = attrs['status']
            progress = attrs['progress']

            LOG.debug('Loopcall: source: %s, target: %s, copy_rate: %s, '
                      'status: %s, progress: %s, mapid: %s', source, target,
                      copy_rate, status, progress, map_id)
            if allow_fctgt and target == name and status == 'copying':
                try:
                    self.ssh.stopfcmap(map_id)
                except exception.VolumeBackendAPIException as ex:
                    LOG.warning(ex)
                    wait_for_copy = True
                try:
                    attrs = self._get_flashcopy_mapping_attributes(map_id)
                except exception.VolumeBackendAPIException as ex:
                    LOG.warning(ex)
                    wait_for_copy = True
                    continue
                if attrs:
                    status = attrs['status']
                else:
                    continue

            if copy_rate == '0':
                if source == name:
                    # Vdisk with snapshots. Return False if snapshot
                    # not allowed.
                    if not allow_snaps:
                        raise loopingcall.LoopingCallDone(retvalue=False)
                    self.ssh.chfcmap(map_id, copyrate='50', autodel='on')
                    wait_for_copy = True
                else:
                    # A snapshot
                    if target != name:
                        msg = (_('Vdisk %(name)s not involved in '
                                 'mapping %(src)s -> %(tgt)s.') %
                               {'name': name, 'src': source, 'tgt': target})
                        LOG.error(msg)
                        raise exception.VolumeDriverException(message=msg)
                    try:
                        if status in ['copying', 'prepared']:
                            self.ssh.stopfcmap(map_id)
                            # Need to wait for the fcmap to change to
                            # stopped state before remove fcmap
                            wait_for_copy = True
                        elif status in ['stopping', 'preparing']:
                            wait_for_copy = True
                        else:
                            self.ssh.rmfcmap(map_id)
                    except exception.VolumeBackendAPIException as ex:
                        LOG.warning(ex)
                        wait_for_copy = True
            # Case 4: Copy in progress - wait and will autodelete
            else:
                try:
                    if status == 'prepared':
                        self.ssh.stopfcmap(map_id)
                        self.ssh.rmfcmap(map_id)
                    elif status in ['idle_or_copied', 'stopped']:
                        # Prepare failed or stopped
                        self.ssh.rmfcmap(map_id)
                    elif (status in ['copying', 'prepared'] and
                          progress == '100'):
                        force = False
                        if rel_info:
                            force = True
                        self.ssh.stopfcmap(map_id, force)
                    else:
                        wait_for_copy = True
                except exception.VolumeBackendAPIException as ex:
                    LOG.warning(ex)
                    wait_for_copy = True

        if not wait_for_copy or not len(mapping_ids):
            raise loopingcall.LoopingCallDone(retvalue=True)

    @volume_utils.trace
    def _check_vdisk_fc_mappings(self, name, allow_snaps=True,
                                 allow_fctgt=False, rel_info=None):
        """FlashCopy mapping check helper."""
        # if this is a remove disk we need to be down to one fc clone
        mapping_ids = self._get_vdisk_fc_mappings(name)
        Rc_mapping_ids = []
        if len(mapping_ids) > 1 and allow_fctgt:
            LOG.debug('Loopcall: vdisk %s has '
                      'more than one fc map. Waiting.', name)
            for map_id in mapping_ids:
                attrs = self._get_flashcopy_mapping_attributes(map_id)
                if not attrs:
                    continue
                if 'yes' == attrs.get('rc_controlled', None):
                    Rc_mapping_ids.append(map_id)
                    continue

                source = attrs['source_vdisk_name']
                target = attrs['target_vdisk_name']
                copy_rate = attrs['copy_rate']
                status = attrs['status']
                progress = attrs['progress']
                LOG.debug('Loopcall: source: %s, target: %s, copy_rate: %s, '
                          'status: %s, progress: %s, mapid: %s',
                          source, target, copy_rate, status, progress, map_id)

                if copy_rate != '0' and source == name:
                    try:
                        if status in ['copying'] and progress == '100':
                            self.ssh.stopfcmap(map_id)
                        elif status == 'idle_or_copied' and progress == '100':
                            # wait for auto-delete of fcmap.
                            continue
                        elif status in ['idle_or_copied', 'stopped']:
                            # Prepare failed or stopped
                            self.ssh.rmfcmap(map_id)
                    # handle VolumeBackendAPIException to let it go through
                    # next attempts in case of any cli exception.
                    except exception.VolumeBackendAPIException as ex:
                        LOG.warning(ex)
            if len(mapping_ids) - len(Rc_mapping_ids) > 1:
                return
        return self._check_delete_vdisk_fc_mappings(
            name, allow_snaps=allow_snaps, allow_fctgt=allow_fctgt,
            rel_info=rel_info)

    def ensure_vdisk_no_fc_mappings(self, name, allow_snaps=True,
                                    allow_fctgt=False, rel_info=None):
        """Ensure vdisk has no flashcopy mappings."""
        timer = loopingcall.FixedIntervalLoopingCall(
            self._check_vdisk_fc_mappings, name,
            allow_snaps, allow_fctgt, rel_info)
        # Create a timer greenthread. The default volume service heart
        # beat is every 10 seconds. The flashcopy usually takes hours
        # before it finishes. Don't set the sleep interval shorter
        # than the heartbeat. Otherwise volume service heartbeat
        # will not be serviced.
        LOG.debug('Calling _ensure_vdisk_no_fc_mappings: vdisk %s.',
                  name)
        ret = timer.start(interval=self.check_fcmapping_interval).wait()
        timer.stop()
        return ret

    def start_relationship(self, volume_name, primary=None,
                           rcrel=None):
        if rcrel is None:
            vol_attrs = self.get_vdisk_attributes(volume_name)
            rcrel = vol_attrs['RC_name']
        self.ssh.startrcrelationship(rcrel, primary)

    def stop_relationship(self, volume_name, access=False, rcrel=None):
        if rcrel is None:
            vol_attrs = self.get_vdisk_attributes(volume_name)
            rcrel = vol_attrs['RC_name']
        self.ssh.stoprcrelationship(rcrel, access=access)

    def create_relationship(self, master, aux, system, asyncmirror,
                            cyclingmode=False, masterchange=None,
                            cycle_period_seconds=None):
        try:
            rc_id = self.ssh.mkrcrelationship(master, aux, system,
                                              asyncmirror, cyclingmode)
        except exception.VolumeBackendAPIException as ex:
            rc_id = None
            # CMMVC5959E is the code in Stowize storage, meaning that
            # there is a relationship that already has this name on the
            # master cluster.
            # pylint: disable=E1101
            if hasattr(ex, 'msg') and 'CMMVC5959E' not in ex.msg:
                # If there is no relation between the primary and the
                # secondary back-end storage, the exception is raised.
                raise
        if rc_id:
            # We need setup master and aux change volumes for gmcv
            # before we can start remote relationship
            # aux change volume must be set on target site
            rel_info = self.ssh.lsrcrelationship(rc_id)
            rc_name = rel_info[0]['name']
            if cycle_period_seconds:
                self.change_relationship_cycleperiod(master,
                                                     cycle_period_seconds,
                                                     rc_name)
            if masterchange:
                self.change_relationship_changevolume(master,
                                                      masterchange, True,
                                                      rc_name)
            else:
                self.start_relationship(master, rcrel=rc_name)
        return rc_name

    def change_relationship_changevolume(self, volume_name,
                                         change_volume, master,
                                         rcrel=None):
        if rcrel is None:
            vol_attrs = self.get_vdisk_attributes(volume_name)
            rcrel = vol_attrs['RC_name']
        if rcrel and change_volume:
            self.ssh.ch_rcrelationship_changevolume(rcrel,
                                                    change_volume,
                                                    master)

    def change_relationship_cycleperiod(self, volume_name,
                                        cycle_period_seconds,
                                        rcrel=None):
        if rcrel is None:
            vol_attrs = self.get_vdisk_attributes(volume_name)
            rcrel = vol_attrs['RC_name']
        if rcrel and cycle_period_seconds:
            self.ssh.ch_rcrelationship_cycleperiod(rcrel,
                                                   cycle_period_seconds)

    def change_relationship_cyclingmode(self, volume_name,
                                        cyclingmode='none',
                                        rcrel=None):
        if rcrel is None:
            vol_attrs = self.get_vdisk_attributes(volume_name)
            rcrel = vol_attrs['RC_name']
        if rcrel and cyclingmode:
            self.ssh.ch_rcrelationship_cyclingmode(rcrel,
                                                   cyclingmode)

    def change_consistgrp_cyclingmode(self, rccg_name,
                                      cyclingmode='none'):
        self.ssh.ch_rcconsistgrp_cyclingmode(rccg_name,
                                             cyclingmode)

    def delete_relationship(self, volume_name, rcrel=None):
        if rcrel is None:
            vol_attrs = self.get_vdisk_attributes(volume_name)
            rcrel = vol_attrs['RC_name']
        self.ssh.rmrcrelationship(rcrel, True)

    def get_relationship_info(self, volume_name):
        vol_attrs = self.get_vdisk_attributes(volume_name)
        if not vol_attrs or not vol_attrs['RC_name']:
            LOG.info("Unable to get remote copy information for "
                     "volume %s", volume_name)
            return None

        relationship = self.ssh.lsrcrelationship(vol_attrs['RC_name'])
        return relationship[0] if len(relationship) > 0 else None

    def is_replicated_volume_primary(self, volume, rel_info):
        # Return true if either source_volume is the primary volume or
        # onboarded auxiliary volume is primary [Reverse replication failover]
        if ((rel_info["master_vdisk_name"] == volume.name and
                rel_info["primary"] == "master") or
            (rel_info["master_vdisk_name"] != volume.name and
                rel_info["primary"] == "aux")):
            return True
        return False

    def get_target_volume_information(self, source_volume):
        source_volume_name = source_volume.name
        rel_info = self.get_relationship_info(source_volume_name)
        if rel_info:
            if source_volume_name == rel_info["aux_vdisk_name"]:
                target_volume = rel_info["master_vdisk_name"]
            else:
                target_volume = rel_info["aux_vdisk_name"]
        else:
            # Retrieving target volume based on Source volume name, if
            # relationship not exists.
            if source_volume_name[:4] == storwize_const.REPLICA_AUX_VOL_PREFIX:
                target_volume = source_volume_name[4:]
            else:
                target_volume = (storwize_const.REPLICA_AUX_VOL_PREFIX +
                                 source_volume_name)
        return (target_volume, rel_info)

    def delete_rc_volume(self, volume_name, rel_info=None,
                         target_vol=False, force_unmap=True,
                         retain_aux_volume=False):
        try:
            # If relationship exists, will delete the relationship.
            if rel_info:
                self.delete_relationship(volume_name,
                                         rcrel=rel_info['name'])
            # Delete change volume
            self.delete_vdisk(
                storwize_const.REPLICA_CHG_VOL_PREFIX + volume_name,
                force_unmap=force_unmap,
                force_delete=False)
            # We want to retain/remove the secondary volume after retyping of
            # primary volume from mirror to non-mirror storage template
            # or on the delete of the primary volume based on user's
            # choice of config value for storwize_svc_retain_aux_volume.
            # The default value is False.
            if (not retain_aux_volume and target_vol) or not target_vol:
                self.delete_vdisk(volume_name,
                                  force_unmap=force_unmap,
                                  force_delete=False)
        except Exception as e:
            msg = (_('Unable to delete the volume for '
                     'volume %(vol)s. Exception: %(err)s.'),
                   {'vol': volume_name, 'err': e})
            LOG.exception(msg)
            raise exception.VolumeDriverException(message=msg)

    def switch_relationship(self, relationship, aux=True):
        self.ssh.switchrelationship(relationship, aux)

    # replication cg
    def chrcrelationship(self, relationship, rccg=None):
        rels = self.ssh.lsrcrelationship(relationship)[0]
        if rccg and rels['consistency_group_name'] == rccg:
            LOG.info('relationship %(rel)s is aleady added to group %(grp)s.',
                     {'rel': relationship, 'grp': rccg})
            return
        if not rccg and rels['consistency_group_name'] == '':
            LOG.info('relationship %(rel)s is aleady removed from group',
                     {'rel': relationship})
            return
        self.ssh.chrcrelationship(relationship, rccg)

    def get_rccg(self, rccg):
        return self.ssh.lsrcconsistgrp(rccg)

    def create_rccg(self, rccg, system):
        self.ssh.mkrcconsistgrp(rccg, system)

    def delete_rccg(self, rccg):
        if self.ssh.lsrcconsistgrp(rccg):
            self.ssh.rmrcconsistgrp(rccg)

    def start_rccg(self, rccg, primary=None):
        self.ssh.startrcconsistgrp(rccg, primary)

    def stop_rccg(self, rccg, access=False):
        self.ssh.stoprcconsistgrp(rccg, access)

    def get_rccg_info(self, volume_name):
        vol_attrs = self.get_vdisk_attributes(volume_name)
        if not vol_attrs or not vol_attrs['RC_name']:
            LOG.warning("Unable to get remote copy information for "
                        "volume %s", volume_name)
            return None

        rcrel = self.ssh.lsrcrelationship(vol_attrs['RC_name'])
        if len(rcrel) > 0 and rcrel[0]['consistency_group_name']:
            return self.ssh.lsrcconsistgrp(rcrel[0]['consistency_group_name'])
        else:
            return None

    def get_rccg_name_by_volume_name(self, volume_name):
        vol_attrs = self.get_vdisk_attributes(volume_name)
        if not vol_attrs:
            LOG.warning("Unable to get volume attributes for "
                        "volume %s", volume_name)
            return None

        rcrel = self.ssh.lsrcrelationship(vol_attrs['RC_name'])
        if len(rcrel) > 0 and rcrel[0].get('consistency_group_name'):
            return rcrel[0]['consistency_group_name']
        else:
            return None

    def create_volumegroup(self, volumegroup_name):
        self.ssh.mkvolumegroup(volumegroup_name)

    def get_volumegroup(self, volumegroup_id_or_name):
        vg = self.ssh.lsvolumegroup(volumegroup_id_or_name)
        return vg if len(vg) > 0 else None

    def delete_volumegroup(self, volumegroup_id_or_name):
        if self.ssh.lsvolumegroup(volumegroup_id_or_name):
            self.ssh.rmvolumegroup(volumegroup_id_or_name)

    def add_vdisk_to_volumegroup(self, vol_name, volumegroup_id):
        self.ssh.chvdisk(vol_name, ['-volumegroup', volumegroup_id])

    def remove_vdisk_from_volumegroup(self, vol_name):
        self.ssh.chvdisk(vol_name, ['-novolumegroup'])

    def check_codelevel_for_volumegroup(self, code_level):
        if not (code_level >= (8, 5, 1, 0)):
            msg = (_('The configured group type spec is '
                     '"volume_group_enabled". '
                     'The supported code level for this group type spec '
                     'is 8.5.1.0 '
                     'The current storage code level is %(code_level)s.')
                   % {'code_level': code_level})
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

    def create_volumegroup_snapshot(self, params):
        self.ssh.addsnapshot(params)

    def is_volumegroup_snapshot_exists(self, params):
        """Check if volumegroup snapshot exists."""
        attrs = self.ssh.lsvolumegroupsnapshot(params)
        return attrs is not None

    def delete_volumegroup_snapshot(self, params):
        """Delete volumegroup snapshot"""
        if not self.is_volumegroup_snapshot_exists(params):
            LOG.info('Tried to delete non-existent volumegroup snapshot.')
            return
        self.ssh.rmsnapshot(params)

    def get_volume_name_from_metadata(self, volume):
        """Get Volume name from metadata if metadata exists"""
        if volume.metadata:
            svc_volume_name = volume.metadata.get("Volume Name", None)
            if svc_volume_name:
                LOG.info('Volume %(cinder_id)s in cinder API is linked to '
                         'volume_name %(svc_volume_name)s in SVC',
                         {'cinder_id': volume.name,
                          'svc_volume_name': svc_volume_name})
                volume.name_id = svc_volume_name.split("-", 1)[1]
        return volume

    def get_partnership_info(self, system_name):
        partnership = self.ssh.lspartnership(system_name)
        return partnership[0] if len(partnership) > 0 else None

    def get_partnershipcandidate_info(self, system_name):
        candidates = self.ssh.lspartnershipcandidate()
        for candidate in candidates:
            if system_name == candidate['name']:
                return candidate
        return None

    def mkippartnership(self, ip_v4, bandwidth=1000, copyrate=50):
        self.ssh.mkippartnership(ip_v4, bandwidth, copyrate)

    def mkfcpartnership(self, system_name, bandwidth=1000, copyrate=50):
        self.ssh.mkfcpartnership(system_name, bandwidth, copyrate)

    def chpartnership(self, partnership_id):
        self.ssh.chpartnership(partnership_id)

    def delete_vdisk(self, vdisk, force_unmap, force_delete):
        """Ensures that vdisk is not part of FC mapping and deletes it."""
        LOG.debug('Enter: delete_vdisk: vdisk %s.', vdisk)
        if not self.is_vdisk_defined(vdisk):
            LOG.info('Tried to delete non-existent vdisk %s.', vdisk)
            return
        self.ensure_vdisk_no_fc_mappings(vdisk, allow_snaps=True,
                                         allow_fctgt=True)
        self.ssh.rmvdisk(vdisk,
                         force_unmap=force_unmap,
                         force_delete=force_delete)
        LOG.debug('Leave: delete_vdisk: vdisk %s.', vdisk)

    def create_copy(self, src, tgt, src_id, config, opts,
                    full_copy, state, pool=None):
        """Create a new snapshot using FlashCopy."""
        LOG.debug('Enter: create_copy: snapshot %(src)s to %(tgt)s.',
                  {'tgt': tgt, 'src': src})

        src_attrs = self.get_vdisk_attributes(src)
        if src_attrs is None:
            msg = (_('create_copy: Source vdisk %(src)s (%(src_id)s) '
                     'does not exist.') % {'src': src, 'src_id': src_id})
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

        src_size = src_attrs['capacity']
        # In case we need to use a specific pool
        if not pool:
            pool = src_attrs['mdisk_grp_name']

        opts['iogrp'] = self.select_io_group(state, opts, pool)
        self.create_vdisk(tgt, src_size, 'b', pool, opts)
        timeout = config.storwize_svc_flashcopy_timeout
        try:
            self.run_flashcopy(src, tgt, timeout,
                               opts['flashcopy_rate'],
                               opts['clean_rate'],
                               full_copy=full_copy)
        except Exception:
            with excutils.save_and_reraise_exception():
                self.delete_vdisk(tgt, force_unmap=False, force_delete=True)

        LOG.debug('Leave: _create_copy: snapshot %(tgt)s from '
                  'vdisk %(src)s.',
                  {'tgt': tgt, 'src': src})

    def extend_vdisk(self, vdisk, amount):
        self.ssh.expandvdisksize(vdisk, amount)

    def add_vdisk_copy(self, vdisk, dest_pool, volume_type, state, config,
                       auto_delete=False):
        """Add a vdisk copy in the given pool."""
        resp = self.ssh.lsvdiskcopy(vdisk)
        if len(resp) > 1:
            msg = (_('add_vdisk_copy failed: A copy of volume %s exists. '
                     'Adding another copy would exceed the limit of '
                     '2 copies.') % vdisk)
            raise exception.VolumeDriverException(message=msg)
        orig_copy_id = resp[0].get("copy_id", None)

        if orig_copy_id is None:
            msg = (_('add_vdisk_copy started without a vdisk copy in the '
                     'expected pool.'))
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

        if volume_type is None:
            opts = self.get_vdisk_params(config, state, None)
        else:
            opts = self.get_vdisk_params(config, state, volume_type['id'],
                                         volume_type=volume_type)
        is_dr_pool = self.is_data_reduction_pool(dest_pool)
        if is_dr_pool and opts['rsize'] != -1:
            self.check_data_reduction_pool_params(opts)
        params = self._get_vdisk_create_params(opts, is_dr_pool)
        try:
            new_copy_id = self.ssh.addvdiskcopy(vdisk, dest_pool, params,
                                                auto_delete)
        except exception.VolumeBackendAPIException as e:
            msg = (_('Unable to add vdiskcopy for volume %(vol)s. '
                     'Exception: %(err)s.'),
                   {'vol': vdisk, 'err': e})
            LOG.exception(msg)
            raise exception.VolumeDriverException(message=msg)
        return (orig_copy_id, new_copy_id)

    def is_vdisk_copy_synced(self, vdisk, copy_id):
        sync = self.ssh.lsvdiskcopy(vdisk, copy_id=copy_id)[0]['sync']
        if sync == 'yes':
            return True
        return False

    def rm_vdisk_copy(self, vdisk, copy_id):
        self.ssh.rmvdiskcopy(vdisk, copy_id)

    def lsvdiskcopy(self, vdisk, copy_id=None):
        return self.ssh.lsvdiskcopy(vdisk, copy_id)

    @staticmethod
    def can_migrate_to_host(host, state):
        if 'location_info' not in host['capabilities']:
            return None
        info = host['capabilities']['location_info']
        try:
            (dest_type, dest_id, dest_pool) = info.split(':')
        except ValueError:
            return None
        if (dest_type != 'StorwizeSVCDriver' or dest_id != state['system_id']):
            return None
        return dest_pool

    def add_vdisk_qos(self, vdisk, qos, vdisk_size):
        """Add the QoS configuration to the volume."""
        for key, value in qos.items():
            if key in self.svc_qos and key == "IOThrottling":
                param = self.svc_qos[key]['param']
                if storwize_const.IOPS_PER_GB in qos.values():
                    value = value * vdisk_size
                    if not int(value):
                        value = 1
                vdisk_params = ['-' + param, str(int(value))]
                # Add -unitmb param to the chvdisk if qos:IOThrottling_unit
                # is added in extra specs
                key_unit = self.svc_qos[key].get('unit', None)
                if key_unit in qos:
                    key_unit_param = qos.get(key_unit)
                    if (key_unit_param and
                            key_unit_param == storwize_const.MBPS):
                        t_val = '-' + self.svc_qos[key_unit][key_unit_param]
                        vdisk_params.append(t_val)
                self.ssh.chvdisk(vdisk, vdisk_params)

    def update_vdisk_qos(self, vdisk, qos, vdisk_size):
        """Update all the QoS in terms of a key and value.

        svc_qos saves all the supported QoS parameters. Going through
        this dict, we set the new values to all the parameters. If QoS is
        available in the QoS configuration, the value is taken from it;
        if not, the value will be set to default.
        """
        iothrottling = 'IOThrottling'
        if iothrottling in qos:
            throttling_value = qos[iothrottling]
            key_unit = self.svc_qos[iothrottling]['unit']
            throttling_unit = qos[key_unit]

            # check if throttling unit specified is in allowed units
            # if not allowed - we will go with default unit - iops
            param = self.svc_qos[iothrottling]['param']
            unit_param = self.svc_qos[key_unit][storwize_const.MBPS]
            default_throttling_value = self.svc_qos[iothrottling]['default']
            if throttling_unit in self.svc_qos[key_unit]:
                # check if specified throttling unit is not the default unit
                # if not default unit - specify the parameter for the
                # special unit
                if throttling_unit == storwize_const.MBPS:
                    # Uppdating vdisk_params to disable iops limit and
                    # enable only bandwidth limit - in mbps
                    # disable iops
                    disable_vdisk_params = ['-' + param,
                                            default_throttling_value]
                    # enable mbps
                    enable_vdisk_params = ['-' + param,
                                           str(int(throttling_value)),
                                           '-' + unit_param]
                else:
                    # This means that we have to disable mbps limit (bandwidth)
                    # and enable iops limit
                    if throttling_unit == storwize_const.IOPS_PER_GB:
                        throttling_value = throttling_value * vdisk_size
                    # disable mbps
                    disable_vdisk_params = ['-' + param,
                                            default_throttling_value,
                                            '-' + unit_param]
                    # enable iops
                    enable_vdisk_params = ['-' + param,
                                           str(int(throttling_value))]
            # Disable conditional vdisk_params
            self.ssh.chvdisk(vdisk, disable_vdisk_params)
            # Enable conditional vdisk_params
            self.ssh.chvdisk(vdisk, enable_vdisk_params)

    def disable_vdisk_qos(self, vdisk, qos):
        """Disable the QoS."""
        for key, value in qos.items():
            if key in self.svc_qos and key == 'IOThrottling':
                # qos of previous volume type is in format:
                # qos - {'IOThrottling': 1000, 'IOThrottling_unit': 'iops'}
                param = self.svc_qos[key]['param']
                vdisk_params = ['-' + param, self.svc_qos[key]['default']]
                # clear out iops limit
                self.ssh.chvdisk(vdisk, vdisk_params)
                vdisk_params.append(
                    '-' + self.svc_qos['IOThrottling_unit']['mbps'])
                # clear out mbps limit
                self.ssh.chvdisk(vdisk, vdisk_params)

    def change_vdisk_options(self, vdisk, changes, opts, state):
        change_value = {'warning': '', 'easytier': '', 'autoexpand': ''}
        if 'warning' in opts:
            change_value['warning'] = '%s%%' % str(opts['warning'])
        if 'easytier' in opts:
            change_value['easytier'] = 'on' if opts['easytier'] else 'off'
        if 'autoexpand' in opts:
            change_value['autoexpand'] = 'on' if opts['autoexpand'] else 'off'

        for key in changes:
            self.ssh.chvdisk(vdisk, ['-' + key, change_value[key]])

    def change_vdisk_iogrp(self, vdisk, state, iogrp):
        if state['code_level'] < (6, 4, 0, 0):
            LOG.debug('Ignore change IO group as storage code level is '
                      '%(code_level)s, below the required 6.4.0.0.',
                      {'code_level': state['code_level']})
        else:
            self.ssh.addvdiskaccess(vdisk, str(iogrp[0]))
            try:
                self.ssh.movevdisk(vdisk, str(iogrp[0]))
            except exception.VolumeBackendAPIException as e:
                self.ssh.rmvdiskaccess(vdisk, str(iogrp[0]))
                msg = (_('movevdisk command failed for %(vdisk),'
                         'performing rmdiskaccess for %(iogrp)s.'
                         'Exception: %(err)s.'),
                       {'vdisk': vdisk, 'iogrp': iogrp[0], 'err': e})
                LOG.exception(msg)
                raise exception.VolumeBackendAPIException(data=msg)
            self.ssh.rmvdiskaccess(vdisk, str(iogrp[1]))

    def vdisk_by_uid(self, vdisk_uid):
        """Returns the properties of the vdisk with the specified UID.

        Returns None if no such disk exists.
        """

        vdisks = self.ssh.lsvdisks_from_filter('vdisk_UID', vdisk_uid)

        if len(vdisks) == 0:
            return None

        if len(vdisks) != 1:
            msg = (_('Expected single vdisk returned from lsvdisk when '
                     'filtering on vdisk_UID.  %(count)s were returned.') %
                   {'count': len(vdisks)})
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

        vdisk = vdisks.result[0]

        return self.ssh.lsvdisk(vdisk['name'])

    def is_vdisk_in_use(self, vdisk):
        """Returns True if the specified vdisk is mapped to at least 1 host."""
        resp = self.ssh.lsvdiskhostmap(vdisk)
        return len(resp) != 0

    def rename_vdisk(self, vdisk, new_name):
        self.ssh.chvdisk(vdisk, ['-name', new_name])

    def migratevdisk(self, vdisk, dest_pool, copy_id='0'):
        self.ssh.migratevdisk(vdisk, dest_pool, copy_id)

    def is_system_topology_hyperswap(self, state):
        """Returns True if the system version higher than 7.5 and the system

        topology is hyperswap.
        """
        if state['code_level'] < (7, 6, 0, 0):
            LOG.debug('Hyperswap failure as the storage '
                      'code_level is %(code_level)s, below '
                      'the required 7.6.0.0.',
                      {'code_level': state['code_level']})
        else:
            if state['topology'] == 'hyperswap':
                return True
            else:
                LOG.debug('Hyperswap failure as the storage system '
                          'topology is not hyperswap.')
        return False

    def check_hyperswap_pool(self, pool, peer_pool):
        # Check the hyperswap pools.
        if not peer_pool:
            raise exception.InvalidInput(
                reason=_('The peer pool is necessary for hyperswap volume, '
                         'please configure the peer pool.'))
        pool_attr = None
        peer_pool_attr = None
        for stat_pool in self.stats.get('pools', []):
            if stat_pool['pool_name'] == pool:
                pool_attr = stat_pool
            elif stat_pool['pool_name'] == peer_pool:
                peer_pool_attr = stat_pool

        if pool_attr is None:
            pool_attr = self.get_pool_attrs(pool)
        if peer_pool_attr is None:
            peer_pool_attr = self.get_pool_attrs(peer_pool)

        if not peer_pool_attr:
            raise exception.InvalidInput(
                reason=_('The hyperswap peer pool %s '
                         'is invalid.') % peer_pool)

        if not pool_attr['site_id'] or not peer_pool_attr['site_id']:
            raise exception.InvalidInput(
                reason=_('The site_id of pools is necessary for hyperswap '
                         'volume, but there is no site_id in the pool or '
                         'peer pool.'))

        if pool_attr['site_id'] == peer_pool_attr['site_id']:
            raise exception.InvalidInput(
                reason=_('The hyperswap volume must be configured in two '
                         'independent sites, the pool %(pool)s is on the '
                         'same site as peer_pool %(peer_pool)s. ') %
                {'pool': pool, 'peer_pool': peer_pool})

    def pretreatment_before_revert(self, name):
        mapping_ids = self._get_vdisk_fc_mappings(name)
        for map_id in mapping_ids:
            attrs = self._get_flashcopy_mapping_attributes(map_id)
            if not attrs:
                continue
            target = attrs['target_vdisk_name']
            copy_rate = attrs['copy_rate']
            progress = attrs['progress']
            status = attrs['status']
            if status in ['copying', 'prepared'] and target == name:
                if copy_rate != '0' and progress != '100':
                    msg = (_('Cannot start revert since fcmap %(map_id)s '
                             'in progress, current progress is %(progress)s')
                           % {'map_id': map_id, 'progress': progress})
                    LOG.error(msg)
                    raise exception.VolumeDriverException(message=msg)
                elif copy_rate != '0' and progress == '100':
                    LOG.debug('Split completed clone map_id=%(map_id)s fcmap',
                              {'map_id': map_id})
                    self.ssh.stopfcmap(map_id)


class CLIResponse(object):
    """Parse SVC CLI output and generate iterable."""

    def __init__(self, raw, ssh_cmd=None, delim='!', with_header=True):
        super(CLIResponse, self).__init__()
        if ssh_cmd:
            self.ssh_cmd = ' '.join(ssh_cmd)
        else:
            self.ssh_cmd = 'None'
        self.raw = raw
        self.delim = delim
        self.with_header = with_header
        self.result = self._parse()

    def select(self, *keys):
        for a in self.result:
            vs = []
            for k in keys:
                v = a.get(k, None)
                if isinstance(v, str) or v is None:
                    v = [v]
                if isinstance(v, list):
                    vs.append(v)
            for item in zip(*vs):
                if len(item) == 1:
                    yield item[0]
                else:
                    yield item

    def __getitem__(self, key):
        try:
            return self.result[key]
        except KeyError:
            msg = (_('Did not find the expected key %(key)s in %(fun)s: '
                     '%(raw)s.') % {'key': key, 'fun': self.ssh_cmd,
                                    'raw': self.raw})
            raise exception.VolumeBackendAPIException(data=msg)

    def __iter__(self):
        for a in self.result:
            yield a

    def __len__(self):
        return len(self.result)

    def _parse(self):
        def get_reader(content, delim):
            for line in content.lstrip().splitlines():
                line = line.strip()
                if line:
                    yield line.split(delim)
                else:
                    yield []

        if isinstance(self.raw, str):
            stdout, stderr = self.raw, ''
        else:
            stdout, stderr = self.raw
        reader = get_reader(stdout, self.delim)
        result = []

        if self.with_header:
            hds = tuple()
            for row in reader:
                hds = row
                break
            for row in reader:
                cur = dict()
                if len(hds) != len(row):
                    msg = (_('Unexpected CLI response: header/row mismatch. '
                             'header: %(header)s, row: %(row)s.')
                           % {'header': hds,
                              'row': row})
                    raise exception.VolumeBackendAPIException(data=msg)
                for k, v in zip(hds, row):
                    CLIResponse.append_dict(cur, k, v)
                result.append(cur)
        else:
            cur = dict()
            for row in reader:
                if row:
                    CLIResponse.append_dict(cur, row[0], ' '.join(row[1:]))
                elif cur:  # start new section
                    result.append(cur)
                    cur = dict()
            if cur:
                result.append(cur)
        return result

    @staticmethod
    def append_dict(dict_, key, value):
        key, value = key.strip(), value.strip()
        obj = dict_.get(key, None)
        if obj is None:
            dict_[key] = value
        elif isinstance(obj, list):
            obj.append(value)
            dict_[key] = obj
        else:
            dict_[key] = [obj, value]
        return dict_


class StorwizeSVCCommonDriver(san.SanDriver,
                              driver.ManageableVD,
                              driver.MigrateVD,
                              driver.CloneableImageVD):
    """IBM Storwize V7000 SVC abstract base class for iSCSI/FC volume drivers.

    Version history:

    .. code-block:: none

        1.0 - Initial driver
        1.1 - FC support, create_cloned_volume, volume type support,
              get_volume_stats, minor bug fixes
        1.2.0 - Added retype
        1.2.1 - Code refactor, improved exception handling
        1.2.2 - Fix bug #1274123 (races in host-related functions)
        1.2.3 - Fix Fibre Channel connectivity: bug #1279758 (add delim
                to lsfabric, clear unused data from connections, ensure
                matching WWPNs by comparing lower case
        1.2.4 - Fix bug #1278035 (async migration/retype)
        1.2.5 - Added support for manage_existing (unmanage is inherited)
        1.2.6 - Added QoS support in terms of I/O throttling rate
        1.3.1 - Added support for volume replication
        1.3.2 - Added support for consistency group
        1.3.3 - Update driver to use ABC metaclasses
        2.0 - Code refactor, split init file and placed shared methods
              for FC and iSCSI within the StorwizeSVCCommonDriver class
        2.1 - Added replication V2 support to the global/metro mirror
              mode
        2.1.1 - Update replication to version 2.1
        2.1.2 - Added support volume_group (Flash copy)
    """

    VERSION = "2.1.2"
    VDISKCOPYOPS_INTERVAL = 600
    DEFAULT_GR_SLEEP = random.randint(20, 500) / 100.0

    def __init__(self, *args, **kwargs):
        super(StorwizeSVCCommonDriver, self).__init__(*args, **kwargs)
        self.configuration.append_config_values(storwize_svc_opts)
        self._backend_name = self.configuration.safe_get('volume_backend_name')
        self.active_ip = self.configuration.san_ip
        self.inactive_ip = self.configuration.storwize_san_secondary_ip
        self._master_backend_helpers = StorwizeHelpers(self._run_ssh)
        self._aux_backend_helpers = None
        self._helpers = self._master_backend_helpers
        self._vdiskcopyops = {}
        self._vdiskcopyops_loop = None
        self.protocol = None
        self._storwize_portset = self.configuration.storwize_portset
        self._master_state = {'storage_nodes': {},
                              'enabled_protocols': set(),
                              'compression_enabled': False,
                              'available_iogrps': [],
                              'system_name': None,
                              'system_id': None,
                              'code_level': None,
                              }
        self._state = self._master_state
        self._aux_state = {'storage_nodes': {},
                           'enabled_protocols': set(),
                           'compression_enabled': False,
                           'available_iogrps': [],
                           'system_name': None,
                           'system_id': None,
                           'code_level': None,
                           }
        self._active_backend_id = kwargs.get('active_backend_id')

        # This list is used to ensure volume export
        self._volumes_list = []

        # This dictionary is used to map each replication target to certain
        # replication manager object.
        self.replica_manager = {}

        # One driver can be configured with only one replication target
        # to failover.
        self._replica_target = {}

        # This boolean is used to indicate whether replication is supported
        # by this storage.
        self._replica_enabled = False

        # This list is used to save the supported replication modes.
        self._supported_replica_types = []

        # This is used to save the available pools in failed-over status
        self._secondary_pools = None

        # This dictionary is used to save pools information.
        self._stats = {}

        # Storwize has the limitation that can not burst more than 3 new ssh
        # connections within 1 second. So slow down the initialization.
        time.sleep(1)

    def do_setup(self, ctxt):
        """Check that we have all configuration details from the storage."""
        LOG.debug('enter: do_setup')

        # v2.1 replication setup
        self._get_storwize_config()

        # Validate that the pool exists
        self._validate_pools_exist()

        # Get list of all volumes
        self._get_all_volumes()

        # Update the pool stats
        self._update_volume_stats()

        # Save the pool stats information in helpers class.
        self._master_backend_helpers.stats = self._stats

        # Build the list of in-progress vdisk copy operations
        if ctxt is None:
            admin_context = context.get_admin_context()
        else:
            admin_context = ctxt.elevated()
        volumes = objects.VolumeList.get_all_by_host(admin_context, self.host)

        for volume in volumes:
            metadata = volume.admin_metadata
            curr_ops = metadata.get('vdiskcopyops', None)
            if curr_ops:
                ops = [tuple(x.split(':')) for x in curr_ops.split(';')]
                self._vdiskcopyops[volume['id']] = ops

        # if vdiskcopy exists in database, start the looping call
        if len(self._vdiskcopyops) >= 1:
            self._vdiskcopyops_loop = loopingcall.FixedIntervalLoopingCall(
                self._check_volume_copy_ops)
            self._vdiskcopyops_loop.start(interval=self.VDISKCOPYOPS_INTERVAL)
        LOG.debug('leave: do_setup')

    def _update_storwize_state(self, state, helper):
        # Get storage system name, id, and code level
        state.update(helper.get_system_info())

        # Check if compression is supported
        state['compression_enabled'] = helper.compression_enabled()

        # Get the available I/O groups
        state['available_iogrps'] = helper.get_available_io_groups()

        # Get the iSCSI and FC names of the Storwize/SVC nodes
        state['storage_nodes'] = helper.get_node_info()

        # Add the iSCSI IP addresses and WWPNs to the storage node info
        helper.add_iscsi_ip_addrs(state['storage_nodes'], state['code_level'],
                                  portset=self._storwize_portset)
        helper.add_fc_wwpns(state['storage_nodes'], state['code_level'])

        # For each node, check what connection modes it supports.  Delete any
        # nodes that do not support any types (may be partially configured).
        to_delete = []
        for k, node in state['storage_nodes'].items():
            if ((len(node['ipv4']) or len(node['ipv6']) or
                    len(node['IP_address']))
                    and len(node['iscsi_name'])):
                node['enabled_protocols'].append('iSCSI')
                state['enabled_protocols'].add('iSCSI')
            if len(node['WWPN']):
                node['enabled_protocols'].append('FC')
                state['enabled_protocols'].add('FC')
            if not len(node['enabled_protocols']):
                to_delete.append(k)
        for delkey in to_delete:
            del state['storage_nodes'][delkey]

    def _get_backend_pools(self):
        if not self._active_backend_id:
            return self.configuration.storwize_svc_volpool_name
        elif not self._secondary_pools:
            self._secondary_pools = [self._replica_target.get('pool_name')]
        return self._secondary_pools

    def _get_backend_peer_pool(self):
        if not self._active_backend_id:
            return self.configuration.storwize_peer_pool

    def _validate_pools_exist(self):
        # Validate that the pool exists
        pools = self._get_backend_pools()
        for pool in pools:
            if not self._helpers.is_pool_defined(pool):
                reason = (_('Failed getting details for pool %s.') % pool)
                raise exception.InvalidInput(reason=reason)

    def _get_all_volumes(self):
        # Get list of all volumes
        pools = self._get_backend_pools()
        for pool in pools:
            pool_vols = self._helpers.get_pool_volumes(pool)
            for volume in pool_vols:
                self._volumes_list.append(volume['name'])

    def check_for_setup_error(self):
        """Ensure that the flags are set properly."""
        LOG.debug('enter: check_for_setup_error')

        # Check that we have the system ID information
        if self._state['system_name'] is None:
            exception_msg = (_('Unable to determine system name.'))
            raise exception.VolumeBackendAPIException(data=exception_msg)
        if self._state['system_id'] is None:
            exception_msg = (_('Unable to determine system id.'))
            raise exception.VolumeBackendAPIException(data=exception_msg)

        # Make sure we have at least one node configured
        if not len(self._state['storage_nodes']):
            msg = _('do_setup: No configured nodes.')
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

        if self.protocol not in self._state['enabled_protocols']:
            # TODO(mc_nair): improve this error message by looking at
            # self._state['enabled_protocols'] to tell user what driver to use
            raise exception.InvalidInput(
                reason=_('The storage device does not support %(prot)s. '
                         'Please configure the device to support %(prot)s or '
                         'switch to a driver using a different protocol.')
                % {'prot': self.protocol})

        required_flags = ['san_ip', 'san_ssh_port', 'san_login',
                          'storwize_svc_volpool_name']
        for flag in required_flags:
            if not self.configuration.safe_get(flag):
                raise exception.InvalidInput(reason=_('%s is not set.') % flag)

        # Ensure that either password or keyfile were set
        if not (self.configuration.san_password or
                self.configuration.san_private_key):
            raise exception.InvalidInput(
                reason=_('Password or SSH private key is required for '
                         'authentication: set either san_password or '
                         'san_private_key option.'))

        opts = self._helpers.build_default_opts(self.configuration)
        self._helpers.check_vdisk_opts(self._state, opts)

        LOG.debug('leave: check_for_setup_error')

    def _run_ssh(self, cmd_list, check_exit_code=True, attempts=1):
        cinder_utils.check_ssh_injection(cmd_list)
        command = ' '.join(cmd_list)
        if not self.sshpool:
            try:
                self.sshpool = self._set_up_sshpool(self.active_ip)
            except paramiko.SSHException:
                LOG.warning('Unable to use san_ip to create SSHPool. Now '
                            'attempting to use storwize_san_secondary_ip '
                            'to create SSHPool.')
                if self._toggle_ip():
                    self.sshpool = self._set_up_sshpool(self.active_ip)
                else:
                    LOG.warning('Unable to create SSHPool using san_ip '
                                'and not able to use '
                                'storwize_san_secondary_ip since it is '
                                'not configured.')
                    raise
        try:
            return self._ssh_execute(self.sshpool, command,
                                     check_exit_code, attempts)

        except Exception:
            # Need to check if creating an SSHPool storwize_san_secondary_ip
            # before raising an error.
            try:
                if self._toggle_ip():
                    LOG.warning("Unable to execute SSH command with "
                                "%(inactive)s. Attempting to execute SSH "
                                "command with %(active)s.",
                                {'inactive': self.inactive_ip,
                                 'active': self.active_ip})
                    self.sshpool = self._set_up_sshpool(self.active_ip)
                    return self._ssh_execute(self.sshpool, command,
                                             check_exit_code, attempts)
                else:
                    LOG.warning('Not able to use '
                                'storwize_san_secondary_ip since it is '
                                'not configured.')
                    raise
            except Exception:
                with excutils.save_and_reraise_exception():
                    LOG.error("Error running SSH command: %s",
                              command)

    def _set_up_sshpool(self, ip):
        password = self.configuration.san_password
        privatekey = self.configuration.san_private_key
        min_size = self.configuration.ssh_min_pool_conn
        max_size = self.configuration.ssh_max_pool_conn
        sshpool = ssh_utils.SSHPool(
            ip,
            self.configuration.san_ssh_port,
            self.configuration.ssh_conn_timeout,
            self.configuration.san_login,
            password=password,
            privatekey=privatekey,
            min_size=min_size,
            max_size=max_size)

        return sshpool

    def _ssh_execute(self, sshpool, command,
                     check_exit_code=True, attempts=1):
        try:
            with sshpool.item() as ssh:
                while attempts > 0:
                    attempts -= 1
                    try:
                        return processutils.ssh_execute(
                            ssh,
                            command,
                            check_exit_code=check_exit_code,
                            sanitize_stdout=False)
                    except Exception as e:
                        LOG.error('Error has occurred: %s', e)
                        last_exception = e
                        greenthread.sleep(self.DEFAULT_GR_SLEEP)
                    try:
                        std_err = last_exception.stderr
                        if std_err is not None and not self._is_ascii(std_err):
                            std_err = encodeutils.safe_decode(std_err,
                                                              errors='ignore')
                            LOG.error("The stderr has non-ascii characters. "
                                      "Please check the error code.\n"
                                      "Stderr: %s", std_err)
                            std_err = std_err.split()[0]
                        raise processutils.ProcessExecutionError(
                            exit_code=last_exception.exit_code,
                            stdout=last_exception.stdout,
                            stderr=std_err,
                            cmd=last_exception.cmd)
                    except AttributeError:
                        raise processutils.ProcessExecutionError(
                            exit_code=-1,
                            stdout="",
                            stderr="Error running SSH command",
                            cmd=command)

        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.error("Error running SSH command: %s", command)

    def _is_ascii(self, value):
        try:
            return all(ord(c) < 128 for c in value)
        except TypeError:
            return False

    def _toggle_ip(self):
        # Change active_ip if storwize_san_secondary_ip is set.
        if self.configuration.storwize_san_secondary_ip is None:
            return False

        self.inactive_ip, self.active_ip = self.active_ip, self.inactive_ip
        LOG.info('Toggle active_ip from %(old)s to %(new)s.',
                 {'old': self.inactive_ip,
                  'new': self.active_ip})
        return True

    def ensure_export(self, ctxt, volume):
        """Check that the volume exists on the storage.

        The system does not "export" volumes as a Linux iSCSI target does,
        and therefore we just check that the volume exists on the storage.
        """
        volume_defined = volume['name'] in self._volumes_list

        if not volume_defined:
            LOG.error('ensure_export: Volume %s not found on storage.',
                      volume['name'])

    def create_export(self, ctxt, volume, connector):
        model_update = None
        return model_update

    def remove_export(self, ctxt, volume):
        pass

    def create_export_snapshot(self, ctxt, snapshot, connector):
        model_update = None
        return model_update

    def remove_export_snapshot(self, ctxt, snapshot):
        pass

    def _get_vdisk_params(self, type_id, volume_type=None,
                          volume_metadata=None):
        return self._helpers.get_vdisk_params(self.configuration,
                                              self._state, type_id,
                                              volume_type=volume_type,
                                              volume_metadata=volume_metadata)

    def _check_if_group_type_cg_snapshot(self, volume):
        if (volume.group_id and
                (not volume_utils.is_group_a_cg_snapshot_type(volume.group) and
                 not volume_utils.is_group_a_type
                 (volume.group, "consistent_group_replication_enabled"))):
            msg = _('Create volume with a replication or hyperswap '
                    'group_id is not supported. Please add volume to '
                    'group after volume creation.')
            LOG.error(msg)
            raise exception.VolumeDriverException(reason=msg)

    def _update_replication_properties(self, ctxt, volume, model_update):

        @cinder_utils.retry(exception.VolumeBackendAPIException,
                            interval=2,
                            retries=3)
        def _try_get_relationship_info(volume_name):
            try:
                rel_info = self._helpers.get_relationship_info(volume_name)
                return rel_info
            except Exception:
                msg = (_('_update_replication_properties: Failed to fetch '
                         'relationship details for the volume.'))
                LOG.error(msg)
                raise exception.VolumeBackendAPIException(message=msg)

        model_update = model_update or dict()
        vol_metadata = model_update.get('metadata', {})

        db_metadata = self.db.volume_metadata_get(ctxt.elevated(),
                                                  volume['id'])
        model_update['metadata'] = db_metadata if db_metadata else dict()
        if (('IOThrottle_rate' not in vol_metadata) and
                ('IOThrottle_rate' in model_update['metadata'])):
            del model_update['metadata']['IOThrottle_rate']
        model_update['metadata'].update(vol_metadata)

        rel_info = _try_get_relationship_info(volume.name)

        rep_properties = {
            'Id': 'id',
            'Relationship Name': 'name',
            'Master Cluster Id': 'master_cluster_id',
            'Master Cluster Name': 'master_cluster_name',
            'Master Volume Id': 'master_vdisk_id',
            'Master Volume Name': 'master_vdisk_name',
            'Aux Cluster Id': 'aux_cluster_id',
            'Aux Cluster Name': 'aux_cluster_name',
            'Aux Volume Id': 'aux_vdisk_id',
            'Aux Volume Name': 'aux_vdisk_name',
            'Consistency Group Id': 'consistency_group_id',
            'Consistency Group Name': 'consistency_group_name',
            'Bg Copy Priority': 'bg_copy_priority',
            'Primary': 'primary',
            'Progress': 'progress',
            'Mirroring State': 'state',
            'Status': 'status',
            'Sync': 'sync',
            'Copy Type': 'copy_type',
            'Cycling Mode': 'cycling_mode',
            'Cycle Period Seconds': 'cycle_period_seconds',
            'Master Change Volume Id': 'master_change_vdisk_id',
            'Master Change Volume Name': 'master_change_vdisk_name',
            'Aux Change Volume Id': 'aux_change_vdisk_id',
            'Aux Change Volume Name': 'aux_change_vdisk_name',
            'Freeze Time': 'freeze_time'
        }
        # Update model for replication
        if not rel_info:
            for key in rep_properties:
                if key in model_update['metadata']:
                    del model_update['metadata'][key]
        else:
            for key, value in rep_properties.items():
                model_update['metadata'][key] = rel_info.get(value)
        return model_update

    def _update_rccg_properties(self, ctxt, volume, group=None):
        rccg_name = self._get_rccg_name(group) if group else ""
        if not volume.metadata:
            volume.metadata = dict()
        volume.metadata['Consistency Group Name'] = rccg_name
        volume.save()

    def _update_volumegroup_properties(self, ctxt, volume, group=None):
        volumegroup_name = self._get_volumegroup_name(group) if group else ""
        if not volume.metadata:
            volume.metadata = dict()
        volume.metadata['Volume Group Name'] = volumegroup_name
        volume.save()

    def _update_volumegroup_snapshot_properties(self, ctxt, snapshot,
                                                group_snapshot=None):
        volumegroup_snapshot_name = (
            self._get_volumegroup_snapshot_name(group_snapshot)
            if group_snapshot else "")
        if not snapshot.metadata:
            snapshot.metadata = dict()
        snapshot.metadata['snapshot_name'] = volumegroup_snapshot_name
        snapshot.save()

    def create_volume(self, volume):
        LOG.debug('enter: create_volume: volume %s', volume['name'])
        # Create a replication or hyperswap volume with group_id is not
        # allowed.
        self._check_if_group_type_cg_snapshot(volume)
        opts = self._get_vdisk_params(volume['volume_type_id'],
                                      volume_metadata=
                                      volume.get('volume_metadata'))
        ctxt = context.get_admin_context()
        rep_type = self._get_volume_replicated_type(ctxt, volume)

        pool = volume_utils.extract_host(volume['host'], 'pool')
        model_update = dict()

        if opts['volume_topology'] == 'hyperswap':
            LOG.debug('Volume %s to be created is a hyperswap volume.',
                      volume.name)
            if not self._helpers.is_system_topology_hyperswap(self._state):
                reason = _('Create hyperswap volume failed, the system is '
                           'below release 7.6.0.0 or it is not hyperswap '
                           'topology.')
                raise exception.InvalidInput(reason=reason)
            if opts['mirror_pool'] or rep_type:
                reason = _('Create hyperswap volume with streched cluster or '
                           'replication enabled is not supported.')
                raise exception.InvalidInput(reason=reason)
            if not opts['easytier']:
                msg = _('The default easytier of hyperswap volume is '
                        'on, it does not support easytier off.')
                raise exception.VolumeDriverException(message=msg)
            self._helpers.check_hyperswap_pool(pool, opts['peer_pool'])
            self._helpers.create_hyperswap_volume(volume.name, volume.size,
                                                  'gb', pool, opts)
            # Updating Hyperswap volume replication properties
            model_update = self._update_replication_properties(ctxt, volume,
                                                               model_update)
        else:
            if opts['mirror_pool'] and rep_type:
                reason = _('Create mirror volume with replication enabled is '
                           'not supported.')
                raise exception.InvalidInput(reason=reason)
            opts['iogrp'] = self._helpers.select_io_group(self._state,
                                                          opts, pool)
            self._helpers.create_vdisk(volume['name'], str(volume['size']),
                                       'gb', pool, opts)
        if opts['qos']:
            self._helpers.add_vdisk_qos(volume['name'], opts['qos'],
                                        volume['size'])
            model_update = self._qos_model_update(model_update, volume)

        model_update[
            'replication_status'] = fields.ReplicationStatus.NOT_CAPABLE

        if rep_type:
            replica_obj = self._get_replica_obj(rep_type)
            replica_obj.volume_replication_setup(ctxt, volume)
            model_update[
                'replication_status'] = fields.ReplicationStatus.ENABLED
            # Updating replication properties for a volume with replication
            # enabled.
            model_update = self._update_replication_properties(ctxt, volume,
                                                               model_update)

        LOG.debug('leave: create_volume:\n volume: %(vol)s\n '
                  'model_update %(model_update)s',
                  {'vol': volume['name'],
                   'model_update': model_update})
        return model_update

    def delete_volume(self, volume):
        LOG.debug('enter: delete_volume: volume %s', volume['name'])
        ctxt = context.get_admin_context()
        if self._state['code_level'] < (7, 7, 0, 0):
            force_unmap = False
        else:
            force_unmap = True
        hyper_volume = self.is_volume_hyperswap(volume)
        if hyper_volume:
            LOG.debug('Volume %s to be deleted is a hyperswap '
                      'volume.', volume.name)
            self._helpers.delete_hyperswap_volume(volume.name,
                                                  force_unmap=force_unmap,
                                                  force_delete=False)
            return

        rep_type = self._get_volume_replicated_type(ctxt, volume)
        if rep_type or (
                volume.replication_status not in ["not-capable", "disabled"]):
            target_volume, rel_info = (
                self._helpers.get_target_volume_information(volume))
            if self._aux_backend_helpers:
                self._aux_backend_helpers.delete_rc_volume(
                    target_volume,
                    rel_info,
                    target_vol=True,
                    force_unmap=force_unmap,
                    retain_aux_volume=self.configuration.safe_get(
                        'storwize_svc_retain_aux_volume'))
                # As the relationship got deleted, updated rel_info
                # as None and sent to master_backend_helper
                rel_info = None
            if not self._active_backend_id:
                self._master_backend_helpers.delete_rc_volume(
                    volume['name'], rel_info, force_unmap=force_unmap)
            else:
                # If it's in fail over state, also try to delete the volume
                # in master backend
                try:
                    self._master_backend_helpers.delete_rc_volume(
                        volume['name'], rel_info, force_unmap=force_unmap)
                except Exception as ex:
                    LOG.error('Failed to get delete volume %(volume)s in '
                              'master backend. Exception: %(err)s.',
                              {'volume': volume['name'],
                               'err': ex})
        else:
            if self._active_backend_id:
                msg = (_('Error: delete non-replicate volume in failover mode'
                         ' is not allowed.'))
                LOG.error(msg)
                raise exception.VolumeDriverException(message=msg)
            else:
                self._helpers.delete_vdisk(
                    volume['name'],
                    force_unmap=force_unmap,
                    force_delete=False)

        if volume['id'] in self._vdiskcopyops:
            del self._vdiskcopyops[volume['id']]

            if not len(self._vdiskcopyops):
                self._vdiskcopyops_loop.stop()
                self._vdiskcopyops_loop = None
        LOG.debug('leave: delete_volume: volume %s', volume['name'])

    def create_snapshot(self, snapshot):
        ctxt = context.get_admin_context()
        try:
            # TODO(zhaochy): change to use snapshot.volume
            source_vol = self.db.volume_get(ctxt, snapshot['volume_id'])
        except Exception:
            msg = (_('create_snapshot: get source volume failed.'))
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

        pool = volume_utils.extract_host(source_vol['host'], 'pool')
        opts = self._get_vdisk_params(source_vol['volume_type_id'])

        self._helpers.create_copy(snapshot['volume_name'], snapshot['name'],
                                  snapshot['volume_id'], self.configuration,
                                  opts, False, self._state, pool=pool)

    def delete_snapshot(self, snapshot):
        if self._state['code_level'] < (7, 7, 0, 0):
            force_unmap = False
        else:
            force_unmap = True
        self._helpers.delete_vdisk(
            snapshot['name'], force_unmap=force_unmap, force_delete=False)

    def create_volume_from_snapshot(self, volume, snapshot):
        # Create volume from snapshot with a replication or hyperswap group_id
        # is not allowed.
        model_update = dict()
        self._check_if_group_type_cg_snapshot(volume)
        opts = self._get_vdisk_params(volume['volume_type_id'],
                                      volume_metadata=
                                      volume.get('volume_metadata'))
        pool = volume_utils.extract_host(volume['host'], 'pool')
        self._helpers.create_copy(snapshot['name'], volume['name'],
                                  snapshot['id'], self.configuration,
                                  opts, True, self._state, pool=pool)
        # The volume size is equal to the snapshot size in most
        # of the cases. But in some scenario, the volume size
        # may be bigger than the source volume size.
        # SVC does not support flashcopy between two volumes
        # with two different size. So use the snapshot size to
        # create volume first and then extend the volume to-
        # the target size.
        if volume['size'] > snapshot['volume_size']:
            # extend the new created target volume to expected size.
            self._extend_volume_op(volume, volume['size'],
                                   snapshot['volume_size'])
        if opts['qos']:
            self._helpers.add_vdisk_qos(volume['name'], opts['qos'],
                                        volume['size'])
            model_update = self._qos_model_update(model_update, volume)

        ctxt = context.get_admin_context()
        model_update[
            'replication_status'] = fields.ReplicationStatus.NOT_CAPABLE
        rep_type = self._get_volume_replicated_type(ctxt, volume)

        if rep_type:
            self._validate_replication_enabled()
            replica_obj = self._get_replica_obj(rep_type)
            replica_obj.volume_replication_setup(ctxt, volume)
            model_update[
                'replication_status'] = fields.ReplicationStatus.ENABLED
            # Updating replication properties for a volume with replication
            # enabled.
            model_update = self._update_replication_properties(ctxt, volume,
                                                               model_update)

        if opts['volume_topology'] == 'hyperswap':
            LOG.debug('The volume %s to be created is a hyperswap '
                      'volume.', volume.name)
            # Ensures the vdisk is not part of FC mapping.
            # Otherwize convert it to hyperswap volume will be failed.
            self._helpers.ensure_vdisk_no_fc_mappings(volume['name'],
                                                      allow_snaps=True,
                                                      allow_fctgt=False)

            self._helpers.convert_volume_to_hyperswap(volume['name'],
                                                      opts,
                                                      self._state)

        return model_update

    def create_cloned_volume(self, tgt_volume, src_volume):
        """Creates a clone of the specified volume."""
        # Create a cloned volume with a replication or hyperswap group_id is
        # not allowed.
        model_update = dict()
        self._check_if_group_type_cg_snapshot(tgt_volume)
        opts = self._get_vdisk_params(tgt_volume['volume_type_id'],
                                      volume_metadata=
                                      tgt_volume.get('volume_metadata'))
        pool = volume_utils.extract_host(tgt_volume['host'], 'pool')
        self._helpers.create_copy(src_volume['name'], tgt_volume['name'],
                                  src_volume['id'], self.configuration,
                                  opts, True, self._state, pool=pool)

        # The source volume size is equal to target volume size
        # in most of the cases. But in some scenarios, the target
        # volume size may be bigger than the source volume size.
        # SVC does not support flashcopy between two volumes
        # with two different sizes. So use source volume size to
        # create target volume first and then extend target
        # volume to original size.
        ctxt = context.get_admin_context()
        if tgt_volume['size'] > src_volume['size']:
            # extend the new created target volume to expected size.
            self._extend_volume_op(tgt_volume, tgt_volume['size'],
                                   src_volume['size'])

        if opts['qos']:
            self._helpers.add_vdisk_qos(tgt_volume['name'], opts['qos'],
                                        tgt_volume['size'])
            model_update = self._qos_model_update(model_update, tgt_volume)

        if opts['volume_topology'] == 'hyperswap':
            LOG.debug('The source volume %s to be cloned is a hyperswap '
                      'volume.', src_volume.name)
            # Ensures the vdisk is not part of FC mapping.
            # Otherwize convert it to hyperswap volume will be failed.
            self._helpers.ensure_vdisk_no_fc_mappings(tgt_volume['name'],
                                                      allow_snaps=True,
                                                      allow_fctgt=False)

            self._helpers.convert_volume_to_hyperswap(tgt_volume['name'],
                                                      opts,
                                                      self._state)
            # Updating Hyperswap volume replication properties
            model_update = self._update_replication_properties(ctxt,
                                                               tgt_volume,
                                                               model_update)

        model_update[
            'replication_status'] = fields.ReplicationStatus.NOT_CAPABLE
        ctxt = context.get_admin_context()
        rep_type = self._get_volume_replicated_type(ctxt, tgt_volume)

        if rep_type:
            self._validate_replication_enabled()
            replica_obj = self._get_replica_obj(rep_type)
            replica_obj.volume_replication_setup(ctxt, tgt_volume)
            model_update[
                'replication_status'] = fields.ReplicationStatus.ENABLED
            # Updating replication properties for a volume with replication
            # enabled.
            model_update = self._update_replication_properties(ctxt,
                                                               tgt_volume,
                                                               model_update)
        return model_update

    def extend_volume(self, volume, new_size):
        self._extend_volume_op(volume, new_size)

    def _extend_volume_op(self, volume, new_size, old_size=None):
        LOG.debug('enter: _extend_volume_op: volume %s', volume['id'])
        if self._state['code_level'] < (7, 7, 0, 0):
            force_unmap = False
        else:
            force_unmap = True
        volume_name = self._get_target_vol(volume)

        tgt_vol, rel_info = self._helpers.get_target_volume_information(
            volume)

        ret = self._helpers.ensure_vdisk_no_fc_mappings(volume_name,
                                                        allow_snaps=False,
                                                        rel_info=rel_info)
        if not ret:
            msg = (_('_extend_volume_op: Extending a volume with snapshots is '
                     'not supported.'))
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

        if old_size is None:
            old_size = volume.size
        extend_amt = int(new_size) - old_size

        if rel_info:
            LOG.warning('_extend_volume_op: Extending a volume with '
                        'remote copy or with "active-active" relationship is '
                        'not recommended.')
            rep_type = rel_info['copy_type']
            cyclingmode = rel_info['cycling_mode']
            rc_name = rel_info['name']
            master_helper = self._master_backend_helpers
            target_helper = self._aux_backend_helpers
            if rep_type == 'activeactive':
                hs_opts = self._get_vdisk_params(volume['volume_type_id'],
                                                 volume_metadata=
                                                 volume.get(
                                                     'volume_metadata'))
                try:
                    master_helper.convert_hyperswap_volume_to_normal(
                        volume_name, hs_opts['peer_pool'])
                except Exception as e:
                    msg = (_('_extend_volume_op: Failed to convert hyperswap '
                             'volume to normal volume %(volume)s. Exception: '
                             '%(err)s.') % {'volume': volume.id, 'err': e})
                    LOG.error(msg)
                    raise exception.VolumeDriverException(message=msg)

                try:
                    master_helper.extend_vdisk(volume_name, extend_amt)
                except Exception as e:
                    msg = (_('_extend_volume_op: Failed to extend a hyperswap '
                             'volume %(volume)s. Exception: '
                             '%(err)s.') % {'volume': volume.id, 'err': e})
                    LOG.error(msg)
                    raise exception.VolumeDriverException(message=msg)
                finally:
                    try:
                        master_helper.convert_extended_volume_to_hyperswap(
                            volume_name, hs_opts, self._state)
                    except Exception as e:
                        msg = (_('_extend_volume_op: Failed to convert volume '
                                 'to hyperswap volume %(volume)s. Exception: '
                                 '%(err)s.') % {'volume': volume.id, 'err': e})
                        LOG.error(msg)
                        raise exception.VolumeDriverException(message=msg)
            else:
                try:
                    if storwize_const.GMCV_MULTI == cyclingmode:
                        rccg_name = (
                            self._helpers.get_rccg_name_by_volume_name(
                                volume.name))
                        # Update gmcv volume cyclingmode to 'none'
                        if rccg_name:
                            master_helper.stop_rccg(rccg_name)
                            master_helper.change_consistgrp_cyclingmode(
                                rccg_name)
                            master_helper.start_rccg(rccg_name)
                        else:
                            master_helper.stop_relationship(volume.name,
                                                            rcrel=rc_name)
                            master_helper.change_relationship_cyclingmode(
                                volume.name, rcrel=rc_name)
                            master_helper.start_relationship(volume.name,
                                                             rcrel=rc_name)

                        tgt_change_vol = (
                            storwize_const.REPLICA_CHG_VOL_PREFIX + tgt_vol)
                        source_change_vol = (
                            storwize_const.REPLICA_CHG_VOL_PREFIX +
                            volume.name)

                        # Delete source_change_volume and target_change_volume
                        master_helper.delete_vdisk(source_change_vol,
                                                   force_unmap=force_unmap,
                                                   force_delete=True)
                        target_helper.delete_vdisk(tgt_change_vol,
                                                   force_unmap=force_unmap,
                                                   force_delete=True)
                    # Extend primary volume and auxiliary volume
                    flag = self._helpers.is_replicated_volume_primary(
                        volume, rel_info)
                    if flag:
                        # source_volume is the primary volume or
                        # onboarded auxiliary volume is primary
                        # [Reverse replication failover]
                        target_helper.extend_vdisk(tgt_vol, extend_amt)
                        master_helper.extend_vdisk(volume.name, extend_amt)
                    else:
                        # Auxiliary volume is onboarded as source volume
                        # [Reverse Replication] or
                        # source volume with primary as aux [Failover]
                        master_helper.extend_vdisk(volume.name, extend_amt)
                        target_helper.extend_vdisk(tgt_vol, extend_amt)

                    if storwize_const.GMCV_MULTI == cyclingmode:
                        # Convert global mirror volume to GMCV volume with
                        # the new volume-size
                        self._convert_global_mirror_volume_to_gmcv(
                            volume, tgt_vol, new_size, rel_info,
                            rccg_name=rccg_name)
                except Exception as e:
                    msg = (_('Failed to extend a volume with remote copy '
                             '%(volume)s. Exception: '
                             '%(err)s.') % {'volume': volume.id,
                                            'err': e})
                    rel_info = self._helpers.get_relationship_info(volume_name)
                    new_cyclingmode = (
                        rel_info['cycling_mode'] if rel_info else 'multi')
                    if (storwize_const.GMCV_MULTI == cyclingmode and
                            cyclingmode != new_cyclingmode):
                        # Convert global mirror volume to GMCV volume with
                        # the current volume-size
                        self._convert_global_mirror_volume_to_gmcv(
                            volume, tgt_vol, volume['size'], rel_info,
                            rccg_name=rccg_name)

                    LOG.error(msg)
                    raise exception.VolumeDriverException(message=msg)
        else:
            self._helpers.extend_vdisk(volume_name, extend_amt)
        LOG.debug('leave: _extend_volume_op: volume %s', volume.id)

        # Update the QoS IOThrottling value to the volume properties
        opts = self._get_vdisk_params(volume['volume_type_id'],
                                      volume_metadata=
                                      volume.get('volume_metadata'))
        if opts['qos'] and opts['qos']['IOThrottling_unit']:
            unit = opts['qos']['IOThrottling_unit']
            if storwize_const.IOPS_PER_GB in unit:
                self._helpers.update_vdisk_qos(volume_name,
                                               opts['qos'],
                                               new_size)
                # Add the QoS IOThrottling value to Volume Metadata
                model_update = self._qos_model_update(dict(), volume)
                # Update the Volume Metadata in the DB
                self.db.volume_metadata_update(
                    context.get_admin_context(),
                    volume['id'], model_update['metadata'], False)

    def _convert_global_mirror_volume_to_gmcv(self, volume, target_vol, size,
                                              rel_info, rccg_name=None):
        master_helper = self._master_backend_helpers
        target_helper = self._aux_backend_helpers
        tgt_change_vol = (storwize_const.REPLICA_CHG_VOL_PREFIX + target_vol)
        src_change_vol = (storwize_const.REPLICA_CHG_VOL_PREFIX + volume.name)
        rc_name = rel_info['name']
        # Create source change volume if it doesn't exist
        src_attr = master_helper.get_vdisk_attributes(volume.name)
        src_change_attr = master_helper.get_vdisk_attributes(src_change_vol)
        if not src_change_attr:
            src_change_opts = self._get_vdisk_params(volume.volume_type_id)
            src_change_opts['iogrp'] = src_attr['IO_group_id']
            # Change volumes would usually be thin-provisioned
            src_change_opts['autoexpand'] = True
            master_helper.create_vdisk(src_change_vol, str(int(size)), 'gb',
                                       src_attr['mdisk_grp_name'],
                                       src_change_opts)

        # Create target change volume if it doesn't exist
        target_change_attr = (
            target_helper.get_vdisk_attributes(tgt_change_vol))
        if not target_change_attr:
            target_change_opts = self._get_vdisk_params(
                volume.volume_type_id)
            target_change_pool = self._replica_target.get('pool_name')
            target_change_opts['iogrp'] = src_attr['IO_group_id']
            # Change Volumes would usually be thin-provisioned
            target_change_opts['autoexpand'] = True
            target_helper.create_vdisk(tgt_change_vol, str(int(size)), 'gb',
                                       target_change_pool, target_change_opts)

        if rccg_name:
            # Update consistency group cyclingmode to 'multi'
            master_helper.stop_rccg(rccg_name)
            master_helper.change_consistgrp_cyclingmode(rccg_name, 'multi')
        else:
            # Update volume cyclingmode to 'multi'
            master_helper.stop_relationship(volume.name, rcrel=rc_name)
            master_helper.change_relationship_cyclingmode(volume.name, 'multi',
                                                          rc_name)

        # Set source_change_volume and target_change_volume
        if rel_info["master_vdisk_name"] == volume.name:
            master_helper.change_relationship_changevolume(volume.name,
                                                           src_change_vol,
                                                           True, rc_name)
            target_helper.change_relationship_changevolume(target_vol,
                                                           tgt_change_vol,
                                                           False, rc_name)
        else:
            # Auxiliary volume is onboarded as source volume
            # [Reverse Replication Scenario]
            master_helper.change_relationship_changevolume(volume.name,
                                                           src_change_vol,
                                                           False, rc_name)
            target_helper.change_relationship_changevolume(target_vol,
                                                           tgt_change_vol,
                                                           True, rc_name)

        if rccg_name:
            # Start gmcv consistency group relationshi
            master_helper.start_rccg(rccg_name)
        else:
            # Start gmcv volume relationship
            master_helper.start_relationship(volume.name, rcrel=rc_name)

    def _qos_model_update(self, model_update, volume):
        """add volume wwn and IOThrottle_rate to the metadata of the volume"""
        model_update = model_update or dict()
        vol_metadata = model_update.get('metadata', {})

        db_meta = self.db.volume_metadata_get(context.get_admin_context(),
                                              volume['id'])
        model_update['metadata'] = db_meta if db_meta else dict()
        model_update['metadata'].update(vol_metadata)

        attrs = self._helpers.get_vdisk_attributes(volume['name'])
        model_update['metadata']['volume_wwn'] = attrs['vdisk_UID']
        iops_limit = attrs.get('IOPs_limit')
        bw_limit_mbps = attrs.get('bandwidth_limit_MB')
        if iops_limit:
            model_update['metadata']['IOThrottle_rate'] = (
                "%s IOps" % iops_limit)
        elif bw_limit_mbps:
            model_update['metadata']['IOThrottle_rate'] = (
                "%s MBps" % bw_limit_mbps)
        else:
            # there is no IOThrottle_rate defined - remove it from metadata
            # This case is seen during retype from a storage template
            # with qos to storage template without qos (the qos rate
            # was leftover in the volume details on UI).
            if 'IOThrottle_rate' in model_update['metadata']:
                del model_update['metadata']['IOThrottle_rate']
        model_update['host'] = volume['host']
        return (model_update)

    def add_vdisk_copy(self, volume, dest_pool, vol_type, auto_delete=False):
        return self._helpers.add_vdisk_copy(volume, dest_pool,
                                            vol_type, self._state,
                                            self.configuration,
                                            auto_delete=auto_delete)

    def _add_vdisk_copy_op(self, ctxt, volume, new_op):
        metadata = self.db.volume_admin_metadata_get(ctxt.elevated(),
                                                     volume['id'])
        curr_ops = metadata.get('vdiskcopyops', None)
        if curr_ops:
            curr_ops_list = [tuple(x.split(':')) for x in curr_ops.split(';')]
            new_ops_list = curr_ops_list.append(new_op)
        else:
            new_ops_list = [new_op]
        new_ops_str = ';'.join([':'.join(x) for x in new_ops_list])
        self.db.volume_admin_metadata_update(ctxt.elevated(), volume['id'],
                                             {'vdiskcopyops': new_ops_str},
                                             False)
        if volume['id'] in self._vdiskcopyops:
            self._vdiskcopyops[volume['id']].append(new_op)
        else:
            self._vdiskcopyops[volume['id']] = [new_op]

        # We added the first copy operation, so start the looping call
        if len(self._vdiskcopyops) == 1:
            self._vdiskcopyops_loop = loopingcall.FixedIntervalLoopingCall(
                self._check_volume_copy_ops)
            self._vdiskcopyops_loop.start(interval=self.VDISKCOPYOPS_INTERVAL)

    def _rm_vdisk_copy_op(self, ctxt, volume, orig_copy_id, new_copy_id):
        try:
            self._vdiskcopyops[volume['id']].remove((orig_copy_id,
                                                     new_copy_id))
            if not len(self._vdiskcopyops[volume['id']]):
                del self._vdiskcopyops[volume['id']]
            if not len(self._vdiskcopyops):
                self._vdiskcopyops_loop.stop()
                self._vdiskcopyops_loop = None
        except KeyError:
            LOG.error('_rm_vdisk_copy_op: Volume %s does not have any '
                      'registered vdisk copy operations.', volume['id'])
            return
        except ValueError:
            LOG.error('_rm_vdisk_copy_op: Volume %(vol)s does not have '
                      'the specified vdisk copy operation: orig=%(orig)s '
                      'new=%(new)s.',
                      {'vol': volume['id'], 'orig': orig_copy_id,
                       'new': new_copy_id})
            return

        metadata = self.db.volume_admin_metadata_get(ctxt.elevated(),
                                                     volume['id'])
        curr_ops = metadata.get('vdiskcopyops', None)
        if not curr_ops:
            LOG.error('_rm_vdisk_copy_op: Volume metadata %s does not '
                      'have any registered vdisk copy operations.',
                      volume['id'])
            return
        curr_ops_list = [tuple(x.split(':')) for x in curr_ops.split(';')]
        try:
            curr_ops_list.remove((orig_copy_id, new_copy_id))
        except ValueError:
            LOG.error('_rm_vdisk_copy_op: Volume %(vol)s metadata does '
                      'not have the specified vdisk copy operation: '
                      'orig=%(orig)s new=%(new)s.',
                      {'vol': volume['id'], 'orig': orig_copy_id,
                       'new': new_copy_id})
            return

        if len(curr_ops_list):
            new_ops_str = ';'.join([':'.join(x) for x in curr_ops_list])
            self.db.volume_admin_metadata_update(ctxt.elevated(), volume['id'],
                                                 {'vdiskcopyops': new_ops_str},
                                                 False)
        else:
            self.db.volume_admin_metadata_delete(ctxt.elevated(), volume['id'],
                                                 'vdiskcopyops')

    def _check_volume_copy_ops(self):
        LOG.debug("Enter: update volume copy status.")
        ctxt = context.get_admin_context()
        copy_items = list(self._vdiskcopyops.items())
        for vol_id, copy_ops in copy_items:
            try:
                volume = self.db.volume_get(ctxt, vol_id)
            except Exception:
                LOG.warning('Volume %s does not exist.', vol_id)
                del self._vdiskcopyops[vol_id]
                if not len(self._vdiskcopyops):
                    self._vdiskcopyops_loop.stop()
                    self._vdiskcopyops_loop = None
                continue

            for copy_op in copy_ops:
                try:
                    synced = self._helpers.is_vdisk_copy_synced(volume['name'],
                                                                copy_op[1])
                except Exception:
                    LOG.info('_check_volume_copy_ops: Volume %(vol)s does '
                             'not have the specified vdisk copy '
                             'operation: orig=%(orig)s new=%(new)s.',
                             {'vol': volume['id'], 'orig': copy_op[0],
                              'new': copy_op[1]})
                else:
                    if synced:
                        self._helpers.rm_vdisk_copy(volume['name'], copy_op[0])
                        self._rm_vdisk_copy_op(ctxt, volume, copy_op[0],
                                               copy_op[1])
        LOG.debug("Exit: update volume copy status.")

    # #### V2.1 replication methods #### #
    @volume_utils.trace
    def failover_host(self, context, volumes, secondary_id=None, groups=None):
        if not self._replica_enabled:
            msg = _("Replication is not properly enabled on backend.")
            LOG.error(msg)
            raise exception.UnableToFailOver(reason=msg)

        if storwize_const.FAILBACK_VALUE == secondary_id:
            # In this case the administrator would like to fail back.
            secondary_id, volumes_update, groups_update = self._host_failback(
                context, volumes, groups)
        elif (secondary_id == self._replica_target['backend_id'] or
                secondary_id is None):
            # In this case the administrator would like to fail over.
            secondary_id, volumes_update, groups_update = self._host_failover(
                context, volumes, groups)
        else:
            msg = (_("Invalid secondary id %s.") % secondary_id)
            LOG.error(msg)
            raise exception.InvalidReplicationTarget(reason=msg)

        return secondary_id, volumes_update, groups_update

    def _host_failback(self, ctxt, volumes, groups):
        """Fail back all the volume on the secondary backend."""
        volumes_update = []
        groups_update = []
        if not self._active_backend_id:
            LOG.info("Host has been failed back. doesn't need "
                     "to fail back again")
            return None, volumes_update, groups_update

        try:
            self._master_backend_helpers.get_system_info()
        except Exception:
            msg = (_("Unable to failback due to primary is not reachable."))
            LOG.error(msg)
            raise exception.UnableToFailOver(reason=msg)

        bypass_volumes, rep_volumes = self._classify_volume(ctxt, volumes)

        # start synchronize from aux volume to master volume
        self._sync_with_aux(ctxt, rep_volumes)
        self._sync_replica_groups(ctxt, groups)
        self._wait_replica_ready(ctxt, rep_volumes)
        self._wait_replica_groups_ready(ctxt, groups)

        rep_volumes_update = self._failback_replica_volumes(ctxt,
                                                            rep_volumes)
        volumes_update.extend(rep_volumes_update)

        rep_vols_in_grp_update, groups_update = self._failback_replica_groups(
            ctxt, groups)
        volumes_update.extend(rep_vols_in_grp_update)

        bypass_volumes_update = self._bypass_volume_process(bypass_volumes)
        volumes_update.extend(bypass_volumes_update)

        self._helpers = self._master_backend_helpers
        self._active_backend_id = None
        self._state = self._master_state

        self._update_volume_stats()
        self._master_backend_helpers.stats = self._stats

        return storwize_const.FAILBACK_VALUE, volumes_update, groups_update

    def _failback_replica_volumes(self, ctxt, rep_volumes):
        LOG.debug('enter: _failback_replica_volumes')
        volumes_update = []

        for volume in rep_volumes:
            rep_type = self._get_volume_replicated_type(ctxt, volume)
            replica_obj = self._get_replica_obj(rep_type)
            tgt_volume = storwize_const.REPLICA_AUX_VOL_PREFIX + volume['name']
            rep_info = self._helpers.get_relationship_info(tgt_volume)
            if not rep_info:
                volumes_update.append(
                    {'volume_id': volume['id'],
                     'updates':
                         {'replication_status':
                          fields.ReplicationStatus.ERROR,
                          'status': 'error'}})
                LOG.error('_failback_replica_volumes:no rc-releationship '
                          'is established between master: %(master)s and '
                          'aux %(aux)s. Please re-establish the '
                          'relationship and synchronize the volumes on '
                          'backend storage.',
                          {'master': volume['name'], 'aux': tgt_volume})
                continue
            LOG.debug('_failover_replica_volumes: vol=%(vol)s, master_vol='
                      '%(master_vol)s, aux_vol=%(aux_vol)s, state=%(state)s, '
                      'primary=%(primary)s',
                      {'vol': volume['name'],
                       'master_vol': rep_info['master_vdisk_name'],
                       'aux_vol': rep_info['aux_vdisk_name'],
                       'state': rep_info['state'],
                       'primary': rep_info['primary']})
            if volume.status == 'in-use':
                LOG.warning('_failback_replica_volumes: failback in-use '
                            'volume: %(volume)s is not recommended.',
                            {'volume': volume.name})
            try:
                replica_obj.replication_failback(volume)
                model_updates = {
                    'replication_status': fields.ReplicationStatus.ENABLED}
                volumes_update.append(
                    {'volume_id': volume['id'],
                     'updates': model_updates})
            except exception.VolumeDriverException:
                LOG.error('Unable to fail back volume %(volume_id)s',
                          {'volume_id': volume.id})
                volumes_update.append(
                    {'volume_id': volume['id'],
                     'updates': {'replication_status':
                                 fields.ReplicationStatus.ERROR,
                                 'status': 'error'}})
        LOG.debug('leave: _failback_replica_volumes '
                  'volumes_update=%(volumes_update)s',
                  {'volumes_update': volumes_update})
        return volumes_update

    def _bypass_volume_process(self, bypass_vols):
        volumes_update = []
        for vol in bypass_vols:
            if vol.replication_driver_data:
                rep_data = json.loads(vol.replication_driver_data)
                update_status = rep_data['previous_status']
                rep_data = ''
            else:
                update_status = 'error'
                rep_data = json.dumps({'previous_status': vol.status})

            volumes_update.append(
                {'volume_id': vol.id,
                 'updates': {'status': update_status,
                             'replication_driver_data': rep_data}})

        return volumes_update

    def _failback_replica_groups(self, ctxt, groups):
        volumes_update = []
        groups_update = []
        for grp in groups:
            try:
                grp_rep_status = self._rep_grp_failback(
                    ctxt, grp, sync_grp=False)['replication_status']
            except Exception as ex:
                LOG.error('Fail to failback group %(grp)s during host '
                          'failback due to error: %(error)s',
                          {'grp': grp.id, 'error': ex})
                grp_rep_status = fields.ReplicationStatus.ERROR

            # Update all the volumes' status in that group
            for vol in grp.volumes:
                vol_update = {'volume_id': vol.id,
                              'updates':
                                  {'replication_status': grp_rep_status,
                                   'status': (
                                       vol.status if grp_rep_status ==
                                       fields.ReplicationStatus.ENABLED
                                       else 'error')}}
                volumes_update.append(vol_update)
            grp_status = (fields.GroupStatus.AVAILABLE
                          if grp_rep_status ==
                          fields.ReplicationStatus.ENABLED
                          else fields.GroupStatus.ERROR)
            grp_update = {'group_id': grp.id,
                          'updates': {'replication_status': grp_rep_status,
                                      'status': grp_status}}
            groups_update.append(grp_update)
        return volumes_update, groups_update

    def _sync_with_aux(self, ctxt, volumes):
        LOG.debug('enter: _sync_with_aux ')
        try:
            rep_mgr = self._get_replica_mgr()
            rep_mgr.establish_target_partnership()
        except Exception as ex:
            LOG.warning('Fail to establish partnership in backend. '
                        'error=%(ex)s', {'error': ex})
        for volume in volumes:
            tgt_volume = storwize_const.REPLICA_AUX_VOL_PREFIX + volume['name']
            rep_info = self._helpers.get_relationship_info(tgt_volume)
            if not rep_info:
                LOG.error('_sync_with_aux: no rc-releationship is '
                          'established between master: %(master)s and aux '
                          '%(aux)s. Please re-establish the relationship '
                          'and synchronize the volumes on backend '
                          'storage.', {'master': volume['name'],
                                       'aux': tgt_volume})
                continue
            LOG.debug('_sync_with_aux: volume: %(volume)s rep_info:master_vol='
                      '%(master_vol)s, aux_vol=%(aux_vol)s, state=%(state)s, '
                      'primary=%(primary)s',
                      {'volume': volume['name'],
                       'master_vol': rep_info['master_vdisk_name'],
                       'aux_vol': rep_info['aux_vdisk_name'],
                       'state': rep_info['state'],
                       'primary': rep_info['primary']})
            try:
                if (rep_info['state'] not in
                        [storwize_const.REP_CONSIS_SYNC,
                         storwize_const.REP_CONSIS_COPYING]):
                    if rep_info['primary'] == 'master':
                        self._helpers.start_relationship(tgt_volume,
                                                         rcrel=
                                                         rep_info['name'])
                    else:
                        self._helpers.start_relationship(tgt_volume,
                                                         primary='aux',
                                                         rcrel=
                                                         rep_info['name'])
            except Exception as ex:
                LOG.warning('Fail to copy data from aux to master. master:'
                            ' %(master)s and aux %(aux)s. Please '
                            're-establish the relationship and synchronize'
                            ' the volumes on backend storage. error='
                            '%(ex)s', {'master': volume['name'],
                                       'aux': tgt_volume,
                                       'error': ex})
        LOG.debug('leave: _sync_with_aux.')

    def _wait_replica_ready(self, ctxt, volumes):
        for volume in volumes:
            tgt_volume = storwize_const.REPLICA_AUX_VOL_PREFIX + volume['name']
            try:
                self._wait_replica_vol_ready(ctxt, tgt_volume)
            except Exception as ex:
                LOG.error('_wait_replica_ready: wait for volume:%(volume)s'
                          ' remote copy synchronization failed due to '
                          'error:%(err)s.', {'volume': tgt_volume,
                                             'err': ex})

    def _wait_replica_vol_ready(self, ctxt, volume):
        LOG.debug('enter: _wait_replica_vol_ready: volume=%(volume)s',
                  {'volume': volume})

        def _replica_vol_ready():
            rep_info = self._helpers.get_relationship_info(volume)
            if not rep_info:
                msg = (_('_wait_replica_vol_ready: no rc-releationship '
                         'is established for volume:%(volume)s. Please '
                         're-establish the rc-relationship and '
                         'synchronize the volumes on backend storage.'),
                       {'volume': volume})
                LOG.error(msg)
                raise exception.VolumeBackendAPIException(data=msg)
            LOG.debug('_replica_vol_ready:volume: %(volume)s rep_info: '
                      'master_vol=%(master_vol)s, aux_vol=%(aux_vol)s, '
                      'state=%(state)s, primary=%(primary)s',
                      {'volume': volume,
                       'master_vol': rep_info['master_vdisk_name'],
                       'aux_vol': rep_info['aux_vdisk_name'],
                       'state': rep_info['state'],
                       'primary': rep_info['primary']})
            if (rep_info['state'] in
                    [storwize_const.REP_CONSIS_SYNC,
                     storwize_const.REP_CONSIS_COPYING]):
                return True
            elif rep_info['state'] == storwize_const.REP_IDL_DISC:
                msg = (_('Wait synchronize failed. volume: %(volume)s'),
                       {'volume': volume})
                LOG.error(msg)
                raise exception.VolumeBackendAPIException(data=msg)
            return False

        self._helpers._wait_for_a_condition(
            _replica_vol_ready, timeout=storwize_const.DEFAULT_RC_TIMEOUT,
            interval=storwize_const.DEFAULT_RC_INTERVAL,
            raise_exception=True)
        LOG.debug('leave: _wait_replica_vol_ready: volume=%(volume)s',
                  {'volume': volume})

    def _sync_replica_groups(self, ctxt, groups):
        for grp in groups:
            rccg_name = self._get_rccg_name(grp)
            self._sync_with_aux_grp(ctxt, rccg_name)

    def _wait_replica_groups_ready(self, ctxt, groups):
        for grp in groups:
            rccg_name = self._get_rccg_name(grp)
            self._wait_replica_grp_ready(ctxt, rccg_name)

    def _host_failover(self, ctxt, volumes, groups):
        volumes_update = []
        groups_update = []
        if self._active_backend_id:
            LOG.info("Host has been failed over to %s",
                     self._active_backend_id)
            return self._active_backend_id, volumes_update, groups_update

        try:
            self._aux_backend_helpers.get_system_info()
        except Exception as ex:
            msg = (_("Unable to failover due to replication target is not "
                     "reachable. error=%(ex)s"), {'error': ex})
            LOG.error(msg)
            raise exception.UnableToFailOver(reason=msg)

        bypass_volumes, rep_volumes = self._classify_volume(ctxt, volumes)

        rep_volumes_update = self._failover_replica_volumes(ctxt, rep_volumes)
        volumes_update.extend(rep_volumes_update)

        rep_vols_in_grp_update, groups_update = self._failover_replica_groups(
            ctxt, groups)
        volumes_update.extend(rep_vols_in_grp_update)

        bypass_volumes_update = self._bypass_volume_process(bypass_volumes)
        volumes_update.extend(bypass_volumes_update)

        self._helpers = self._aux_backend_helpers
        self._active_backend_id = self._replica_target['backend_id']
        self._secondary_pools = [self._replica_target['pool_name']]
        self._state = self._aux_state

        self._update_volume_stats()
        self._aux_backend_helpers.stats = self._stats

        return self._active_backend_id, volumes_update, groups_update

    def _failover_replica_volumes(self, ctxt, rep_volumes):
        LOG.debug('enter: _failover_replica_volumes')
        volumes_update = []

        for volume in rep_volumes:
            rep_type = self._get_volume_replicated_type(ctxt, volume)
            replica_obj = self._get_replica_obj(rep_type)
            # Try do the fail-over.
            try:
                rep_info = self._aux_backend_helpers.get_relationship_info(
                    storwize_const.REPLICA_AUX_VOL_PREFIX + volume['name'])
                if not rep_info:
                    volumes_update.append(
                        {'volume_id': volume['id'],
                         'updates':
                             {'replication_status':
                              fields.ReplicationStatus.FAILOVER_ERROR,
                              'status': 'error'}})
                    LOG.error('_failover_replica_volumes: no rc-'
                              'releationship is established for volume:'
                              '%(volume)s. Please re-establish the rc-'
                              'relationship and synchronize the volumes on'
                              ' backend storage.',
                              {'volume': volume.name})
                    continue
                LOG.debug('_failover_replica_volumes: vol=%(vol)s, '
                          'master_vol=%(master_vol)s, aux_vol=%(aux_vol)s, '
                          'state=%(state)s, primary=%(primary)s',
                          {'vol': volume['name'],
                           'master_vol': rep_info['master_vdisk_name'],
                           'aux_vol': rep_info['aux_vdisk_name'],
                           'state': rep_info['state'],
                           'primary': rep_info['primary']})
                if volume.status == 'in-use':
                    LOG.warning('_failover_replica_volumes: failover in-use '
                                'volume: %(volume)s is not recommended.',
                                {'volume': volume.name})
                replica_obj.failover_volume_host(ctxt, volume)
                model_updates = {
                    'replication_status': fields.ReplicationStatus.FAILED_OVER}
                volumes_update.append(
                    {'volume_id': volume['id'],
                     'updates': model_updates})
            except exception.VolumeDriverException:
                LOG.error('Unable to failover to aux volume. Please make '
                          'sure that the aux volume is ready.')
                volumes_update.append(
                    {'volume_id': volume['id'],
                     'updates': {'status': 'error',
                                 'replication_status':
                                 fields.ReplicationStatus.FAILOVER_ERROR}})
        LOG.debug('leave: _failover_replica_volumes '
                  'volumes_update=%(volumes_update)s',
                  {'volumes_update': volumes_update})
        return volumes_update

    def _failover_replica_groups(self, ctxt, groups):
        volumes_update = []
        groups_update = []
        for grp in groups:
            try:
                grp_rep_status = self._rep_grp_failover(
                    ctxt, grp)['replication_status']
            except Exception as ex:
                LOG.error('Fail to failover group %(grp)s during host '
                          'failover due to error: %(error)s',
                          {'grp': grp.id, 'error': ex})
                grp_rep_status = fields.ReplicationStatus.ERROR

            # Update all the volumes' status in that group
            for vol in grp.volumes:
                vol_update = {'volume_id': vol.id,
                              'updates':
                                  {'replication_status': grp_rep_status,
                                   'status': (
                                       vol.status if grp_rep_status ==
                                       fields.ReplicationStatus.FAILED_OVER
                                       else 'error')}}
                volumes_update.append(vol_update)
            grp_status = (fields.GroupStatus.AVAILABLE
                          if grp_rep_status ==
                          fields.ReplicationStatus.FAILED_OVER
                          else fields.GroupStatus.ERROR)
            grp_update = {'group_id': grp.id,
                          'updates': {'replication_status': grp_rep_status,
                                      'status': grp_status}}
            groups_update.append(grp_update)
        return volumes_update, groups_update

    def _classify_volume(self, ctxt, volumes):
        bypass_volumes = []
        replica_volumes = []

        for v in volumes:
            volume_type = self._get_volume_replicated_type(ctxt, v)
            grp = v.group
            if grp and volume_utils.is_group_a_type(
                    grp, "consistent_group_replication_enabled"):
                continue
            elif volume_type and v.status in ['available', 'in-use']:
                replica_volumes.append(v)
            else:
                bypass_volumes.append(v)
        return bypass_volumes, replica_volumes

    def _get_replica_obj(self, rep_type):
        replica_manager = self.replica_manager[
            self._replica_target['backend_id']]
        return replica_manager.get_replica_obj(rep_type)

    def _get_replica_mgr(self):
        replica_manager = self.replica_manager[
            self._replica_target['backend_id']]
        return replica_manager

    def _get_target_vol(self, volume):
        tgt_vol = volume['name']
        if self._active_backend_id:
            ctxt = context.get_admin_context()
            rep_type = self._get_volume_replicated_type(ctxt, volume)
            if rep_type:
                tgt_vol = (storwize_const.REPLICA_AUX_VOL_PREFIX +
                           volume['name'])
        return tgt_vol

    def _validate_replication_enabled(self):
        if not self._replica_enabled:
            msg = _("Replication is not properly configured on backend.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def _get_specs_replicated_type(self, volume_type):
        replication_type = None
        extra_specs = volume_type.get("extra_specs", {})
        rep_val = extra_specs.get('replication_enabled')
        if rep_val == "<is> True":
            replication_type = extra_specs.get('replication_type',
                                               storwize_const.GLOBAL)
            # The format for replication_type in extra spec is in
            # "<in> global". Otherwise, the code will
            # not reach here.
            if replication_type != storwize_const.GLOBAL:
                # Pick up the replication type specified in the
                # extra spec from the format like "<in> global".
                replication_type = replication_type.split()[1]
            if replication_type not in storwize_const.VALID_REP_TYPES:
                msg = (_("Invalid replication type %s.") % replication_type)
                LOG.error(msg)
                raise exception.InvalidInput(reason=msg)
        return replication_type

    def _get_volume_replicated_type(self, ctxt, volume, vol_type_id=None):
        replication_type = None
        volume_type = None
        volume_type_id = volume.volume_type_id if volume else vol_type_id
        if volume_type_id:
            volume_type = objects.VolumeType.get_by_name_or_id(
                ctxt, volume_type_id)
        if volume_type:
            replication_type = self._get_specs_replicated_type(volume_type)
        return replication_type

    def is_volume_hyperswap(self, volume):
        """Returns True if the volume type is hyperswap."""
        is_hyper_volume = False
        if 'volume_type_id' in volume:
            opts = self._get_vdisk_params(volume.volume_type_id)
            if opts['volume_topology'] == 'hyperswap':
                is_hyper_volume = True
        return is_hyper_volume

    def _get_storwize_config(self):
        # Update the storwize state
        try:
            self._update_storwize_state(self._master_state, self._helpers)
        except Exception as err:
            LOG.warning('Fail to get system %(san_ip)s info. error=%(error)s',
                        {'san_ip': self.active_ip, 'error': err})
            if not self._active_backend_id:
                with excutils.save_and_reraise_exception():
                    pass
        self._do_replication_setup()

        if self._active_backend_id and self._replica_target:
            self._helpers = self._aux_backend_helpers
            self._state = self._aux_state

        self._replica_enabled = (True if (self._helpers.replication_licensed()
                                          and self._replica_target) else False)
        if self._replica_enabled:
            self._supported_replica_types = storwize_const.VALID_REP_TYPES

    def _do_replication_setup(self):
        rep_devs = self.configuration.safe_get('replication_device')
        if not rep_devs:
            return

        if len(rep_devs) > 1:
            raise exception.InvalidInput(
                reason='Multiple replication devices are configured. '
                       'Now only one replication_device is supported.')

        required_flags = ['san_ip', 'backend_id', 'san_login',
                          'san_password', 'pool_name']
        for flag in required_flags:
            if flag not in rep_devs[0]:
                raise exception.InvalidInput(
                    reason=_('%s is not set.') % flag)

        rep_target = {}
        rep_target['san_ip'] = rep_devs[0].get('san_ip')
        rep_target['backend_id'] = rep_devs[0].get('backend_id')
        rep_target['san_login'] = rep_devs[0].get('san_login')
        rep_target['san_password'] = rep_devs[0].get('san_password')
        rep_target['pool_name'] = rep_devs[0].get('pool_name')

        # Each replication target will have a corresponding replication.
        self._replication_initialize(rep_target)

    def _replication_initialize(self, target):
        rep_manager = storwize_rep.StorwizeSVCReplicationManager(
            self, target, StorwizeHelpers)

        if self._active_backend_id:
            if self._active_backend_id != target['backend_id']:
                msg = (_("Invalid secondary id %s.") % self._active_backend_id)
                LOG.error(msg)
                raise exception.InvalidInput(reason=msg)
        # Setup partnership only in non-failover state
        else:
            try:
                rep_manager.establish_target_partnership()
            except exception.VolumeDriverException:
                LOG.error('The replication src %(src)s has not '
                          'successfully established partnership with the '
                          'replica target %(tgt)s.',
                          {'src': self.configuration.san_ip,
                           'tgt': target['backend_id']})

        self._aux_backend_helpers = rep_manager.get_target_helpers()
        self.replica_manager[target['backend_id']] = rep_manager
        self._replica_target = target
        self._update_storwize_state(self._aux_state, self._aux_backend_helpers)

    # Replication Group (Tiramisu)
    @volume_utils.trace
    def enable_replication(self, context, group, volumes):
        """Enables replication for a group and volumes in the group."""
        model_update = {'replication_status': fields.ReplicationStatus.ENABLED}
        volumes_update = []
        rccg_name = self._get_rccg_name(group)
        rccg = self._helpers.get_rccg(rccg_name)
        if rccg and rccg['relationship_count'] != '0':
            try:
                if rccg['primary'] == 'aux':
                    self._helpers.start_rccg(rccg_name, primary='aux')
                else:
                    self._helpers.start_rccg(rccg_name, primary='master')
            except exception.VolumeBackendAPIException as err:
                LOG.error("Failed to enable group replication on %(rccg)s. "
                          "Exception: %(exception)s.",
                          {'rccg': rccg_name, 'exception': err})
                model_update[
                    'replication_status'] = fields.ReplicationStatus.ERROR
        else:
            if rccg:
                LOG.error("Enable replication on empty group %(rccg)s is "
                          "forbidden.", {'rccg': rccg['name']})
            else:
                LOG.error("Failed to enable group replication: %(grp)s does "
                          "not exist in backend.", {'grp': group.id})
            model_update['replication_status'] = fields.ReplicationStatus.ERROR

        for vol in volumes:
            volumes_update.append(
                {'id': vol.id,
                 'replication_status': model_update['replication_status']})
        return model_update, volumes_update

    @volume_utils.trace
    def disable_replication(self, context, group, volumes):
        """Disables replication for a group and volumes in the group."""
        model_update = {
            'replication_status': fields.ReplicationStatus.DISABLED}
        volumes_update = []
        rccg_name = self._get_rccg_name(group)
        rccg = self._helpers.get_rccg(rccg_name)
        if rccg and rccg['relationship_count'] != '0':
            try:
                self._helpers.stop_rccg(rccg_name)
            except exception.VolumeBackendAPIException as err:
                LOG.error("Failed to disable group replication on %(rccg)s. "
                          "Exception: %(exception)s.",
                          {'rccg': rccg_name, 'exception': err})
                model_update[
                    'replication_status'] = fields.ReplicationStatus.ERROR
        else:
            if rccg:
                LOG.error("Disable replication on empty group %(rccg)s is "
                          "forbidden.", {'rccg': rccg['name']})
            else:
                LOG.error("Failed to disable group replication: %(grp)s does "
                          "not exist in backend.", {'grp': group.id})
            model_update['replication_status'] = fields.ReplicationStatus.ERROR

        for vol in volumes:
            volumes_update.append(
                {'id': vol.id,
                 'replication_status': model_update['replication_status']})
        return model_update, volumes_update

    @volume_utils.trace
    def failover_replication(self, context, group, volumes,
                             secondary_backend_id=None):
        """Fails over replication for a group and volumes in the group."""
        volumes_model_update = []
        model_update = {}
        if not self._replica_enabled:
            msg = _("Replication is not properly enabled on backend.")
            LOG.error(msg)
            raise exception.UnableToFailOver(reason=msg)

        if storwize_const.FAILBACK_VALUE == secondary_backend_id:
            # In this case the administrator would like to group fail back.
            model_update = self._rep_grp_failback(context, group)
        elif (secondary_backend_id == self._replica_target['backend_id'] or
                secondary_backend_id is None):
            # In this case the administrator would like to group fail over.
            model_update = self._rep_grp_failover(context, group)
        else:
            msg = (_("Invalid secondary id %s.") % secondary_backend_id)
            LOG.error(msg)
            raise exception.InvalidReplicationTarget(reason=msg)

        for vol in volumes:
            volume_model_update = {'id': vol.id,
                                   'replication_status':
                                       model_update['replication_status']}
            volumes_model_update.append(volume_model_update)
        return model_update, volumes_model_update

    @volume_utils.trace
    def _rep_grp_failback(self, ctxt, group, sync_grp=True):
        """Fail back all the volume in the replication group."""
        model_update = {
            'replication_status': fields.ReplicationStatus.ENABLED}
        rccg_name = self._get_rccg_name(group)

        try:
            self._aux_backend_helpers.stop_rccg(rccg_name, access=True)
            self._aux_backend_helpers.start_rccg(rccg_name, primary='master')
            return model_update
        except exception.VolumeBackendAPIException as e:
            msg = (_('Unable to fail back the group %(rccg)s, error: '
                     '%(error)s') % {"rccg": rccg_name, "error": e})
            LOG.exception(msg)
            raise exception.UnableToFailOver(reason=msg)

    @volume_utils.trace
    def _rep_grp_failover(self, ctxt, group):
        """Fail over all the volume in the replication group."""
        model_update = {
            'replication_status': fields.ReplicationStatus.FAILED_OVER}
        rccg_name = self._get_rccg_name(group)

        try:
            self._aux_backend_helpers.stop_rccg(rccg_name, access=True)
            self._helpers.start_rccg(rccg_name, primary='aux')
            return model_update
        except exception.VolumeBackendAPIException as e:
            msg = (_('Unable to fail over the group %(rccg)s to the aux '
                     'back-end, error: %(error)s') %
                   {"rccg": rccg_name, "error": e})
            LOG.exception(msg)
            raise exception.UnableToFailOver(reason=msg)

    @volume_utils.trace
    def _sync_with_aux_grp(self, ctxt, rccg_name):
        try:
            rccg = self._helpers.get_rccg(rccg_name)
            if rccg and rccg['relationship_count'] != '0':
                if (rccg['state'] not in
                        [storwize_const.REP_CONSIS_SYNC,
                         storwize_const.REP_CONSIS_COPYING]):
                    if rccg['primary'] == 'master':
                        self._helpers.start_rccg(rccg_name, primary='master')
                    else:
                        self._helpers.start_rccg(rccg_name, primary='aux')
            else:
                LOG.warning('group %(grp)s is not in sync.',
                            {'grp': rccg_name})
        except exception.VolumeBackendAPIException as ex:
            LOG.warning('Fail to copy data from aux group %(rccg)s to master '
                        'group. Please recheck the relationship and '
                        'synchronize the group on backend storage. error='
                        '%(error)s', {'rccg': rccg['name'], 'error': ex})

    def _wait_replica_grp_ready(self, ctxt, rccg_name):
        LOG.debug('_wait_replica_grp_ready: group=%(rccg)s',
                  {'rccg': rccg_name})

        def _replica_grp_ready():
            rccg = self._helpers.get_rccg(rccg_name)
            if not rccg:
                msg = (_('_replica_grp_ready: no group %(rccg)s exists on the '
                         'backend. Please re-create the rccg and synchronize '
                         'the volumes on backend storage.'),
                       {'rccg': rccg_name})
                LOG.error(msg)
                raise exception.VolumeBackendAPIException(data=msg)
            if rccg['relationship_count'] == '0':
                return True
            LOG.debug('_replica_grp_ready: group: %(rccg)s: state=%(state)s, '
                      'primary=%(primary)s',
                      {'rccg': rccg['name'], 'state': rccg['state'],
                       'primary': rccg['primary']})
            if rccg['state'] in [storwize_const.REP_CONSIS_SYNC,
                                 storwize_const.REP_CONSIS_COPYING]:
                return True
            if rccg['state'] == storwize_const.REP_IDL_DISC:
                msg = (_('Wait synchronize failed. group: %(rccg)s') %
                       {'rccg': rccg_name})
                LOG.error(msg)
                raise exception.VolumeBackendAPIException(data=msg)
            return False
        try:
            self._helpers._wait_for_a_condition(
                _replica_grp_ready,
                timeout=storwize_const.DEFAULT_RCCG_TIMEOUT,
                interval=storwize_const.DEFAULT_RCCG_INTERVAL,
                raise_exception=True)
        except Exception as ex:
            LOG.error('_wait_replica_grp_ready: wait for group %(rccg)s '
                      'synchronization failed due to '
                      'error: %(err)s.', {'rccg': rccg_name,
                                          'err': ex})

    def get_replication_error_status(self, context, groups):
        """Returns error info for replicated groups and its volumes.

        The failover/failback only happens manually, no need to update the
        status.
        """
        return [], []

    def _get_vol_sys_info(self, volume):
        tgt_vol = volume.name
        backend_helper = self._helpers
        node_state = self._state
        grp = volume.group
        if grp and volume_utils.is_group_a_type(
                grp, "consistent_group_replication_enabled"):
            if (grp.replication_status ==
                    fields.ReplicationStatus.FAILED_OVER):
                tgt_vol = (storwize_const.REPLICA_AUX_VOL_PREFIX +
                           volume.name)
                backend_helper = self._aux_backend_helpers
                node_state = self._aux_state
            else:
                backend_helper = self._master_backend_helpers
                node_state = self._master_state
        elif self._active_backend_id:
            ctxt = context.get_admin_context()
            rep_type = self._get_volume_replicated_type(ctxt, volume)
            if rep_type:
                tgt_vol = (storwize_const.REPLICA_AUX_VOL_PREFIX +
                           volume.name)

        return tgt_vol, backend_helper, node_state

    def _toggle_rep_vol_info(self, volume, helper):
        if helper == self._master_backend_helpers:
            vol_name = storwize_const.REPLICA_AUX_VOL_PREFIX + volume.name
            backend_helper = self._aux_backend_helpers
            node_state = self._aux_state
        else:
            vol_name = volume.name
            backend_helper = self._master_backend_helpers
            node_state = self._master_state
        return vol_name, backend_helper, node_state

    def _get_map_info_from_connector(self, volume, connector, iscsi=False):
        if volume.display_name == 'backup-snapshot':
            LOG.debug('It is a virtual volume %(vol)s for detach snapshot.',
                      {'vol': volume.id})
            vol_name = volume.name
            backend_helper = self._helpers
            node_state = self._state
        else:
            vol_name, backend_helper, node_state = self._get_vol_sys_info(
                volume)

        backend_helper.initialize_host_info()

        info = {}
        if 'host' in connector:
            # get host according to FC protocol
            connector = connector.copy()
            if not iscsi:
                connector.pop('initiator', None)
                info = {'driver_volume_type': 'fibre_channel',
                        'data': {}}
            else:
                info = {'driver_volume_type': 'iscsi',
                        'data': {}}
            host_name = backend_helper.get_host_from_connector(
                connector, volume_name=vol_name, iscsi=iscsi)
            vol_mapped = backend_helper.check_vol_mapped_to_host(vol_name,
                                                                 host_name)
            if host_name is None or not vol_mapped:
                ctxt = context.get_admin_context()
                rep_type = self._get_volume_replicated_type(ctxt, volume)
                if host_name is None and not rep_type:
                    msg = (_('_get_map_info_from_connector: Failed to get '
                             'host name from connector.'))
                    LOG.error(msg)
                    raise exception.VolumeDriverException(message=msg)
                if rep_type:
                    # Try to unmap the volume in the secondary side if it is a
                    # replication volume.
                    (vol_name, backend_helper,
                     node_state) = self._toggle_rep_vol_info(volume,
                                                             backend_helper)
                    try:
                        host_name = backend_helper.get_host_from_connector(
                            connector, volume_name=vol_name, iscsi=iscsi)
                    except Exception as ex:
                        LOG.warning('Failed to get host mapping for volume '
                                    '%(volume)s in the secondary side. '
                                    'Exception: %(err)s.',
                                    {'volume': vol_name, 'err': ex})
                        return info, None, None, None, None
                    if host_name is None:
                        msg = (_('_get_map_info_from_connector: Failed to get '
                                 'host name from connector.'))
                        LOG.error(msg)
                        raise exception.VolumeDriverException(message=msg)
        else:
            host_name = None

        return info, host_name, vol_name, backend_helper, node_state

    def _check_snapshot_replica_volume_status(self, snapshot):
        ctxt = context.get_admin_context()
        if self._get_volume_replicated_type(ctxt, None,
                                            snapshot.volume_type_id):
            LOG.debug('It is a replication volume snapshot for backup.')
            rep_volume = objects.Volume.get_by_id(ctxt, snapshot.volume_id)
            volume_name, backend_helper, node_state = self._get_vol_sys_info(
                rep_volume)
            if backend_helper != self._helpers or self._active_backend_id:
                msg = (_('The snapshot of the replication volume %s has '
                         'failed over to the aux backend. It can not attach'
                         ' to the aux backend.') % volume_name)
                LOG.error(msg)
                raise exception.VolumeDriverException(message=msg)

    def migrate_volume(self, ctxt, volume, host):
        """Migrate directly if source and dest are managed by same storage.

        We create a new vdisk copy in the desired pool, and add the original
        vdisk copy to the admin_metadata of the volume to be deleted. The
        deletion will occur using a periodic task once the new copy is synced.

        :param ctxt: Context
        :param volume: A dictionary describing the volume to migrate
        :param host: A dictionary describing the host to migrate to, where
                     host['host'] is its name, and host['capabilities'] is a
                     dictionary of its reported capabilities.
        """
        LOG.debug('enter: migrate_volume: id=%(id)s, host=%(host)s',
                  {'id': volume['id'], 'host': host['host']})

        # hyperswap volume doesn't support migrate
        if self.is_volume_hyperswap(volume):
            msg = _('migrate_volume: Migrating a hyperswap volume is '
                    'not supported.')
            LOG.error(msg)
            raise exception.InvalidInput(message=msg)

        false_ret = (False, None)
        dest_pool = self._helpers.can_migrate_to_host(host, self._state)
        if dest_pool is None:
            return false_ret

        ctxt = context.get_admin_context()
        volume_type_id = volume['volume_type_id']
        if volume_type_id is not None:
            vol_type = volume_types.get_volume_type(ctxt, volume_type_id)
        else:
            vol_type = None

        resp = self._helpers.lsvdiskcopy(volume.name)
        if len(resp) > 1:
            copies = self._helpers.get_vdisk_copies(volume.name)
            src_pool = copies['primary']['mdisk_grp_name']
            mirror_pool = copies['secondary']['mdisk_grp_name']
            opts = self._get_vdisk_params(volume.volume_type_id)
            if opts['rsize'] != -1:
                if (self._helpers.is_data_reduction_pool(src_pool) or
                        self._helpers.is_data_reduction_pool(mirror_pool)):
                    msg = _('Unable to migrate: the thin-provisioned or '
                            'compressed volume can not be migrated from a data'
                            ' reduction pool. ')
                    raise exception.VolumeDriverException(message=msg)
                elif self._helpers.is_data_reduction_pool(dest_pool):
                    msg = _('Unable to migrate: the thin-provisioned or '
                            'compressed volume can not be migrated to a data '
                            'reduction pool.')
                    raise exception.VolumeDriverException(message=msg)
            self._helpers.migratevdisk(volume.name, dest_pool,
                                       copies['primary']['copy_id'])
        else:
            self._check_volume_copy_ops()
            if self._state['code_level'] < (7, 6, 0, 0):
                new_op = self.add_vdisk_copy(volume.name, dest_pool,
                                             vol_type)
                self._add_vdisk_copy_op(ctxt, volume, new_op)
            else:
                self.add_vdisk_copy(volume.name, dest_pool, vol_type,
                                    auto_delete=True)

        LOG.debug('leave: migrate_volume: id=%(id)s, host=%(host)s',
                  {'id': volume.id, 'host': host['host']})
        return (True, None)

    def _verify_iogrp(self, rsize, pool, opts, rep_type, status):
        if rsize != -1 and self._helpers.is_volume_type_dr_pools(
                pool, opts, rep_type, rep_target_pool=self._replica_target[
                    'pool_name'] if rep_type else None):
            msg = _('Unable to retype: the thin-provisioned or compressed '
                    'vol in data reduction pool can not modify iogrp.')
            raise exception.VolumeDriverException(message=msg)

    def _verify_retype_params(self, volume, new_opts, old_opts, need_copy,
                              change_mirror, new_rep_type, old_rep_type,
                              vdisk_changes, old_pool, new_pool, old_io_grp):
        # Some volume parameters can not be changed or changed at the same
        # time during volume retype operation. This function checks the
        # retype parameters.
        resp = self._helpers.lsvdiskcopy(volume.name)
        if old_opts['mirror_pool'] and len(resp) == 1:
            msg = (_('Unable to retype: volume %s is a mirrorred vol. But it '
                     'has only one copy in storage.') % volume.name)
            raise exception.VolumeDriverException(message=msg)

        is_old_type_dr_pool = self._helpers.is_volume_type_dr_pools(
            old_pool, old_opts, old_rep_type,
            rep_target_pool=self._replica_target[
                'pool_name'] if old_rep_type else None)
        is_new_type_dr_pool = self._helpers.is_volume_type_dr_pools(
            new_pool, new_opts, new_rep_type,
            rep_target_pool=self._replica_target[
                'pool_name'] if new_rep_type else None)
        need_check_dr_pool_param = False

        if need_copy:
            # mirror volume can not add volume-copy again.
            if len(resp) > 1:
                msg = (_('Unable to retype: current action needs volume-copy. '
                         'A copy of volume %s exists. Adding another copy '
                         'would exceed the limit of 2 copies.') % volume.name)
                raise exception.VolumeDriverException(message=msg)
            if old_opts['mirror_pool'] or new_opts['mirror_pool']:
                msg = (_('Unable to retype: current action needs volume-copy, '
                         'it is not allowed for mirror volume '
                         '%s.') % volume.name)
                raise exception.VolumeDriverException(message=msg)
            need_check_dr_pool_param = True

        if change_mirror:
            if (new_opts['mirror_pool'] and
                    not self._helpers.is_pool_defined(
                        new_opts['mirror_pool'])):
                msg = (_('Unable to retype: The pool %s in which mirror copy '
                         'is stored is not valid') % new_opts['mirror_pool'])
                raise exception.VolumeDriverException(message=msg)
            # migrate second copy to a dr pool or from a dr pool is not allowed
            if (old_opts['mirror_pool'] and new_opts[
                    'mirror_pool'] and old_opts['rsize'] != -1):
                if is_old_type_dr_pool or is_new_type_dr_pool:
                    msg = _('Unable to retype: the thin-provisioned or '
                            'compressed vol can not be migrated from a dr pool'
                            ' or to a dr pool.')
                    raise exception.VolumeDriverException(message=msg)
            if not old_opts['mirror_pool'] and new_opts['mirror_pool']:
                need_check_dr_pool_param = True

        if new_rep_type != old_rep_type:
            if (old_io_grp not in
                    StorwizeHelpers._get_valid_requested_io_groups(
                        self._state, new_opts)):
                msg = (_('Unable to retype: it is not allowed to change '
                         'replication type and io group at the same time.'))
                LOG.error(msg)
                raise exception.VolumeDriverException(message=msg)
            if new_rep_type and old_rep_type:
                msg = (_('Unable to retype: it is not allowed to change '
                         '%(old_rep_type)s volume to %(new_rep_type)s '
                         'volume.') %
                       {'old_rep_type': old_rep_type,
                        'new_rep_type': new_rep_type})
                LOG.error(msg)
                raise exception.VolumeDriverException(message=msg)
            if not old_rep_type and new_rep_type:
                if new_opts['rsize'] != -1 and is_new_type_dr_pool:
                    try:
                        self._helpers.check_data_reduction_pool_params(
                            new_opts)
                    except Exception as err:
                        msg = (_("Failed to retype volume, the error is "
                                 "%s") % err)
                        raise exception.VolumeDriverException(message=msg)
        elif storwize_const.GMCV == new_rep_type:
            # To gmcv, we may change cycle_period_seconds if needed
            previous_cps = old_opts.get('cycle_period_seconds')
            new_cps = new_opts.get('cycle_period_seconds')
            if previous_cps != new_cps:
                self._helpers.change_relationship_cycleperiod(volume.name,
                                                              new_cps)

        if (is_new_type_dr_pool and new_opts[
                'rsize'] != -1 and need_check_dr_pool_param == 1):
            try:
                self._helpers.check_data_reduction_pool_params(new_opts)
            except Exception as err:
                msg = (_("Failed to retype volume, the error is "
                         "%s") % err)
                raise exception.VolumeDriverException(message=msg)

        if vdisk_changes and not need_copy:
            if is_old_type_dr_pool or is_new_type_dr_pool:
                msg = _('The volume specified is a thin or compressed volume '
                        'in a data reduction pool. The autoexpand and warning'
                        ' and easytier can not be changed.')
                raise exception.VolumeDriverException(message=msg)

    def _check_hyperswap_retype_params(self, volume, new_opts, old_opts,
                                       change_mirror, new_rep_type,
                                       old_rep_type, old_pool,
                                       new_pool, old_io_grp):
        if new_opts['mirror_pool'] or old_opts['mirror_pool']:
            msg = (_('Unable to retype volume %s: current action needs '
                     'volume-copy, it is not allowed for hyperswap '
                     'type.') % volume.name)
            LOG.error(msg)
            raise exception.InvalidInput(message=msg)
        if new_rep_type or old_rep_type:
            msg = _('Retype between replicated volume and hyperswap volume'
                    ' is not allowed.')
            LOG.error(msg)
            raise exception.InvalidInput(message=msg)
        if (old_io_grp not in
                StorwizeHelpers._get_valid_requested_io_groups(
                    self._state, new_opts)):
            msg = _('Unable to retype: it is not allowed to change '
                    'hyperswap type and IO group at the same time.')
            LOG.error(msg)
            raise exception.InvalidInput(message=msg)
        if new_opts['volume_topology'] == 'hyperswap':
            if old_pool != new_pool:
                msg = (_('Unable to retype volume %s: current action needs '
                         'volume pool change, hyperswap volume does not '
                         'support pool change.') % volume.name)
                LOG.error(msg)
                raise exception.InvalidInput(message=msg)
            if not new_opts['easytier']:
                raise exception.InvalidInput(
                    reason=_('The default easytier of hyperswap volume is '
                             'on, it does not support easytier off.'))
            if old_opts['volume_topology'] != 'hyperswap':
                is_new_type_dr_pool = self._helpers.is_volume_type_dr_pools(
                    new_pool, new_opts)
                if is_new_type_dr_pool and new_opts['rsize'] != -1:
                    try:
                        self._helpers.check_data_reduction_pool_params(
                            new_opts)
                    except Exception as err:
                        msg = (_("Failed to retype volume, the error is "
                                 "%s") % err)
                        raise exception.VolumeDriverException(reason=msg)
                if self._helpers._get_vdisk_fc_mappings(volume.name):
                    msg = _('Unable to retype: it is not allowed to change a '
                            'normal volume with snapshot to a hyperswap '
                            'volume.')
                    LOG.error(msg)
                    raise exception.InvalidInput(message=msg)
            if (old_opts['volume_topology'] == 'hyperswap' and
                    old_opts['peer_pool'] != new_opts['peer_pool']):
                msg = _('Unable to retype: it is not allowed to change a '
                        'hyperswap volume peer_pool.')
                LOG.error(msg)
                raise exception.InvalidInput(message=msg)

    def _retype_hyperswap_volume(self, ctxt, volume, host, old_opts,
                                 new_opts, old_pool, new_pool, vdisk_changes,
                                 need_copy, new_type):
        if (old_opts['volume_topology'] != 'hyperswap' and
                new_opts['volume_topology'] == 'hyperswap'):
            LOG.debug('retype: Convert a normal volume %s to hyperswap '
                      'volume.', volume.name)
            self._helpers.convert_volume_to_hyperswap(volume.name,
                                                      new_opts,
                                                      self._state)
        elif (old_opts['volume_topology'] == 'hyperswap' and
                new_opts['volume_topology'] != 'hyperswap'):
            LOG.debug('retype: Convert a hyperswap volume %s to normal '
                      'volume.', volume.name)
            if new_pool == old_pool:
                self._helpers.convert_hyperswap_volume_to_normal(
                    volume.name,
                    old_opts['peer_pool'])
            elif new_pool == old_opts['peer_pool']:
                self._helpers.convert_hyperswap_volume_to_normal(
                    volume.name,
                    old_pool)
        else:
            rel_info = self._helpers.get_relationship_info(volume.name)
            aux_vdisk = rel_info['aux_vdisk_name']
            if need_copy:
                self.add_vdisk_copy(aux_vdisk, old_opts['peer_pool'], new_type,
                                    auto_delete=True)
            elif vdisk_changes:
                self._helpers.change_vdisk_options(aux_vdisk,
                                                   vdisk_changes,
                                                   new_opts, self._state)
        if need_copy:
            self.add_vdisk_copy(volume.name, old_pool, new_type,
                                auto_delete=True)
        elif vdisk_changes:
            self._helpers.change_vdisk_options(volume.name,
                                               vdisk_changes,
                                               new_opts, self._state)

    def retype(self, ctxt, volume, new_type, diff, host):
        """Convert the volume to be of the new type.

        Returns a boolean indicating whether the retype occurred.

        :param ctxt: Context
        :param volume: A dictionary describing the volume to migrate
        :param new_type: A dictionary describing the volume type to convert to
        :param diff: A dictionary with the difference between the two types
        :param host: A dictionary describing the host to migrate to, where
                     host['host'] is its name, and host['capabilities'] is a
                     dictionary of its reported capabilities.
        """
        def retype_iogrp_property(volume, new, old):
            if new != old:
                self._helpers.change_vdisk_iogrp(volume['name'],
                                                 self._state, (new, old))

        LOG.debug('enter: retype: id=%(id)s, new_type=%(new_type)s,'
                  'diff=%(diff)s, host=%(host)s', {'id': volume['id'],
                                                   'new_type': new_type,
                                                   'diff': diff,
                                                   'host': host})

        no_copy_keys = ['warning', 'autoexpand', 'easytier']
        copy_keys = ['rsize', 'grainsize', 'compression']
        all_keys = no_copy_keys + copy_keys
        old_opts = self._get_vdisk_params(volume['volume_type_id'],
                                          volume_metadata=
                                          volume.get('volume_metadata'))
        new_opts = self._get_vdisk_params(new_type['id'],
                                          volume_type=new_type)

        vdisk_changes = []
        need_copy = False
        change_mirror = False

        for key in all_keys:
            if old_opts[key] != new_opts[key]:
                if key in copy_keys:
                    need_copy = True
                    break
                elif key in no_copy_keys:
                    vdisk_changes.append(key)

        old_pool = volume_utils.extract_host(volume['host'], 'pool')
        new_pool = volume_utils.extract_host(host['host'], 'pool')
        if old_pool != new_pool:
            need_copy = True

        if old_opts['mirror_pool'] != new_opts['mirror_pool']:
            change_mirror = True

        # Check if retype affects volume replication
        model_update = dict()
        new_rep_type = self._get_specs_replicated_type(new_type)
        old_rep_type = self._get_volume_replicated_type(ctxt, volume)
        old_io_grp = self._helpers.get_volume_io_group(volume['name'])
        new_io_grp = self._helpers.select_io_group(self._state,
                                                   new_opts, new_pool)
        self._verify_retype_params(volume, new_opts, old_opts, need_copy,
                                   change_mirror, new_rep_type, old_rep_type,
                                   vdisk_changes, old_pool, new_pool,
                                   old_io_grp)

        if old_opts['volume_topology'] or new_opts['volume_topology']:
            self._check_hyperswap_retype_params(volume, new_opts, old_opts,
                                                change_mirror, new_rep_type,
                                                old_rep_type, old_pool,
                                                new_pool, old_io_grp)
            self._retype_hyperswap_volume(ctxt, volume, host, old_opts,
                                          new_opts, old_pool, new_pool,
                                          vdisk_changes, need_copy,
                                          new_type)
            # Updating Hyperswap volume replication properties
            model_update = self._update_replication_properties(ctxt, volume,
                                                               model_update)
        else:
            # hyperswap volume will select iogrp by storage. ignore iogrp here.
            if old_io_grp != new_io_grp:
                self._verify_iogrp(old_opts['rsize'], old_pool, old_opts,
                                   old_rep_type,
                                   volume.previous_status)
            if need_copy:
                self._check_volume_copy_ops()
                dest_pool = self._helpers.can_migrate_to_host(host,
                                                              self._state)
                if dest_pool is None:
                    return False

                retype_iogrp_property(volume,
                                      new_io_grp, old_io_grp)
                try:
                    if self._state['code_level'] < (7, 6, 0, 0):
                        new_op = self.add_vdisk_copy(volume.name, dest_pool,
                                                     new_type)
                        self._add_vdisk_copy_op(ctxt, volume, new_op)
                    else:
                        self.add_vdisk_copy(volume.name, dest_pool, new_type,
                                            auto_delete=True)
                except exception.VolumeDriverException:
                    # roll back changing iogrp property
                    retype_iogrp_property(volume, old_io_grp, new_io_grp)
                    msg = (_('Unable to retype: A copy of volume %s exists. '
                             'Retyping would exceed the limit of 2 copies.'),
                           volume['id'])
                    raise exception.VolumeDriverException(message=msg)
            else:
                retype_iogrp_property(volume, new_io_grp, old_io_grp)

                self._helpers.change_vdisk_options(volume['name'],
                                                   vdisk_changes,
                                                   new_opts, self._state)
                if change_mirror:
                    copies = self._helpers.get_vdisk_copies(volume.name)
                    if not old_opts['mirror_pool'] and new_opts['mirror_pool']:
                        # retype from non mirror vol to mirror vol
                        self.add_vdisk_copy(volume['name'],
                                            new_opts['mirror_pool'], new_type)
                    elif (old_opts['mirror_pool'] and
                            not new_opts['mirror_pool']):
                        # retype from mirror vol to non mirror vol
                        secondary = copies['secondary']
                        if secondary:
                            self._helpers.rm_vdisk_copy(
                                volume.name, secondary['copy_id'])
                    else:
                        # migrate the second copy to another pool.
                        self._helpers.migratevdisk(
                            volume.name, new_opts['mirror_pool'],
                            copies['secondary']['copy_id'])
        if new_opts['qos']:
            # Add the new QoS setting to the volume. If the volume has an
            # old QoS setting, it will be overwritten.
            self._helpers.update_vdisk_qos(volume['name'], new_opts['qos'],
                                           volume['size'])
            model_update = self._qos_model_update(model_update, volume)
        elif old_opts['qos']:
            # If the old_opts contain QoS keys, disable them.
            self._helpers.disable_vdisk_qos(volume['name'], old_opts['qos'])
            model_update = self._qos_model_update(model_update, volume)

        if new_opts['flashcopy_rate'] != old_opts['flashcopy_rate']:
            self._helpers.update_flashcopy_rate(volume.name,
                                                new_opts['flashcopy_rate'])

        if new_opts['clean_rate']:
            # Add the new clean_rate. If the old FC maps has the clean_rate
            # it will be overwritten.
            self._helpers.update_clean_rate(volume.name,
                                            new_opts['clean_rate'])

        # Delete replica if needed
        if self._state['code_level'] < (7, 7, 0, 0):
            force_unmap = False
        else:
            force_unmap = True

        if old_rep_type and not new_rep_type:
            target_volume, rel_info = (
                self._helpers.get_target_volume_information(volume))
            self._aux_backend_helpers.delete_rc_volume(
                target_volume,
                rel_info,
                target_vol=True,
                force_unmap=force_unmap,
                retain_aux_volume=self.configuration.safe_get(
                    'storwize_svc_retain_aux_volume'))
            if storwize_const.GMCV == old_rep_type:
                self._helpers.delete_vdisk(
                    storwize_const.REPLICA_CHG_VOL_PREFIX + volume['name'],
                    force_unmap=force_unmap, force_delete=False)
            model_update['replication_status'] = (
                fields.ReplicationStatus.DISABLED)
            model_update['replication_driver_data'] = None
            model_update['replication_extended_status'] = None
            # Updating replication properties for a volume with replication
            # enabled.
            model_update = self._update_replication_properties(ctxt, volume,
                                                               model_update)
        # Add replica if needed
        if not old_rep_type and new_rep_type:
            replica_obj = self._get_replica_obj(new_rep_type)
            if storwize_const.GMCV == new_rep_type:
                replica_obj.volume_replication_setup(ctxt, volume, new_type)
                # Set cycle_period_seconds if needed
                self._helpers.change_relationship_cycleperiod(
                    volume['name'],
                    new_opts.get('cycle_period_seconds'))
            else:
                replica_obj.volume_replication_setup(ctxt, volume)
            model_update['replication_status'] = (
                fields.ReplicationStatus.ENABLED)
            # Updating replication properties for a volume with replication
            # enabled.
            model_update = self._update_replication_properties(ctxt, volume,
                                                               model_update)

        LOG.debug('exit: retype: ild=%(id)s, new_type=%(new_type)s,'
                  'diff=%(diff)s, host=%(host)s', {'id': volume['id'],
                                                   'new_type': new_type,
                                                   'diff': diff,
                                                   'host': host['host']})
        return True, model_update

    def update_migrated_volume(self, ctxt, volume, new_volume,
                               original_volume_status):
        """Return model update from Storwize for migrated volume.

        This method should rename the back-end volume name(id) on the
        destination host back to its original name(id) on the source host.

        :param ctxt: The context used to run the method update_migrated_volume
        :param volume: The original volume that was migrated to this backend
        :param new_volume: The migration volume object that was created on
                           this backend as part of the migration process
        :param original_volume_status: The status of the original volume
        :returns: model_update to update DB with any needed changes
        """
        current_name = new_volume.name
        original_volume_name = volume.name
        LOG.debug("Attempt rename of %(cur)s to original name %(orig)s",
                  dict(cur=current_name, orig=original_volume_name))
        try:
            self._helpers.rename_vdisk(current_name, original_volume_name)
            rep_type = self._get_volume_replicated_type(ctxt, new_volume)
            if rep_type:
                rel_info = self._helpers.get_relationship_info(current_name)
                aux_vol = (storwize_const.REPLICA_AUX_VOL_PREFIX +
                           original_volume_name)
                self._aux_backend_helpers.rename_vdisk(
                    rel_info['aux_vdisk_name'], aux_vol)
        except exception.VolumeBackendAPIException:
            LOG.error('Unable to rename the logical volume '
                      'for volume: %s', volume['id'])
            return {'_name_id': new_volume['_name_id'] or new_volume['id']}
        # If the back-end name(id) for the volume has been renamed,
        # it is OK for the volume to keep the original name(id) and there is
        # no need to use the column "_name_id" to establish the mapping
        # relationship between the volume id and the back-end volume
        # name(id).
        # Set the key "_name_id" to None for a successful rename.
        model_update = {'_name_id': None}
        return model_update

    def manage_existing(self, volume, ref):
        """Manages an existing vdisk.

        Renames the vdisk to match the expected name for the volume.
        Error checking done by manage_existing_get_size is not repeated -
        if we got here then we have a vdisk that isn't in use (or we don't
        care if it is in use.
        """
        # Check that the reference is valid
        vdisk = self._manage_input_check(ref)
        vdisk_io_grp = self._helpers.get_volume_io_group(vdisk['name'])
        if vdisk_io_grp not in self._state['available_iogrps']:
            msg = (_("Failed to manage existing volume due to "
                     "the volume to be managed is not in a valid "
                     "I/O group."))
            raise exception.ManageExistingVolumeTypeMismatch(reason=msg)

        # Add replication check
        ctxt = context.get_admin_context()
        rep_type = self._get_volume_replicated_type(ctxt, volume)
        vol_rep_type = None
        rel_info = self._helpers.get_relationship_info(vdisk['name'])
        copies = self._helpers.get_vdisk_copies(vdisk['name'])
        if rel_info and rel_info['copy_type'] != 'activeactive':
            vol_rep_type = (
                storwize_const.GMCV if
                storwize_const.GMCV_MULTI == rel_info['cycling_mode']
                else rel_info['copy_type'])

            aux_info = self._aux_backend_helpers.get_system_info()
            if rel_info['aux_cluster_id'] != aux_info['system_id']:
                msg = (_("Failed to manage existing volume due to the aux "
                         "cluster for volume %(volume)s is %(aux_id)s. The "
                         "configured cluster id is %(cfg_id)s") %
                       {'volume': vdisk['name'],
                        'aux_id': rel_info['aux_cluster_id'],
                        'cfg_id': aux_info['system_id']})
                raise exception.ManageExistingVolumeTypeMismatch(reason=msg)

        if vol_rep_type != rep_type:
            msg = (_("Failed to manage existing volume due to "
                     "the replication type of the volume to be managed is "
                     "mismatch with the provided replication type."))
            raise exception.ManageExistingVolumeTypeMismatch(reason=msg)
        elif storwize_const.GMCV == rep_type:
            if volume['volume_type_id']:
                rep_opts = self._get_vdisk_params(
                    volume['volume_type_id'],
                    volume_metadata=volume.get('volume_metadata'))
                # Check cycle_period_seconds
                rep_cps = str(rep_opts.get('cycle_period_seconds'))
            if rel_info['cycle_period_seconds'] != rep_cps:
                msg = (_("Failed to manage existing volume due to "
                         "the cycle_period_seconds %(vol_cps)s of "
                         "the volume to be managed is mismatch with "
                         "cycle_period_seconds %(type_cps)s in "
                         "the provided gmcv replication type.") %
                       {'vol_cps': rel_info['cycle_period_seconds'],
                        'type_cps': rep_cps})
                raise exception.ManageExistingVolumeTypeMismatch(reason=msg)

        pool = volume_utils.extract_host(volume['host'], 'pool')
        if copies['primary']['mdisk_grp_name'] != pool:
            msg = (_("Failed to manage existing volume due to the "
                     "pool of the volume to be managed does not "
                     "match the backend pool. Pool of the "
                     "volume to be managed is %(vdisk_pool)s. Pool "
                     "of the backend is %(backend_pool)s.") %
                   {'vdisk_pool': copies['primary']['mdisk_grp_name'],
                    'backend_pool': pool})
            raise exception.ManageExistingVolumeTypeMismatch(reason=msg)

        if volume['volume_type_id']:
            opts = self._get_vdisk_params(volume['volume_type_id'],
                                          volume_metadata=
                                          volume.get('volume_metadata'))
            # Manage hyperswap volume
            if rel_info and rel_info['copy_type'] == 'activeactive':
                if opts['volume_topology'] != 'hyperswap':
                    msg = _("Failed to manage existing volume due to "
                            "the hyperswap volume to be managed is "
                            "mismatched with the provided non-hyperswap type.")
                    raise exception.ManageExistingVolumeTypeMismatch(
                        reason=msg)
                aux_vdisk = rel_info['aux_vdisk_name']
                aux_vol_attr = self._helpers.get_vdisk_attributes(aux_vdisk)
                peer_pool = aux_vol_attr['mdisk_grp_name']
                if opts['peer_pool'] != peer_pool:
                    msg = (_("Failed to manage existing hyperswap volume due "
                             "to peer pool mismatch. The peer pool of the "
                             "volume to be managed is %(vol_pool)s, but the "
                             "peer_pool of the chosen type is %(peer_pool)s.")
                           % {'vol_pool': peer_pool,
                              'peer_pool': opts['peer_pool']})
                    raise exception.ManageExistingVolumeTypeMismatch(
                        reason=msg)
            else:
                if opts['volume_topology'] == 'hyperswap':
                    msg = _("Failed to manage existing volume, the volume to "
                            "be managed is not a hyperswap volume, "
                            "mismatch with the provided hyperswap type.")
                    raise exception.ManageExistingVolumeTypeMismatch(
                        reason=msg)

            resp = self._helpers.lsvdiskcopy(vdisk['name'])
            expected_copy_num = 2 if opts['mirror_pool'] else 1
            if len(resp) != expected_copy_num:
                msg = (_("Failed to manage existing volume due to mirror type "
                         "mismatch. Volume to be managed has %(resp_len)s "
                         "copies. mirror_pool of the chosen type is "
                         "%(mirror_pool)s.") %
                       {'resp_len': len(resp),
                        'mirror_pool': opts['mirror_pool']})
                raise exception.ManageExistingVolumeTypeMismatch(reason=msg)
            if (opts['mirror_pool'] and opts['mirror_pool'] !=
                    copies['secondary']['mdisk_grp_name']):
                msg = (_("Failed to manage existing volume due to mirror pool "
                         "mismatch. The secondary pool of the volume to be "
                         "managed is %(sec_copy_pool)s. mirror_pool of the "
                         "chosen type is %(mirror_pool)s.") %
                       {'sec_copy_pool': copies['secondary']['mdisk_grp_name'],
                        'mirror_pool': opts['mirror_pool']})
                raise exception.ManageExistingVolumeTypeMismatch(
                    reason=msg)

            vdisk_copy = self._helpers.get_vdisk_copy_attrs(vdisk['name'], '0')
            if vdisk_copy['autoexpand'] == 'on' and opts['rsize'] == -1:
                msg = (_("Failed to manage existing volume due to "
                         "the volume to be managed is thin, but "
                         "the volume type chosen is thick."))
                raise exception.ManageExistingVolumeTypeMismatch(reason=msg)

            if not vdisk_copy['autoexpand'] and opts['rsize'] != -1:
                msg = (_("Failed to manage existing volume due to "
                         "the volume to be managed is thick, but "
                         "the volume type chosen is thin."))
                raise exception.ManageExistingVolumeTypeMismatch(reason=msg)

            if (vdisk_copy['compressed_copy'] == 'no' and
                    opts['compression']):
                msg = (_("Failed to manage existing volume due to the "
                         "volume to be managed is not compress, but "
                         "the volume type chosen is compress."))
                raise exception.ManageExistingVolumeTypeMismatch(reason=msg)

            if (vdisk_copy['compressed_copy'] == 'yes' and
                    not opts['compression']):
                msg = (_("Failed to manage existing volume due to the "
                         "volume to be managed is compress, but "
                         "the volume type chosen is not compress."))
                raise exception.ManageExistingVolumeTypeMismatch(reason=msg)

            if (vdisk_io_grp not in
                    StorwizeHelpers._get_valid_requested_io_groups(
                        self._state, opts)):
                msg = (_("Failed to manage existing volume due to "
                         "I/O group mismatch. The I/O group of the "
                         "volume to be managed is %(vdisk_iogrp)s. I/O group"
                         " of the chosen type is %(opt_iogrp)s.") %
                       {'vdisk_iogrp': vdisk['IO_group_name'],
                        'opt_iogrp': opts['iogrp']})
                raise exception.ManageExistingVolumeTypeMismatch(reason=msg)

            if opts['rsize'] != -1 and self._helpers.is_volume_type_dr_pools(
                    pool, opts, rep_type, rep_target_pool=self._replica_target[
                        'pool_name'] if rep_type else None):
                try:
                    self._helpers.check_data_reduction_pool_params(opts)
                except Exception as err:
                    msg = (_("Failed to manage existing volume, the error is "
                             "%s") % err)
                    raise exception.ManageExistingVolumeTypeMismatch(
                        reason=msg)
        model_update = {'replication_status':
                        fields.ReplicationStatus.NOT_CAPABLE}
        self._helpers.rename_vdisk(vdisk['name'], volume['name'])
        if vol_rep_type:
            aux_vol = storwize_const.REPLICA_AUX_VOL_PREFIX + volume['name']
            self._aux_backend_helpers.rename_vdisk(rel_info['aux_vdisk_name'],
                                                   aux_vol)
            if storwize_const.GMCV == vol_rep_type:
                self._helpers.rename_vdisk(
                    rel_info['master_change_vdisk_name'],
                    storwize_const.REPLICA_CHG_VOL_PREFIX + volume['name'])
                self._aux_backend_helpers.rename_vdisk(
                    rel_info['aux_change_vdisk_name'],
                    storwize_const.REPLICA_CHG_VOL_PREFIX + aux_vol)
            model_update = {'replication_status':
                            fields.ReplicationStatus.ENABLED}
        return model_update

    def manage_existing_get_size(self, volume, ref):
        """Return size of an existing Vdisk for manage_existing.

        existing_ref is a dictionary of the form:
        {'source-id': <uid of disk>} or
        {'source-name': <name of the disk>}

        Optional elements are:
          'manage_if_in_use':  True/False (default is False)
            If set to True, a volume will be managed even if it is currently
            attached to a host system.
        """

        # Check that the reference is valid
        vdisk = self._manage_input_check(ref)

        # Check if the disk is in use, if we need to.
        manage_if_in_use = ref.get('manage_if_in_use', False)
        if (not manage_if_in_use and
                self._helpers.is_vdisk_in_use(vdisk['name'])):
            reason = _('The specified vdisk is mapped to a host.')
            raise exception.ManageExistingInvalidReference(existing_ref=ref,
                                                           reason=reason)

        return int(math.ceil(float(vdisk['capacity']) / units.Gi))

    def unmanage(self, volume):
        """Remove the specified volume from Cinder management."""
        pass

    @staticmethod
    def _get_rccg_name(group, grp_id=None, hyper_grp=False):
        group_id = group.id if group else grp_id
        rccg = (storwize_const.HYPERCG_PREFIX
                if hyper_grp else storwize_const.RCCG_PREFIX)
        return rccg + group_id[0:4] + '-' + group_id[-5:]

    @staticmethod
    def _get_volumegroup_name(group, grp_id=None):
        group_id = group.id if group else grp_id
        vg = storwize_const.VG_PREFIX
        return vg + group_id[0:4] + '-' + group_id[-5:]

    @staticmethod
    def _get_volumegroup_snapshot_name(group_snapshot, grp_snapshot_id=None):
        group_snapshot_id = (
            group_snapshot.id if group_snapshot else grp_snapshot_id)
        vg_snapshot = storwize_const.VG_SNAPSHOT_PREFIX
        return vg_snapshot + group_snapshot_id

    # Add CG capability to generic volume groups
    def create_group(self, context, group):
        """Creates a group.

        :param context: the context of the caller.
        :param group: the group object.
        :returns: model_update
        """
        LOG.debug("Creating group.")

        model_update = {'status': fields.GroupStatus.AVAILABLE}
        group_type = objects.GroupType.get_by_id(context, group.group_type_id)
        if len(group_type.group_specs) > 1:
            LOG.error('Unable to create group: create group with mixed specs '
                      '%s is not supported.', group_type.group_specs)
            model_update = {'status': fields.GroupStatus.ERROR}
            return model_update

        support_grps = ['group_snapshot_enabled',
                        'consistent_group_snapshot_enabled',
                        'consistent_group_replication_enabled',
                        'hyperswap_group_enabled',
                        'volume_group_enabled']
        supported_grp = False
        for grp_spec in support_grps:
            if volume_utils.is_group_a_type(group, grp_spec):
                supported_grp = True
                break
        if not supported_grp:
            LOG.error('Unable to create group: %s is not a supported group '
                      'type.', group.group_type_id)
            model_update = {'status': fields.GroupStatus.ERROR}
            return model_update

        if (volume_utils.is_group_a_cg_snapshot_type(group) or
                volume_utils.is_group_a_type(group, "group_snapshot_enabled")):
            for vol_type_id in group.volume_type_ids:
                replication_type = self._get_volume_replicated_type(
                    context, None, vol_type_id)
                if replication_type:
                    # An unsupported configuration
                    LOG.error('Unable to create group: create consistent '
                              'snapshot group with replication volume type is '
                              'not supported.')
                    model_update = {'status': fields.GroupStatus.ERROR}
                    return model_update
                opts = self._get_vdisk_params(vol_type_id)
                if opts['volume_topology']:
                    # An unsupported configuration
                    LOG.error('Unable to create group: create consistent '
                              'snapshot group with a hyperswap volume type'
                              ' is not supported.')
                    model_update = {'status': fields.GroupStatus.ERROR}
                    return model_update

        # We'll rely on the generic group implementation if it is
        # a non-consistent snapshot group.
        if volume_utils.is_group_a_type(group, "group_snapshot_enabled"):
            raise NotImplementedError()

        if volume_utils.is_group_a_type(
                group, "consistent_group_replication_enabled"):
            self._validate_replication_enabled()
            rccg_type = None
            for vol_type_id in group.volume_type_ids:
                replication_type = self._get_volume_replicated_type(
                    context, None, vol_type_id)
                if not replication_type:
                    # An unsupported configuration
                    LOG.error('Unable to create group: create consistent '
                              'replication group with non-replication volume'
                              ' type is not supported.')
                    model_update = {'status': fields.GroupStatus.ERROR}
                    return model_update
                if not rccg_type:
                    rccg_type = replication_type
                elif rccg_type != replication_type:
                    # An unsupported configuration
                    LOG.error('Unable to create group: create consistent '
                              'replication group with different replication '
                              'types is not supported.')
                    model_update = {'status': fields.GroupStatus.ERROR}
                    return model_update
            rccg_name = self._get_rccg_name(group)
            try:
                tgt_sys = self._aux_backend_helpers.get_system_info()
                self._helpers.create_rccg(
                    rccg_name, tgt_sys.get('system_id'))
                model_update.update({'replication_status':
                                    fields.ReplicationStatus.ENABLED})
            except exception.VolumeBackendAPIException as err:
                LOG.error("Failed to create rccg  %(rccg)s. "
                          "Exception: %(exception)s.",
                          {'rccg': rccg_name, 'exception': err})
                model_update = {'status': fields.GroupStatus.ERROR}
            return model_update

        if volume_utils.is_group_a_type(group, "hyperswap_group_enabled"):
            if not self._helpers.is_system_topology_hyperswap(self._state):
                LOG.error('Unable to create group: create group on '
                          'a system that does not support hyperswap.')
                model_update = {'status': fields.GroupStatus.ERROR}

            for vol_type_id in group.volume_type_ids:
                opts = self._get_vdisk_params(vol_type_id)
                if not opts['volume_topology']:
                    # An unsupported configuration
                    LOG.error('Unable to create group: create consistent '
                              'hyperswap group with non-hyperswap volume'
                              ' type is not supported.')
                    model_update = {'status': fields.GroupStatus.ERROR}
                    return model_update

        storwize_volume_group = self.configuration.safe_get(
            'storwize_volume_group')
        LOG.info('CONFIG:value of storwize_volume_group'
                 ' is %s', storwize_volume_group)

        if volume_utils.is_group_a_type(group, "volume_group_enabled"):
            if storwize_volume_group:
                try:
                    self._helpers.check_codelevel_for_volumegroup(
                        self._state['code_level'])
                    for vol_type_id in group.volume_type_ids:
                        replication_type = self._get_volume_replicated_type(
                            context, None, vol_type_id)
                        if replication_type:
                            # An unsupported configuration
                            LOG.error('Unable to create group: '
                                      'volume_group_enabled group with '
                                      'replication volume type is '
                                      'not supported.')
                            model_update = {'status': fields.GroupStatus.ERROR}
                            return model_update
                        opts = self._get_vdisk_params(vol_type_id)
                        if opts['volume_topology']:
                            # An unsupported configuration
                            LOG.error('Unable to create group: '
                                      'volume_group_enabled group with a '
                                      'hyperswap volume type is '
                                      'not supported.')
                            model_update = {'status': fields.GroupStatus.ERROR}
                            return model_update
                    volumegroup_name = self._get_volumegroup_name(group)
                    self._helpers.create_volumegroup(volumegroup_name)
                except exception.VolumeBackendAPIException as err:
                    LOG.error("Failed to create volume group %(volumegroup)s. "
                              "Exception: %(exception)s.",
                              {'volumegroup': volumegroup_name,
                                  'exception': err})
                    model_update = {'status': fields.GroupStatus.ERROR}
                    return model_update
            else:
                LOG.error('Unable to create group: Error creating volume group'
                          ' with storwize_volume_group value set to False'
                          ' in the configuration.')
                model_update = {'status': fields.GroupStatus.ERROR}
                return model_update

        return model_update

    def delete_group(self, context, group, volumes):
        """Deletes a group.

        :param context: the context of the caller.
        :param group: the group object.
        :param volumes: a list of volume objects in the group.
        :returns: model_update, volumes_model_update
        """
        LOG.debug("Deleting group.")

        # we'll rely on the generic group implementation if it is
        # not a consistency group and not a consistency replication
        # request and not a hyperswap group request.
        if (not volume_utils.is_group_a_cg_snapshot_type(group) and not
                volume_utils.is_group_a_type(
                    group,
                    "consistent_group_replication_enabled")
                and not volume_utils.is_group_a_type(
                    group,
                    "hyperswap_group_enabled")
                and not volume_utils.is_group_a_type(
                    group,
                    "volume_group_enabled")):
            raise NotImplementedError()

        model_update = {'status': fields.GroupStatus.DELETED}
        volumes_model_update = []
        if volume_utils.is_group_a_type(
                group, "consistent_group_replication_enabled"):
            model_update, volumes_model_update = self._delete_replication_grp(
                group, volumes)

        elif volume_utils.is_group_a_type(group, "hyperswap_group_enabled"):
            model_update, volumes_model_update = self._delete_hyperswap_grp(
                group, volumes)

        elif volume_utils.is_group_a_type(group, "volume_group_enabled"):
            self._helpers.check_codelevel_for_volumegroup(
                self._state['code_level'])
            model_update, volumes_model_update = self._delete_volumegroup(
                group, volumes)

        else:
            for volume in volumes:
                try:
                    self._helpers.delete_vdisk(
                        volume['name'],
                        force_unmap=False,
                        force_delete=True)
                    volumes_model_update.append(
                        {'id': volume.id, 'status': 'deleted'})
                except exception.VolumeBackendAPIException as err:
                    model_update['status'] = (
                        fields.GroupStatus.ERROR_DELETING)
                    LOG.error("Failed to delete the volume %(vol)s of CG. "
                              "Exception: %(exception)s.",
                              {'vol': volume.name, 'exception': err})
                    volumes_model_update.append(
                        {'id': volume.id,
                         'status': fields.GroupStatus.ERROR_DELETING})

        return model_update, volumes_model_update

    def update_group(self, context, group, add_volumes=None,
                     remove_volumes=None):
        """Updates a group.

        :param context: the context of the caller.
        :param group: the group object.
        :param add_volumes: a list of volume objects to be added.
        :param remove_volumes: a list of volume objects to be removed.
        :returns: model_update, add_volumes_update, remove_volumes_update
        """

        LOG.debug("Updating group.")

        # we'll rely on the generic group implementation if it is not a
        # consistency group request and not consistency replication request
        # and not a hyperswap group request.
        if (not volume_utils.is_group_a_cg_snapshot_type(group) and not
                volume_utils.is_group_a_type(
                    group,
                    "consistent_group_replication_enabled")
                and not volume_utils.is_group_a_type(
                    group,
                    "hyperswap_group_enabled")
                and not volume_utils.is_group_a_type(
                    group,
                    "volume_group_enabled")):
            raise NotImplementedError()

        if volume_utils.is_group_a_type(
                group, "consistent_group_replication_enabled"):
            return self._update_replication_grp(context, group, add_volumes,
                                                remove_volumes)

        if volume_utils.is_group_a_type(group, "hyperswap_group_enabled"):
            return self._update_hyperswap_group(context, group,
                                                add_volumes, remove_volumes)

        if volume_utils.is_group_a_cg_snapshot_type(group):
            return None, None, None

        if volume_utils.is_group_a_type(group, "volume_group_enabled"):
            self._helpers.check_codelevel_for_volumegroup(
                self._state['code_level'])
            return self._update_volumegroup(context, group, add_volumes,
                                            remove_volumes)

    def create_group_from_src(self, context, group, volumes,
                              group_snapshot=None, snapshots=None,
                              source_group=None, source_vols=None):
        """Creates a group from source.

        :param context: the context of the caller.
        :param group: the Group object to be created.
        :param volumes: a list of Volume objects in the group.
        :param group_snapshot: the GroupSnapshot object as source.
        :param snapshots: a list of snapshot objects in group_snapshot.
        :param source_group: the Group object as source.
        :param source_vols: a list of volume objects in the source_group.
        :returns: model_update, volumes_model_update
        """
        LOG.debug('Enter: create_group_from_src.')

        is_hyper_group = False
        if volume_utils.is_group_a_type(group, "hyperswap_group_enabled"):
            is_hyper_group = True

        if (not volume_utils.is_group_a_cg_snapshot_type(group) and
                not volume_utils.is_group_a_type
                (group, "consistent_group_replication_enabled")
                and not volume_utils.is_group_a_type(
                group, "hyperswap_group_enabled")):
            # we'll rely on the generic volume groups implementation if it is
            # not a consistency group request.
            raise NotImplementedError()

        if group_snapshot and snapshots:
            cg_name = 'cg-' + group_snapshot.id
            sources = snapshots

        elif source_group and source_vols:
            cg_name = 'cg-' + source_group.id
            sources = source_vols

        else:
            error_msg = _("create_group_from_src must be creating from a "
                          "group snapshot, or a source group.")
            raise exception.InvalidInput(reason=error_msg)
        LOG.debug('create_group_from_src: cg_name %(cg_name)s'
                  ' %(sources)s', {'cg_name': cg_name, 'sources': sources})
        self._helpers.create_fc_consistgrp(cg_name)
        timeout = self.configuration.storwize_svc_flashcopy_timeout
        model_update, volumes_model = (
            self._helpers.create_cg_from_source(group,
                                                cg_name,
                                                sources,
                                                volumes,
                                                self._state,
                                                self.configuration,
                                                timeout))
        if volume_utils.is_group_a_type(
                group, "consistent_group_replication_enabled"):
            self._validate_replication_enabled()
            rccg_name = self._get_rccg_name(group)
            try:
                tgt_sys = self._aux_backend_helpers.get_system_info()
                self._helpers.create_rccg(rccg_name,
                                          tgt_sys.get('system_id'))
                model_update.update({'replication_status':
                                    fields.ReplicationStatus.ENABLED})
            except exception.VolumeBackendAPIException as err:
                LOG.error("Failed to create rccg  %(rccg)s. "
                          "Exception: %(exception)s.",
                          {'rccg': rccg_name, 'exception': err})
                model_update = {'status': fields.GroupStatus.ERROR}

        for vol in volumes:
            rep_type = self._get_volume_replicated_type(context,
                                                        vol)
            volume_model = dict()
            for model in volumes_model:
                if vol.id == model["id"]:
                    volume_model = model
                    break
            if rep_type:
                replica_obj = self._get_replica_obj(rep_type)
                replica_obj.volume_replication_setup(context, vol)
                volume_model['replication_status'] = (
                    fields.ReplicationStatus.ENABLED)
                # Updating replication properties for a volume with replication
                # enabled.
                self._update_replication_properties(context, vol,
                                                    volume_model)

            opts = self._get_vdisk_params(vol['volume_type_id'],
                                          volume_metadata=
                                          vol.get('volume_metadata'))
            if opts['qos']:
                # Updating QoS properties for a volume
                self._helpers.add_vdisk_qos(vol['name'], opts['qos'],
                                            vol['size'])
                self._qos_model_update(volume_model, vol)

            if is_hyper_group:
                self._helpers.ensure_vdisk_no_fc_mappings(vol['name'],
                                                          allow_snaps=True,
                                                          allow_fctgt=False)
                opts = self._get_vdisk_params(vol['volume_type_id'],
                                              volume_metadata=
                                              vol.get('volume_metadata'))
                self._helpers.convert_volume_to_hyperswap(vol['name'],
                                                          opts,
                                                          self._state)

        if volume_utils.is_group_a_type(
                group, "consistent_group_replication_enabled"):
            model_update, added_vols, removed_vols = (
                self._update_replication_grp(context, group, volumes, []))
            if model_update.get('status') != fields.GroupStatus.ERROR:
                # Updating RCCG property to volume metadata
                for model in volumes_model:
                    model['metadata']['Consistency Group Name'] = rccg_name

        LOG.debug("Leave: create_group_from_src.")
        return model_update, volumes_model

    def create_group_snapshot(self, context, group_snapshot, snapshots):
        """Creates a group_snapshot.

        :param context: the context of the caller.
        :param group_snapshot: the GroupSnapshot object to be created.
        :param snapshots: a list of Snapshot objects in the group_snapshot.
        :returns: model_update, snapshots_model_update
        """

        if (volume_utils.is_group_a_cg_snapshot_type(group_snapshot) or
                volume_utils.is_group_a_type
                (group_snapshot, "consistent_group_replication_enabled")
                or volume_utils.is_group_a_type(
                group_snapshot, "hyperswap_group_enabled")):
            # Use group_snapshot id as cg name
            cg_name = 'cg_snap-' + group_snapshot.id
            # Create new cg as cg_snapshot
            self._helpers.create_fc_consistgrp(cg_name)

            timeout = self.configuration.storwize_svc_flashcopy_timeout

            model_update, snapshots_model = (
                self._helpers.run_consistgrp_snapshots(cg_name,
                                                       snapshots,
                                                       self._state,
                                                       self.configuration,
                                                       timeout))
        elif volume_utils.is_group_a_type(
                group_snapshot, "volume_group_enabled"):
            try:
                self._helpers.check_codelevel_for_volumegroup(
                    self._state['code_level'])
                params = dict()
                # Use group_snapshot id as volumegroup name
                volumegroup_snapshot_name = (
                    self._get_volumegroup_snapshot_name(group_snapshot))
                params["name"] = volumegroup_snapshot_name
                volumegroup_name = self._get_volumegroup_name(
                    None, grp_id=group_snapshot.group_id)
                params["volumegroup"] = volumegroup_name
                model_update = {'status': fields.GroupSnapshotStatus.AVAILABLE}
                snapshots_model = []
                self._helpers.create_volumegroup_snapshot(params)
            except exception.VolumeBackendAPIException as err:
                model_update['status'] = fields.GroupSnapshotStatus.ERROR
                LOG.error("Failed to create VolumeGroup Snapshot. "
                          "Exception: %s.", err)
            for snapshot in snapshots:
                self._update_volumegroup_snapshot_properties(
                    context, snapshot, group_snapshot)
                snapshots_model.append(
                    {'id': snapshot['id'],
                     'status': model_update['status'],
                     'replication_status': fields.ReplicationStatus.NOT_CAPABLE
                     })
        else:
            # we'll rely on the generic group implementation if it is not a
            # consistency group/volumegroup request.
            raise NotImplementedError()

        return model_update, snapshots_model

    def delete_group_snapshot(self, context, group_snapshot, snapshots):
        """Deletes a group_snapshot.

        :param context: the context of the caller.
        :param group_snapshot: the GroupSnapshot object to be deleted.
        :param snapshots: a list of snapshot objects in the group_snapshot.
        :returns: model_update, snapshots_model_update
        """

        if (volume_utils.is_group_a_cg_snapshot_type(group_snapshot) or
                volume_utils.is_group_a_type(
                group_snapshot, "hyperswap_group_enabled")):

            cgsnapshot_id = group_snapshot.id
            cg_name = 'cg_snap-' + cgsnapshot_id

            model_update, snapshots_model = (
                self._helpers.delete_consistgrp_snapshots(cg_name,
                                                          snapshots))
        elif volume_utils.is_group_a_type(
                group_snapshot, "volume_group_enabled"):
            try:
                self._helpers.check_codelevel_for_volumegroup(
                    self._state['code_level'])
                params = dict()
                volumegroup_snapshot_name = (
                    self._get_volumegroup_snapshot_name(group_snapshot))
                params["name"] = volumegroup_snapshot_name
                volumegroup_name = self._get_volumegroup_name(
                    None, grp_id=group_snapshot.group_id)
                params["volumegroup"] = volumegroup_name
                model_update = {'status': fields.GroupSnapshotStatus.DELETED}
                snapshots_model = []
                self._helpers.delete_volumegroup_snapshot(params)
                for snapshot in snapshots:
                    self._update_volumegroup_snapshot_properties(
                        context, snapshot)
                    snapshots_model.append(
                        {'id': snapshot['id'],
                         'status': fields.GroupSnapshotStatus.DELETED})
            except exception.VolumeBackendAPIException as err:
                model_update['status'] = (
                    fields.GroupSnapshotStatus.ERROR_DELETING)
                for snapshot in snapshots:
                    snapshots_model.append(
                        {'id': snapshot['id'],
                         'status': fields.GroupSnapshotStatus.ERROR_DELETING})
                LOG.error("Failed to delete the volume_group_snapshot %(snap) "
                          "with Exception: %(exception)s.",
                          {'snap': group_snapshot.group_id, 'exception': err})

        else:
            # we'll rely on the generic group implementation if it is not a
            # consistency group/volumegroup request.
            raise NotImplementedError()

        return model_update, snapshots_model

    @volume_utils.trace
    def revert_to_snapshot(self, context, volume, snapshot):
        """Revert volume to snapshot."""
        if snapshot.volume_size != volume.size:
            raise exception.InvalidInput(
                reason=_('Reverting volume is not supported if the volume '
                         'size is not equal to the snapshot size.'))

        rep_type = self._get_volume_replicated_type(context, volume)

        if rep_type:
            try:
                rccg_name = self._helpers.get_rccg_name_by_volume_name(
                    volume.name)
                if rccg_name:
                    self._helpers.stop_rccg(rccg_name, access=False)
                else:
                    self._helpers.stop_relationship(volume.name, access=False)
            except Exception as err:
                msg = (_("Stop RC or rccg relationship has failed for %(vol)s "
                         "due to: %(err)s.")
                       % {"vol": volume.name, "err": err})
                LOG.error(msg)
                raise exception.VolumeBackendAPIException(data=msg)
        try:
            self._helpers.pretreatment_before_revert(volume.name)
        except Exception as err:
            msg = (_("Pretreatment before revert volume %(vol)s to snapshot "
                     "%(snap)s failed due to: %(err)s.")
                   % {"vol": volume.name, "snap": snapshot.name, "err": err})
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        opts = self._get_vdisk_params(volume.volume_type_id)
        try:
            self._helpers.run_flashcopy(
                snapshot.name, volume.name,
                self.configuration.storwize_svc_flashcopy_timeout,
                opts['flashcopy_rate'], opts['clean_rate'], True, True)
            if rep_type:
                if rccg_name:
                    self._helpers.start_rccg(rccg_name, primary=None)
                else:
                    self._helpers.start_relationship(volume.name, primary=None)
        except Exception as err:
            msg = (_("Reverting volume %(vol)s to snapshot %(snap)s failed "
                     "due to: %(err)s.")
                   % {"vol": volume.name, "snap": snapshot.name, "err": err})
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def get_pool(self, volume):
        attr = self._helpers.get_vdisk_attributes(volume['name'])

        if attr is None:
            msg = (_('get_pool: Failed to get attributes for volume '
                     '%s') % volume['name'])
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

        return attr['mdisk_grp_name']

    def get_hyperswap_storage_state(self):
        storage_state = fields.ReplicationStatus.ENABLED
        disabled_reason = None
        site_node_info = {}
        site_node_down_info = {}

        storage_nodes = self._helpers.get_node_info(online_node=False)

        for node, node_info in storage_nodes.items():
            if node_info['site_id']:
                site = node_info['site_id']
                if site not in site_node_info:
                    site_node_info[site] = []
                    site_node_down_info[site] = {'nodes_down': 0}

                site_node_info[site].append(node_info)
                if node_info['status'] not in ['online', 'degraded']:
                    site_node_down_info[site]['nodes_down'] += 1

        for site, site_info in site_node_down_info.items():
            if len(site_node_info[site]) == site_info['nodes_down']:
                storage_state = fields.ReplicationStatus.DISABLED
                site_name = site_node_info[site][0]['site_name']
                disabled_reason = "{0} is down".format(site_name)
                break

        return storage_state, disabled_reason

    def _update_volume_stats(self):
        """Retrieve stats info from volume group."""

        LOG.debug("Updating volume stats.")
        data = {}

        data['vendor_name'] = 'IBM'
        data['driver_version'] = self.VERSION
        data['storage_protocol'] = self.protocol
        data['pools'] = []

        backend_name = self.configuration.safe_get('volume_backend_name')
        data['volume_backend_name'] = (backend_name or
                                       self._state['system_name'])

        data['pools'] = [self._build_pool_stats(pool)
                         for pool in
                         self._get_backend_pools()]

        if self._helpers.is_system_topology_hyperswap(self._state):
            peer_pool = self._get_backend_peer_pool()
            if peer_pool:
                data['pools'].append(self._build_pool_stats(peer_pool))

        if self._replica_enabled:
            data['replication'] = self._replica_enabled
            data['replication_enabled'] = self._replica_enabled
            data['replication_targets'] = self._get_replication_targets()
            data['consistent_group_replication_enabled'] = True
            remote_data = dict()
            remote_data['pools'] = [self._build_pool_stats(pool, target=True)
                                    for pool in
                                    [self._replica_target.get('pool_name')]]
            self._aux_backend_helpers.stats = remote_data

        if self._helpers.is_system_topology_hyperswap(self._state):
            data['replication_enabled'] = True
            try:
                state, reason = self.get_hyperswap_storage_state()
                if state != fields.ReplicationStatus.ENABLED:
                    data['replication_enabled'] = False
                    data['disabled_reason'] = reason
            except exception.VolumeBackendAPIException as exc:
                LOG.warning("Failed to get node info. "
                            "Exception: %(ex)s.", {'ex': exc.msg})

        self._stats = data

    def _build_pool_stats(self, pool, target=False):
        """Build pool status"""
        QoS_support = True
        pool_stats = {}
        is_dr_pool = False
        if target:
            pool_data = self._aux_backend_helpers.get_pool_attrs(pool)
            system_id = self._aux_state['system_id']
            compression_enabled = self._aux_state['compression_enabled']
        else:
            pool_data = self._helpers.get_pool_attrs(pool)
            system_id = self._state['system_id']
            compression_enabled = self._state['compression_enabled']
        if pool_data:
            easy_tier = pool_data['easy_tier'] in ['on', 'auto']
            total_capacity_gb = float(pool_data['capacity']) / units.Gi
            free_capacity_gb = float(pool_data['free_capacity']) / units.Gi
            provisioned_capacity_gb = float(
                pool_data['virtual_capacity']) / units.Gi

            rsize = self.configuration.safe_get(
                'storwize_svc_vol_rsize')
            # rsize of -1 or 100 means fully allocate the mdisk
            use_thick_provisioning = rsize == -1 or rsize == 100
            over_sub_ratio = self.configuration.safe_get(
                'max_over_subscription_ratio')
            location_info = ('StorwizeSVCDriver:%(sys_id)s:%(pool)s' %
                             {'sys_id': system_id,
                              'pool': pool_data['name']})
            multiattach = (self.configuration.
                           storwize_svc_multihostmap_enabled)
            backend_state = ('up' if pool_data['status'] == 'online' else
                             'down')

            # Get the data_reduction information for pool and set
            # is_dr_pool flag.
            if pool_data.get('data_reduction'):
                is_dr_pool = pool_data.get('data_reduction').lower() == 'yes'

            pool_stats = {
                'pool_name': pool_data['name'],
                'total_capacity_gb': total_capacity_gb,
                'free_capacity_gb': free_capacity_gb,
                'provisioned_capacity_gb': provisioned_capacity_gb,
                'compression_support': compression_enabled,
                'reserved_percentage':
                    self.configuration.reserved_percentage,
                'QoS_support': QoS_support,
                'consistencygroup_support': True,
                'location_info': location_info,
                'easytier_support': easy_tier,
                'multiattach': multiattach,
                'thin_provisioning_support': not use_thick_provisioning,
                'thick_provisioning_support': use_thick_provisioning,
                'max_over_subscription_ratio': over_sub_ratio,
                'consistent_group_snapshot_enabled': True,
                'backend_state': backend_state,
                'data_reduction': is_dr_pool,
                'site_id': pool_data['site_id'],
                'site_name': pool_data['site_name'],
            }
            if self._replica_enabled:
                pool_stats.update({
                    'replication_enabled': self._replica_enabled,
                    'replication_type': self._supported_replica_types,
                    'replication_targets': self._get_replication_targets(),
                    'replication_count': len(self._get_replication_targets()),
                    'consistent_group_replication_enabled': True
                })

        else:
            LOG.error('Failed getting details for pool %s.', pool)
            pool_stats = {'pool_name': pool,
                          'total_capacity_gb': 0,
                          'free_capacity_gb': 0,
                          'provisioned_capacity_gb': 0,
                          'thin_provisioning_support': True,
                          'thick_provisioning_support': False,
                          'max_over_subscription_ratio': 0,
                          'reserved_percentage': 0,
                          'data_reduction': is_dr_pool,
                          'site_id': None,
                          'site_name': None,
                          'backend_state': 'down'}

        return pool_stats

    def _get_replication_targets(self):
        return [self._replica_target['backend_id']]

    def _manage_input_check(self, ref):
        """Verify the input of manage function."""
        # Check that the reference is valid
        if 'source-name' in ref:
            manage_source = ref['source-name']
            vdisk = self._helpers.get_vdisk_attributes(manage_source)
        elif 'source-id' in ref:
            manage_source = ref['source-id']
            vdisk = self._helpers.vdisk_by_uid(manage_source)
        else:
            reason = _('Reference must contain source-id or '
                       'source-name element.')
            raise exception.ManageExistingInvalidReference(existing_ref=ref,
                                                           reason=reason)

        if vdisk is None:
            reason = (_('No vdisk with the UID specified by ref %s.')
                      % manage_source)
            raise exception.ManageExistingInvalidReference(existing_ref=ref,
                                                           reason=reason)
        return vdisk

    def _delete_replication_grp(self, group, volumes):
        if self._state['code_level'] < (7, 7, 0, 0):
            force_unmap = False
        else:
            force_unmap = True
        model_update = {'status': fields.GroupStatus.DELETED}
        volumes_model_update = []
        rccg_name = self._get_rccg_name(group)
        try:
            self._helpers.delete_rccg(rccg_name)
        except exception.VolumeBackendAPIException as err:
            LOG.error("Failed to delete rccg  %(rccg)s. "
                      "Exception: %(exception)s.",
                      {'rccg': rccg_name, 'exception': err})
            model_update = {'status': fields.GroupStatus.ERROR_DELETING}

        for volume in volumes:
            try:
                target_volume, rel_info = (
                    self._helpers.get_target_volume_information(volume))
                self._aux_backend_helpers.delete_rc_volume(
                    target_volume, rel_info, target_vol=True,
                    force_unmap=force_unmap)
                self._master_backend_helpers.delete_rc_volume(
                    volume.name, force_unmap=force_unmap)
                volumes_model_update.append(
                    {'id': volume.id, 'status': 'deleted'})
            except exception.VolumeDriverException as err:
                model_update['status'] = (
                    fields.GroupStatus.ERROR_DELETING)
                LOG.error("Failed to delete the volume %(vol)s of CG. "
                          "Exception: %(exception)s.",
                          {'vol': volume.name, 'exception': err})
                volumes_model_update.append(
                    {'id': volume.id,
                     'status': fields.GroupStatus.ERROR_DELETING})
        return model_update, volumes_model_update

    def _update_replication_grp(self, context, group,
                                add_volumes, remove_volumes):
        model_update = {'status': fields.GroupStatus.AVAILABLE}
        LOG.info("Update replication group: %(group)s. ", {'group': group.id})

        rccg_name = self._get_rccg_name(group)
        # This code block fails during remove of volumes from group
        try:
            rccg = self._helpers.get_rccg(rccg_name)
        except Exception as ex:
            if len(add_volumes) > 0:
                LOG.exception("Unable to retrieve "
                              "replication group information. Failed "
                              "with exception %(ex)s", ex)

        if not rccg and len(add_volumes) > 0:
            LOG.error("Failed to update group: %(grp)s does not exist in "
                      "backend.", {'grp': group.id})
            model_update['status'] = fields.GroupStatus.ERROR
            return model_update, None, None

        # Add remote copy relationship to rccg
        added_vols = []
        for volume in add_volumes:
            try:
                vol_name = (volume.name if not self._active_backend_id else
                            storwize_const.REPLICA_AUX_VOL_PREFIX +
                            volume.name)
                rcrel = self._helpers.get_relationship_info(vol_name)
                if not rcrel:
                    LOG.error("Failed to update group: remote copy "
                              "relationship of %(vol)s does not exist in "
                              "backend.", {'vol': volume.id})
                    model_update['status'] = fields.GroupStatus.ERROR
                else:
                    if rccg and rccg.get('cycling_mode', None) == 'multi':
                        self._helpers.stop_relationship(vol_name,
                                                        rcrel=rcrel['name'])
                        rcrel = self._helpers.get_relationship_info(vol_name)
                        if (rccg['state'] != 'empty' and
                           rccg['state'] != 'consistent_stopped' or
                           rccg['state'] != 'inconsistent_stopped'):
                            self._helpers.stop_rccg(rccg_name)
                            # To handle existing group updation, refresh rccg
                            # state to avoid unnecessary stop_rccg calls.
                            rccg = self._helpers.get_rccg(rccg_name)

                    if (rccg['copy_type'] != 'empty_group' and
                        any(k for k in ('copy_type', 'state', 'primary',
                                        'cycling_mode', 'cycle_period_seconds')
                            if rccg[k] != rcrel[k])):
                        LOG.error("Failed to update rccg %(rccg)s: remote "
                                  "copy type of %(vol)s is %(vol_rc_type)s, "
                                  "the rccg type is %(rccg_type)s. rcrel "
                                  "state %(rcrel_state)s, rccg state is "
                                  "%(rccg_state)s rcrel primary is "
                                  "%(rcrel_primary)s, rccg primary is "
                                  "%(rccg_primary)s. rcrel cycling mode is "
                                  "%(rcrel_cmode)s, rccg cycling mode is "
                                  "%(rccg_cmode)s. rcrel cycling period is "
                                  "%(rcrel_period)s, rccg cycling "
                                  "period is %(rccg_period)s. ",
                                  {'rccg': rccg_name,
                                   'vol': volume.id,
                                   'vol_rc_type': rcrel['copy_type'],
                                   'rccg_type': rccg['copy_type'],
                                   'rcrel_state': rcrel['state'],
                                   'rccg_state': rccg['state'],
                                   'rcrel_primary': rcrel['primary'],
                                   'rccg_primary': rccg['primary'],
                                   'rcrel_cmode': rcrel['cycling_mode'],
                                   'rccg_cmode': rccg['cycling_mode'],
                                   'rcrel_period':
                                   rcrel['cycle_period_seconds'],
                                   'rccg_period':
                                   rccg['cycle_period_seconds']})
                        # This rcrel updation failed ,it has to be started
                        # explicitly.
                        self._helpers.start_relationship(vol_name,
                                                         rcrel=rcrel['name'])
                        model_update['status'] = fields.GroupStatus.ERROR
                    else:
                        self._helpers.chrcrelationship(rcrel['name'],
                                                       rccg_name)
                        if rccg['copy_type'] == 'empty_group':
                            rccg = self._helpers.get_rccg(rccg_name)
                        added_vols.append({'id': volume.id,
                                          'group_id': group.id})
                        # Updating RCCG properties for a volume
                        self._update_rccg_properties(context, volume, group)
            except exception.VolumeBackendAPIException as err:
                model_update['status'] = fields.GroupStatus.ERROR
                LOG.error("Failed to add the remote copy of volume %(vol)s to "
                          "group. Exception: %(exception)s.",
                          {'vol': volume.name, 'exception': err})
                self._helpers.start_relationship(vol_name)

        if (rccg and len(add_volumes) > 0 and
                rccg.get('cycling_mode', None) == 'multi'):
            if rccg.get('primary', None) == 'aux':
                self._helpers.start_rccg(rccg_name, primary='aux')
            elif rccg.get('primary', None) == 'master':
                self._helpers.start_rccg(rccg_name, primary='master')

        # Remove remote copy relationship from rccg
        removed_vols = []
        for volume in remove_volumes:
            try:
                vol_name = (volume.name if not self._active_backend_id else
                            storwize_const.REPLICA_AUX_VOL_PREFIX +
                            volume.name)
                rcrel = self._helpers.get_relationship_info(vol_name)
                if not rcrel:
                    LOG.error("Failed to update group: remote copy "
                              "relationship of %(vol)s does not exist in "
                              "backend.", {'vol': volume.id})
                    model_update['status'] = fields.GroupStatus.ERROR
                else:
                    self._helpers.chrcrelationship(rcrel['name'])
                    removed_vols.append({'id': volume.id,
                                         'group_id': None})
                    # Updating RCCG properties for a volume
                    self._update_rccg_properties(context, volume)
            except exception.VolumeBackendAPIException as err:
                model_update['status'] = fields.GroupStatus.ERROR
                LOG.error("Failed to remove the remote copy of volume %(vol)s "
                          "from group. Exception: %(exception)s.",
                          {'vol': volume.name, 'exception': err})
        return model_update, added_vols, removed_vols

    def _delete_volumegroup(self, group, volumes):
        model_update = {'status': fields.GroupStatus.DELETED}
        volumegroup_name = self._get_volumegroup_name(group)
        volumes_model_update = []
        force_unmap = True
        if self._state['code_level'] < (7, 7, 0, 0):
            force_unmap = False
        for volume in volumes:
            volume = self._helpers.get_volume_name_from_metadata(volume)
            if self._active_backend_id:
                msg = (_('Error: deleting non-replicated volume in '
                         'failover mode is not allowed.'))
                LOG.error(msg)
                volume.name_id = None
                raise exception.VolumeDriverException(message=msg)
            else:
                try:
                    self._helpers.delete_vdisk(
                        volume.name,
                        force_unmap=force_unmap,
                        force_delete=True)
                    volumes_model_update.append({'id': volume.id,
                                                 'status': 'deleted'})
                except exception.VolumeBackendAPIException as err:
                    model_update['status'] = (
                        fields.GroupStatus.ERROR_DELETING)
                    LOG.error("Failed to delete the volume %(vol)s of CG. "
                              "Exception: %(exception)s.",
                              {'vol': volume.name, 'exception': err})
                    volume.name_id = None
                    volumes_model_update.append(
                        {'id': volume.id,
                         'status': fields.GroupStatus.ERROR_DELETING})
            volume.name_id = None

        try:
            self._helpers.delete_volumegroup(volumegroup_name)
        except exception.VolumeBackendAPIException as err:
            LOG.error("Failed to delete volume group %(volumegroup)s. "
                      "Exception: %(exception)s.",
                      {'volumegroup': volumegroup_name, 'exception': err})
            model_update = {'status': fields.GroupStatus.ERROR_DELETING}

        return model_update, volumes_model_update

    def _update_volumegroup(self, context, group, add_volumes,
                            remove_volumes):
        model_update = {'status': fields.GroupStatus.AVAILABLE}
        LOG.info("Update volume group: %(volumegroup_id)s. ",
                 {'volumegroup_id': group.id})

        volumegroup_name = self._get_volumegroup_name(group)
        # This code block fails during remove of volumes from group
        try:
            volumegroup = self._helpers.get_volumegroup(volumegroup_name)
            volumegroup_id = volumegroup["id"]
        except Exception as ex:
            if len(add_volumes) > 0:
                LOG.exception("Unable to retrieve volume group "
                              "information. Failed with exception "
                              "%(ex)s", ex)
        if not volumegroup and len(add_volumes) > 0:
            LOG.error("Failed to update group: %(volumegroup)s does not "
                      "exist in backend.",
                      {'volumegroup': volumegroup_name})
            model_update['status'] = fields.GroupStatus.ERROR
            return model_update, None, None

        # Add volume(s) to the volume group
        added_vols = []
        for volume in add_volumes:
            vol_name = volume.name
            try:
                self._helpers.add_vdisk_to_volumegroup(vol_name,
                                                       volumegroup_id)
                added_vols.append({'id': volume.id,
                                   'group_id': group.id})
                self._update_volumegroup_properties(context, volume, group)
            except exception.VolumeBackendAPIException as err:
                model_update['status'] = fields.GroupStatus.ERROR
                LOG.error("Failed to add the volume %(vol)s to "
                          "group. Exception: %(exception)s.",
                          {'vol': volume.name, 'exception': err})

        # Remove volume(s) from the volume group
        removed_vols = []
        for volume in remove_volumes:
            vol_name = volume.name
            try:
                self._helpers.remove_vdisk_from_volumegroup(vol_name)
                removed_vols.append({'id': volume.id,
                                     'group_id': None})
                self._update_volumegroup_properties(context, volume)
            except exception.VolumeBackendAPIException as err:
                model_update['status'] = fields.GroupStatus.ERROR
                LOG.error("Failed to remove the volume %(vol)s from "
                          "group. Exception: %(exception)s.",
                          {'vol': volume.name, 'exception': err})

        return model_update, added_vols, removed_vols

    def _delete_hyperswap_grp(self, group, volumes):
        model_update = {'status': fields.GroupStatus.DELETED}
        volumes_model_update = []

        for volume in volumes:
            try:
                self._helpers.delete_hyperswap_volume(volume.name,
                                                      force_unmap=False,
                                                      force_delete=True)
                volumes_model_update.append(
                    {'id': volume.id, 'status': 'deleted'})
            except exception.VolumeDriverException as err:
                LOG.error("Failed to delete the volume %(vol)s of CG. "
                          "Exception: %(exception)s.",
                          {'vol': volume.name, 'exception': err})
                volumes_model_update.append(
                    {'id': volume.id,
                     'status': 'error_deleting'})
        return model_update, volumes_model_update

    def _update_hyperswap_group(self, context, group,
                                add_volumes=None, remove_volumes=None):
        LOG.info("Update hyperswap group: %(group)s. ", {'group': group.id})
        model_update = {'status': fields.GroupStatus.AVAILABLE}

        added_vols = []
        for volume in add_volumes:
            hyper_volume = self.is_volume_hyperswap(volume)
            if not hyper_volume:
                LOG.error("Failed to update rccg: the non hyperswap volume"
                          " of %(vol)s can't be added to hyperswap group.",
                          {'vol': volume.id})
                model_update['status'] = fields.GroupStatus.ERROR
                continue
            added_vols.append({'id': volume.id, 'group_id': group.id})

        removed_vols = []
        for volume in remove_volumes:
            hyper_volume = self.is_volume_hyperswap(volume)
            if not hyper_volume:
                LOG.error("Failed to update rccg: the non hyperswap volume"
                          " of %(vol)s can't be added to hyperswap group.",
                          {'vol': volume.id})
                model_update['status'] = fields.GroupStatus.ERROR
                continue
            removed_vols.append({'id': volume.id, 'group_id': None})

        return model_update, added_vols, removed_vols

    def _get_volume_host_site_from_conf(self, volume, connector, iscsi=False):
        host_site = self.configuration.safe_get('storwize_preferred_host_site')
        select_site = None
        if not host_site:
            LOG.debug('There is no host_site configured for volume %s.',
                      volume.name)
            return select_site
        if iscsi:
            for site, iqn in host_site.items():
                if connector['initiator'].lower() in iqn.lower():
                    if select_site is None:
                        select_site = site
                    elif select_site != site:
                        msg = _('Configured the host IQN in both sites.')
                        LOG.error(msg)
                        raise exception.InvalidConfigurationValue(message=msg)
        else:
            for wwpn in connector['wwpns']:
                for site, wwpn_list in host_site.items():
                    if wwpn.lower() in wwpn_list.lower():
                        if select_site is None:
                            select_site = site
                        elif select_site != site:
                            msg = _('Configured the host wwpns not in the'
                                    ' same site.')
                            LOG.error(msg)
                            raise exception.InvalidConfigurationValue(
                                message=msg)
        return select_site

    def _update_host_site_for_hyperswap_volume(self, host_name, host_site):
        host_info = self._helpers.ssh.lshost(host=host_name)
        if not host_info[0]['site_name'] and host_site:
            self._helpers.update_host(host_name, host_site)
        elif host_info[0]['site_name']:
            ref_host_site = host_info[0]['site_name']
            if host_site and host_site != ref_host_site:
                msg = (_('The existing host site is %(ref_host_site)s,'
                         ' but the new host site is %(host_site)s.') %
                       {'ref_host_site': ref_host_site,
                        'host_site': host_site})
                LOG.error(msg)
                raise exception.InvalidConfigurationValue(message=msg)
