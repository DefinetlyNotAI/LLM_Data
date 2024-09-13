=================================
Dell PowerFlex Storage driver
=================================

Overview
--------

Dell PowerFlex (formerly named Dell ScaleIO/VxFlex OS) is a
software-only solution that uses existing servers local
disks and LAN to create a virtual SAN that has all of the benefits of
external storage, but at a fraction of the cost and complexity. Using the
driver, Block Storage hosts can connect to a PowerFlex Storage
cluster.

The Dell PowerFlex Cinder driver is designed and tested to work with
both PowerFlex and with ScaleIO. The
:ref:`configuration options <cg_configuration_options_dellemc>`
are identical for both PowerFlex and ScaleIO.

.. _powerflex_docs:

Official PowerFlex documentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To find the PowerFlex documentation:

#. Go to the `PowerFlex product documentation page <https://docs.delltechnologies.com/>`_.

#. On the page, search for the relevant PowerFlex version.

Supported PowerFlex or VxFlex OS Versions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Dell PowerFlex Block Storage driver has been tested against the
following versions of VxFlex OS and PowerFlex and found to be
compatible:

* PowerFlex 3.6.0

* PowerFlex 4.0.x

* PowerFlex 4.5.x

Please consult the :ref:`powerflex_docs`
to determine supported operating systems for each version
of PowerFlex or VxFlex OS.

Deployment prerequisites
~~~~~~~~~~~~~~~~~~~~~~~~

* The PowerFlex Gateway must be installed and accessible in the network.
  For installation steps, refer to the Preparing the installation Manager
  and the Gateway section in PowerFlex Deployment Guide. See
  :ref:`powerflex_docs`.

* PowerFlex Storage Data Client (SDC) must be installed
  on all OpenStack nodes.

.. note:: Ubuntu users must follow the specific instructions in the PowerFlex
          OS Deployment Guide for Ubuntu environments. See the ``Deploying
          on Ubuntu Servers`` section in PowerFlex Deployment Guide. See
          :ref:`powerflex_docs`.

Supported operations
~~~~~~~~~~~~~~~~~~~~

* Create, delete, clone, attach, detach, migrate, manage, and unmanage volumes

* Create, delete, manage, and unmanage volume snapshots

* Create a volume from a snapshot

* Revert a volume to a snapshot

* Copy an image to a volume

* Copy a volume to an image

* Extend a volume

* Get volume statistics

* Create, list, update, and delete consistency groups

* Create, list, update, and delete consistency group snapshots

* OpenStack replication v2.1 support

* Cinder volume active/active support

PowerFlex Block Storage driver configuration
--------------------------------------------

This section explains how to configure and connect the block storage
nodes to a PowerFlex storage cluster.

Edit the ``cinder.conf`` file by adding the configuration below under
a new section (for example, ``[powerflex]``) and change the ``enable_backends``
setting (in the ``[DEFAULT]`` section) to include this new back end.
The configuration file is usually located at
``/etc/cinder/cinder.conf``.

For a configuration example, refer to the example
:ref:`cinder.conf <cg_configuration_example_dellemc>`.

PowerFlex driver name
~~~~~~~~~~~~~~~~~~~~~

Configure the driver name by adding the following parameter:

.. code-block:: ini

   volume_driver = cinder.volume.drivers.dell_emc.powerflex.driver.PowerFlexDriver

PowerFlex Gateway server IP
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The PowerFlex Gateway provides a REST interface to PowerFlex.

Configure the Gateway server IP address by adding the following parameter:

.. code-block:: ini

   san_ip = <PowerFlex GATEWAY IP>

PowerFlex Storage Pools
~~~~~~~~~~~~~~~~~~~~~~~

Multiple Storage Pools and Protection Domains can be listed for use by
the virtual machines. The list should include every Protection Domain and
Storage Pool pair that you would like Cinder to utilize.

To retrieve the available Storage Pools, use the command
:command:`scli --query_all` and search for available Storage Pools.

Configure the available Storage Pools by adding the following parameter:

.. code-block:: ini

   powerflex_storage_pools = <Comma-separated list of protection domain:storage pool name>

PowerFlex user credentials
~~~~~~~~~~~~~~~~~~~~~~~~~~

