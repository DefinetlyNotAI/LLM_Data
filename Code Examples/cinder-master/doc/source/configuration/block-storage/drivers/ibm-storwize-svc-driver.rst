============================================
IBM Storage Virtualize family volume driver
============================================

The volume management driver for Storage Virtualize family offers various
block storage services. It provides OpenStack Compute instances with access
to IBM Storage Virtualize family storage products. These products include the
SAN Volume Controller, Storwize and FlashSystem family members built with IBM
Storage Virtualize (including FlashSystem 5xxx, 7xxx, 9xxx).

For specific product publications, see `IBM Documentation
<https://www.ibm.com/docs>`_.

.. note::
   IBM Storage Virtualize family is formerly known as IBM Storwize.
   As a result, the product code contains 'Storwize' terminology and prefixes.

Supported operations
~~~~~~~~~~~~~~~~~~~~

The IBM Storage Virtualize family volume driver supports the following block
storage service volume operations:

-  Create, list, delete, attach (map), and detach (unmap) volumes.
-  Create, list, and delete volume snapshots.
-  Copy an image to a volume.
-  Copy a volume to an image.
-  Clone a volume.
-  Extend a volume.
-  Retype a volume.
-  Create a volume from a snapshot.
-  Create, list, and delete consistency group.
-  Create, list, and delete consistency group snapshot.
-  Modify consistency group (add or remove volumes).
-  Create consistency group from source (source can be a CG or CG snapshot)
-  Manage an existing volume.
-  Failover-host for replicated back ends.
-  Failback-host for replicated back ends.
-  Create, list, and delete replication group.
-  Enable, disable replication group.
-  Failover, failback replication group.

Configure the Storage Virtualize family system
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Network configuration
---------------------

The Storage Virtualize family system must be configured for iSCSI, Fibre
Channel, or both.

If using iSCSI, each Storage Virtualize family node should have at least
one iSCSI IP address. The Storage Virtualize family driver uses an iSCSI IP
address associated with the volume's preferred node (if available) to
attach the volume to the instance, otherwise it uses the first available
iSCSI IP address of the system. The driver obtains the iSCSI IP address
directly from the storage system. You do not need to provide these iSCSI
IP addresses directly to the driver.

.. note::

   If using iSCSI, ensure that the compute nodes have iSCSI network
   access to the Storage Virtualize family system.

If using Fibre Channel (FC), each Storage Virtualize family node should
have at least one WWPN port configured. The driver uses all available
WWPNs to attach the volume to the instance. The driver obtains the
WWPNs directly from the storage system. You do not need to provide
these WWPNs directly to the driver.

.. note::

   If using FC, ensure that the compute nodes have FC connectivity to
   the Storage Virtualize family system.

iSCSI CHAP authentication
-------------------------

If using iSCSI for data access and the
``storwize_svc_iscsi_chap_enabled`` is set to ``True``, the driver will
associate randomly-generated CHAP secrets with all hosts on the Storage
Virtualize family. The compute nodes use these secrets when creating
iSCSI connections.

.. warning::

   CHAP secrets are added to existing hosts as well as newly-created
   ones. If the CHAP option is enabled, hosts will not be able to
   access the storage without the generated secrets.

.. note::

   Not all OpenStack Compute drivers support CHAP authentication.
   Please check compatibility before using.

.. note::

   CHAP secrets are passed from OpenStack Block Storage to Compute in
   clear text. This communication should be secured to ensure that CHAP
   secrets are not discovered.

Configure storage pools
-----------------------

The IBM Storage Virtualize family driver can allocate volumes in multiple
pools. The pools should be created in advance and be provided to the driver
using the ``storwize_svc_volpool_name`` configuration flag in the form
of a comma-separated list.
For the complete list of configuration flags, see :ref:`config_flags`.

Configure user authentication for the driver
--------------------------------------------

