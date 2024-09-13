# Copyright 2014 IBM Corp.
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

import random

from eventlet import greenthread
from oslo_concurrency import processutils
from oslo_log import log as logging
from oslo_utils import excutils

from cinder import exception
from cinder.i18n import _
from cinder import ssh_utils
from cinder import utils
from cinder.volume.drivers.ibm.storwize_svc import storwize_const
from cinder.volume import volume_utils

LOG = logging.getLogger(__name__)


class StorwizeSVCReplication(object):
    def __init__(self, driver, replication_target=None):
        self.driver = driver
        self.target = replication_target or {}

    @volume_utils.trace
    def failover_volume_host(self, context, vref):
        # Make the aux volume writeable.
        try:
            tgt_volume = storwize_const.REPLICA_AUX_VOL_PREFIX + vref.name
            self.target_helpers.stop_relationship(tgt_volume, access=True)
            try:
                self.target_helpers.start_relationship(tgt_volume, 'aux')
            except exception.VolumeBackendAPIException as e:
                LOG.error('Error running startrcrelationship due to %(err)s.',
                          {'err': e})
            return
        except Exception as e:
            msg = (_('Unable to fail-over the volume %(id)s to the '
                   'secondary back-end, error: %(error)s') %
                   {"id": vref['id'], "error": str(e)})
            LOG.exception(msg)
            raise exception.VolumeDriverException(message=msg)

    @volume_utils.trace
    def replication_failback(self, volume):
        tgt_volume = storwize_const.REPLICA_AUX_VOL_PREFIX + volume['name']
        rel_info = self.target_helpers.get_relationship_info(tgt_volume)
        if rel_info:
            try:
                self.target_helpers.stop_relationship(tgt_volume, access=True)
                self.target_helpers.start_relationship(tgt_volume, 'master')
                return
            except Exception as e:
                msg = (_('Unable to fail-back the volume: %(vol)s to the '
                         'master back-end, error: %(error)s') %
                       {"vol": volume['name'], "error": str(e)})
                LOG.exception(msg)
                raise exception.VolumeDriverException(message=msg)

    def volume_replication_setup(self, context, vref):
        pass


class StorwizeSVCReplicationGlobalMirror(StorwizeSVCReplication):
    """Support for Storwize/SVC global mirror mode replication.

    Global Mirror establishes a Global Mirror relationship between
    two volumes of equal size. The volumes in a Global Mirror relationship
    are referred to as the master (source) volume and the auxiliary
    (target) volume. This mode is dedicated to the asynchronous volume
    replication.
    """

    asyncmirror = True

    def __init__(self, driver, replication_target=None, target_helpers=None):
        super(StorwizeSVCReplicationGlobalMirror, self).__init__(
            driver, replication_target)
        self.target_helpers = target_helpers

    def volume_replication_setup(self, context, vref):
        LOG.debug('enter: volume_replication_setup: volume %s', vref['name'])

        target_vol_name = storwize_const.REPLICA_AUX_VOL_PREFIX + vref['name']
        try:
            opts = self.driver._get_vdisk_params(vref['volume_type_id'])
            pool = self.target.get('pool_name')
            src_attr = self.driver._helpers.get_vdisk_attributes(
                vref['name'])
            opts['iogrp'] = src_attr['IO_group_id']
            try:
                self.target_helpers.create_vdisk(target_vol_name,
                                                 str(vref['size']),
                                                 'gb', pool, opts)
            except exception.VolumeBackendAPIException as excp:
                if "CMMVC6035E" in excp.msg:
                    LOG.info('Target Volume: %(vol)s already exists',
                             {'vol': target_vol_name})

            target_system_id = self.driver._aux_state['system_id']
            self.driver._helpers.create_relationship(
                vref['name'], target_vol_name, target_system_id,
                self.asyncmirror)
        except Exception as e:
            msg = (_("Unable to set up mirror mode replication for %(vol)s. "
                     "Exception: %(err)s.") % {'vol': vref['id'],
                                               'err': e})
            LOG.exception(msg)
            raise exception.VolumeDriverException(message=msg)
        LOG.debug('leave: volume_replication_setup:volume %s', vref['name'])


class StorwizeSVCReplicationMetroMirror(
        StorwizeSVCReplicationGlobalMirror):
    """Support for Storwize/SVC metro mirror mode replication.

    Metro Mirror establishes a Metro Mirror relationship between
    two volumes of equal size. The volumes in a Metro Mirror relationship
    are referred to as the master (source) volume and the auxiliary
    (target) volume.
    """

    asyncmirror = False

    def __init__(self, driver, replication_target=None, target_helpers=None):
        super(StorwizeSVCReplicationMetroMirror, self).__init__(
            driver, replication_target, target_helpers)


