# Copyright (c) 2014 SUSE Linux Products GmbH.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

__all__ = [
    'list_opts'
]

import copy
import itertools

import manila.api.common
import manila.api.middleware.auth
import manila.common.config
import manila.compute
import manila.compute.nova
import manila.coordination
import manila.data.drivers.nfs
import manila.data.helper
import manila.data.manager
import manila.db.api
import manila.db.base
import manila.exception
import manila.image
import manila.image.glance
import manila.message.api
import manila.network
import manila.network.linux.interface
import manila.network.neutron.api
import manila.network.neutron.neutron_network_plugin
import manila.network.standalone_network_plugin
import manila.quota
import manila.scheduler.drivers.base
import manila.scheduler.drivers.simple
import manila.scheduler.host_manager
import manila.scheduler.manager
import manila.scheduler.scheduler_options
import manila.scheduler.weighers
import manila.scheduler.weighers.capacity
import manila.scheduler.weighers.pool
import manila.service
import manila.share.api
import manila.share.driver
import manila.share.drivers.cephfs.driver
import manila.share.drivers.container.driver
import manila.share.drivers.container.storage_helper
import manila.share.drivers.dell_emc.driver
import manila.share.drivers.dell_emc.plugins.isilon.isilon
import manila.share.drivers.dell_emc.plugins.powermax.connection
import manila.share.drivers.generic
import manila.share.drivers.glusterfs
import manila.share.drivers.glusterfs.common
import manila.share.drivers.glusterfs.layout
import manila.share.drivers.glusterfs.layout_directory
import manila.share.drivers.glusterfs.layout_volume
import manila.share.drivers.hdfs.hdfs_native
import manila.share.drivers.hitachi.hnas.driver
import manila.share.drivers.hitachi.hsp.driver
import manila.share.drivers.hpe.hpe_3par_driver
import manila.share.drivers.huawei.huawei_nas
import manila.share.drivers.ibm.gpfs
import manila.share.drivers.infinidat.infinibox
import manila.share.drivers.infortrend.driver
import manila.share.drivers.inspur.as13000.as13000_nas
import manila.share.drivers.inspur.instorage.instorage
import manila.share.drivers.lvm
import manila.share.drivers.macrosan.macrosan_nas
import manila.share.drivers.maprfs.maprfs_native
import manila.share.drivers.netapp.options
import manila.share.drivers.nexenta.options
import manila.share.drivers.purestorage.flashblade
import manila.share.drivers.qnap.qnap
import manila.share.drivers.quobyte.quobyte
import manila.share.drivers.service_instance
import manila.share.drivers.tegile.tegile
import manila.share.drivers.vastdata.driver
import manila.share.drivers.windows.service_instance
import manila.share.drivers.windows.winrm_helper
import manila.share.drivers.zfsonlinux.driver
import manila.share.drivers.zfssa.zfssashare
import manila.share.drivers_private_data
import manila.share.hook
import manila.share.manager
import manila.volume
import manila.volume.cinder
import manila.wsgi.eventlet_server