The driver requires access to the Storage Virtualize family system
management interface. The driver communicates with the management using
SSH. The driver should be provided with the Storage Virtualize family
management IP using the ``san_ip`` flag, and the management port should
be provided by the ``san_ssh_port`` flag. By default, the port value is
configured to be port 22 (SSH). Also, you can set the secondary
management IP using the ``storwize_san_secondary_ip`` flag.

.. note::

   Make sure the compute node running the cinder-volume management
   driver has SSH network access to the storage system.

To allow the driver to communicate with the Storage Virtualize family
system, you must provide the driver with a user on the storage system.
The driver has two authentication methods: password-based authentication
and SSH key pair authentication. The user should have an Administrator
role. It is suggested to create a new user for the management driver.
Please consult with your storage and security administrator regarding
the preferred authentication method and how passwords or SSH keys should
be stored in a secure manner.

.. note::

   When creating a new user on the Storage Virtualize family system, make sure
   the user belongs to the Administrator group or to another group that
   has an Administrator role.

If using password authentication, assign a password to the user on the
Storage Virtualize family system. The driver configuration flags for the user
and password are ``san_login`` and ``san_password``, respectively.

If you are using the SSH key pair authentication, create SSH private and
public keys using the instructions below or by any other method.
Associate the public key with the user by uploading the public key:
select the :guilabel:`choose file` option in the Storage Virtualize family
management GUI under :guilabel:`SSH public key`. Alternatively, you may
associate the SSH public key using the command-line interface; details can
be found in the Storage Virtualize family documentation. The private key
should be provided to the driver using the ``san_private_key`` configuration
flag.

Create a SSH key pair with OpenSSH
----------------------------------

You can create an SSH key pair using OpenSSH, by running:

.. code-block:: console

   $ ssh-keygen -t rsa

The command prompts for a file to save the key pair. For example, if you
select ``key`` as the filename, two files are created: ``key`` and
``key.pub``. The ``key`` file holds the private SSH key and ``key.pub``
holds the public SSH key.

The command also prompts for a pass phrase, which should be empty.

The private key file should be provided to the driver using the
``san_private_key`` configuration flag. The public key should be
uploaded to the Storage Virtualize family system using the storage
management GUI or command-line interface.

.. note::

   Ensure that Cinder has read permissions on the private key file.

Configure the Storage Virtualize family driver
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Enable the Storage Virtualize family driver
--------------------------------------------

Set the volume driver to the Storage Virtualize family driver by setting
the ``volume_driver`` option in the ``cinder.conf`` file as follows:

iSCSI:

.. code-block:: ini

   [svc1234]
   volume_driver = cinder.volume.drivers.ibm.storwize_svc.storwize_svc_iscsi.StorwizeSVCISCSIDriver
   san_ip = 1.2.3.4
   san_login = superuser
   san_password = passw0rd
   storwize_svc_volpool_name = cinder_pool1
   volume_backend_name = svc1234

FC:

.. code-block:: ini

   [svc1234]
   volume_driver = cinder.volume.drivers.ibm.storwize_svc.storwize_svc_fc.StorwizeSVCFCDriver
   san_ip = 1.2.3.4
   san_login = superuser
   san_password = passw0rd
   storwize_svc_volpool_name = cinder_pool1
   volume_backend_name = svc1234

Replication configuration
-------------------------

Add the following to the back-end specification to specify another storage
to replicate to:

.. code-block:: ini

   replication_device = backend_id:rep_svc,
                        san_ip:1.2.3.5,
                        san_login:superuser,
                        san_password:passw0rd,
                        pool_name:cinder_pool1

The ``backend_id`` is a unique name of the remote storage, the ``san_ip``,
``san_login``, and ``san_password`` is authentication information for the
remote storage. The ``pool_name`` is the pool name for the replication
target volume.

.. note::

   Only one ``replication_device`` can be configured for one back end
   storage since only one replication target is supported now.

.. _config_flags:

Storage Virtualize family driver options in cinder.conf
--------------------------------------------------------

The following options specify default values for all volumes. Some can
be over-ridden using volume types, which are described below.