class StorwizeSVCReplicationGMCV(StorwizeSVCReplicationGlobalMirror):
    """Support for Storwize/SVC GMCV mode replication.

    Global Mirror with Change Volumes(GMCV) provides asynchronous replication
    based on point-in-time copies of data. The volumes in a GMCV relationship
    are referred to as the master (source) volume, master change volume, the
    auxiliary (target) volume and auxiliary change volume.
    """

    asyncmirror = True

    def __init__(self, driver, replication_target=None, target_helpers=None):
        super(StorwizeSVCReplicationGMCV, self).__init__(
            driver, replication_target, target_helpers)

    def volume_replication_setup(self, context, vref, new_type=None):
        LOG.debug('enter: volume_replication_setup: volume %s', vref['name'])
        source_change_vol_name = (storwize_const.REPLICA_CHG_VOL_PREFIX +
                                  vref['name'])
        target_vol_name = storwize_const.REPLICA_AUX_VOL_PREFIX + vref['name']
        target_change_vol_name = (storwize_const.REPLICA_CHG_VOL_PREFIX +
                                  target_vol_name)
        try:
            if new_type:
                new_type_opts = self.driver._get_vdisk_params(
                    new_type['id'], volume_type=new_type)
            src_attr = self.driver._helpers.get_vdisk_attributes(
                vref['name'])
            # Source change volume creation
            src_change_opts = self.driver._get_vdisk_params(
                vref['volume_type_id'])
            src_change_opts['iogrp'] = src_attr['IO_group_id']
            # Change volumes would usually be thin-provisioned
            src_change_opts['autoexpand'] = True
            src_change_pool = src_attr['mdisk_grp_name']
            if new_type:
                src_child_pool = (
                    new_type_opts['storwize_svc_src_child_pool'])
            else:
                src_child_pool = (
                    src_change_opts['storwize_svc_src_child_pool'])
            if src_child_pool:
                src_change_pool = src_child_pool
            try:
                self.driver._helpers.create_vdisk(source_change_vol_name,
                                                  str(vref['size']),
                                                  'gb',
                                                  src_change_pool,
                                                  src_change_opts)
            except exception.VolumeBackendAPIException as excp:
                if "CMMVC6035E" in excp.msg:
                    msg = ('Source change volume: %s already exists'
                           % source_change_vol_name)
                    LOG.info(msg)

            # Target volume creation
            target_opts = self.driver._get_vdisk_params(
                vref['volume_type_id'])
            target_pool = self.target.get('pool_name')
            target_opts['iogrp'] = src_attr['IO_group_id']
            try:
                self.target_helpers.create_vdisk(target_vol_name,
                                                 str(vref['size']),
                                                 'gb',
                                                 target_pool,
                                                 target_opts)
            except exception.VolumeBackendAPIException as excp:
                if "CMMVC6035E" in excp.msg:
                    msg = ('Target Volume: %s already exists'
                           % target_vol_name)
                    LOG.info(msg)

            # Target change volume creation
            target_change_opts = self.driver._get_vdisk_params(
                vref['volume_type_id'])
            target_change_pool = self.target.get('pool_name')
            if new_type:
                target_child_pool = (
                    new_type_opts['storwize_svc_target_child_pool'])
            else:
                target_child_pool = (
                    target_change_opts['storwize_svc_target_child_pool'])
            if target_child_pool:
                target_change_pool = target_child_pool
            target_change_opts['iogrp'] = src_attr['IO_group_id']
            # Change Volumes would usually be thin-provisioned
            target_change_opts['autoexpand'] = True
            try:
                self.target_helpers.create_vdisk(target_change_vol_name,
                                                 str(vref['size']),
                                                 'gb',
                                                 target_change_pool,
                                                 target_change_opts)
            except exception.VolumeBackendAPIException as excp:
                if "CMMVC6035E" in excp.msg:
                    msg = ('Target Change Volume: %s already exists'
                           % target_change_vol_name)
                    LOG.info(msg)

            target_system_id = self.driver._aux_state['system_id']
            # Get cycle_period_seconds
            src_change_opts = self.driver._get_vdisk_params(
                vref['volume_type_id'])
            cycle_period_seconds = src_change_opts.get('cycle_period_seconds')
            rc_name = self.driver._helpers.create_relationship(
                vref['name'], target_vol_name, target_system_id,
                self.asyncmirror, True, source_change_vol_name,
                cycle_period_seconds)
            # Set target change volume
            self.target_helpers.change_relationship_changevolume(
                target_vol_name, target_change_vol_name, False,
                rc_name)
            # Start gmcv relationship
            self.driver._helpers.start_relationship(vref['name'],
                                                    rcrel=rc_name)
        except Exception as e:
            msg = (_("Unable to set up gmcv mode replication for %(vol)s. "
                     "Exception: %(err)s.") % {'vol': vref['id'],
                                               'err': str(e)})
            LOG.exception(msg)
            raise exception.VolumeDriverException(message=msg)
        LOG.debug('leave: volume_replication_setup:volume %s', vref['name'])