Block Storage requires a PowerFlex user with administrative
privileges. Dell recommends creating a dedicated OpenStack user
account that has an administrative user role.

Refer to the PowerFlex User Guide for details on user account management.

Configure the user credentials by adding the following parameters:

.. code-block:: ini

   san_login = <POWERFLEX_USER>
   san_password = <POWERFLEX_PASSWD>

Oversubscription
~~~~~~~~~~~~~~~~

Configure the oversubscription ratio by adding the following parameter
under the separate section for PowerFlex:

.. code-block:: ini

   powerflex_max_over_subscription_ratio = <OVER_SUBSCRIPTION_RATIO>

.. note::

   The default value for ``powerflex_max_over_subscription_ratio``
   is 10.0.

Oversubscription is calculated correctly by the Block Storage service
only if the extra specification ``provisioning:type``
appears in the volume type regardless of the default provisioning type.
Maximum oversubscription value supported for PowerFlex is 10.0.

Default provisioning type
~~~~~~~~~~~~~~~~~~~~~~~~~

If provisioning type settings are not specified in the volume type,
the default value is set according to the ``san_thin_provision``
option in the configuration file. The default provisioning type
will be ``thin`` if the option is not specified in the configuration
file. To set the default provisioning type ``thick``, set
the ``san_thin_provision`` option to ``false``
in the configuration file, as follows:

.. code-block:: ini

   san_thin_provision = false

The configuration file is usually located in
``/etc/cinder/cinder.conf``.
For a configuration example, see:
:ref:`cinder.conf <cg_configuration_example_dellemc>`.

.. _cg_configuration_example_dellemc:

Configuration example
~~~~~~~~~~~~~~~~~~~~~

**cinder.conf example file**

You can update the ``cinder.conf`` file by editing the necessary
parameters as follows:

.. code-block:: ini

   [DEFAULT]
   enabled_backends = powerflex

   [powerflex]
   volume_driver = cinder.volume.drivers.dell_emc.powerflex.driver.PowerFlexDriver
   volume_backend_name = powerflex
   san_ip = GATEWAY_IP
   powerflex_storage_pools = Domain1:Pool1,Domain2:Pool2
   san_login = POWERFLEX_USER
   san_password = POWERFLEX_PASSWD
   san_thin_provision = false

Connector configuration
~~~~~~~~~~~~~~~~~~~~~~~

Before using attach/detach volume operations PowerFlex connector must be
properly configured. On each node where PowerFlex SDC is installed do the
following:

#. Create ``/opt/emc/scaleio/openstack/connector.conf`` if it does not
   exist.

   .. code-block:: console

     $ mkdir -p /opt/emc/scaleio/openstack
     $ touch /opt/emc/scaleio/openstack/connector.conf

#. For each PowerFlex section in the ``cinder.conf`` create the same section in
   the ``/opt/emc/scaleio/openstack/connector.conf`` and populate it with
   passwords. Example:

   .. code-block:: ini

      [powerflex]
      san_password = POWERFLEX_PASSWD
      replicating_san_password = REPLICATION_SYSTEM_POWERFLEX_PASSWD # if applicable

      [powerflex-new]
      san_password = SIO2_PASSWD
      replicating_san_password = REPLICATION_SYSTEM_SIO2_PASSWD # if applicable

.. _cg_configuration_options_dellemc:

Configuration options
~~~~~~~~~~~~~~~~~~~~~

The PowerFlex driver supports these configuration options:

.. config-table::
   :config-target: PowerFlex

   cinder.volume.drivers.dell_emc.powerflex.driver

Volume Types
------------

Volume types can be used to specify characteristics of volumes allocated via
the PowerFlex Driver. These characteristics are defined as ``Extra Specs``
within ``Volume Types``.

.. _powerflex_pd_sp:

PowerFlex Protection Domain and Storage Pool
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When multiple storage pools are specified in the Cinder configuration,
users can specify which pool should be utilized by adding the ``pool_name``
Extra Spec to the volume type extra-specs and setting the value to the
requested protection_domain:storage_pool.

.. code-block:: console

   $ openstack volume type create powerflex_type_1
   $ openstack volume type set --property volume_backend_name=powerflex powerflex_type_1
   $ openstack volume type set --property pool_name=Domain2:Pool2 powerflex_type_1