.. note::
   IBM Storage Virtualize family is formerly known as IBM Storwize.
   As a result, the product code contains 'Storwize' terminology and prefixes.

.. include:: ../../tables/cinder-storwize.inc

Note the following:

* The authentication requires either a password (``san_password``) or
  SSH private key (``san_private_key``). One must be specified. If
  both are specified, the driver uses only the SSH private key.

* The driver creates thin-provisioned volumes by default. The
  ``storwize_svc_vol_rsize`` flag defines the initial physical
  allocation percentage for thin-provisioned volumes, or if set to
  ``-1``, the driver creates full allocated volumes. More details about
  the available options are available in the Storage Virtualize family
  documentation.


Placement with volume types
---------------------------

The IBM Storage Virtualize family exposes capabilities that can be added to
the ``extra specs`` of volume types, and used by the filter
scheduler to determine placement of new volumes. Make sure to prefix
these keys with ``capabilities:`` to indicate that the scheduler should
use them. The following ``extra specs`` are supported:

-  ``capabilities:volume_backend_name`` - Specify a specific back-end
   where the volume should be created. The back-end name is a
   concatenation of the name of the Storage Virtualize family storage system
   as shown in ``lssystem``, an underscore, and the name of the pool (mdisk
   group). For example:

   .. code-block:: ini

      capabilities:volume_backend_name=myV7000_openstackpool

-  ``capabilities:compression_support`` - Specify a back-end according to
   compression support. A value of ``True`` should be used to request a
   back-end that supports compression, and a value of ``False`` will
   request a back-end that does not support compression. If you do not
   have constraints on compression support, do not set this key. Note
   that specifying ``True`` does not enable compression; it only
   requests that the volume be placed on a back-end that supports
   compression. Example syntax:

   .. code-block:: ini

      capabilities:compression_support='<is> True'

.. note::

   Currently, the compression_enabled() API that indicates compression_license
   support is not fully functional. It does not work on all storage types.
   Additional functionalities will be added in a later release.

-  ``capabilities:easytier_support`` - Similar semantics as the
   ``compression_support`` key, but for specifying according to support
   of the Easy Tier feature. Example syntax:

   .. code-block:: ini

      capabilities:easytier_support='<is> True'

-  ``capabilities:pool_name`` - Specify a specific pool to create volume
   if only multiple pools are configured. pool_name should be one value
   configured in storwize_svc_volpool_name flag. Example syntax:

   .. code-block:: ini

      capabilities:pool_name=cinder_pool2

Configure per-volume creation options
-------------------------------------

Volume types can also be used to pass options to the IBM Storage Virtualize
family driver, which over-ride the default values set in the configuration
file. Contrary to the previous examples where the ``capabilities`` scope
was used to pass parameters to the Cinder scheduler, options can be
passed to the Storage Virtualize family driver with the ``drivers`` scope.

The following ``extra specs`` keys are supported by the Storage Virtualize
family driver:

- rsize
- warning
- autoexpand
- grainsize
- compression
- easytier
- multipath
- iogrp
- mirror_pool
- volume_topology
- peer_pool
- flashcopy_rate
- clean_rate
- cycle_period_seconds

These keys have the same semantics as their counterparts in the
configuration file. They are set similarly; for example, ``rsize=2`` or
``compression=False``.

Example: Volume types
---------------------

In the following example, we create a volume type to specify a
controller that supports compression, and enable compression:

.. code-block:: console

   $ openstack volume type create compressed
   $ openstack volume type set --property capabilities:compression_support='<is> True' --property drivers:compression=True compressed

We can then create a 50GB volume using this type:

.. code-block:: console

   $ openstack volume create "compressed volume" --type compressed --size 50

In the following example, create a volume type that enables
synchronous replication (metro mirror):

.. code-block:: console

   $ openstack volume type create ReplicationType
   $ openstack volume type set --property replication_type="<in> metro" \
     --property replication_enabled='<is> True' --property volume_backend_name=svc234 ReplicationType

