======================================
Lenovo Fibre Channel and iSCSI drivers
======================================

The ``LenovoFCDriver`` and ``LenovoISCSIDriver`` Cinder drivers allow
Lenovo S-Series arrays to be used for block storage in OpenStack
deployments.

System requirements
~~~~~~~~~~~~~~~~~~~

To use the Lenovo drivers, the following are required:

- Lenovo S2200, S3200, DS2200, DS4200 or DS6200 array with:

  - iSCSI or FC host interfaces
  - G22x firmware or later

- Network connectivity between the OpenStack host and the array
  management interfaces

- HTTPS or HTTP must be enabled on the array

Supported operations
~~~~~~~~~~~~~~~~~~~~

- Create, delete, attach, and detach volumes.
- Create, list, and delete volume snapshots.
- Create a volume from a snapshot.
- Copy an image to a volume.
- Copy a volume to an image.
- Clone a volume.
- Extend a volume.
- Migrate a volume with back-end assistance.
- Retype a volume.
- Manage and unmanage a volume.

.. note::

  The generic grouping functionality supported in the G265 and later
  firmware is not supported by OpenStack Cinder due to differences in
  the grouping models used in Cinder and the S-Series firmware.

Configuring the array
~~~~~~~~~~~~~~~~~~~~~

#. Verify that the array can be managed using an HTTPS connection. HTTP
   can also be used if ``hpmsa_api_protocol=http`` is placed into the
   appropriate sections of the ``cinder.conf`` file, but this option is
   deprecated and will be removed in a future release.

   Confirm that virtual pools A and B are present if you plan to use
   virtual pools for OpenStack storage.

#. Edit the ``cinder.conf`` file to define a storage back-end entry for
   each storage pool on the array that will be managed by OpenStack. Each
   entry consists of a unique section name, surrounded by square brackets,
   followed by options specified in ``key=value`` format.

   -  The ``lenovo_pool_name`` value specifies the name of the storage
      pool on the array.

   -  The ``volume_backend_name`` option value can be a unique value, if
      you wish to be able to assign volumes to a specific storage pool on
      the array, or a name that is shared among multiple storage pools to
      let the volume scheduler choose where new volumes are allocated.

   -  The rest of the options will be repeated for each storage pool in a
      given array:

      * ``volume_driver`` specifies the Cinder driver name.
      * ``san_ip`` specifies the IP addresses or host names of the array's
        management controllers.
      * ``san_login`` and ``san_password`` specify the username and password
        of an array user account with ``manage`` privileges.
      * ``driver_use_ssl`` should be set to ``true`` to enable use of the
        HTTPS protocol.
      * ``lenovo_iscsi_ips`` specifies the iSCSI IP addresses for the array
        if using the iSCSI transport protocol.

   In the examples below, two back ends are defined, one for pool A and one
   for pool B, and a common ``volume_backend_name`` is used so that a
   single volume type definition can be used to allocate volumes from both
   pools.

   **Example: iSCSI example back-end entries**

   .. code-block:: ini

      [pool-a]
      lenovo_pool_name = A
      volume_backend_name = lenovo-array
      volume_driver = cinder.volume.drivers.lenovo.lenovo_iscsi.LenovoISCSIDriver
      san_ip = 10.1.2.3
      san_login = manage
      san_password = !manage
      lenovo_iscsi_ips = 10.2.3.4,10.2.3.5
      driver_use_ssl = true

      [pool-b]
      lenovo_pool_name = B
      volume_backend_name = lenovo-array
      volume_driver = cinder.volume.drivers.lenovo.lenovo_iscsi.LenovoISCSIDriver
      san_ip = 10.1.2.3
      san_login = manage
      san_password = !manage
      lenovo_iscsi_ips = 10.2.3.4,10.2.3.5
      driver_use_ssl = true

   **Example: Fibre Channel example back-end entries**

   .. code-block:: ini

      [pool-a]
      lenovo_pool_name = A
      volume_backend_name = lenovo-array
      volume_driver = cinder.volume.drivers.lenovo.lenovo_fc.LenovoFCDriver
      san_ip = 10.1.2.3
      san_login = manage
      san_password = !manage
      driver_use_ssl = true

      [pool-b]
      lenovo_pool_name = B
      volume_backend_name = lenovo-array
      volume_driver = cinder.volume.drivers.lenovo.lenovo_fc.LenovoFCDriver
      san_ip = 10.1.2.3
      san_login = manage
      san_password = !manage
      driver_use_ssl = true

#. If HTTPS is not enabled in the array, add
   ``lenovo_api_protocol = http`` in each of the back-end definitions.

#. If HTTPS is enabled, you can enable certificate verification with the
   option ``driver_ssl_cert_verify = True``. You may also use the
   ``driver_ssl_cert_path`` option to specify the path to a
   CA_BUNDLE file containing CAs other than those in the default list.

#. Modify the ``[DEFAULT]`` section of the ``cinder.conf`` file to add an
   ``enabled_backends`` parameter specifying the back-end entries you added,
   and a ``default_volume_type`` parameter specifying the name of a volume
   type that you will create in the next step.

   **Example: [DEFAULT] section changes**

   .. code-block:: ini

      [DEFAULT]
      # ...
      enabled_backends = pool-a,pool-b
      default_volume_type = lenovo

#. Create a new volume type for each distinct ``volume_backend_name`` value
   that you added to the ``cinder.conf`` file. The example below
   assumes that the same ``volume_backend_name=lenovo-array``
   option was specified in all of the
   entries, and specifies that the volume type ``lenovo`` can be used to
   allocate volumes from any of them.

   **Example: Creating a volume type**

   .. code-block:: console

      $ openstack volume type create lenovo
      $ openstack volume type set --property volume_backend_name=lenovo-array lenovo

#. After modifying the ``cinder.conf`` file,
   restart the ``cinder-volume`` service.

Driver-specific options
~~~~~~~~~~~~~~~~~~~~~~~

The following table contains the configuration options that are specific
to the Lenovo drivers.

.. config-table::
   :config-target: Lenovo

   cinder.volume.drivers.lenovo.lenovo_common