PowerFlex thin provisioning support
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Block Storage driver supports creation of thin-provisioned and
thick-provisioned volumes.
The provisioning type settings can be added as an extra specification
of the volume type, as follows:

.. code-block:: console

   $ openstack volume type create powerflex_type_thick
   $ openstack volume type set --property provisioning:type=thick powerflex_type_thick

PowerFlex QoS support
~~~~~~~~~~~~~~~~~~~~~

QoS support for the PowerFlex driver includes the ability to set the
following capabilities:

``maxIOPS``
 The QoS I/O rate limit. If not set, the I/O rate will be unlimited.
 The setting must be larger than 10.

``maxIOPSperGB``
 The QoS I/O rate limit.
 The limit will be calculated by the specified value multiplied by
 the volume size.
 The setting must be larger than 10.

``maxBWS``
 The QoS I/O bandwidth rate limit in KBs. If not set, the I/O
 bandwidth rate will be unlimited. The setting must be a multiple of 1024.

``maxBWSperGB``
 The QoS I/O bandwidth rate limit in KBs.
 The limit will be calculated by the specified value multiplied by
 the volume size.
 The setting must be a multiple of 1024.

The QoS keys above must be created and associated with a volume type.
For example:

.. code-block:: console

   $ openstack volume qos create qos-limit-iops --consumer back-end --property maxIOPS=5000
   $ openstack volume type create powerflex_limit_iops
   $ openstack volume qos associate qos-limit-iops powerflex_limit_iops

The driver always chooses the minimum between the QoS keys value
and the relevant calculated value of ``maxIOPSperGB`` or ``maxBWSperGB``.

Since the limits are per SDC, they will be applied after the volume
is attached to an instance, and thus to a compute node/SDC.

PowerFlex compression support
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Starting from version 3.0, PowerFlex supports volume compression.
By default driver will create volumes without compression.
In order to create a compressed volume, a volume type which enables
compression support needs to be created first:

.. code-block:: console

   $ openstack volume type create powerflex_compressed
   $ openstack volume type set --property provisioning:type=compressed powerflex_compressed

If a volume with this type is scheduled to a storage pool which doesn't
support compression, then ``thin`` provisioning will be used.
See table below for details.

+-------------------+----------------------------+--------------------+
| provisioning:type |  storage pool supports compression              |
|                   +----------------------------+--------------------+
|                   | yes (PowerFlex 3.0 FG pool)|  no (other pools)  |
+===================+============================+====================+
|   compressed      |     thin with compression  |     thin           |
+-------------------+----------------------------+--------------------+
|   thin            |        thin                |     thin           |
+-------------------+----------------------------+--------------------+
|   thick           |        thin                |     thick          |
+-------------------+----------------------------+--------------------+
|   not set         |        thin                |     thin           |
+-------------------+----------------------------+--------------------+

.. note::
    PowerFlex 3.0 Fine Granularity storage pools don't support thick provisioned volumes.

You can add property ``compression_support='<is> True'`` to volume type to
limit volumes allocation only to data pools which supports compression.

.. code-block:: console

   $ openstack volume type set  --property compression_support='<is> True' powerflex_compressed

PowerFlex replication support
-----------------------------

Starting from version 3.5, PowerFlex supports volume replication.

Prerequisites
~~~~~~~~~~~~~

* PowerFlex replication components must be installed on source and destination
  systems.

* Source and destination systems must have the same configuration for
  Protection Domains and their Storage Pools (i.e. names, zero padding, etc.).

* Source and destination systems must be paired and have at least one
  Replication Consistency Group created.

See :ref:`powerflex_docs` for instructions.

Configure replication
~~~~~~~~~~~~~~~~~~~~~