In the following example, we create a volume type to support stretch cluster
volume or mirror volume:

.. code-block:: console

   $ openstack volume type create mirror_vol_type
   $ openstack volume type set --property volume_backend_name=svc1 \
     --property drivers:mirror_pool=pool2 mirror_vol_type

Volume types can be used, for example, to provide users with different

-  performance levels (such as, allocating entirely on an HDD tier,
   using Easy Tier for an HDD-SDD mix, or allocating entirely on an SSD
   tier)

-  resiliency levels (such as, allocating volumes in pools with
   different RAID levels)

-  features (such as, enabling/disabling Real-time Compression,
   replication volume creation)

QOS
---

The Storage Virtualize family driver provides QOS support for storage volumes
by controlling the I/O amount. QOS is enabled by editing the
``etc/cinder/cinder.conf`` file and setting the
``storwize_svc_allow_tenant_qos`` to ``True``.

There are three ways to set the Storage Virtualize family ``IOThrotting``
parameter for storage volumes:

-  Add the ``qos:IOThrottling`` key into a QOS specification and
   associate it with a volume type.

-  Add the ``qos:IOThrottling`` key into an extra specification with a
   volume type.

-  Add the ``qos:IOThrottling`` key to the storage volume metadata.

.. note::

   If you are changing a volume type with QOS to a new volume type
   without QOS, the QOS configuration settings will be removed.

Operational notes for the Storage Virtualize family driver
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Migrate volumes
---------------

In the context of OpenStack block storage's volume migration feature,
the IBM Storage Virtualize family driver enables the storage's virtualization
technology. When migrating a volume from one pool to another, the volume
will appear in the destination pool almost immediately, while the
storage moves the data in the background.

.. note::

   To enable this feature, both pools involved in a given volume
   migration must have the same values for ``extent_size``. If the
   pools have different values for ``extent_size``, the data will still
   be moved directly between the pools (not host-side copy), but the
   operation will be synchronous.

Extend volumes
--------------

The IBM Storage Virtualize family driver allows for extending a volume's
size, but only for volumes without snapshots.

Snapshots and clones
--------------------

Snapshots are implemented using FlashCopy with no background copy
(space-efficient). Volume clones (volumes created from existing volumes)
are implemented with FlashCopy, but with background copy enabled. This
means that volume clones are independent, full copies. While this
background copy is taking place, attempting to delete or extend the
source volume will result in that operation waiting for the copy to
complete.

Volume retype
-------------

The IBM Storage Virtualize family driver enables you to modify volume types.
When you modify volume types, you can also change these extra specs properties:

-  rsize

-  warning

-  autoexpand

-  grainsize

-  compression

-  easytier

-  iogrp

-  nofmtdisk

-  mirror_pool

-  volume_topology

-  peer_pool

-  flashcopy_rate

-  cycle_period_seconds

.. note::

   When you change the ``rsize``, ``grainsize`` or ``compression``
   properties, volume copies are asynchronously synchronized on the
   array.

.. note::

   To change the ``iogrp`` property, IBM Storage Virtualize family firmware version
   6.4.0 or later is required.

Replication operation
---------------------

Configure replication in volume type
<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

A volume is only replicated if the volume is created with a volume-type
that has the extra spec ``replication_enabled`` set to ``<is> True``. Three
types of replication are supported now, global mirror(async), global mirror
with change volume(async) and metro mirror(sync). It can be specified by a
volume-type that has the extra spec ``replication_type`` set to
``<in> global``, ``<in> gmcv`` or ``<in> metro``. If no ``replication_type``
is specified, global mirror will be created for replication.

If ``replication_type`` set to ``<in> gmcv``, cycle_period_seconds can be
set as the cycling time perform global mirror relationship with multi cycling
mode. Default value is 300. Example syntax:

.. code-block:: console

   $ cinder type-create gmcv_type
   $ cinder type-key gmcv_type set replication_enabled='<is> True' \
     replication_type="<in> gmcv" drivers:cycle_period_seconds=500

