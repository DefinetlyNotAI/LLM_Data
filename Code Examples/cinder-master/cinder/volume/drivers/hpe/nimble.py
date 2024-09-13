# Nimble Storage, Inc. (c) 2013-2014
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
Volume driver for Nimble Storage.

This driver supports Nimble Storage controller CS-Series and Nimble AF Arrays.

"""

import abc
import functools
import json
import random
import re
import string
import sys

import eventlet
from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import units
import requests

from cinder.common import constants
from cinder import exception
from cinder.i18n import _
from cinder import interface
from cinder.objects import fields
from cinder.objects import volume
from cinder import utils
from cinder.volume import configuration
from cinder.volume import driver
from cinder.volume.drivers.san import san
from cinder.volume import volume_types
from cinder.volume import volume_utils
from cinder.zonemanager import utils as fczm_utils


DRIVER_VERSION = "4.3.0"
AES_256_XTS_CIPHER = 'aes_256_xts'
DEFAULT_CIPHER = 'none'
EXTRA_SPEC_ENCRYPTION = 'nimble:encryption'
EXTRA_SPEC_PERF_POLICY = 'nimble:perfpol-name'
EXTRA_SPEC_DEDUPE = 'nimble:dedupe'
EXTRA_SPEC_IOPS_LIMIT = 'nimble:iops-limit'
EXTRA_SPEC_FOLDER = 'nimble:folder'
DEFAULT_PERF_POLICY_SETTING = 'default'
DEFAULT_ENCRYPTION_SETTING = 'no'
DEFAULT_DEDUPE_SETTING = 'false'
DEFAULT_IOPS_LIMIT_SETTING = None
DEFAULT_FOLDER_SETTING = None
DEFAULT_SNAP_QUOTA = sys.maxsize
BACKUP_VOL_PREFIX = 'backup-vol-'
AGENT_TYPE_OPENSTACK = 'openstack'
AGENT_TYPE_OPENSTACK_GST = 'openstackv2'
AGENT_TYPE_NONE = 'none'
SM_SUBNET_DATA = 'data'
SM_SUBNET_MGMT_PLUS_DATA = 'mgmt-data'
SM_STATE_MSG = "is already in requested state"
SM_OBJ_EXIST_MSG = "Object exists"
SM_OBJ_ENOENT_MSG = "No such object"
SM_OBJ_HAS_CLONE = "has a clone"
IOPS_ERR_MSG = "Please set valid IOPS limit in the range"
LUN_ID = '0'
WARN_LEVEL = 80
DEFAULT_SLEEP = 5
MIN_IOPS = 256
MAX_IOPS = 4294967294
NimbleDefaultVersion = 1


LOG = logging.getLogger(__name__)

nimble_opts = [
    cfg.StrOpt('nimble_pool_name',
               default='default',
               help='Nimble Controller pool name'),
    cfg.StrOpt('nimble_subnet_label',
               default='*',
               help='Nimble Subnet Label'),
    cfg.BoolOpt('nimble_verify_certificate',
                default=False,
                help='Whether to verify Nimble SSL Certificate'),
    cfg.StrOpt('nimble_verify_cert_path',
               help='Path to Nimble Array SSL certificate'), ]

CONF = cfg.CONF
CONF.register_opts(nimble_opts, group=configuration.SHARED_CONF_GROUP)


class NimbleDriverException(exception.VolumeDriverException):
    message = _("Nimble Cinder Driver exception")


class NimbleAPIException(exception.VolumeBackendAPIException):
    message = _("Unexpected response from Nimble API")


class NimbleBaseVolumeDriver(san.SanDriver):
    """OpenStack driver to enable Nimble Controller.

    Version history:

    .. code-block:: none


        1.0 - Initial driver
        1.1.1 - Updated VERSION to Nimble driver version
        1.1.2 - Update snap-quota to unlimited
        2.0.0 - Added Extra Spec Capability
                Correct capacity reporting
                Added Manage/Unmanage volume support
        2.0.1 - Added multi-initiator support through extra-specs
        2.0.2 - Fixed supporting extra specs while cloning vols
        3.0.0 - Newton Support for Force Backup
        3.1.0 - Fibre Channel Support
        4.0.0 - Migrate from SOAP to REST API
                Add support for Group Scoped Target
        4.0.1 - Add QoS and dedupe support
        4.1.0 - Added multiattach support
                Added revert to snapshot support
                Added consistency groups support
        4.2.0 - The Nimble driver is now located in the
                cinder.volume.drivers.hpe module.
        4.3.0 - Added group replication support
    """
    VERSION = DRIVER_VERSION

    # ThirdPartySystems wiki page
    CI_WIKI_NAME = "HPE_Nimble_Storage_CI"

    def __init__(self, *args, **kwargs):
        super(NimbleBaseVolumeDriver, self).__init__(*args, **kwargs)
        self.APIExecutor = None
        self.group_stats = {}
        self.api_protocol = None
        self._storage_protocol = None
        self._group_target_enabled = False
        self.configuration.append_config_values(nimble_opts)
        self.verify = False
        if self.configuration.nimble_verify_certificate is True:
            self.verify = self.configuration.nimble_verify_cert_path or True
        self.APIExecutor_remote_array = None
        self.remote_array = {}
        self._replicated_type = False

    @staticmethod
    def get_driver_options():
        return nimble_opts

    def _check_config(self):
        """Ensure that the flags we care about are set."""
        required_config = ['san_ip', 'san_login', 'san_password']
        for attr in required_config:
            if not getattr(self.configuration, attr, None):
                raise exception.InvalidInput(reason=_('%s is not set.') %
                                             attr)

    def create_volume(self, volume):
        """Create a new volume."""
        reserve = not self.configuration.san_thin_provision
        LOG.debug("Creating volume: %(name)s", {'name': volume['name']})
        self.APIExecutor.create_vol(
            volume,
            self.configuration.nimble_pool_name, reserve,
            self._storage_protocol,
            self._group_target_enabled)
        volume_type = volume.get('volume_type')
        consis_group_snap_type = False
        LOG.debug("volume_type: %(vol_type)s", {'vol_type': volume_type})

        if volume_type is not None:
            consis_group_snap_type = self.is_volume_group_snap_type(
                volume_type)
            LOG.debug("consis_group_snap_type: %(cg_type)s",
                      {'cg_type': consis_group_snap_type})
            cg_id = volume.get('group_id', None)
            LOG.debug("cg_id: %(cg_id)s", {'cg_id': cg_id})
        if consis_group_snap_type and cg_id:
            volume_id = self.APIExecutor.get_volume_id_by_name(volume['name'])
            cg_volcoll_id = self.APIExecutor.get_volcoll_id_by_name(cg_id)
            self.APIExecutor.associate_volcoll(volume_id, cg_volcoll_id)

        model_info = self._get_model_info(volume['name'])
        if self._replicated_type:
            model_info['replication_status'] = 'enabled'
        return model_info

    def is_volume_backup_clone(self, volume):
        """check if the volume is created through cinder-backup workflow.

        :param volume
        """
        vol_info = self.APIExecutor.get_vol_info(volume['name'])
        LOG.debug("is_clone: %(is_clone)s base_snap_id: %(snap)s, "
                  "parent_vol_id: %(vol)s",
                  {'is_clone': vol_info['clone'],
                   'snap': vol_info['base_snap_id'],
                   'vol': vol_info['parent_vol_id']})

        if vol_info['base_snap_id'] and (
           vol_info['parent_vol_id'] is not None):
            LOG.debug("Nimble base-snap exists for volume %(vol)s",
                      {'vol': volume['name']})
            volume_name_prefix = volume['name'].replace(volume['id'], "")
            LOG.debug("volume_name_prefix : %(prefix)s",
                      {'prefix': volume_name_prefix})
            snap_id = self.APIExecutor.get_snap_info_by_id(
                vol_info['base_snap_id'],
                vol_info['parent_vol_id'])
            snap_info = self.APIExecutor.get_snap_info_detail(snap_id['id'])
            LOG.debug("snap_info description %(snap_info)s",
                      {'snap_info': snap_info['description']})
            if snap_info['description'] and BACKUP_VOL_PREFIX in (
                    snap_info['description']):
                # TODO(rkumar): get parent vol id from parent volume name
                parent_vol_name = self.APIExecutor.get_volume_name(
                    vol_info['parent_vol_id'])
                parent_vol_id = parent_vol_name. replace(
                    volume_name_prefix, "")
                if BACKUP_VOL_PREFIX + parent_vol_id in snap_info[
                   'description']:
                    LOG.info('Nimble backup-snapshot exists name=%('
                             'name)s', {'name': snap_info['name']})
                    snap_vol_name = self.APIExecutor.get_volume_name(
                        snap_info['vol_id'])
                    LOG.debug("snap_vol_name %(snap)s",
                              {'snap': snap_vol_name})
                    return snap_info['name'], snap_vol_name
        return "", ""

    def delete_volume(self, volume):
        """Delete the specified volume."""
        backup_snap_name, backup_vol_name = self.is_volume_backup_clone(volume)
        eventlet.sleep(DEFAULT_SLEEP)

        if self._replicated_type:
            group_id = self.APIExecutor_remote_array.get_group_id()
            LOG.debug("group_id: %(id)s", {'id': group_id})
            volume_id = self.APIExecutor_remote_array.get_volume_id_by_name(
                volume['name'])
            LOG.debug("volume_id: %(id)s", {'id': volume_id})

            LOG.debug("claim vol on remote array")
            self.APIExecutor_remote_array.claim_vol(volume_id, group_id)

            LOG.debug("delete vol on remote array")
            self.APIExecutor_remote_array.delete_vol(volume['name'])

        # make the volume as offline
        self.APIExecutor.online_vol(volume['name'], False)

        LOG.debug("Deleting volume %(vol)s", {'vol': volume['name']})

        @utils.retry(NimbleAPIException, retries=3)
        def _retry_remove_vol(volume):
            self.APIExecutor.delete_vol(volume['name'])
        try:
            _retry_remove_vol(volume)
        except NimbleAPIException as ex:
            LOG.debug("delete volume exception: %s", ex)
            if SM_OBJ_HAS_CLONE in str(ex):
                LOG.warning('Volume %(vol)s : %(state)s',
                            {'vol': volume['name'],
                             'state': SM_OBJ_HAS_CLONE})
                # set the volume back to be online and raise busy exception
                self.APIExecutor.online_vol(volume['name'], True)
                raise exception.VolumeIsBusy(volume_name=volume['name'])
            raise
        # Nimble backend does not delete the snapshot from the parent volume
        # if there is a dependent clone. So the deletes need to be in reverse
        # order i.e.
        # 1. First delete the clone volume used for backup
        # 2. Delete the base snapshot used for clone from the parent volume.
        # This is only done for the force backup clone operation as it is
        # a temporary operation in which we are certain that the snapshot does
        # not need to be preserved after the backup is completed.

        if (backup_snap_name != "" and backup_vol_name != "") and (
           backup_snap_name is not None):
            LOG.debug("Delete volume backup vol: %(vol)s snap: %(snap)s",
                      {'vol': backup_vol_name,
                       'snap': backup_snap_name})
            self.APIExecutor.online_snap(backup_vol_name,
                                         False,
                                         backup_snap_name)

            self.APIExecutor.delete_snap(backup_vol_name,
                                         backup_snap_name)

    def _generate_random_string(self, length):
        """Generates random_string."""
        char_set = string.ascii_lowercase
        return ''.join(random.sample(char_set, length))

    def _clone_volume_from_snapshot(self, volume, snapshot):
        """Clone volume from snapshot.

        Extend the volume if the size of the volume is more than the snapshot.
        """
        reserve = not self.configuration.san_thin_provision
        pool_name = self.configuration.nimble_pool_name
        self.APIExecutor.clone_vol(volume, snapshot, reserve,
                                   self._group_target_enabled,
                                   self._storage_protocol,
                                   pool_name)
        if (volume['size'] > snapshot['volume_size']):
            vol_size = volume['size'] * units.Ki
            reserve_size = 100 if reserve else 0
            data = {"data": {'size': vol_size,
                             'reserve': reserve_size,
                             'warn_level': int(WARN_LEVEL),
                             'limit': 100,
                             'snap_limit': DEFAULT_SNAP_QUOTA}}
            LOG.debug("Edit Vol request %(data)s", {'data': data})
            self.APIExecutor.edit_vol(volume['name'], data)
        return self._get_model_info(volume['name'])

    def create_cloned_volume(self, volume, src_vref):
        """Create a clone of the specified volume."""
        snapshot_name = ('openstack-clone-' +
                         volume['name'] + '-' +
                         self._generate_random_string(12))
        snapshot = {'volume_name': src_vref['name'],
                    'name': snapshot_name,
                    'volume_size': src_vref['size'],
                    'display_name': volume.display_name,
                    'display_description': ''}
        self.APIExecutor.snap_vol(snapshot)
        self._clone_volume_from_snapshot(volume, snapshot)
        return self._get_model_info(volume['name'])

    def create_export(self, context, volume, connector):
        """Driver entry point to get the export info for a new volume."""
        return self._get_model_info(volume['name'])

    def ensure_export(self, context, volume):
        """Driver entry point to get the export info for an existing volume."""
        return self._get_model_info(volume['name'])

    def create_snapshot(self, snapshot):
        """Create a snapshot."""
        self.APIExecutor.snap_vol(snapshot)

    def delete_snapshot(self, snapshot):
        """Delete a snapshot."""
        self.APIExecutor.online_snap(
            snapshot['volume_name'],
            False,
            snapshot['name'])
        self.APIExecutor.delete_snap(snapshot['volume_name'],
                                     snapshot['name'])

    def create_volume_from_snapshot(self, volume, snapshot):
        """Create a volume from a snapshot."""
        self._clone_volume_from_snapshot(volume, snapshot)
        return self._get_model_info(volume['name'])

    def _enable_group_scoped_target(self, group_info):
        if 'version_current' in group_info:
            current_version = group_info['version_current']
            major_minor = current_version.split(".")
            if len(major_minor) >= 3:
                major = major_minor[0]
                minor = major_minor[1]
                # TODO(rkumar): Fix the major version
                if int(major) >= 4 and int(minor) >= 0:
                    # Enforce group scoped target
                    if 'group_target_enabled' in group_info:
                        if group_info['group_target_enabled'] is False:
                            try:
                                self.APIExecutor.enable_group_scoped_target()
                            except Exception:
                                raise NimbleAPIException(_("Unable to enable"
                                                         " GST"))
                        self._group_target_enabled = True
                        LOG.info("Group Scoped Target enabled for "
                                 "group %(group)s: %(ip)s",
                                 {'group': group_info['name'],
                                  'ip': self.configuration.san_ip})
                    elif 'group_target_enabled' not in group_info:
                        LOG.info("Group Scoped Target NOT "
                                 "present for group %(group)s: "
                                 "%(ip)s",
                                 {'group': group_info['name'],
                                  'ip': self.configuration.san_ip})
            else:
                raise NimbleAPIException(_("Unable to get current software "
                                           "version for %s") %
                                         self.configuration.san_ip)

    def get_volume_stats(self, refresh=False):
        """Get volume stats. This is more of getting group stats."""
        if refresh:
            group_info = self.APIExecutor.get_group_info()
            if 'usage_valid' not in group_info:
                raise NimbleDriverException(_('SpaceInfo returned by '
                                              'array is invalid'))
            total_capacity = (group_info['usable_capacity_bytes'] /
                              float(units.Gi))
            free_space = (group_info['free_space'] /
                          float(units.Gi))
            LOG.debug('total_capacity=%(capacity)f '
                      'free_space=%(free)f',
                      {'capacity': total_capacity,
                       'free': free_space})

            backend_name = self.configuration.safe_get(
                'volume_backend_name') or self.__class__.__name__
            self.group_stats = {'volume_backend_name': backend_name,
                                'vendor_name': 'Nimble',
                                'driver_version': DRIVER_VERSION,
                                'storage_protocol': self._storage_protocol}
            # Just use a single pool for now, FIXME to support multiple
            # pools
            single_pool = dict(
                pool_name=backend_name,
                total_capacity_gb=total_capacity,
                free_capacity_gb=free_space,
                reserved_percentage=0,
                QoS_support=False,
                multiattach=True,
                thin_provisioning_support=True,
                consistent_group_snapshot_enabled=True,
                consistent_group_replication_enabled=self._replicated_type,
                replication_enabled=self._replicated_type)
            self.group_stats['pools'] = [single_pool]
        return self.group_stats

    def extend_volume(self, volume, new_size):
        """Extend an existing volume."""
        volume_name = volume['name']
        LOG.info('Entering extend_volume volume=%(vol)s '
                 'new_size=%(size)s',
                 {'vol': volume_name, 'size': new_size})
        vol_size = int(new_size) * units.Ki
        reserve = not self.configuration.san_thin_provision
        reserve_size = 100 if reserve else 0
        LOG.debug("new volume size in MB (size)s", {'size': vol_size})
        data = {"data": {'size': vol_size,
                         'reserve': reserve_size,
                         'warn_level': int(WARN_LEVEL),
                         'limit': 100,
                         'snap_limit': DEFAULT_SNAP_QUOTA}}
        self.APIExecutor.edit_vol(volume_name, data)

    def _get_existing_volume_ref_name(self, existing_ref):
        """Returns the volume name of an existing ref"""
        vol_name = None
        if 'source-name' in existing_ref:
            vol_name = existing_ref['source-name']
        else:
            reason = _("Reference must contain source-name.")
            raise exception.ManageExistingInvalidReference(
                existing_ref=existing_ref,
                reason=reason)

        return vol_name

    def _get_volumetype_extraspecs_with_type(self, type_id):
        specs = {}
        if type_id is not None:
            specs = volume_types.get_volume_type_extra_specs(type_id)
        return specs

    def retype(self, context, volume, new_type, diff, host):
        """Retype from one volume type to another.

        At this point HPE Nimble Storage does not differentiate between
        volume types on the same array. This is a no-op for us if there are
        no extra specs else honor the extra-specs.
        """
        if new_type is None:
            return True, None
        LOG.debug("retype called with volume_type %s", new_type)

        volume_type_id = new_type['id']
        if volume_type_id is None:
            raise NimbleAPIException(_("No volume_type_id present in"
                                       " %(type)s") % {'type': new_type})

        LOG.debug("volume_type id is %s", volume_type_id)
        specs_map = self._get_volumetype_extraspecs_with_type(
            volume_type_id)
        if specs_map is None:
            # no extra specs to retype
            LOG.debug("volume_type %s has no extra specs", volume_type_id)
            return True, None
        vol_info = self.APIExecutor.get_vol_info(volume['name'])
        LOG.debug("new extra specs %s", specs_map)
        data = self.APIExecutor.get_valid_nimble_extraspecs(specs_map,
                                                            vol_info)
        if data is None:
            # return if there is no update
            LOG.debug("no data to update for %s", new_type)
            return True, None
        try:
            # offline the volume before edit
            self.APIExecutor.online_vol(volume['name'], False)
            # modify the volume
            LOG.debug("updated volume %s", data)
            self.APIExecutor.edit_vol(volume['name'], data)
            # make the volume online after changing the specs
            self.APIExecutor.online_vol(volume['name'], True)
        except NimbleAPIException as ex:
            raise NimbleAPIException(_("Unable to retype %(vol)s to "
                                       "%(type)s: %(err)s") %
                                     {'vol': volume['name'],
                                      'type': new_type,
                                      'err': ex.message})
        return True, None

    def manage_existing(self, volume, external_ref):
        """Manage an existing nimble volume (import to cinder)"""

        # Get the volume name from the external reference
        target_vol_name = self._get_existing_volume_ref_name(external_ref)
        LOG.debug('Entering manage_existing. '
                  'Target_volume_name =%s', target_vol_name)

        # Get vol info from the volume name obtained from the reference
        vol_info = self.APIExecutor.get_vol_info(target_vol_name)

        # Check if volume is already managed by OpenStack
        if vol_info['agent_type'] == AGENT_TYPE_OPENSTACK or (
           vol_info['agent_type'] == AGENT_TYPE_OPENSTACK_GST):
            raise exception.ManageExistingAlreadyManaged(
                volume_ref=volume['id'])

        # If agent-type is not None then raise exception
        if vol_info['agent_type'] != AGENT_TYPE_NONE:
            msg = (_('Volume should have agent-type set as None.'))
            raise exception.InvalidVolume(reason=msg)

        new_vol_name = volume['name']
        LOG.info("Volume status before managing it : %(status)s",
                 {'status': vol_info['online']})
        if vol_info['online'] is True:
            msg = (_('Volume %s is online. Set volume to offline for '
                     'managing using OpenStack.') % target_vol_name)
            raise exception.InvalidVolume(reason=msg)

        # edit the volume
        data = {'data': {'name': new_vol_name}}
        if self._group_target_enabled is True:
            # check if any ACL's are attached to this volume
            if 'access_control_records' in vol_info and (
               vol_info['access_control_records'] is not None):
                msg = (_('Volume %s has ACL associated with it. Remove ACL '
                         'for managing using OpenStack') % target_vol_name)
                raise exception.InvalidVolume(reason=msg)
            data['data']['agent_type'] = AGENT_TYPE_OPENSTACK_GST
        else:
            data['data']['agent_type'] = AGENT_TYPE_OPENSTACK

        LOG.debug("Data for edit %(data)s", {'data': data})
        self.APIExecutor.edit_vol(target_vol_name, data)

        # make the volume online after rename
        self.APIExecutor.online_vol(new_vol_name, True)

        return self._get_model_info(new_vol_name)

    def manage_existing_get_size(self, volume, external_ref):
        """Return size of an existing volume"""

        LOG.debug('Volume name : %(name)s  External ref : %(ref)s',
                  {'name': volume['name'], 'ref': external_ref})

        target_vol_name = self._get_existing_volume_ref_name(external_ref)

        # get vol info
        vol_info = self.APIExecutor.get_vol_info(target_vol_name)

        LOG.debug('Volume size : %(size)s  Volume-name : %(name)s',
                  {'size': vol_info['size'], 'name': vol_info['name']})

        return int(vol_info['size'] / units.Ki)

    def unmanage(self, volume):
        """Removes the specified volume from Cinder management."""

        vol_name = volume['name']
        LOG.debug("Entering unmanage_volume volume =%s", vol_name)

        # check agent type
        vol_info = self.APIExecutor.get_vol_info(vol_name)
        if vol_info['agent_type'] != AGENT_TYPE_OPENSTACK and (
           vol_info['agent_type'] != AGENT_TYPE_OPENSTACK_GST):
            msg = (_('Only volumes managed by OpenStack can be unmanaged.'))
            raise exception.InvalidVolume(reason=msg)

        data = {'data': {'agent_type': AGENT_TYPE_NONE}}
        # update the agent-type to None
        self.APIExecutor.edit_vol(vol_name, data)

        # offline the volume
        self.APIExecutor.online_vol(vol_name, False)

    def _do_replication_setup(self, array_id=None):
        devices = self.configuration.replication_device
        if devices:
            dev = devices[0]
            remote_array = dict(dev.items())
            remote_array['san_login'] = (
                dev.get('ssh_login', self.configuration.san_login))
            remote_array['san_password'] = (
                dev.get('san_password', self.configuration.san_password))
            try:
                self.APIExecutor_remote_array = NimbleRestAPIExecutor(
                    username=remote_array['san_login'],
                    password=remote_array['san_password'],
                    ip=remote_array['san_ip'],
                    verify=self.verify)
                LOG.debug("created APIExecutor for remote ip: %(ip)s",
                          {'ip': remote_array['san_ip']})
            except Exception:
                LOG.error('Failed to create REST client.'
                          ' Check san_ip, username, password'
                          ' and make sure the array version is compatible')
                raise

            self._replicated_type = True
            self.remote_array = remote_array

    def do_setup(self, context):
        """Setup the Nimble Cinder volume driver."""
        self._check_config()
        # Setup API Executor
        san_ip = self.configuration.san_ip
        LOG.debug("san_ip: %(ip)s", {'ip': san_ip})
        try:
            self.APIExecutor = NimbleRestAPIExecutor(
                username=self.configuration.san_login,
                password=self.configuration.san_password,
                ip=self.configuration.san_ip,
                verify=self.verify)
            if self._storage_protocol == constants.ISCSI:
                group_info = self.APIExecutor.get_group_info()
                self._enable_group_scoped_target(group_info)
        except Exception:
            LOG.error('Failed to create REST client. '
                      'Check san_ip, username, password'
                      ' and make sure the array version is compatible')
            raise
        self._update_existing_vols_agent_type(context)
        self._do_replication_setup()
        if self._replicated_type:
            LOG.debug("for %(ip)s, schedule_name is: %(name)s",
                      {'ip': san_ip,
                       'name': self.remote_array['schedule_name']})

    def _update_existing_vols_agent_type(self, context):
        backend_name = self.configuration.safe_get('volume_backend_name')
        all_vols = volume.VolumeList.get_all(
            context, None, None, None, None, {'status': 'available'})
        for vol in all_vols:
            if backend_name in vol.host:
                try:
                    vol_info = self.APIExecutor.get_vol_info(vol.name)
                    # update agent_type only if no ACL's are present
                    if 'access_control_records' in vol_info and (
                       vol_info['access_control_records'] is None):
                        if self._group_target_enabled:
                            LOG.debug("Updating %(vol)s to have agent_type :"
                                      "%(agent)s",
                                      {'vol': vol.name,
                                       'agent': AGENT_TYPE_OPENSTACK_GST})
                            # check if this is an upgrade case from
                            # openstack to openstackv2
                            if vol_info['agent_type'] == AGENT_TYPE_NONE:
                                data = {'data': {'agent_type':
                                                 AGENT_TYPE_OPENSTACK_GST}}
                                self.APIExecutor.edit_vol(vol.name, data)
                            elif vol_info['agent_type'] == (
                                    AGENT_TYPE_OPENSTACK):
                                # 1. update the agent type to None
                                data = {'data': {'agent_type':
                                                 AGENT_TYPE_NONE}}
                                self.APIExecutor.edit_vol(vol.name, data)
                                # 2. update the agent type to openstack_gst
                                data = {'data': {'agent_type':
                                                 AGENT_TYPE_OPENSTACK_GST}}
                                self.APIExecutor.edit_vol(vol.name, data)
                        else:
                            LOG.debug("Updating %(vol)s to have agent_type :"
                                      "%(agent)s",
                                      {'vol': vol.name,
                                       'agent': AGENT_TYPE_OPENSTACK_GST})
                            if vol_info['agent_type'] == AGENT_TYPE_NONE:
                                data = {'data': {'agent_type':
                                                 AGENT_TYPE_OPENSTACK}}
                                self.APIExecutor.edit_vol(vol.name, data)
                            elif vol_info['agent_type'] == (
                                    AGENT_TYPE_OPENSTACK_GST):
                                # 1. update the agent type to None
                                data = {'data': {'agent_type':
                                                 AGENT_TYPE_NONE}}
                                self.APIExecutor.edit_vol(vol.name, data)
                                # 2. update the agent type to openstack
                                data = {'data': {'agent_type':
                                                 AGENT_TYPE_OPENSTACK}}
                                self.APIExecutor.edit_vol(vol.name, data)
                except NimbleAPIException:
                    # just log the error but don't fail driver initialization
                    LOG.warning('Error updating agent-type for '
                                'volume %s.', vol.name)

    def _get_model_info(self, volume_name):
        """Get model info for the volume."""
        return (
            {'provider_location': self._get_provider_location(volume_name),
             'provider_auth': None})

    @abc.abstractmethod
    def _get_provider_location(self, volume_name):
        """Volume info for iSCSI and FC"""

        pass

    def _create_igroup_for_initiator(self, initiator_name, wwpns):
        """Creates igroup for an initiator and returns the igroup name."""
        igrp_name = 'openstack-' + self._generate_random_string(12)
        LOG.info('Creating initiator group %(grp)s '
                 'with initiator %(iname)s',
                 {'grp': igrp_name, 'iname': initiator_name})
        if self._storage_protocol == constants.ISCSI:
            self.APIExecutor.create_initiator_group(igrp_name)
            self.APIExecutor.add_initiator_to_igroup(igrp_name, initiator_name)
        elif self._storage_protocol == constants.FC:
            self.APIExecutor.create_initiator_group_fc(igrp_name)
            for wwpn in wwpns:
                self.APIExecutor.add_initiator_to_igroup_fc(igrp_name, wwpn)
        return igrp_name

    def _get_igroupname_for_initiator_fc(self, initiator_wwpns):
        initiator_groups = self.APIExecutor.get_initiator_grp_list()
        for initiator_group in initiator_groups:
            if 'fc_initiators' in initiator_group and initiator_group[
               'fc_initiators'] is not None:
                wwpns_list = []
                for initiator in initiator_group['fc_initiators']:
                    wwpn = str(initiator['wwpn']).replace(":", "")
                    wwpns_list.append(wwpn)
                LOG.debug("initiator_wwpns=%(initiator)s "
                          "wwpns_list_from_array=%(wwpns)s",
                          {'initiator': initiator_wwpns,
                           'wwpns': wwpns_list})
                if set(initiator_wwpns) == set(wwpns_list):
                    LOG.info('igroup %(grp)s found for '
                             'initiator %(wwpns_list)s',
                             {'grp': initiator_group['name'],
                              'wwpns_list': wwpns_list})
                    return initiator_group['name']
        LOG.info('No igroup found for initiators %s', initiator_wwpns)
        return ''

    def _get_igroupname_for_initiator(self, initiator_name):
        initiator_groups = self.APIExecutor.get_initiator_grp_list()
        for initiator_group in initiator_groups:
            if initiator_group['iscsi_initiators'] is not None:
                if (len(initiator_group['iscsi_initiators']) == 1 and
                    initiator_group['iscsi_initiators'][0]['iqn'] ==
                        initiator_name):
                    LOG.info('igroup %(grp)s found for '
                             'initiator %(iname)s',
                             {'grp': initiator_group['name'],
                              'iname': initiator_name})
                    return initiator_group['name']
        LOG.info('No igroup found for initiator %s', initiator_name)
        return ''

    def get_lun_number(self, volume, initiator_group_name):
        vol_info = self.APIExecutor.get_vol_info(volume['name'])
        for acl in vol_info['access_control_records']:
            if (initiator_group_name == acl['initiator_group_name']):
                LOG.info("access_control_record =%(acl)s",
                         {'acl': acl})
                lun = acl['lun']
                LOG.info("LUN : %(lun)s", {"lun": lun})
                return lun
        raise NimbleAPIException(_("Lun number not found for volume %(vol)s "
                                   "with initiator_group: %(igroup)s") %
                                 {'vol': volume['name'],
                                  'igroup': initiator_group_name})

    def _is_multiattach(self, volume):
        if volume.multiattach:
            attachment_list = volume.volume_attachment
            try:
                attachment_list = attachment_list.objects
            except AttributeError:
                pass

            if attachment_list is not None and len(attachment_list) > 1:
                LOG.info("Volume %(volume)s is attached to multiple "
                         "instances on host %(host_name)s, "
                         "skip terminate volume connection",
                         {'volume': volume.name,
                          'host_name': volume.host.split('@')[0]})
                return True
        return False

    def revert_to_snapshot(self, context, volume, snapshot):
        vol_info = self.APIExecutor.get_vol_info(volume['name'])
        snap_info = self.APIExecutor.get_snap_info(snapshot['name'],
                                                   volume['name'])
        snap_id = snap_info['id']
        volume_id = vol_info['id']
        LOG.debug("Reverting volume %(vol)s with snapshot id %(snap_id)s",
                  {'vol': volume['name'], 'snap_id': snap_id})
        data = {'data': {"base_snap_id": snap_id, "id": volume_id}}
        try:
            self.APIExecutor.online_vol(volume['name'], False)
            self.APIExecutor.volume_restore(volume['name'], data)
            LOG.info("Volume %(vol)s is successfully restored with "
                     "snap_id %(snap_id)s",
                     {'vol': volume['name'], 'snap_id': snap_id})
            self.APIExecutor.online_vol(volume['name'], True)
        except NimbleAPIException as ex:
            raise NimbleAPIException(_("Unable to restore %(vol)s to "
                                       "%(snap_id)s: %(err)s") %
                                     {'vol': volume['name'],
                                      'snap_id': snap_id,
                                      'err': ex.message})
        return self._get_model_info(volume['name'])

    def is_volume_group_snap_type(self, volume_type):
        consis_group_snap_type = False
        if volume_type:
            extra_specs = volume_type.get('extra_specs')
            if 'consistent_group_snapshot_enabled' in extra_specs:
                gsnap_val = extra_specs['consistent_group_snapshot_enabled']
                consis_group_snap_type = (gsnap_val == "<is> True")
        return consis_group_snap_type

    def create_group(self, context, group):
        """Creates a generic group"""
        if not volume_utils.is_group_a_cg_snapshot_type(group):
            raise NotImplementedError()
        cg_type = False
        cg_name = group.id
        description = group.description if group.description else group.name
        LOG.info('Create group: %(name)s, %(description)s', {'name': cg_name,
                 'description': description})
        for volume_type in group.volume_types:
            if volume_type:
                extra_specs = volume_type.get('extra_specs')
                if 'consistent_group_snapshot_enabled' in extra_specs:
                    gsnap_val = extra_specs[
                        'consistent_group_snapshot_enabled']
                    cg_type = (gsnap_val == "<is> True")
                    if not cg_type:
                        msg = _('For a volume type to be a part of consistent'
                                ' group, volume type extra spec must have '
                                'consistent_group_snapshot_enabled'
                                '="<is> True"')
                        LOG.error(msg)
                        raise exception.InvalidInput(reason=msg)
        self.APIExecutor.create_volcoll(cg_name, description)
        return {'status': fields.GroupStatus.AVAILABLE}

    def delete_group(self, context, group, volumes):
        """Deletes a group."""
        if not volume_utils.is_group_a_cg_snapshot_type(group):
            raise NotImplementedError()
        LOG.info("Delete Consistency Group %s.", group.id)
        model_updates = {"status": fields.GroupStatus.DELETED}
        error_statuses = [
            fields.GroupStatus.ERROR,
            fields.GroupStatus.ERROR_DELETING,
        ]
        volume_model_updates = []
        for tmp_volume in volumes:
            update_item = {"id": tmp_volume.id}
            try:
                self.delete_volume(tmp_volume)
                update_item["status"] = "deleted"
            except exception.VolumeBackendAPIException:
                update_item["status"] = fields.VolumeStatus.ERROR_DELETING
                if model_updates["status"] not in error_statuses:
                    model_updates["status"] = fields.GroupStatus.ERROR_DELETING
                    LOG.error("Failed to delete volume %(vol_id)s of "
                              "group %(group_id)s.",
                              {"vol_id": tmp_volume.id, "group_id": group.id})
            volume_model_updates.append(update_item)
        cg_name = group.id
        cg_id = self.APIExecutor.get_volcoll_id_by_name(cg_name)
        self.APIExecutor.delete_volcoll(cg_id)
        return model_updates, volume_model_updates

    def update_group(self, context, group, add_volumes=None,
                     remove_volumes=None):
        if (not volume_utils.is_group_a_cg_snapshot_type(group)):
            raise NotImplementedError()
        model_update = {'status': fields.GroupStatus.AVAILABLE}

        for tmp_volume in add_volumes:
            volume_id = self.APIExecutor.get_volume_id_by_name(
                tmp_volume['name'])
            vol_snap_enable = self.is_volume_group_snap_type(
                tmp_volume.get('volume_type'))
            cg_id = self.APIExecutor.get_volcoll_id_by_name(group.id)
            try:
                if vol_snap_enable:
                    self.APIExecutor.associate_volcoll(volume_id, cg_id)
                else:
                    msg = (_('Volume with volume id %s is not '
                             'supported as extra specs of this '
                             'volume does not have '
                             'consistent_group_snapshot_enabled="<is> True"'
                             ) % volume['id'])
                    LOG.error(msg)
                    raise exception.InvalidInput(reason=msg)
            except NimbleAPIException:
                msg = ('Volume collection does not exist.')
                LOG.error(msg)
                raise NimbleAPIException(msg)

        for tmp_volume in remove_volumes:
            volume_id = self.APIExecutor.get_volume_id_by_name(
                tmp_volume['name'])
            try:
                self.APIExecutor.dissociate_volcoll(volume_id)
            except NimbleAPIException:
                msg = ('Volume collection does not exist.')
                LOG.error(msg)
                raise NimbleAPIException(msg)

        return model_update, None, None

    def create_group_snapshot(self, context, group_snapshot, snapshots):
        """Creates a group snapshot."""
        if not volume_utils.is_group_a_cg_snapshot_type(group_snapshot):
            raise NotImplementedError()
        group_id = group_snapshot.group_id
        snap_name = group_snapshot.id
        cg_id = self.APIExecutor.get_volcoll_id_by_name(group_id)
        try:
            self.APIExecutor.snapcoll_create(snap_name, cg_id)
        except NimbleAPIException:
            msg = ('Error creating cg snapshot')
            LOG.error(msg)
            raise NimbleAPIException(msg)
        snapshot_model_updates = []
        for snapshot in snapshots:
            snapshot_update = {'id': snapshot['id'],
                               'status': fields.SnapshotStatus.AVAILABLE}
            snapshot_model_updates.append(snapshot_update)
        model_update = {'status': fields.GroupSnapshotStatus.AVAILABLE}
        return model_update, snapshot_model_updates

    def delete_group_snapshot(self, context, group_snapshot, snapshots):
        """Deletes a group snapshot."""
        if not volume_utils.is_group_a_cg_snapshot_type(group_snapshot):
            raise NotImplementedError()
        snap_name = group_snapshot.id
        model_update = {'status': fields.ConsistencyGroupStatus.DELETED}
        snapshots_model_update = []
        snapcoll_id = self.APIExecutor.get_snapcoll_id_by_name(snap_name)
        try:
            self.APIExecutor.snapcoll_delete(snapcoll_id)
            for snapshot in snapshots:
                snapshots_model_update.append(
                    {'id': snapshot.id,
                     'status': fields.SnapshotStatus.DELETED})
        except Exception as e:
            LOG.error("Error deleting volume group snapshot."
                      "Error received: %(e)s", {'e': e})
            model_update = {
                'status': fields.GroupSnapshotStatus.ERROR_DELETING}
        return model_update, snapshots_model_update

    def create_group_from_src(self, context, group, volumes,
                              group_snapshot=None, snapshots=None,
                              source_group=None, source_vols=None):
        """Creates the volume group from source."""
        if not volume_utils.is_group_a_cg_snapshot_type(group):
            raise NotImplementedError()
        self.create_group(context, group)
        cg_id = self.APIExecutor.get_volcoll_id_by_name(group.id)
        try:
            if group_snapshot is not None and snapshots is not None:
                for tmp_volume, snapshot in zip(volumes, snapshots):
                    self.create_volume_from_snapshot(tmp_volume, snapshot)
                    volume_id = self.APIExecutor.get_volume_id_by_name(
                        tmp_volume['name'])
                    self.APIExecutor.associate_volcoll(volume_id, cg_id)
            elif source_group is not None and source_vols is not None:
                for tmp_volume, src_vol in zip(volumes, source_vols):
                    self.create_cloned_volume(tmp_volume, src_vol)
                    volume_id = self.APIExecutor.get_volume_id_by_name(
                        tmp_volume['name'])
                    self.APIExecutor.associate_volcoll(volume_id, cg_id)
        except NimbleAPIException:
            msg = ('Error creating cg snapshot')
            LOG.error(msg)
            raise NimbleAPIException(msg)
        return None, None

    def _time_to_secs(self, time):
        # time is specified as 'HH:MM' or 'HH:MM:SS'
        # qualified with am or pm, or in 24-hour clock
        time = time.strip("'")
        arr = time.split(':')
        (hours, minutes) = (arr[0], arr[1])
        total_secs = 0

        if len(arr) == 2:
            hours = int(hours)
            if minutes.endswith('pm'):
                # for time like 12:01pm, no need to add 12 to hours
                if hours != 12:
                    # for other time like 01:05pm, we have add 12 to hours
                    hours += 12
                minutes = minutes.strip('pm')
            if minutes.endswith('am'):
                minutes = minutes.strip('am')
            minutes = int(minutes)

            total_secs = hours * 3600 + minutes * 60
            return total_secs

        if len(arr) == 3:
            seconds = arr[2]
            hours = int(hours)
            minutes = int(minutes)

            if seconds.endswith('pm'):
                # for time like 12:01:01pm, no need to add 12 to hours
                if hours != 12:
                    # for other time like 01:05:05pm, we have add 12 to hours
                    hours += 12
                seconds = seconds.strip('pm')
            if seconds.endswith('am'):
                seconds = seconds.strip('am')
            seconds = int(seconds)

            total_secs = hours * 3600 + minutes * 60 + seconds
            return total_secs

    def enable_replication(self, context, group, volumes):
        LOG.debug("try to enable repl on group %(group)s", {'group': group.id})

        if not group.is_replicated:
            raise NotImplementedError()

        model_update = {}
        try:
            # If replication is enabled for volume type, apply the schedule
            nimble_group_name = group.id
            san_ip = self.configuration.san_ip

            # apply schedule
            sched_name = self.remote_array['schedule_name']
            partner_name = self.remote_array['downstream_partner']
            LOG.debug("for %(ip)s, schedule_name is: %(name)s",
                      {'ip': san_ip, 'name': sched_name})

            kwargs = {}
            optionals = ['period', 'period_unit', 'num_retain',
                         'num_retain_replica', 'at_time', 'until_time',
                         'days', 'replicate_every', 'alert_threshold']
            for key in optionals:
                if key in self.remote_array:
                    value = self.remote_array[key]
                    kwargs[key] = value

                    if key == 'at_time' or key == 'until_time':
                        seconds = self._time_to_secs(value)
                        kwargs[key] = seconds

            self.APIExecutor.set_schedule_for_volcoll(
                sched_name, nimble_group_name, partner_name, **kwargs)
            model_update.update({
                'replication_status': fields.ReplicationStatus.ENABLED})
        except Exception as e:
            model_update.update({
                'replication_status': fields.ReplicationStatus.ERROR})
            LOG.error("Error enabling replication on group %(group)s. "
                      "Exception received: %(e)s.",
                      {'group': group.id, 'e': e})

        return model_update, None

    def disable_replication(self, context, group, volumes):
        LOG.debug("try disable repl on group %(group)s", {'group': group.id})

        if not group.is_replicated:
            raise NotImplementedError()

        model_update = {}
        try:
            san_ip = self.configuration.san_ip
            sched_name = self.remote_array['schedule_name']
            LOG.debug("for %(ip)s, schedule_name is: %(name)s",
                      {'ip': san_ip, 'name': sched_name})

            data = self.APIExecutor.get_volcoll_details(group.id)
            LOG.debug("data: %(data)s", {'data': data})
            sched_id = data['schedule_list'][0]['id']

            self.APIExecutor.delete_schedule(sched_id)
            model_update.update({
                'replication_status': fields.ReplicationStatus.DISABLED})
        except Exception as e:
            model_update.update({
                'replication_status': fields.ReplicationStatus.ERROR})
            LOG.error("Error disabling replication on group %(group)s. "
                      "Exception received: %(e)s.",
                      {'group': group.id, 'e': e})

        return model_update, None

    def failover_replication(self, context, group, volumes,
                             secondary_backend_id=None):
        LOG.debug("try to failover/failback group %(group)s to %(backend)s",
                  {'group': group.id, 'backend': secondary_backend_id})

        group_update = {}
        volume_update_list = []

        partner_name = secondary_backend_id
        partner_id = None
        if partner_name != 'default':
            LOG.debug("failover to secondary array")
            partner_id = self.APIExecutor.get_partner_id_by_name(partner_name)
            LOG.debug("partner_id %(id)s", {'id': partner_id})

            volcoll_id = self.APIExecutor.get_volcoll_id_by_name(group.id)
            LOG.debug("volcoll_id %(id)s", {'id': volcoll_id})

            self.APIExecutor.handover(volcoll_id, partner_id)
            rep_status = fields.ReplicationStatus.FAILED_OVER

        if partner_name == 'default':
            LOG.debug("failback to primary array")

            data = self.APIExecutor_remote_array.get_volcoll_details(group.id)
            partner_name = data['replication_partner']
            LOG.debug("partner_name: %(name)s", {'name': partner_name})

            partner_id = self.APIExecutor_remote_array.get_partner_id_by_name(
                partner_name)
            LOG.debug("partner_id %(id)s", {'id': partner_id})

            volcoll_id = self.APIExecutor_remote_array.get_volcoll_id_by_name(
                group.id)
            LOG.debug("volcoll_id %(id)s", {'id': volcoll_id})

            self.APIExecutor_remote_array.handover(volcoll_id, partner_id)
            rep_status = fields.ReplicationStatus.ENABLED

        group_update['replication_status'] = rep_status
        for vol in volumes:
            volume_update = {
                'id': vol.id,
                'replication_status': rep_status}
            volume_update_list.append(volume_update)

        return group_update, volume_update_list


@interface.volumedriver
class NimbleISCSIDriver(NimbleBaseVolumeDriver, san.SanISCSIDriver):

    """OpenStack driver to enable Nimble ISCSI Controller."""

    def __init__(self, *args, **kwargs):
        super(NimbleISCSIDriver, self).__init__(*args, **kwargs)
        self._storage_protocol = constants.ISCSI
        self._group_target_name = None

    def _set_gst_for_group(self):
        group_info = self.APIExecutor.get_group_info()
        if 'group_target_enabled' in group_info and (
                group_info['group_target_enabled']) is True and (
                    'group_target_name' in group_info) and (
                    group_info['group_target_name'] is not None):
            self._group_target_name = group_info['group_target_name']

    def _get_gst_for_group(self):
        return self._group_target_name

    def initialize_connection(self, volume, connector):
        """Driver entry point to attach a volume to an instance."""
        LOG.info('Entering initialize_connection volume=%(vol)s'
                 ' connector=%(conn)s location=%(loc)s',
                 {'vol': volume,
                  'conn': connector,
                  'loc': volume['provider_location']})
        initiator_name = connector['initiator']
        initiator_group_name = self._get_igroupname_for_initiator(
            initiator_name)
        if not initiator_group_name:
            initiator_group_name = self._create_igroup_for_initiator(
                initiator_name, None)
        LOG.info('Initiator group name is %(grp)s for initiator '
                 '%(iname)s',
                 {'grp': initiator_group_name, 'iname': initiator_name})
        self.APIExecutor.add_acl(volume, initiator_group_name)
        properties = {"driver_volume_type": "iscsi",
                      "data": {"target_discovered": False, "discard": True}}
        properties['data']['volume_id'] = volume['id']  # used by xen currently
        (iscsi_portal, iqn) = volume['provider_location'].split()
        if self._get_gst_for_group() is not None:
            lun_num = self.get_lun_number(volume, initiator_group_name)
            netconfig = self.APIExecutor.get_netconfig('active')
            target_portals = self._get_data_ips(netconfig)
            LOG.info("target portals %(portals)s", {'portals': target_portals})
            target_luns = [int(lun_num)] * len(target_portals)
            target_iqns = [iqn] * len(target_portals)
            LOG.debug("target iqns %(iqns)s target luns %(luns)s",
                      {'iqns': target_iqns, 'luns': target_luns})
            if target_luns and target_iqns and target_portals:
                properties["data"]["target_luns"] = target_luns
                properties["data"]["target_iqns"] = target_iqns
                properties["data"]["target_portals"] = target_portals
        else:
            # handling volume scoped target
            lun_num = LUN_ID
            properties['data']['target_portal'] = iscsi_portal
            properties['data']['target_iqn'] = iqn
            properties['data']['target_lun'] = int(lun_num)

        return properties

    def terminate_connection(self, volume, connector, **kwargs):
        """Driver entry point to unattach a volume from an instance."""
        LOG.info('Entering terminate_connection volume=%(vol)s'
                 ' connector=%(conn)s location=%(loc)s.',
                 {'vol': volume['name'],
                  'conn': connector,
                  'loc': volume['provider_location']})

        if connector is None:
            LOG.warning("Removing ALL host connections for volume %s",
                        volume)
            self.APIExecutor.remove_all_acls(volume)
            return
        if self._is_multiattach(volume):
            return

        initiator_name = connector['initiator']
        initiator_group_name = self._get_igroupname_for_initiator(
            initiator_name)
        if not initiator_group_name:
            raise NimbleDriverException(_('No initiator group found for '
                                          'initiator %s') % initiator_name)
        self.APIExecutor.remove_acl(volume, initiator_group_name)
        eventlet.sleep(DEFAULT_SLEEP)

    def _get_provider_location(self, volume_name):
        """Get volume iqn for initiator access."""
        vol_info = self.APIExecutor.get_vol_info(volume_name)
        netconfig = self.APIExecutor.get_netconfig('active')
        self._set_gst_for_group()
        if self._get_gst_for_group() is not None:
            iqn = self._get_gst_for_group()
        else:
            iqn = vol_info['target_name']
        target_ipaddr = self._get_discovery_ip(netconfig)
        iscsi_portal = target_ipaddr + ':3260'
        provider_location = '%s %s' % (iscsi_portal, iqn)
        LOG.info('vol_name=%(name)s provider_location=%(loc)s',
                 {'name': volume_name, 'loc': provider_location})
        return provider_location

    def _get_data_ips(self, netconfig):
        """Get data ips."""
        subnet_label = self.configuration.nimble_subnet_label
        LOG.debug('subnet_label used %(netlabel)s, netconfig %(netconf)s',
                  {'netlabel': subnet_label, 'netconf': netconfig})
        ret_data_ips = []
        for subnet in netconfig['array_list'][0]['nic_list']:
            LOG.info('Exploring array subnet label %s', subnet[
                'subnet_label'])
            if subnet['data_ip']:
                if subnet_label == '*':
                    # if all subnets are mentioned then return all portals
                    # else just return specific subnet
                    LOG.info('Data ip %(data_ip)s is used '
                             'on data subnet %(net_label)s',
                             {'data_ip': subnet['data_ip'],
                              'net_label': subnet['subnet_label']})
                    ret_data_ips.append(str(subnet['data_ip']) + ':3260')
                elif subnet_label == subnet['subnet_label']:
                    LOG.info('Data ip %(data_ip)s is used'
                             ' on subnet %(net_label)s',
                             {'data_ip': subnet['data_ip'],
                              'net_label': subnet['subnet_label']})
                    data_ips_single_subnet = []
                    data_ips_single_subnet.append(str(subnet['data_ip']) +
                                                  ':3260')
                    return data_ips_single_subnet
        if ret_data_ips:
            LOG.info('Data ips %s', ret_data_ips)
            return ret_data_ips
        else:
            raise NimbleDriverException(_('No suitable data ip found'))

    def _get_discovery_ip(self, netconfig):
        """Get discovery ip."""
        subnet_label = self.configuration.nimble_subnet_label
        LOG.debug('subnet_label used %(netlabel)s, netconfig %(netconf)s',
                  {'netlabel': subnet_label, 'netconf': netconfig})
        ret_discovery_ip = ''
        for subnet in netconfig['subnet_list']:
            LOG.info('Exploring array subnet label %s', subnet['label'])
            if subnet_label == '*':
                # Use the first data subnet, save mgmt+data for later
                if subnet['type'] == SM_SUBNET_DATA:
                    LOG.info('Discovery ip %(disc_ip)s is used '
                             'on data subnet %(net_label)s',
                             {'disc_ip': subnet['discovery_ip'],
                              'net_label': subnet['label']})
                    return subnet['discovery_ip']
                elif (subnet['type'] == SM_SUBNET_MGMT_PLUS_DATA):
                    LOG.info('Discovery ip %(disc_ip)s is found'
                             ' on mgmt+data subnet %(net_label)s',
                             {'disc_ip': subnet['discovery_ip'],
                              'net_label': subnet['label']})
                    ret_discovery_ip = subnet['discovery_ip']
            # If subnet is specified and found, use the subnet
            elif subnet_label == subnet['label']:
                LOG.info('Discovery ip %(disc_ip)s is used'
                         ' on subnet %(net_label)s',
                         {'disc_ip': subnet['discovery_ip'],
                          'net_label': subnet['label']})
                return subnet['discovery_ip']
        if ret_discovery_ip:
            LOG.info('Discovery ip %s is used on mgmt+data subnet',
                     ret_discovery_ip)
            return ret_discovery_ip
        else:
            raise NimbleDriverException(_('No suitable discovery ip found'))


@interface.volumedriver
class NimbleFCDriver(NimbleBaseVolumeDriver, driver.FibreChannelDriver):
    """OpenStack driver to enable Nimble FC Driver Controller."""

    def __init__(self, *args, **kwargs):
        super(NimbleFCDriver, self).__init__(*args, **kwargs)
        self._storage_protocol = constants.FC
        self._lookup_service = fczm_utils.create_lookup_service()

    def _get_provider_location(self, volume_name):
        """Get array info wwn details."""
        netconfig = self.APIExecutor.get_netconfig('active')
        array_name = netconfig['group_leader_array']
        provider_location = '%s' % (array_name)
        LOG.info('vol_name=%(name)s provider_location=%(loc)s',
                 {'name': volume_name, 'loc': provider_location})
        return provider_location

    def _build_initiator_target_map(self, target_wwns, connector):
        """Build the target_wwns and the initiator target map."""
        LOG.debug("_build_initiator_target_map for %(wwns)s",
                  {'wwns': target_wwns})
        init_targ_map = {}

        if self._lookup_service:
            # use FC san lookup to determine which wwpns to use
            # for the new VLUN.
            dev_map = self._lookup_service.get_device_mapping_from_network(
                connector['wwpns'],
                target_wwns)
            map_fabric = dev_map
            LOG.info("dev_map =%(fabric)s", {'fabric': map_fabric})

            for fabric_name in dev_map:
                fabric = dev_map[fabric_name]
                for initiator in fabric['initiator_port_wwn_list']:
                    if initiator not in init_targ_map:
                        init_targ_map[initiator] = []
                    init_targ_map[initiator] += fabric['target_port_wwn_list']
                    init_targ_map[initiator] = list(set(
                        init_targ_map[initiator]))
        else:
            init_targ_map = dict.fromkeys(connector["wwpns"], target_wwns)

        return init_targ_map

    def initialize_connection(self, volume, connector):
        """Driver entry point to attach a volume to an instance."""
        LOG.info('Entering initialize_connection volume=%(vol)s'
                 ' connector=%(conn)s location=%(loc)s',
                 {'vol': volume,
                  'conn': connector,
                  'loc': volume['provider_location']})
        wwpns = []
        initiator_name = connector['initiator']
        for wwpn in connector['wwpns']:
            wwpns.append(wwpn)
        initiator_group_name = self._get_igroupname_for_initiator_fc(wwpns)

        if not initiator_group_name:
            initiator_group_name = self._create_igroup_for_initiator(
                initiator_name, wwpns)

        LOG.info('Initiator group name is %(grp)s for initiator '
                 '%(iname)s',
                 {'grp': initiator_group_name, 'iname': initiator_name})
        self.APIExecutor.add_acl(volume, initiator_group_name)
        lun = self.get_lun_number(volume, initiator_group_name)
        init_targ_map = {}
        (array_name) = volume['provider_location'].split()

        target_wwns = self.get_wwpns_from_array(array_name)

        init_targ_map = self._build_initiator_target_map(target_wwns,
                                                         connector)

        data = {'driver_volume_type': 'fibre_channel',
                'data': {'target_lun': lun,
                         'target_discovered': True,
                         'discard': True,
                         'target_wwn': target_wwns,
                         'initiator_target_map': init_targ_map}}

        LOG.info("Return FC data for zone addition: %(data)s.",
                 {'data': data})
        fczm_utils.add_fc_zone(data)
        return data

    def terminate_connection(self, volume, connector, **kwargs):
        """Driver entry point to unattach a volume from an instance."""
        LOG.info('Entering terminate_connection volume=%(vol)s'
                 ' connector=%(conn)s location=%(loc)s.',
                 {'vol': volume,
                  'conn': connector,
                  'loc': volume['provider_location']})
        wwpns = []
        if connector is None:
            LOG.warning("Removing ALL host connections for volume %s",
                        volume)
            self.APIExecutor.remove_all_acls(volume)
            return
        if self._is_multiattach(volume):
            return

        initiator_name = connector['initiator']
        for wwpn in connector['wwpns']:
            wwpns.append(wwpn)
        (array_name) = volume['provider_location'].split()
        target_wwns = self.get_wwpns_from_array(array_name)
        init_targ_map = self._build_initiator_target_map(target_wwns,
                                                         connector)
        initiator_group_name = self._get_igroupname_for_initiator_fc(wwpns)
        if not initiator_group_name:
            raise NimbleDriverException(
                _('No initiator group found for initiator %s') %
                initiator_name)
        LOG.debug("initiator_target_map %s", init_targ_map)
        self.APIExecutor.remove_acl(volume, initiator_group_name)
        eventlet.sleep(DEFAULT_SLEEP)
        # FIXME to check for other volumes attached to the host and then
        # return the data. Bug https://bugs.launchpad.net/cinder/+bug/1617472

        data = {'driver_volume_type': 'fibre_channel',
                'data': {'target_wwn': target_wwns}}

        # FIXME: need to optionally add the initiator_target_map here when
        # there are no more volumes exported to the initiator / target pair
        # otherwise the zone will never get removed.
        fczm_utils.remove_fc_zone(data)
        return data

    def get_wwpns_from_array(self, array_name):
        """Retrieve the wwpns from the array"""
        LOG.debug("get_wwpns_from_array %s", array_name)
        target_wwpns = []
        interface_info = self.APIExecutor.get_fc_interface_list(array_name)
        LOG.info("interface_info %(interface_info)s",
                 {"interface_info": interface_info})
        for wwpn_list in interface_info:
            wwpn = wwpn_list['wwpn']
            wwpn = wwpn.replace(":", "")
            target_wwpns.append(wwpn)

        return target_wwpns


def _connection_checker(func):
    """Decorator to re-establish and re-run the api if session has expired."""
    @functools.wraps(func)
    def inner_connection_checker(self, *args, **kwargs):
        for attempts in range(2):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                if attempts < 1 and (re.search("Failed to execute",
                                     str(e))):
                    LOG.info('Session might have expired.'
                             ' Trying to relogin')
                    self.login()
                    continue
                else:
                    LOG.error('Re-throwing Exception %s', e)
                    raise
    return inner_connection_checker


class NimbleRestAPIExecutor(object):

    """Makes Nimble REST API calls."""

    def __init__(self, api_version=NimbleDefaultVersion, *args, **kwargs):
        self.token_id = None
        self.ip = kwargs['ip']
        self.username = kwargs['username']
        self.password = kwargs['password']
        self.verify = kwargs['verify']
        self.api_version = api_version
        self.uri = "https://%(ip)s:5392/v%(version)s/" % {
            'ip': self.ip,
            'version': self.api_version}
        self.login()

    def login(self):
        data = {'data': {"username": self.username,
                         "password": self.password,
                         "app_name": "NimbleCinderDriver"}}
        r = requests.post(self.uri + "tokens",
                          data=json.dumps(data),
                          verify=self.verify)

        if r.status_code != 201 and r.status_code != 200:
            msg = _("Failed to login for user %s"), self.username
            raise NimbleAPIException(msg)
        self.token_id = r.json()['data']['session_token']
        self.headers = {'X-Auth-Token': self.token_id}

    def get_group_id(self):
        api = 'groups'
        r = self.get(api)
        if not r.json()['data']:
            raise NimbleAPIException(_("Unable to retrieve Group Object for : "
                                       "%s") % self.ip)
        return r.json()['data'][0]['id']

    def get_group_info(self):
        group_id = self.get_group_id()
        api = 'groups/' + str(group_id)
        r = self.get(api)
        if not r.json()['data']:
            raise NimbleAPIException(_("Unable to retrieve Group info for: %s")
                                     % group_id)
        return r.json()['data']

    def get_folder_id(self, folder_name):
        api = 'folders'
        filter = {"name": folder_name}
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise NimbleAPIException(_("Unable to retrieve information for "
                                       "Folder: %s") % folder_name)
        return r.json()['data'][0]['id']

    def get_performance_policy_id(self, perf_policy_name):
        api = 'performance_policies/'
        filter = {'name': perf_policy_name}
        LOG.debug("Performance policy Name %s", perf_policy_name)
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise NimbleAPIException(_("No performance policy found for: "
                                     "%(perf)s") % {'perf': perf_policy_name})
        LOG.debug("Performance policy ID :%(perf)s",
                  {'perf': r.json()['data'][0]['id']})
        return r.json()['data'][0]['id']

    def get_netconfig(self, role):
        api = "network_configs/detail"
        filter = {'role': role}
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise NimbleAPIException(_("No %s network config exists") % role)
        return r.json()['data'][0]

    def _get_volumetype_extraspecs(self, volume):
        specs = {}

        type_id = volume['volume_type_id']
        if type_id is not None:
            specs = volume_types.get_volume_type_extra_specs(type_id)
        return specs

    def _get_extra_spec_values(self, extra_specs):
        """Nimble specific extra specs."""
        perf_policy_name = extra_specs.get(EXTRA_SPEC_PERF_POLICY,
                                           DEFAULT_PERF_POLICY_SETTING)
        encryption = extra_specs.get(EXTRA_SPEC_ENCRYPTION,
                                     DEFAULT_ENCRYPTION_SETTING)
        iops_limit = extra_specs.get(EXTRA_SPEC_IOPS_LIMIT,
                                     DEFAULT_IOPS_LIMIT_SETTING)
        folder_name = extra_specs.get(EXTRA_SPEC_FOLDER,
                                      DEFAULT_FOLDER_SETTING)
        dedupe = extra_specs.get(EXTRA_SPEC_DEDUPE,
                                 DEFAULT_DEDUPE_SETTING)
        extra_specs_map = {}
        extra_specs_map[EXTRA_SPEC_PERF_POLICY] = perf_policy_name
        extra_specs_map[EXTRA_SPEC_ENCRYPTION] = encryption
        extra_specs_map[EXTRA_SPEC_IOPS_LIMIT] = iops_limit
        extra_specs_map[EXTRA_SPEC_DEDUPE] = dedupe
        extra_specs_map[EXTRA_SPEC_FOLDER] = folder_name
        return extra_specs_map

    def get_valid_nimble_extraspecs(self, extra_specs_map, vol_info):

        extra_specs_map_updated = self._get_extra_spec_values(extra_specs_map)
        data = {"data": {}}
        perf_policy_name = extra_specs_map_updated[EXTRA_SPEC_PERF_POLICY]
        perf_policy_id = self.get_performance_policy_id(perf_policy_name)
        data['perfpolicy_id'] = perf_policy_id

        encrypt = extra_specs_map_updated[EXTRA_SPEC_ENCRYPTION]
        cipher = DEFAULT_CIPHER
        if encrypt.lower() == 'yes':
            cipher = AES_256_XTS_CIPHER
        data['cipher'] = cipher
        if extra_specs_map.get('multiattach') == "<is> True":
            data['multi_initiator'] = True
        else:
            data['multi_initiator'] = False
        folder_name = extra_specs_map_updated[EXTRA_SPEC_FOLDER]
        folder_id = None
        pool_id = vol_info['pool_id']
        pool_name = vol_info['pool_name']
        if folder_name is not None:
            # validate if folder exists in pool_name
            pool_info = self.get_pool_info(pool_id)
            if 'folder_list' in pool_info and (pool_info['folder_list'] is
                                               not None):
                for folder_list in pool_info['folder_list']:
                    LOG.debug("folder_list : %s", folder_list)
                    if folder_list['fqn'] == "/" + folder_name:
                        LOG.debug("Folder %(folder)s present in pool "
                                  "%(pool)s",
                                  {'folder': folder_name,
                                   'pool': pool_name})
                        folder_id = self.get_folder_id(folder_name)
                        if folder_id is not None:
                            data['data']["folder_id"] = folder_id
                if folder_id is None:
                    raise NimbleAPIException(_("Folder '%(folder)s' not "
                                               "present in pool  '%("
                                               "pool)s'") %
                                             {'folder': folder_name,
                                              'pool': pool_name})
            else:
                raise NimbleAPIException(_(
                    "Folder '%(folder)s' not present in pool '%(pool)s'")
                    % {'folder': folder_name,
                       'pool': pool_name})
        iops_limit = extra_specs_map_updated[EXTRA_SPEC_IOPS_LIMIT]
        if iops_limit is not None:
            if not iops_limit.isdigit() or (
               int(iops_limit) < MIN_IOPS) or (int(iops_limit) > MAX_IOPS):
                raise NimbleAPIException(_("%(err)s [%(min)s, %(max)s]")
                                         % {'err': IOPS_ERR_MSG,
                                            'min': MIN_IOPS,
                                            'max': MAX_IOPS})

            data['data']['limit_iops'] = iops_limit

        dedupe = extra_specs_map_updated[EXTRA_SPEC_DEDUPE]
        if dedupe.lower() == 'true':
            data['data']['dedupe_enabled'] = True

        return data

    def create_vol(self, volume, pool_name, reserve, protocol, is_gst_enabled):
        response = self._execute_create_vol(volume, pool_name, reserve,
                                            protocol, is_gst_enabled)
        LOG.info('Successfully created volume %(name)s',
                 {'name': response['name']})
        return response['name']

    def _is_ascii(self, value):
        try:
            return all(ord(c) < 128 for c in value)
        except TypeError:
            return False

    def _execute_create_vol(self, volume, pool_name, reserve, protocol,
                            is_gst_enabled):
        """Create volume

        :return: r['data']
        """

        # Set volume size, display name and description
        volume_size = volume['size'] * units.Ki
        reserve_size = 100 if reserve else 0
        # Set volume description
        display_name = getattr(volume, 'display_name', '')
        display_description = getattr(volume, 'display_description', '')
        if self._is_ascii(display_name) and self._is_ascii(
                display_description):
            display_list = [getattr(volume, 'display_name', ''),
                            getattr(volume, 'display_description', '')]
            description = ':'.join(filter(None, display_list))
        elif self._is_ascii(display_name):
            description = display_name
        elif self._is_ascii(display_description):
            description = display_description
        else:
            description = ""

        # Limit description size to 254 characters
        description = description[:254]
        pool_id = self.get_pool_id(pool_name)

        specs = self._get_volumetype_extraspecs(volume)
        extra_specs_map = self._get_extra_spec_values(specs)
        perf_policy_name = extra_specs_map[EXTRA_SPEC_PERF_POLICY]
        perf_policy_id = self.get_performance_policy_id(perf_policy_name)
        encrypt = extra_specs_map[EXTRA_SPEC_ENCRYPTION]
        multi_initiator = volume.get('multiattach', False)
        folder_name = extra_specs_map[EXTRA_SPEC_FOLDER]
        iops_limit = extra_specs_map[EXTRA_SPEC_IOPS_LIMIT]
        dedupe = extra_specs_map[EXTRA_SPEC_DEDUPE]

        cipher = DEFAULT_CIPHER
        if encrypt.lower() == 'yes':
            cipher = AES_256_XTS_CIPHER
        if is_gst_enabled is True:
            agent_type = AGENT_TYPE_OPENSTACK_GST
        else:
            agent_type = AGENT_TYPE_OPENSTACK

        LOG.debug('Creating a new volume=%(vol)s size=%(size)s'
                  ' reserve=%(reserve)s in pool=%(pool)s'
                  ' description=%(description)s with Extra Specs'
                  ' perfpol-name=%(perfpol-name)s'
                  ' encryption=%(encryption)s cipher=%(cipher)s'
                  ' agent-type=%(agent-type)s'
                  ' multi-initiator=%(multi-initiator)s',
                  {'vol': volume['name'],
                   'size': volume_size,
                   'reserve': reserve_size,
                   'pool': pool_name,
                   'description': description,
                   'perfpol-name': perf_policy_name,
                   'encryption': encrypt,
                   'cipher': cipher,
                   'agent-type': agent_type,
                   'multi-initiator': multi_initiator})
        data = {"data":
                {'name': volume['name'],
                 'description': description,
                 'size': volume_size,
                 'reserve': reserve_size,
                 'warn_level': int(WARN_LEVEL),
                 'limit': 100,
                 'snap_limit': DEFAULT_SNAP_QUOTA,
                 'online': True,
                 'pool_id': pool_id,
                 'agent_type': agent_type,
                 'perfpolicy_id': perf_policy_id,
                 'encryption_cipher': cipher}}

        if protocol == constants.ISCSI:
            data['data']['multi_initiator'] = multi_initiator

        if dedupe.lower() == 'true':
            data['data']['dedupe_enabled'] = True

        folder_id = None
        if folder_name is not None:
            # validate if folder exists in pool_name
            pool_info = self.get_pool_info(pool_id)
            if 'folder_list' in pool_info and (pool_info['folder_list'] is
                                               not None):
                for folder_list in pool_info['folder_list']:
                    LOG.debug("folder_list : %s", folder_list)
                    if folder_list['fqn'] == "/" + folder_name:
                        LOG.debug("Folder %(folder)s present in pool "
                                  "%(pool)s",
                                  {'folder': folder_name,
                                   'pool': pool_name})
                        folder_id = self.get_folder_id(folder_name)
                        if folder_id is not None:
                            data['data']["folder_id"] = folder_id
                if folder_id is None:
                    raise NimbleAPIException(_("Folder '%(folder)s' not "
                                               "present in pool '%(pool)s'") %
                                             {'folder': folder_name,
                                              'pool': pool_name})
            else:
                raise NimbleAPIException(_("Folder '%(folder)s' not present in"
                                           " pool '%(pool)s'") %
                                         {'folder': folder_name,
                                          'pool': pool_name})

        if iops_limit is not None:
            if not iops_limit.isdigit() or (
               int(iops_limit) < MIN_IOPS) or (int(iops_limit) > MAX_IOPS):
                raise NimbleAPIException(_("%(err)s [%(min)s, %(max)s]") %
                                         {'err': IOPS_ERR_MSG,
                                          'min': MIN_IOPS,
                                          'max': MAX_IOPS})

            data['data']['limit_iops'] = iops_limit

        LOG.debug("Volume metadata :%s", volume.metadata)
        for key, value in volume.metadata.items():
            LOG.debug("Key %(key)s Value %(value)s",
                      {'key': key, 'value': value})
            if key == EXTRA_SPEC_IOPS_LIMIT and value.isdigit():
                if type(value) is int or int(value) < MIN_IOPS or (
                   int(value) > MAX_IOPS):
                    raise NimbleAPIException(_("%(err)s [%(min)s, %(max)s]") %
                                             {'err': IOPS_ERR_MSG,
                                              'min': MIN_IOPS,
                                              'max': MAX_IOPS})
                LOG.debug("IOPS Limit %s", value)
                data['data']['limit_iops'] = value
        LOG.debug("Data : %s", data)

        api = 'volumes'
        r = self.post(api, data)
        return r['data']

    def create_initiator_group(self, initiator_grp_name):
        api = "initiator_groups"
        data = {"data": {"name": initiator_grp_name,
                         "access_protocol": "iscsi",
                         }}
        r = self.post(api, data)
        return r['data']

    def create_initiator_group_fc(self, initiator_grp_name):
        api = "initiator_groups"

        data = {}
        data["data"] = {}
        data["data"]["name"] = initiator_grp_name
        data["data"]["access_protocol"] = "fc"
        r = self.post(api, data)
        return r['data']

    def get_initiator_grp_id(self, initiator_grp_name):
        api = "initiator_groups"
        filter = {'name': initiator_grp_name}
        r = self.get_query(api, filter)
        return r.json()['data'][0]['id']

    def add_initiator_to_igroup(self, initiator_grp_name, initiator_name):
        initiator_group_id = self.get_initiator_grp_id(initiator_grp_name)
        api = "initiators"
        data = {"data": {
            "access_protocol": "iscsi",
            "initiator_group_id": initiator_group_id,
            "label": initiator_name,
            "iqn": initiator_name
        }}
        r = self.post(api, data)
        return r['data']

    def add_initiator_to_igroup_fc(self, initiator_grp_name, wwpn):
        initiator_group_id = self.get_initiator_grp_id(initiator_grp_name)
        api = "initiators"
        data = {"data": {
            "access_protocol": "fc",
            "initiator_group_id": initiator_group_id,
            "wwpn": self._format_to_wwpn(wwpn)
        }}
        r = self.post(api, data)
        return r['data']

    def get_pool_id(self, pool_name):
        api = "pools/"
        filter = {'name': pool_name}
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise NimbleAPIException(_("Unable to retrieve information for "
                                       "pool : %(pool)s") %
                                     {'pool': pool_name})
        return r.json()['data'][0]['id']

    def get_pool_info(self, pool_id):
        api = 'pools/' + str(pool_id)
        r = self.get(api)
        return r.json()['data']

    def get_initiator_grp_list(self):
        api = "initiator_groups/detail"
        r = self.get(api)
        if 'data' not in r.json():
            raise NimbleAPIException(_("Unable to retrieve initiator group "
                                       "list"))
        LOG.info('Successfully retrieved InitiatorGrpList')
        return r.json()['data']

    def get_initiator_grp_id_by_name(self, initiator_group_name):
        api = 'initiator_groups'
        filter = {"name": initiator_group_name}
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise NimbleAPIException(_("Unable to retrieve information for "
                                       "initiator group : %s") %
                                     initiator_group_name)
        return r.json()['data'][0]['id']

    def get_volume_id_by_name(self, name):
        api = "volumes"
        filter = {"name": name}
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise NimbleAPIException(_("Unable to retrieve information for "
                                       "volume: %s") % name)
        return r.json()['data'][0]['id']

    def get_volume_name(self, volume_id):
        api = "volumes/" + str(volume_id)
        r = self.get(api)
        if not r.json()['data']:
            raise NimbleAPIException(_("Unable to retrieve information for "
                                       "volume: %s") % volume_id)
        return r.json()['data']['name']

    def add_acl(self, volume, initiator_group_name):
        initiator_group_id = self.get_initiator_grp_id_by_name(
            initiator_group_name)
        volume_id = self.get_volume_id_by_name(volume['name'])
        data = {'data': {"apply_to": 'both',
                         "initiator_group_id": initiator_group_id,
                         "vol_id": volume_id
                         }}
        api = 'access_control_records'
        try:
            self.post(api, data)
        except NimbleAPIException as ex:
            LOG.debug("add_acl_exception: %s", ex)
            if SM_OBJ_EXIST_MSG in str(ex):
                LOG.warning('Volume %(vol)s : %(state)s',
                            {'vol': volume['name'],
                             'state': SM_OBJ_EXIST_MSG})
            else:
                msg = (_("Add access control failed with error:  %s") %
                       str(ex))
                raise NimbleAPIException(msg)

    def get_acl_record(self, volume_id, initiator_group_id):
        filter = {"vol_id": volume_id,
                  "initiator_group_id": initiator_group_id}
        api = "access_control_records"
        r = self.get_query(api, filter)
        LOG.info("ACL record is %(result)s", {'result': r.json()})
        if not r.json()['data']:
            LOG.warning('ACL is not available for this volume %(vol_id)s', {
                        'vol_id': volume_id})
            return
        return r.json()['data'][0]

    def get_volume_acl_records(self, volume_id):
        api = "volumes/" + str(volume_id)
        r = self.get(api)
        if not r.json()['data']:
            raise NimbleAPIException(_("Unable to retrieve information for "
                                       "volume: %s") % volume_id)
        return r.json()['data']['access_control_records']

    def remove_all_acls(self, volume):
        LOG.info("removing all access control list from volume=%(vol)s",
                 {"vol": volume['name']})
        volume_id = self.get_volume_id_by_name(volume['name'])
        acl_records = self.get_volume_acl_records(volume_id)
        if acl_records is not None:
            for acl_record in acl_records:
                LOG.info("removing acl=%(acl)s with igroup=%(igroup)s",
                         {"acl": acl_record['id'],
                          "igroup": acl_record['initiator_group_name']})
                self.remove_acl(volume, acl_record['initiator_group_name'])

    def remove_acl(self, volume, initiator_group_name):
        LOG.info("removing ACL from volume=%(vol)s "
                 "and %(igroup)s",
                 {"vol": volume['name'],
                  "igroup": initiator_group_name})
        initiator_group_id = self.get_initiator_grp_id_by_name(
            initiator_group_name)
        volume_id = self.get_volume_id_by_name(volume['name'])

        try:
            acl_record = self.get_acl_record(volume_id, initiator_group_id)
            LOG.debug("ACL Record %(acl)s", {"acl": acl_record})
            if acl_record is not None:
                acl_id = acl_record['id']
                api = 'access_control_records/%s' % acl_id
                self.delete(api)
        except NimbleAPIException as ex:
            LOG.debug("remove_acl_exception: %s", ex)
            if SM_OBJ_ENOENT_MSG in str(ex):
                LOG.warning('Volume %(vol)s : %(state)s',
                            {'vol': volume['name'],
                             'state': SM_OBJ_ENOENT_MSG})
            else:
                msg = (_("Remove access control failed with error:  %s") %
                       str(ex))
                raise NimbleAPIException(msg)

    def get_snap_info_by_id(self, snap_id, vol_id):
        filter = {"id": snap_id, "vol_id": vol_id}
        api = 'snapshots'
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise NimbleAPIException(_("Unable to retrieve snapshot info for "
                                       "snap_id: %(snap)s volume id: %(vol)s")
                                     % {'snap': snap_id,
                                        'vol': vol_id})
        LOG.debug("SnapInfo :%s", r.json()['data'][0])
        return r.json()['data'][0]

    def get_snap_info(self, snap_name, vol_name):
        filter = {"name": snap_name, "vol_name": vol_name}
        api = 'snapshots'
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise NimbleAPIException(_("Snapshot: %(snap)s of Volume: %(vol)s "
                                       "doesn't exist") %
                                     {'snap': snap_name,
                                      'vol': vol_name})
        return r.json()['data'][0]

    def get_snap_info_detail(self, snap_id):
        api = 'snapshots/detail'
        filter = {'id': snap_id}
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise NimbleAPIException(_("Snapshot: %s doesn't exist") % snap_id)
        return r.json()['data'][0]

    def get_volcoll_id_by_name(self, volcoll_name):
        api = "volume_collections"
        filter = {"name": volcoll_name}
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise Exception("Unable to retrieve information for volcoll: {0}"
                            .format(volcoll_name))
        return r.json()['data'][0]['id']

    def get_volcoll_details(self, volcoll_name):
        api = "volume_collections/detail"
        filter = {"name": volcoll_name}
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise Exception("Unable to retrieve information for volcoll: {0}"
                            .format(volcoll_name))
        return r.json()['data'][0]

    def get_snapcoll_id_by_name(self, snapcoll_name):
        api = "snapshot_collections"
        filter = {"name": snapcoll_name}
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise Exception("Unable to retrieve information for snapcoll: {0}"
                            .format(snapcoll_name))
        return r.json()['data'][0]['id']

    def create_volcoll(self, volcoll_name, description=''):
        api = "volume_collections"
        data = {"data": {"name": volcoll_name, "description": description}}
        r = self.post(api, data)
        return r['data']

    def delete_volcoll(self, volcoll_id):
        api = "volume_collections/" + str(volcoll_id)
        self.delete(api)

    def dissociate_volcoll(self, volume_id):
        api = "volumes/" + str(volume_id)
        data = {'data': {"volcoll_id": ''
                         }
                }
        r = self.put(api, data)
        return r

    def associate_volcoll(self, volume_id, volcoll_id):
        api = "volumes/" + str(volume_id)
        data = {'data': {"volcoll_id": volcoll_id
                         }
                }
        r = self.put(api, data)
        return r

    def snapcoll_create(self, snapcoll_name, volcoll_id):
        data = {'data': {"name": snapcoll_name,
                         "volcoll_id": volcoll_id
                         }
                }
        api = 'snapshot_collections'
        r = self.post(api, data)
        return r

    def snapcoll_delete(self, snapcoll_id):
        api = "snapshot_collections/" + str(snapcoll_id)
        self.delete(api)

    @utils.retry(NimbleAPIException, 2, 3)
    def online_vol(self, volume_name, online_flag):
        volume_id = self.get_volume_id_by_name(volume_name)
        LOG.debug("volume_id %s", str(volume_id))
        eventlet.sleep(DEFAULT_SLEEP)
        api = "volumes/" + str(volume_id)
        data = {'data': {"online": online_flag, 'force': True}}
        try:
            LOG.debug("data :%s", data)
            self.put(api, data)
            LOG.debug("Volume %(vol)s is in requested online state :%(flag)s",
                      {'vol': volume_name,
                       'flag': online_flag})
        except Exception as ex:
            msg = (_("Error  %s") % ex)
            LOG.debug("online_vol_exception: %s", msg)
            if msg.__contains__("Object is %s" % SM_STATE_MSG):
                LOG.warning('Volume %(vol)s : %(state)s',
                            {'vol': volume_name,
                             'state': SM_STATE_MSG})
            # TODO(rkumar): Check if we need to ignore the connected
            # initiator
            elif msg.__contains__("Initiators are connected to"):
                raise NimbleAPIException(msg)
            else:
                raise exception.InvalidVolume(reason=msg)

    def online_snap(self, volume_name, online_flag, snap_name):
        snap_info = self.get_snap_info(snap_name, volume_name)
        api = "snapshots/" + str(snap_info['id'])
        data = {'data': {"online": online_flag}}
        try:
            self.put(api, data)
            LOG.debug("Snapshot %(snap)s is in requested online state "
                      ":%(flag)s",
                      {'snap': snap_name, 'flag': online_flag})
        except Exception as ex:
            LOG.debug("online_snap_exception: %s", ex)
            if str(ex).__contains__("Object %s" % SM_STATE_MSG):
                LOG.warning('Snapshot %(snap)s :%(state)s',
                            {'snap': snap_name,
                             'state': SM_STATE_MSG})
            else:
                raise

    @utils.retry(NimbleAPIException, 2, 3)
    def get_vol_info(self, volume_name):
        volume_id = self.get_volume_id_by_name(volume_name)
        api = 'volumes/' + str(volume_id)
        r = self.get(api)
        if not r.json()['data']:
            raise exception.VolumeNotFound(_("Volume: %s not found") %
                                           volume_name)
        return r.json()['data']

    def delete_vol(self, volume_name):
        volume_id = self.get_volume_id_by_name(volume_name)
        api = "volumes/" + str(volume_id)
        self.delete(api)

    def snap_vol(self, snapshot):
        api = "snapshots"
        volume_name = snapshot['volume_name']
        vol_id = self.get_volume_id_by_name(volume_name)
        snap_name = snapshot['name']
        # Set snapshot description
        display_list = [
            getattr(snapshot, 'display_name', snapshot['display_name']),
            getattr(snapshot, 'display_description', '')]
        snap_description = ':'.join(filter(None, display_list))
        # Limit to 254 characters
        snap_description = snap_description[:254]
        data = {"data": {"name": snap_name,
                         "description": snap_description,
                         "vol_id": vol_id
                         }
                }
        r = self.post(api, data)
        return r['data']

    def clone_vol(self, volume, snapshot, reserve, is_gst_enabled,
                  protocol, pool_name):
        api = "volumes"
        volume_name = snapshot['volume_name']
        snap_name = snapshot['name']
        snap_info = self.get_snap_info(snap_name, volume_name)
        clone_name = volume['name']
        snap_size = snapshot['volume_size']
        reserve_size = 100 if reserve else 0

        specs = self._get_volumetype_extraspecs(volume)
        extra_specs_map = self._get_extra_spec_values(specs)
        perf_policy_name = extra_specs_map.get(EXTRA_SPEC_PERF_POLICY)
        perf_policy_id = self.get_performance_policy_id(perf_policy_name)
        encrypt = extra_specs_map.get(EXTRA_SPEC_ENCRYPTION)
        multi_initiator = volume.get('multiattach', False)
        iops_limit = extra_specs_map[EXTRA_SPEC_IOPS_LIMIT]
        folder_name = extra_specs_map[EXTRA_SPEC_FOLDER]
        pool_id = self.get_pool_id(pool_name)
        # default value of cipher for encryption
        cipher = DEFAULT_CIPHER
        if encrypt.lower() == 'yes':
            cipher = AES_256_XTS_CIPHER
        if is_gst_enabled is True:
            agent_type = AGENT_TYPE_OPENSTACK_GST
        else:
            agent_type = AGENT_TYPE_OPENSTACK

        LOG.info('Cloning volume from snapshot volume=%(vol)s '
                 'snapshot=%(snap)s clone=%(clone)s snap_size=%(size)s '
                 'reserve=%(reserve)s' 'agent-type=%(agent-type)s '
                 'perfpol-name=%(perfpol-name)s '
                 'encryption=%(encryption)s cipher=%(cipher)s '
                 'multi-initiator=%(multi-initiator)s',
                 {'vol': volume_name,
                  'snap': snap_name,
                  'clone': clone_name,
                  'size': snap_size,
                  'reserve': reserve_size,
                  'agent-type': agent_type,
                  'perfpol-name': perf_policy_name,
                  'encryption': encrypt,
                  'cipher': cipher,
                  'multi-initiator': multi_initiator})

        data = {"data": {"name": clone_name,
                         "clone": 'true',
                         "base_snap_id": snap_info['id'],
                         'snap_limit': DEFAULT_SNAP_QUOTA,
                         'warn_level': int(WARN_LEVEL),
                         'limit': 100,
                         "online": 'true',
                         "reserve": reserve_size,
                         "agent_type": agent_type,
                         "perfpolicy_id": perf_policy_id,
                         "encryption_cipher": cipher
                         }
                }
        if protocol == constants.ISCSI:
            data['data']['multi_initiator'] = multi_initiator

        folder_id = None
        if folder_name is not None:
            # validate if folder exists in pool_name
            pool_info = self.get_pool_info(pool_id)
            if 'folder_list' in pool_info and (pool_info['folder_list'] is
                                               not None):
                for folder_list in pool_info['folder_list']:
                    LOG.debug("folder_list : %s", folder_list)
                    if folder_list['fqn'] == "/" + folder_name:
                        LOG.debug("Folder %(folder)s present in pool "
                                  "%(pool)s",
                                  {'folder': folder_name,
                                   'pool': pool_name})
                        folder_id = self.get_folder_id(folder_name)
                        if folder_id is not None:
                            data['data']["folder_id"] = folder_id
                if folder_id is None:
                    raise NimbleAPIException(_("Folder '%(folder)s' not "
                                               "present in pool '%(pool)s'") %
                                             {'folder': folder_name,
                                              'pool': pool_name})
            else:
                raise NimbleAPIException(_("Folder '%(folder)s' not present in"
                                           " pool '%(pool)s'") %
                                         {'folder': folder_name,
                                          'pool': pool_name})

        if iops_limit is not None:
            if not iops_limit.isdigit() or (
               int(iops_limit) < MIN_IOPS) or (int(iops_limit) > MAX_IOPS):
                raise NimbleAPIException(_("%(err)s [%(min)s, %(max)s]") %
                                         {'err': IOPS_ERR_MSG,
                                          'min': MIN_IOPS,
                                          'max': MAX_IOPS})

            data['data']['limit_iops'] = iops_limit
        if iops_limit is not None:
            if not iops_limit.isdigit() or (
               int(iops_limit) < MIN_IOPS) or (int(iops_limit) > MAX_IOPS):
                raise NimbleAPIException(_("Please set valid IOPS limit"
                                         " in the range [%(min)s, %(max)s]") %
                                         {'min': MIN_IOPS,
                                          'max': MAX_IOPS})
            data['data']['limit_iops'] = iops_limit

        LOG.debug("Volume metadata :%s", volume.metadata)
        for key, value in volume.metadata.items():
            LOG.debug("Key %(key)s Value %(value)s",
                      {'key': key, 'value': value})
            if key == EXTRA_SPEC_IOPS_LIMIT and value.isdigit():
                if type(value) is int or int(value) < MIN_IOPS or (
                   int(value) > MAX_IOPS):
                    raise NimbleAPIException(_("Please enter valid IOPS "
                                               "limit in the range ["
                                               "%(min)s, %(max)s]") %
                                             {'min': MIN_IOPS,
                                              'max': MAX_IOPS})
                LOG.debug("IOPS Limit %s", value)
                data['data']['limit_iops'] = value

        r = self.post(api, data)
        return r['data']

    def edit_vol(self, volume_name, data):
        vol_id = self.get_volume_id_by_name(volume_name)
        api = "volumes/" + str(vol_id)
        self.put(api, data)

    def delete_snap(self, volume_name, snap_name):
        snap_info = self.get_snap_info(snap_name, volume_name)
        api = "snapshots/" + str(snap_info['id'])
        try:
            self.delete(api)
        except NimbleAPIException as ex:
            LOG.debug("delete snapshot exception: %s", ex)
            if SM_OBJ_HAS_CLONE in str(ex):
                # if snap has a clone log the error and continue ahead
                LOG.warning('Snapshot %(snap)s : %(state)s',
                            {'snap': snap_name,
                             'state': SM_OBJ_HAS_CLONE})
            else:
                raise

    def volume_restore(self, volume_name, data):
        volume_id = self.get_volume_id_by_name(volume_name)
        api = 'volumes/%s/actions/restore' % volume_id
        self.post(api, data)

    @_connection_checker
    def get(self, api):
        return self.get_query(api, None)

    @_connection_checker
    def get_query(self, api, query):
        url = self.uri + api
        return requests.get(url, headers=self.headers,
                            params=query, verify=self.verify)

    @_connection_checker
    def put(self, api, payload):
        url = self.uri + api
        r = requests.put(url, data=json.dumps(payload),
                         headers=self.headers, verify=self.verify)
        if r.status_code != 201 and r.status_code != 200:
            base = "Failed to execute api %(api)s : Error Code :%(code)s" % {
                'api': api,
                'code': r.status_code}
            LOG.debug("Base error : %(base)s", {'base': base})
            try:
                msg = _("%(base)s Message: %(msg)s") % {
                    'base': base,
                    'msg': r.json()['messages'][1]['text']}
            except IndexError:
                msg = _("%(base)s Message: %(msg)s") % {
                    'base': base,
                    'msg': str(r.json())}
            raise NimbleAPIException(msg)
        return r.json()

    @_connection_checker
    def post(self, api, payload):
        url = self.uri + api
        r = requests.post(url, data=json.dumps(payload),
                          headers=self.headers, verify=self.verify)
        if r.status_code != 201 and r.status_code != 200:
            msg = _("Failed to execute api %(api)s : %(msg)s : %(code)s") % {
                'api': api,
                'msg': r.json()['messages'][1]['text'],
                'code': r.status_code}
            raise NimbleAPIException(msg)
        return r.json()

    @_connection_checker
    def delete(self, api):
        url = self.uri + api
        r = requests.delete(url, headers=self.headers, verify=self.verify)
        if r.status_code != 201 and r.status_code != 200:
            base = "Failed to execute api %(api)s: Error Code: %(code)s" % {
                'api': api,
                'code': r.status_code}
            LOG.debug("Base error : %(base)s", {'base': base})
            try:
                msg = _("%(base)s Message: %(msg)s") % {
                    'base': base,
                    'msg': r.json()['messages'][1]['text']}
            except IndexError:
                msg = _("%(base)s Message: %(msg)s") % {
                    'base': base,
                    'msg': str(r.json())}
            raise NimbleAPIException(msg)
        return r.json()

    def _format_to_wwpn(self, string_wwpn):
        return ':'.join(a + b for a, b in zip(* [iter(string_wwpn)] * 2))

    def get_fc_interface_list(self, array_name):
        """getFibreChannelInterfaceList API to get FC interfaces on array."""
        api = 'fibre_channel_interfaces/detail'
        filter = {'array_name_or_serial': array_name}
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise NimbleAPIException(_("No fc interfaces for array %s") %
                                     array_name)
        return r.json()['data']

    def enable_group_scoped_target(self):
        group_id = self.get_group_id()
        api = "groups/" + str(group_id)
        data = {'data': {'group_target_enabled': True}}
        self.put(api, data)

    def set_schedule_for_volcoll(self, sched_name, volcoll_name,
                                 repl_partner,
                                 period=1,
                                 period_unit='days',
                                 num_retain=10,
                                 num_retain_replica=1,
                                 at_time=0,           # 00:00
                                 until_time=86340,    # 23:59
                                 days='all',
                                 replicate_every=1,
                                 alert_threshold='24:00'):
        volcoll_id = self.get_volcoll_id_by_name(volcoll_name)
        api = "protection_schedules"

        sched_details = {'name': sched_name,
                         'volcoll_or_prottmpl_type': "volume_collection",
                         'volcoll_or_prottmpl_id': volcoll_id,
                         'downstream_partner': repl_partner,
                         'period': period,
                         'period_unit': period_unit,
                         'num_retain': num_retain,
                         'num_retain_replica': num_retain_replica}

        if at_time != 0:
            sched_details['at_time'] = at_time
        if until_time != 86340:
            sched_details['until_time'] = until_time
        if days != 'all':
            sched_details['days'] = days
        if replicate_every != 1:
            sched_details['replicate_every'] = replicate_every
        if alert_threshold != '24:00':
            sched_details['alert_threshold'] = alert_threshold

        data = {'data': sched_details}

        r = self.post(api, data)
        return r['data']

    def delete_schedule(self, sched_id):
        api = "protection_schedules/" + str(sched_id)
        self.delete(api)

    def claim_vol(self, volume_id, group_id):
        api = "volumes/" + str(volume_id)
        group_id = str(group_id)
        data = {'data': {"owned_by_group_id": group_id
                         }
                }
        r = self.put(api, data)
        return r

    def get_partner_id_by_name(self, partner_name):
        api = "replication_partners"
        filter = {"name": partner_name}
        r = self.get_query(api, filter)
        if not r.json()['data']:
            raise Exception("Unable to retrieve information for partner: {0}"
                            .format(partner_name))
        return r.json()['data'][0]['id']

    def handover(self, volcoll_id, partner_id):
        volcoll_id = str(volcoll_id)
        partner_id = str(partner_id)
        api = "volume_collections/" + volcoll_id + "/actions/handover"
        data = {'data': {"id": volcoll_id,
                         "replication_partner_id": partner_id
                         }
                }
        self.post(api, data)