#. Enable replication in ``cinder.conf`` file.

   To enable replication feature for storage backend ``replication_device``
   must be set as below:

   .. code-block:: ini

     [DEFAULT]
     enabled_backends = powerflex

     [powerflex]
     volume_driver = cinder.volume.drivers.dell_emc.powerflex.driver.PowerFlexDriver
     volume_backend_name = powerflex
     san_ip = GATEWAY_IP
     powerflex_storage_pools = Domain1:Pool1,Domain2:Pool2
     san_login = POWERFLEX_USER
     san_password = POWERFLEX_PASSWD
     san_thin_provision = false
     replication_device = backend_id:powerflex_repl,
                          san_ip: REPLICATION_SYSTEM_GATEWAY_IP,
                          san_login: REPLICATION_SYSTEM_POWERFLEX_USER,
                          san_password: REPLICATION_SYSTEM_POWERFLEX_PASSWD

   * Only one replication device is supported for storage backend.

   * The following parameters are optional for replication device:

     * REST API port - ``powerflex_rest_server_port``.

     * SSL certificate verification - ``driver_ssl_cert_verify`` and
       ``driver_ssl_cert_path``.

   For more information see :ref:`cg_configuration_options_dellemc`.

#. Create volume type for volumes with replication enabled.

   .. code-block:: console

     $ openstack volume type create powerflex_replicated
     $ openstack volume type set --property replication_enabled='<is> True' powerflex_replicated

#. Set PowerFlex Replication Consistency Group name for volume type.

   .. code-block:: console

     $ openstack volume type set --property powerflex:replication_cg=<replication_cg name> \
         powerflex_replicated

#. Set Protection Domain and Storage Pool if multiple Protection Domains
   are specified.

   PowerFlex Replication Consistency Group is created between source and
   destination Protection Domains. If more than one Protection Domain is
   specified in ``cinder.conf`` you should set ``pool_name`` property for
   volume type with appropriate Protection Domain and Storage Pool.
   See :ref:`powerflex_pd_sp`.

Failover host
~~~~~~~~~~~~~

In the event of a disaster, or where there is a required downtime the
administrator can issue the failover host command:

.. code-block:: console

   $ cinder failover-host cinder_host@powerflex --backend_id powerflex_repl

After issuing Cinder failover-host command Cinder will switch to configured
replication device, however to get existing instances to use this target and
new paths to volumes it is necessary to first shelve Nova instances and then
unshelve them, this will effectively restart the Nova instance and
re-establish data paths between Nova instances and the volumes.

.. code-block:: console

   $ nova shelve <server>
   $ nova unshelve [--availability-zone <availability_zone>] <server>

If the primary system becomes available, the administrator can initiate
failback operation using ``--backend_id default``:

.. code-block:: console

   $ cinder failover-host cinder_host@powerflex --backend_id default

PowerFlex storage-assisted volume migration
-------------------------------------------

Starting from version 3.0, PowerFlex supports storage-assisted volume
migration.

Known limitations
~~~~~~~~~~~~~~~~~

* Migration between different backends is not supported.

* For migration from Medium Granularity (MG) to Fine Granularity (FG)
  storage pool zero padding must be enabled on the MG pool.

* For migration from MG to MG pool zero padding must be either enabled
  or disabled on both pools.

In the above cases host-assisted migration will be perfomed.

Migrate volume
~~~~~~~~~~~~~~

Volume migration is performed by issuing the following command:

.. code-block:: console

   $ cinder migrate <volume> <host>

.. note:: Volume migration has a timeout of 3600 seconds (1 hour).
          It is done to prevent from endless waiting for migration to
          complete if something unexpected happened. If volume still is in
          migration after timeout has expired, volume status will be changed to
          ``maintenance`` to prevent future operations with this volume. The
          corresponding warning will be logged.

          In this situation the status of the volume should be checked on the
          storage side. If volume migration succeeded, its status can be
          changed manually:

          .. code-block:: console

             $ cinder reset-state --state available <volume>


Using PowerFlex Storage with a containerized overcloud
------------------------------------------------------

#. Create a file with below contents:

   .. code-block:: yaml

      parameter_defaults:
        NovaComputeOptVolumes:
          - /opt/emc/scaleio:/opt/emc/scaleio
        CinderVolumeOptVolumes:
          - /opt/emc/scaleio:/opt/emc/scaleio
        GlanceApiOptVolumes:
          - /opt/emc/scaleio:/opt/emc/scaleio


   Name it whatever you like, e.g. ``powerflex_volumes.yml``.

#. Use ``-e`` to include this customization file to deploy command.

#. Install the Storage Data Client (SDC) on all nodes after deploying
   the overcloud.