.. note::

   It is better to establish the partnership relationship between
   the replication source storage and the replication target
   storage manually on the storage back end before replication
   volume creation.

Failover host
<<<<<<<<<<<<<

The ``failover-host`` command is designed for the case where the primary
storage is down.

.. code-block:: console

   $ cinder failover-host cinder@svciscsi --backend_id target_svc_id

If a failover command has been executed and the primary storage has
been restored, it is possible to do a failback by simply specifying
default as the ``backend_id``:

.. code-block:: console

   $ cinder failover-host cinder@svciscsi --backend_id default

.. note::

   Before you perform a failback operation, synchronize the data
   from the replication target volume to the primary one on the
   storage back end manually, and do the failback only after the
   synchronization is done since the synchronization may take a long time.
   If the synchronization is not done manually, Storage Virtualize family block storage
   service driver will perform the synchronization and do the failback
   after the synchronization is finished.

Replication group
<<<<<<<<<<<<<<<<<

Before creating replication group, a group-spec which key
``consistent_group_replication_enabled`` set to ``<is> True`` should be
set in group type. Volume type used to create group must be replication
enabled, and its ``replication_type`` should be set either ``<in> global``
or ``<in> metro``. The "failover_group" api allows group to be failed over
and back without failing over the entire host. Example syntax:

- Create replication group

.. code-block:: console

   $ cinder group-type-create rep-group-type-example
   $ cinder group-type-key rep-group-type-example set consistent_group_replication_enabled='<is> True'
   $ cinder type-create type-global
   $ cinder type-key type-global set replication_enabled='<is> True' replication_type='<in> global'
   $ cinder group-create rep-group-type-example type-global --name global-group

- Failover replication group

.. code-block:: console

   $ cinder group-failover-replication --secondary-backend-id target_svc_id group_id

- Failback replication group

.. code-block:: console

   $ cinder group-failover-replication --secondary-backend-id default group_id

.. note::

   Optionally, allow-attached-volume can be used to failover the in-use volume, but
   fail over/back an in-use volume is not recommended. If the user does failover
   operation to an in-use volume, the volume status remains in-use after
   failover. But the in-use replication volume would change to read-only since
   the primary volume is changed to auxiliary side and the instance is still
   attached to the master volume. As a result please detach the replication
   volume first and attach again if user want to reuse the in-use replication
   volume as read-write.

HyperSwap Volumes
-----------------

A HyperSwap volume is created with a volume-type that has the extra spec
``drivers:volume_topology`` set to ``hyperswap``.
To support HyperSwap volumes, IBM Storage Virtualize family firmware version
7.6.0 or later is required.
Add the following to the back-end configuration to specify the host preferred
site for HyperSwap volume.
FC:

.. code-block:: ini

   storwize_preferred_host_site = site1:20000090fa17311e&ff00000000000001,
                                  site2:20000089762sedce&ff00000000000000

iSCSI:

.. code-block:: ini

   storwize_preferred_host_site = site1:iqn.1993-08.org.debian:01:eac5ccc1aaa&iqn.1993-08.org.debian:01:be53b7e236be,
                                  site2:iqn.1993-08.org.debian:01:eac5ccc1bbb&iqn.1993-08.org.debian:01:abcdefg9876w

The site1 and site2 are names of the two host sites used in Storage
Virtualize family storage systems. The WWPNs and IQNs are the connectors
used for host mapping in the Storage Virtualize family.

.. code-block:: console

   $ cinder type-create hyper_type
   $ cinder type-key hyper_type set drivers:volume_topology=hyperswap \
     drivers:peer_pool=Pool_site2

.. note::

   The property ``rsize`` is considered as ``buffersize`` for the HyperSwap
   volume.
   The HyperSwap property ``iogrp`` is selected by storage.

A group is created as a HyperSwap group with a group-type that has the
group spec ``hyperswap_group_enabled`` set to ``<is> True``.