# List of *all* options in [DEFAULT] namespace of manila.
# Any new option list or option needs to be registered here.
_global_opt_lists = [
    # Keep list alphabetically sorted
    manila.api.common.api_common_opts,
    [manila.api.middleware.auth.use_forwarded_for_opt],
    manila.common.config.core_opts,
    manila.common.config.debug_opts,
    manila.common.config.global_opts,
    manila.compute._compute_opts,
    manila.coordination.coordination_opts,
    manila.data.drivers.nfs.nfsbackup_service_opts,
    manila.data.helper.data_helper_opts,
    manila.data.manager.backup_opts,
    manila.data.manager.data_opts,
    manila.db.api.db_opts,
    [manila.db.base.db_driver_opt],
    manila.exception.exc_log_opts,
    manila.image._glance_opts,
    manila.message.api.messages_opts,
    manila.network.linux.interface.OPTS,
    manila.network.network_opts,
    manila.network.network_base_opts,
    manila.network.neutron.neutron_network_plugin.
    neutron_network_plugin_opts,
    manila.network.neutron.neutron_network_plugin.
    neutron_single_network_plugin_opts,
    manila.network.neutron.neutron_network_plugin.
    neutron_bind_network_plugin_opts,
    manila.network.neutron.neutron_network_plugin.
    neutron_binding_profile,
    manila.network.neutron.neutron_network_plugin.
    neutron_binding_profile_opts,
    manila.network.standalone_network_plugin.standalone_network_plugin_opts,
    manila.scheduler.drivers.base.scheduler_driver_opts,
    manila.scheduler.host_manager.host_manager_opts,
    [manila.scheduler.manager.scheduler_driver_opt],
    [manila.scheduler.scheduler_options.scheduler_json_config_location_opt],
    manila.scheduler.drivers.simple.simple_scheduler_opts,
    manila.scheduler.weighers.capacity.capacity_weight_opts,
    manila.scheduler.weighers.pool.pool_weight_opts,
    manila.service.service_opts,
    manila.share.api.share_api_opts,
    manila.share.driver.ganesha_opts,
    manila.share.driver.share_opts,
    manila.share.driver.ssh_opts,
    manila.share.drivers_private_data.private_data_opts,
    manila.share.drivers.cephfs.driver.cephfs_opts,
    manila.share.drivers.container.driver.container_opts,
    manila.share.drivers.container.storage_helper.lv_opts,
    manila.share.drivers.dell_emc.driver.EMC_NAS_OPTS,
    manila.share.drivers.dell_emc.plugins.powermax.connection.POWERMAX_OPTS,
    manila.share.drivers.generic.share_opts,
    manila.share.drivers.glusterfs.common.glusterfs_common_opts,
    manila.share.drivers.glusterfs.GlusterfsManilaShare_opts,
    manila.share.drivers.glusterfs.layout.glusterfs_share_layout_opts,
    manila.share.drivers.glusterfs.layout_directory.
    glusterfs_directory_mapped_opts,
    manila.share.drivers.glusterfs.layout_volume.glusterfs_volume_mapped_opts,
    manila.share.drivers.hdfs.hdfs_native.hdfs_native_share_opts,
    manila.share.drivers.hitachi.hnas.driver.hitachi_hnas_opts,
    manila.share.drivers.hitachi.hsp.driver.hitachi_hsp_opts,
    manila.share.drivers.hpe.hpe_3par_driver.HPE3PAR_OPTS,
    manila.share.drivers.huawei.huawei_nas.huawei_opts,
    manila.share.drivers.ibm.gpfs.gpfs_share_opts,
    manila.share.drivers.infinidat.infinibox.infinidat_auth_opts,
    manila.share.drivers.infinidat.infinibox.infinidat_connection_opts,
    manila.share.drivers.infinidat.infinibox.infinidat_general_opts,
    manila.share.drivers.infortrend.driver.infortrend_nas_opts,
    manila.share.drivers.inspur.as13000.as13000_nas.inspur_as13000_opts,
    manila.share.drivers.inspur.instorage.instorage.instorage_opts,
    manila.share.drivers.macrosan.macrosan_nas.macrosan_opts,
    manila.share.drivers.maprfs.maprfs_native.maprfs_native_share_opts,
    manila.share.drivers.lvm.share_opts,
    manila.share.drivers.netapp.options.netapp_proxy_opts,
    manila.share.drivers.netapp.options.netapp_connection_opts,
    manila.share.drivers.netapp.options.netapp_transport_opts,
    manila.share.drivers.netapp.options.netapp_basicauth_opts,
    manila.share.drivers.netapp.options.netapp_provisioning_opts,
    manila.share.drivers.netapp.options.netapp_data_motion_opts,
    manila.share.drivers.netapp.options.netapp_backup_opts,
    manila.share.drivers.nexenta.options.nexenta_connection_opts,
    manila.share.drivers.nexenta.options.nexenta_dataset_opts,
    manila.share.drivers.nexenta.options.nexenta_nfs_opts,
    manila.share.drivers.purestorage.flashblade.flashblade_auth_opts,
    manila.share.drivers.purestorage.flashblade.flashblade_extra_opts,
    manila.share.drivers.purestorage.flashblade.flashblade_connection_opts,
    manila.share.drivers.qnap.qnap.qnap_manila_opts,
    manila.share.drivers.quobyte.quobyte.quobyte_manila_share_opts,
    manila.share.drivers.service_instance.common_opts,
    manila.share.drivers.service_instance.no_share_servers_handling_mode_opts,
    manila.share.drivers.service_instance.share_servers_handling_mode_opts,
    manila.share.drivers.tegile.tegile.tegile_opts,
    manila.share.drivers.windows.service_instance.windows_share_server_opts,
    manila.share.drivers.windows.winrm_helper.winrm_opts,
    manila.share.drivers.zfsonlinux.driver.zfsonlinux_opts,
    manila.share.drivers.zfssa.zfssashare.ZFSSA_OPTS,
    manila.share.hook.hook_options,
    manila.share.manager.share_manager_opts,
    manila.volume._volume_opts,
    manila.wsgi.eventlet_server.socket_opts,
    manila.share.drivers.vastdata.driver.OPTS,
]

_opts = [
    (None, list(itertools.chain(*_global_opt_lists))),
    (manila.volume.cinder.CINDER_GROUP,
     list(itertools.chain(manila.volume.cinder.cinder_opts))),
    (manila.compute.nova.NOVA_GROUP,
     list(itertools.chain(manila.compute.nova.nova_opts))),
    (manila.network.neutron.api.NEUTRON_GROUP,
     list(itertools.chain(manila.network.neutron.api.neutron_opts))),
    (manila.image.glance.GLANCE_GROUP,
     list(itertools.chain(manila.image.glance.glance_opts))),
    (manila.quota.QUOTA_GROUP,
     list(itertools.chain(manila.quota.quota_opts))),
]

_opts.extend(manila.network.neutron.api.list_opts())
_opts.extend(manila.compute.nova.list_opts())
_opts.extend(manila.image.glance.list_opts())
_opts.extend(manila.volume.cinder.list_opts())


def list_opts():
    """Return a list of oslo.config options available in Manila."""
    return [(m, copy.deepcopy(o)) for m, o in _opts]
