=========================================
Nimble & Alletra 6k Storage volume driver
=========================================

Nimble Storage fully integrates with the OpenStack platform through
the Nimble Cinder driver, allowing a host to configure and manage Nimble
and Alletra 6k Storage array features through Block Storage interfaces.

Support for iSCSI storage protocol is available with NimbleISCSIDriver
Volume Driver class and Fibre Channel with NimbleFCDriver.

Support for the Liberty release and above is available from Nimble OS
2.3.8 or later.

Support for the Ocata release and above is available from Nimble OS 3.6 or
later.

For Xena release, Nimble OS 5.3 or later is used and Alletra OS 6.0
or later is used.

Nimble and Alletra 6k Storage Cinder driver does not support port binding
with multiple interfaces on the same subnet due to existing limitation in
os-brick. This is partially referenced in the bug
https://bugs.launchpad.net/os-brick/+bug/1722432 but does not resolve
for multiple software iscsi ifaces.

Supported operations
~~~~~~~~~~~~~~~~~~~~

* Create, delete, clone, attach, and detach volumes
* Create and delete volume snapshots
* Create a volume from a snapshot
* Copy an image to a volume
* Copy a volume to an image
* Extend a volume
* Get volume statistics
* Manage and unmanage a volume
* Enable encryption and default performance policy for a volume-type
  extra-specs
* Force backup of an in-use volume
* Retype a volume
* Create a Thinly Provisioned Volume
* Attach a volume to multiple servers simultaneously (multiattach)
* Volume Revert to Snapshot
* Create, list, update, and delete consistency groups
* Create, list, and delete consistency group snapshots
* Consistency group replication

Nimble and Alletra 6k Storage driver configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Update the file ``/etc/cinder/cinder.conf`` with the given configuration.
Note: These parameters apply to Alletra 6k Storage as well.

In case of a basic (single back-end) configuration, add the parameters
within the ``[default]`` section as follows.

.. code-block:: ini

   [default]
   san_ip = NIMBLE_MGMT_IP
   san_login = NIMBLE_USER
   san_password = NIMBLE_PASSWORD
   use_multipath_for_image_xfer = True
   volume_driver = NIMBLE_VOLUME_DRIVER
   san_thin_provision = True

In case of multiple back-end configuration, for example, configuration
which supports multiple Nimble Storage arrays or a single Nimble Storage
array with arrays from other vendors, use the following parameters.

.. code-block:: ini

   [default]
   enabled_backends = Nimble-Cinder

   [Nimble-Cinder]
   san_ip = NIMBLE_MGMT_IP
   san_login = NIMBLE_USER
   san_password = NIMBLE_PASSWORD
   use_multipath_for_image_xfer = True
   volume_driver = NIMBLE_VOLUME_DRIVER
   volume_backend_name = NIMBLE_BACKEND_NAME

In case of multiple back-end configuration, Nimble Storage volume type
is created and associated with a back-end name as follows.

.. note::

   Single back-end configuration users do not need to create the volume type.

.. code-block:: console

   $ openstack volume type create NIMBLE_VOLUME_TYPE
   $ openstack volume type set --property volume_backend_name=NIMBLE_BACKEND_NAME NIMBLE_VOLUME_TYPE

This section explains the variables used above:

NIMBLE_MGMT_IP
  Management IP address of Nimble/Alletra 6k Storage array/group.

NIMBLE_USER
  Nimble/Alletra 6k Storage account login with minimum ``power user``
  (admin) privilege if RBAC is used.

NIMBLE_PASSWORD
  Password of the admin account for Nimble/Alletra 6k array.

NIMBLE_VOLUME_DRIVER
  Use either cinder.volume.drivers.hpe.nimble.NimbleISCSIDriver for iSCSI or
  cinder.volume.drivers.hpe.nimble.NimbleFCDriver for Fibre Channel.

NIMBLE_BACKEND_NAME
  A volume back-end name which is specified in the ``cinder.conf`` file.
  This is also used while assigning a back-end name to the Nimble volume type.

NIMBLE_VOLUME_TYPE
  The Nimble volume-type which is created from the CLI and associated with
  ``NIMBLE_BACKEND_NAME``.

  .. note::

     Restart the ``cinder-api``, ``cinder-scheduler``, and ``cinder-volume``
     services after updating the ``cinder.conf`` file.

Nimble driver extra spec options
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Nimble volume driver also supports the following extra spec options:

'nimble:encryption'='yes'
  Used to enable encryption for a volume-type.

'nimble:perfpol-name'=PERF_POL_NAME
  PERF_POL_NAME is the name of a performance policy which exists on the
  Nimble/Alletra 6k array and should be enabled for every volume in a
  volume type.

.. note::

    When upgrading to OpenStack deployment to Victoria or later,
    do unset ``nimble:multi-initiator`` extra-spec and set ``multiattach='<is> True'``.

nimble:dedupe'='true'
  Used to enable dedupe support for a volume-type.

'nimble:iops-limit'=IOPS_LIMIT
  Used to set the IOPS_LIMIT between 256 and 4294967294 for all
  volumes created for this volume-type.

'nimble:folder'=FOLDER_NAME
  FOLDER_NAME is the name of the folder which exists on the Nimble/Alletra 6k
  array and should be enabled for every volume in a volume type

These extra-specs can be enabled by using the following command:

.. code-block:: console

   $ openstack volume type set --property KEY=VALUE VOLUME_TYPE

``VOLUME_TYPE`` is the Nimble volume type and ``KEY`` and ``VALUE`` are
the options mentioned above.