class StorwizeSVCReplicationManager(object):

    def __init__(self, driver, replication_target=None, target_helpers=None):
        self.sshpool = None
        self.driver = driver
        self.target = replication_target
        self.target_helpers = target_helpers(self._run_ssh)
        self._master_helpers = self.driver._master_backend_helpers
        self.global_m = StorwizeSVCReplicationGlobalMirror(
            self.driver, replication_target, self.target_helpers)
        self.metro_m = StorwizeSVCReplicationMetroMirror(
            self.driver, replication_target, self.target_helpers)
        self.gmcv = StorwizeSVCReplicationGMCV(
            self.driver, replication_target, self.target_helpers)

    def _run_ssh(self, cmd_list, check_exit_code=True, attempts=1):
        utils.check_ssh_injection(cmd_list)
        # TODO(vhou): We'll have a common method in ssh_utils to take
        # care of this _run_ssh method.
        command = ' '. join(cmd_list)

        if not self.sshpool:
            self.sshpool = ssh_utils.SSHPool(
                self.target.get('san_ip'),
                self.target.get('san_ssh_port', 22),
                self.target.get('ssh_conn_timeout', 30),
                self.target.get('san_login'),
                password=self.target.get('san_password'),
                privatekey=self.target.get('san_private_key', ''),
                min_size=self.target.get('ssh_min_pool_conn', 1),
                max_size=self.target.get('ssh_max_pool_conn', 5),)
        last_exception = None
        try:
            with self.sshpool.item() as ssh:
                while attempts > 0:
                    attempts -= 1
                    try:
                        return processutils.ssh_execute(
                            ssh, command, check_exit_code=check_exit_code)
                    except Exception as e:
                        LOG.error(str(e))
                        last_exception = e
                        greenthread.sleep(random.randint(20, 500) / 100.0)
                try:
                    raise processutils.ProcessExecutionError(
                        exit_code=last_exception.exit_code,
                        stdout=last_exception.stdout,
                        stderr=last_exception.stderr,
                        cmd=last_exception.cmd)
                except AttributeError:
                    raise processutils.ProcessExecutionError(
                        exit_code=-1, stdout="",
                        stderr="Error running SSH command",
                        cmd=command)
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.error("Error running SSH command: %s", command)

    def get_target_helpers(self):
        return self.target_helpers

    def get_replica_obj(self, rep_type):
        if rep_type == storwize_const.GLOBAL:
            return self.global_m
        elif rep_type == storwize_const.METRO:
            return self.metro_m
        elif rep_type == storwize_const.GMCV:
            return self.gmcv
        else:
            return None

    def _partnership_validate_create(self, client, remote_name, remote_ip):
        try:
            partnership_info = client.get_partnership_info(
                remote_name)
            if not partnership_info:
                candidate_info = client.get_partnershipcandidate_info(
                    remote_name)
                if candidate_info:
                    client.mkfcpartnership(remote_name)
                else:
                    client.mkippartnership(remote_ip)
        except Exception:
            msg = (_('Unable to establish the partnership with '
                     'the Storwize cluster %s.'), remote_name)
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

    def _partnership_start(self, client, remote_name):
        try:
            partnership_info = client.get_partnership_info(
                remote_name)
            if (partnership_info and
                    partnership_info['partnership'] != 'fully_configured'):
                client.chpartnership(partnership_info['id'])
        except Exception:
            msg = (_('Unable to start the partnership with '
                     'the Storwize cluster %s.'), remote_name)
            LOG.error(msg)
            raise exception.VolumeDriverException(message=msg)

    def establish_target_partnership(self):
        local_system_info = self._master_helpers.get_system_info()
        target_system_info = self.target_helpers.get_system_info()
        local_system_name = local_system_info['system_name']
        target_system_name = target_system_info['system_name']
        local_ip = self.driver.configuration.safe_get('san_ip')
        target_ip = self.target.get('san_ip')
        # Establish partnership only when the local system and the replication
        # target system is different.
        if target_system_name != local_system_name:
            self._partnership_validate_create(self._master_helpers,
                                              target_system_name, target_ip)
            self._partnership_validate_create(self.target_helpers,
                                              local_system_name, local_ip)
            self._partnership_start(self._master_helpers, target_system_name)
            self._partnership_start(self.target_helpers, local_system_name)
