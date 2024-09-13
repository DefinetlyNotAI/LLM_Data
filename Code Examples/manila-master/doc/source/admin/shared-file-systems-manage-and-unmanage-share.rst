.. _shared_file_systems_manage_and_unmanage_share:

=========================
Manage and unmanage share
=========================

To ``manage`` a share means that an administrator, rather than a share
driver, manages the storage lifecycle. This approach is appropriate when an
administrator already has the custom non-manila share with its size, shared
file system protocol, and export path, and an administrator wants to
register it in the Shared File System service.

To ``unmanage`` a share means to unregister a specified share from the Shared
File Systems service. Administrators can revert an unmanaged share to managed
status if needed.

.. _unmanage_share:

Unmanage a share
----------------

.. note::

    The ``unmanage`` operation is not supported for shares that were created on
    top of share servers and created with share networks until Shared File
    Systems API version ``2.49`` (Stein/Manila 8.0.0 release).

.. important::

    Shares that have dependent snapshots or share replicas cannot be removed
    from the Shared File Systems service unless the snapshots have been removed
    or unmanaged and the share replicas have been removed.

Unmanaging a share removes it from the management of the Shared File Systems
service without deleting the share. It is a non-disruptive operation and
existing clients are not disconnected, and the functionality is aimed at aiding
infrastructure operations and maintenance workflows. To unmanage a share,
run the :command:`manila unmanage <share>` command. Then try to print
the information about the share. The returned result should indicate that
Shared File Systems service won't
find the share:

.. code-block:: console

   $ manila unmanage share_for_docs
   $ manila show share_for_docs
   ERROR: No share with a name or ID of 'share_for_docs' exists.

.. _manage_share:

Manage a share
--------------
.. note::
    The ``manage`` operation is not supported for shares that are exported on
    share servers via share networks until Shared File Systems API version
    ``2.49`` (Stein/Manila 8.0.0 release).

.. note::
    From API version 2.53, if the requester specifies a share type containing
    a ``replication_type`` extra spec while managing a share, manila quota
    system will reserve and consume resources for two additional quotas:
    ``share_replicas`` and ``replica_gigabytes``.
    From API version 2.62, manila quota system will validate size of the
    share against ``per_share_gigabytes`` quota.

To register the non-managed share in the File System service, run the
:command:`manila manage` command:

.. code-block:: console

   manila manage [--name <name>] [--description <description>]
                 [--share_type <share-type>]
                 [--share-server-id <share_server_id>]
                 [--driver_options [<key=value> [<key=value> ...]]]
                 <service_host> <protocol> <export_path>

The positional arguments are:

- service_host. The manage-share service host in
  ``host@backend#POOL`` format, which consists of the host name for
  the back end, the name of the back end, and the pool name for the
  back end.

- protocol. The Shared File Systems protocol of the share to manage. Valid
  values are NFS, CIFS, GlusterFS, HDFS or MAPRFS.

- export_path. The share export path in the format appropriate for the
  protocol:

  - NFS protocol. 10.0.0.1:/foo_path.

  - CIFS protocol. \\\\10.0.0.1\\foo_name_of_cifs_share.

  - HDFS protocol. hdfs://10.0.0.1:foo_port/foo_share_name.

  - GlusterFS. 10.0.0.1:/foo_volume.

  - MAPRFS. maprfs:///share-0 -C  -Z  -N foo.

The optional arguments are:

- name. The name of the share that is being managed.

- share_type. The share type of the share that is being managed. If not
  specified, the service will try to manage the share with the configured
  default share type.

- share_server_id. must be provided to manage shares within share networks.
  This argument can only be used with File Systems API version ``2.49``
  (Stein/Manila 8.0.0 release) and beyond.

- driver_options. An optional set of one or more key and value pairs that
  describe driver options. As a result, a special share type named
  ``for_managing`` was used in example.

To manage share, run:

.. code-block:: console

   $ manila manage \
       manila@paris#shares \
       nfs \
       1.0.0.4:/shares/manila_share_6d2142d8_2b9b_4405_867f_8a48094c893f \
       --name share_for_docs \
       --description "We manage share." \
       --share_type for_managing
   +-----------------------------+--------------------------------------+
   | Property                    | Value                                |
   +-----------------------------+--------------------------------------+
   | status                      | manage_starting                      |
   | share_type_name             | for_managing                         |
   | description                 | We manage share.                     |
   | availability_zone           | None                                 |
   | share_network_id            | None                                 |
   | share_server_id             | None                                 |
   | share_group_id              | None                                 |
   | host                        | manila@paris#shares                  |
   | access_rules_status         | active                               |
   | snapshot_id                 | None                                 |
   | is_public                   | False                                |
   | task_state                  | None                                 |
   | snapshot_support            | True                                 |
   | id                          | ddfb1240-ed5e-4071-a031-b842035a834a |
   | size                        | None                                 |
   | name                        | share_for_docs                       |
   | share_type                  | 14ee8575-aac2-44af-8392-d9c9d344f392 |
   | has_replicas                | False                                |
   | replication_type            | None                                 |
   | created_at                  | 2016-03-25T15:22:43.000000           |
   | share_proto                 | NFS                                  |
   | project_id                  | 907004508ef4447397ce6741a8f037c1     |
   | metadata                    | {}                                   |
   +-----------------------------+--------------------------------------+

Check that the share is available:

.. code-block:: console

   $ manila show share_for_docs
   +----------------------+--------------------------------------------------------------------------+
   | Property             | Value                                                                    |
   +----------------------+--------------------------------------------------------------------------+
   | status               | available                                                                |
   | share_type_name      | for_managing                                                             |
   | description          | We manage share.                                                         |
   | availability_zone    | None                                                                     |
   | share_network_id     | None                                                                     |
   | export_locations     |                                                                          |
   |                      | path = 1.0.0.4:/shares/manila_share_6d2142d8_2b9b_4405_867f_8a48094c893f |
   |                      | preferred = False                                                        |
   |                      | is_admin_only = False                                                    |
   |                      | id = d4d048bf-4159-4a94-8027-e567192b8d30                                |
   |                      | share_instance_id = 4c8e3887-4f9a-4775-bab4-e5840a09c34e                 |
   |                      | path = 2.0.0.3:/shares/manila_share_6d2142d8_2b9b_4405_867f_8a48094c893f |
   |                      | preferred = False                                                        |
   |                      | is_admin_only = True                                                     |
   |                      | id = 1dd4f0a3-778d-486a-a851-b522f6e7cf5f                                |
   |                      | share_instance_id = 4c8e3887-4f9a-4775-bab4-e5840a09c34e                 |
   | share_server_id      | None                                                                     |
   | share_group_id       | None                                                                     |
   | host                 | manila@paris#shares                                                      |
   | access_rules_status  | active                                                                   |
   | snapshot_id          | None                                                                     |
   | is_public            | False                                                                    |
   | task_state           | None                                                                     |
   | snapshot_support     | True                                                                     |
   | id                   | ddfb1240-ed5e-4071-a031-b842035a834a                                     |
   | size                 | 1                                                                        |
   | name                 | share_for_docs                                                           |
   | share_type           | 14ee8575-aac2-44af-8392-d9c9d344f392                                     |
   | has_replicas         | False                                                                    |
   | replication_type     | None                                                                     |
   | created_at           | 2016-03-25T15:22:43.000000                                               |
   | share_proto          | NFS                                                                      |
   | project_id           | 907004508ef4447397ce6741a8f037c1                                         |
   | metadata             | {}                                                                       |
   +----------------------+--------------------------------------------------------------------------+