Configuration options
~~~~~~~~~~~~~~~~~~~~~

The Nimble/Alletra 6k storage driver supports these configuration options:

.. config-table::
   :config-target: Nimble

   cinder.volume.drivers.hpe.nimble

Multipathing
~~~~~~~~~~~~
In OpenStack environments where Cinder block device multipathing is desired
there are a few things to consider.

Configuring mulitpathing varies by system depending on the environment. In a
scenario where solely Nimble devices are being created by Cinder, the
following ``/etc/multipath.conf`` file may be used:

.. code-block:: text

   defaults {
       user_friendly_names yes
       find_multipaths     no
   }

   blacklist {
       devnode "^(ram|raw|loop|fd|md|dm-|sr|scd|st)[0-9]*"
       devnode "^hd[a-z]"
       device {
           vendor  ".*"
           product ".*"
       }
   }

   blacklist_exceptions {
       device {
           vendor  "Nimble"
           product "Server"
       }
   }

   devices {
       device {
           vendor               "Nimble"
           product              "Server"
           path_grouping_policy group_by_prio
           prio                 "alua"
           hardware_handler     "1 alua"
           path_selector        "service-time 0"
           path_checker         tur
           features             "1 queue_if_no_path"
           no_path_retry        30
           failback             immediate
           fast_io_fail_tmo     5
           dev_loss_tmo         infinity
           rr_min_io_rq         1
           rr_weight            uniform
       }
   }

After making changes to ``/etc/multipath.conf``, the multipath subsystem needs
to be reconfigured:

.. code-block:: console

   # multipathd reconfigure

.. tip::

   The latest best practices for Nimble devices can be found in the HPE Nimble
   Storage Linux Integration Guide found on https://infosight.hpe.com

.. important::

   OpenStack Cinder is currently not compatible with the HPE Nimble Storage
   Linux Toolkit (NLT)

Nova needs to be configured to pickup the actual multipath device created on
the host.

In ``/etc/nova/nova.conf``, add the following to the ``[libvirt]`` section:

.. code-block:: ini

   [libvirt]
   volume_use_multipath = True

.. note::
   In versions prior to Newton, the option was called ``iscsi_use_multipath``

After editing the Nova configuration file, the ``nova-conductor`` service
needs to be restarted.

.. tip::
   Depending on which particular OpenStack distribution is being used, Nova
   may use a different configuration file than the default.

To validate that instances get properly connected to the multipath device,
inspect the instance devices:

.. code-block:: console

   # virsh dumpxml <Instance ID | Instance Name | Instance UUID>

Consistency group replication
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To enable consistency group replication, follow below steps:

1. Add `replication_device` to storage backend settings in `cinder.conf`, then
   restart Cinder Volume service.

   Example of `cinder.conf` for volume replications:

   .. code-block:: ini

       [nimble]
       san_ip = xxx.xxx.xxx.xxx
       ...
       replication_device = backend_id:nimblevsagroup2,
                            san_ip:10.132.239.66,
                            san_login:admin,
                            san_password:admin,
                            schedule_name:sched-one,
                            downstream_partner:nimblevsagroup2,
                            period:15,
                            period_unit:minutes


   - Only one `replication_device` can be configured for each primary backend.
   - Keys `backend_id`, `san_ip`, `san_login`, `san_password`, `schedule_name`
     and `downstream_partner` are mandatory.
   - Other parameters are optional (if not given, then default values
     will be used):
     period:1
     period_unit:days
     num_retain:10
     num_retain_replica:1
     at_time:'00:00'
     until_time:'23:59'
     days='all'
     replicate_every:1
     alert_threshold:'24:00'

2. Create a volume type with properties `replication_enabled='<is> True'`
   and `consistent_group_snapshot_enabled='<is> True'`

   .. code-block:: console

       $ cinder type-create nimble
       $ cinder type-key nimble set volume_backend_name='nimble'
       $ cinder type-key nimble set replication_enabled='<is> True'
       $ cinder type-key nimble set consistent_group_snapshot_enabled='<is> True'

3. Create a consistency group type with properties
   `consistent_group_snapshot_enabled='<is> True'`
   and `consistent_group_replication_enabled='<is> True'`.

   .. code-block:: console

       $ cinder --os-volume-api-version 3.38 group-type-create repl_type
       $ cinder --os-volume-api-version 3.38 group-type-key repl_type set
       consistent_group_snapshot_enabled='<is> True' consistent_group_replication_enabled='<is> True'

4. Create a group type with volume types support replication.

   .. code-block:: console

       $ cinder --os-volume-api-version 3.38 group-create --name grp_1 repl_type nimble

5. Create volume in the consistency group.

   .. code-block:: console

       $ cinder --os-volume-api-version 3.38 create --volume-type nimble --group-id {grp_1-id}
       --name {volume-name} {size}

6. Enable consistency group replication.

   .. code-block:: console

       $ cinder --os-volume-api-version 3.38 group-enable-replication grp_1

7. Disable consistency group replication.

   .. code-block:: console

       $ cinder --os-volume-api-version 3.38 group-disable-replication grp_1

8. Failover consistency group replication.

   .. code-block:: console

       $ cinder --os-volume-api-version 3.38 group-failover-replication
       --secondary-backend-id nimblevsagroup2 grp_1

9. Failback consistency group replication.

   .. code-block:: console

       $ cinder --os-volume-api-version 3.38 group-failover-replication
       --secondary-backend-id default grp_1



