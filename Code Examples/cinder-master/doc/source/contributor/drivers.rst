..
      Copyright (c) 2013 OpenStack Foundation
      All Rights Reserved.

      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

Drivers
=======

Cinder exposes an API to users to interact with different storage backend
solutions. The following are standards across all drivers for Cinder services
to properly interact with a driver.

Basic attributes
----------------

There are some basic attributes that all drivers classes should have:

* VERSION: Driver version in string format.  No naming convention is imposed,
  although semantic versioning is recommended.
* CI_WIKI_NAME: Must be the exact name of the `ThirdPartySystems wiki page
  <https://wiki.openstack.org/wiki/ThirdPartySystems>`_. This is used by our
  tooling system to associate jobs to drivers and track their CI reporting
  status correctly.

The tooling system will also use the name and docstring of the driver class.

Configuration options
---------------------

Each driver requires different configuration options set in the cinder.conf
file to operate, and due to the complexities of the Object Oriented programming
mechanisms (inheritance, composition, overwriting, etc.) once your driver
defines its parameters in the code Cinder has no automated way of telling which
configuration options are relevant to your driver.

In order to assist operators and installation tools we recommend reporting the
relevant options:

* For operators: In the documentation under
  ``doc/source/configuration/block-storage``.
* For operators and installers: Through the ``get_driver_options`` static
  method returning that returns a list of all the Oslo Config parameters.

.. _drivers_minimum_features:

Minimum Features
----------------

Minimum features are enforced to avoid having a grid of what features are
supported by which drivers and which releases. Cinder Core requires that all
drivers implement the following minimum features.

Core Functionality
------------------

* Volume Create/Delete
* Volume Attach/Detach
* Snapshot Create/Delete
* Create Volume from Snapshot
* Get Volume Stats
* Copy Image to Volume
* Copy Volume to Image
* Clone Volume
* Extend Volume

Security Requirements
---------------------

* Drivers must delete volumes in a way where volumes deleted from the backend
  will not leak data into new volumes when they are created.  Cinder operates
  in multi-tenant environments and this is critical to ensure data safety.
* Drivers should support secure TLS/SSL communication between the cinder
  volume service and the backend as configured by the "driver_ssl_cert_verify"
  and "driver_ssl_cert_path" options in cinder.conf.
* Drivers should use standard Python libraries to handle encryption-related
  functionality, and not contain custom implementations of encryption code.

.. _drivers_volume_stats:

Volume Stats
------------

Volume stats are used by the different schedulers for the drivers to provide
a report on their current state of the backend. The following should be
provided by a driver.

* driver_version
* free_capacity_gb
* storage_protocol
* total_capacity_gb
* vendor_name
* volume_backend_name

**NOTE:** If the driver is unable to provide a value for free_capacity_gb or
total_capacity_gb, keywords can be provided instead. Please use 'unknown' if
the backend cannot report the value or 'infinite' if the backend has no upper
limit. But, it is recommended to report real values as the Cinder scheduler
assigns lowest weight to any storage backend reporting 'unknown' or 'infinite'.

**NOTE:** By default, Cinder assumes that the driver supports attached volume
extending. If it doesn't, it should report 'online_extend_support=False'.
Otherwise the scheduler will attempt to perform the operation, and may leave
the volume in 'error_extending' state.

Value of ``storage_protocol`` is a single string representing the transport
protocol used by the storage.  Existing protocols are present in
``cinder.common.constants`` and should be used by drivers instead of string
literals.

Variant values only exist for older drivers that were already reporting those
values.  New drivers must use non variant versions.

The ``storage_protocol`` can be used by operators using the
``cinder get-pools --detail`` command, by volume types in their extra specs,
and by the filter and goodness functions.

We must not mistake the value of the ``storage_protocol`` with the identifier
of the os-brick connector, which is returned by the ``initialize_connection``
driver method in the ``driver_volume_type`` dictionary key.  In some cases they
may have the same value, but they are different things.


Feature Enforcement
-------------------

All concrete driver implementations should use the
``cinder.interface.volumedriver`` decorator on the driver class::

    @interface.volumedriver
    class LVMVolumeDriver(driver.VolumeDriver):

This will register the driver and allow automated compliance tests to run
against and verify the compliance of the driver against the required interface
to support the `Core Functionality`_ listed above.

Running ``tox -e compliance`` will verify all registered drivers comply to
this interface. This can be used during development to perform self checks
along the way. Any missing method calls will be identified by the compliance
tests.

The details for the required volume driver interfaces can be found in the
``cinder/interface/volume_*_driver.py`` source.

New Driver Review Checklist
---------------------------

There are some common issues caught during the review of new driver patches
that can easily be avoided. New driver maintainers should review the
:doc:`new_driver_checklist` for some things to watch out for.

.. toctree::
   :hidden:

   new_driver_checklist

Driver Development Documentations
---------------------------------

The LVM driver is our reference for all new driver implementations. The
information below can provide additional documentation for the methods that
volume drivers need to implement.

Volume ID
`````````

Drivers should always get a volume's ID using the ``name_id`` attribute instead
of the ``id`` attribute.

A Cinder volume may have two different UUIDs, a user facing one, and one the
driver should use.

When a volume is created these two are the same, but when doing a generic
migration (create new volume, then copying data) they will be different if we
were unable to rename the new volume in the final migration steps.

So the volume will have been created using the new volume's UUID and the driver
will have to look for it using that UUID, but the user on the other hand will
keep referencing the volume with the original UUID.

Base Driver Interface
`````````````````````
The methods documented below are the minimum required interface for a volume
driver to support. All methods from this interface must be implemented
in order to be an official Cinder volume driver.

.. automodule:: cinder.interface.volume_driver
  :members:
  :noindex:

Manage/Unmanage Support
```````````````````````
An optional feature a volume backend can support is the ability to manage
existing volumes or unmanage volumes - keep the volume on the storage backend
but no longer manage it through Cinder.

To support this functionality, volume drivers must implement these methods:

.. automodule:: cinder.interface.volume_manageable_driver
  :members:
  :noindex:

Manage/Unmanage Snapshot Support
````````````````````````````````
In addition to the ability to manage and unmanage volumes, Cinder backend
drivers may also support managing and unmanaging volume snapshots. These
additional methods must be implemented to support these operations.

.. automodule:: cinder.interface.volume_snapshotmanagement_driver
  :members:
  :noindex:

Volume Consistency Groups
`````````````````````````
Some storage backends support the ability to group volumes and create write
consistent snapshots across the group. In order to support these operations,
the following interface must be implemented by the driver.

.. automodule:: cinder.interface.volume_consistencygroup_driver
  :members:
  :noindex:

Generic Volume Groups
`````````````````````
The generic volume groups feature provides the ability to manage a group of
volumes together. Because this feature is implemented at the manager level,
every driver gets this feature by default. If a driver wants to override
the default behavior to support additional functionalities such as consistent
group snapshot, the following interface must be implemented by the driver.
Once every driver supporting volume consistency groups has added the
consistent group snapshot capability to generic volume groups, we no longer
need the volume consistency groups interface listed above.

.. automodule:: cinder.interface.volume_group_driver
  :members:
  :noindex:

Revert To Snapshot
``````````````````
Some storage backends support the ability to revert a volume to the last
snapshot. To support snapshot revert, the following interface must be
implemented by the driver.

.. automodule:: cinder.interface.volume_snapshot_revert
  :members:
  :noindex:

