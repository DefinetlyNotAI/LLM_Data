# Copyright (c) 2020 Dell Inc. or its subsidiaries.
# All Rights Reserved.
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

"""REST client for Dell EMC PowerStore Cinder Driver."""

import functools
import json

from oslo_log import log as logging
from oslo_utils import strutils
import requests
import requests.exceptions

from cinder import exception
from cinder.i18n import _
from cinder import utils as cinder_utils
from cinder.volume.drivers.dell_emc.powerstore import (
    exception as powerstore_exception)
from cinder.volume.drivers.dell_emc.powerstore import utils

LOG = logging.getLogger(__name__)
VOLUME_NOT_MAPPED_ERROR = "0xE0A08001000F"
SESSION_ALREADY_FAILED_OVER_ERROR = "0xE0201005000C"
TOO_MANY_SNAPS_ERROR = "0xE0A040010003"
MAX_SNAPS_IN_VTREE = 32
QOS_IO_RULE_EXISTS_ERROR = "0xE0A0E0010009"
QOS_POLICY_EXISTS_ERROR = "0xE02020010004"
QOS_UNEXPECTED_RESPONSE_ERROR = "0xE0101001000C"


class PowerStoreClient(object):
    def __init__(self,
                 rest_ip,
                 rest_username,
                 rest_password,
                 verify_certificate,
                 certificate_path,
                 rest_api_connect_timeout,
                 rest_api_read_timeout):
        self.rest_ip = rest_ip
        self.rest_username = rest_username
        self.rest_password = rest_password
        self.verify_certificate = verify_certificate
        self.certificate_path = certificate_path
        self.base_url = "https://%s:/api/rest" % self.rest_ip
        self.ok_codes = [
            requests.codes.ok,
            requests.codes.created,
            requests.codes.accepted,
            requests.codes.no_content,
            requests.codes.partial_content
        ]
        self.rest_api_connect_timeout = rest_api_connect_timeout
        self.rest_api_read_timeout = rest_api_read_timeout

    @property
    def _verify_cert(self):
        verify_cert = self.verify_certificate
        if self.verify_certificate and self.certificate_path:
            verify_cert = self.certificate_path
        return verify_cert

    def check_for_setup_error(self):
        if not all([self.rest_ip, self.rest_username, self.rest_password]):
            msg = _("REST server IP, username and password must be set.")
            raise exception.InvalidInput(reason=msg)

        # log warning if not using certificates
        if not self.verify_certificate:
            LOG.warning("Verify certificate is not set, using default of "
                        "False.")
            self.verify_certificate = False
        LOG.debug("Successfully initialized PowerStore REST client. "
                  "Server IP: %(ip)s, username: %(username)s. "
                  "Verify server's certificate: %(verify_cert)s.",
                  {
                      "ip": self.rest_ip,
                      "username": self.rest_username,
                      "verify_cert": self._verify_cert,
                  })

    def _send_request(self,
                      method,
                      url,
                      payload=None,
                      params=None,
                      log_response_data=True):
        response = None
        r = requests.Response
        try:
            if not params:
                params = {}
            request_params = {
                "auth": (self.rest_username, self.rest_password),
                "verify": self._verify_cert,
                "params": params
            }
            if payload and method != "GET":
                request_params["data"] = json.dumps(payload)
            request_url = self.base_url + url
            timeout = (self.rest_api_connect_timeout,
                       self.rest_api_read_timeout)
            r = requests.request(method, request_url, **request_params,
                                 timeout=timeout)
            log_level = logging.DEBUG
            if r.status_code not in self.ok_codes:
                log_level = logging.ERROR
            LOG.log(log_level,
                    "REST Request: %s %s with body %s",
                    r.request.method,
                    r.request.url,
                    strutils.mask_password(r.request.body))
            if (log_response_data or
                    log_level == logging.ERROR):
                msg = ("REST Response: %s with data %s" %
                       (r.status_code, r.text))
            else:
                msg = "REST Response: %s" % r.status_code
            LOG.log(log_level, msg)
            try:
                response = r.json()
            except ValueError:
                response = None
        except requests.exceptions.Timeout as e:
            r.status_code = requests.codes.internal_server_error
            LOG.error("The request to URL %(url)s failed with timeout "
                      "exception %(exc)s", {"url": url, "exc": e})
        return r, response

    _send_get_request = functools.partialmethod(_send_request, "GET")
    _send_post_request = functools.partialmethod(_send_request, "POST")
    _send_patch_request = functools.partialmethod(_send_request, "PATCH")
    _send_delete_request = functools.partialmethod(_send_request, "DELETE")

    def get_chap_config(self):
        r, response = self._send_get_request(
            "/chap_config/0",
            params={
                "select": "mode"
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore CHAP configuration.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        return response

    def get_metrics(self):
        r, response = self._send_post_request(
            "/metrics/generate",
            payload={
                "entity": "space_metrics_by_cluster",
                "entity_id": "0",
            },
            log_response_data=False
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore metrics.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        try:
            latest_metrics = response[-1]
            return latest_metrics
        except IndexError:
            msg = _("Failed to query PowerStore metrics.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def create_volume(self, name, size, pp_id, group_id):
        r, response = self._send_post_request(
            "/volume",
            payload={
                "name": name,
                "size": size,
                "protection_policy_id": pp_id,
                "volume_group_id": group_id,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to create PowerStore volume %s.") % name
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        return response["id"]

    def delete_volume_or_snapshot(self, entity_id, entity="volume"):
        if entity in ["volume group", "volume group snapshot"]:
            r, response = self._send_delete_request(
                "/volume_group/%s" % entity_id,
                payload={
                    "delete_members": True,
                },
            )
        else:
            r, response = self._send_delete_request("/volume/%s" % entity_id)
        if r.status_code not in self.ok_codes:
            if r.status_code == requests.codes.not_found:
                LOG.warning("PowerStore %(entity)s with id %(entity_id)s is "
                            "not found. Ignoring error.",
                            {
                                "entity": entity,
                                "entity_id": entity_id,
                            })
            else:
                msg = (_("Failed to delete PowerStore %(entity)s with id "
                         "%(entity_id)s.")
                       % {"entity": entity,
                          "entity_id": entity_id, })
                LOG.error(msg)
                raise exception.VolumeBackendAPIException(data=msg)

    def extend_volume(self, volume_id, size):
        r, response = self._send_patch_request(
            "/volume/%s" % volume_id,
            payload={
                "size": size,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to extend PowerStore volume with id %s.")
                   % volume_id)
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def create_snapshot(self, volume_id, name):
        r, response = self._send_post_request(
            "/volume/%s/snapshot" % volume_id,
            payload={
                "name": name,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to create snapshot %(snapshot_name)s for "
                     "PowerStore volume with id %(volume_id)s.")
                   % {"snapshot_name": name,
                      "volume_id": volume_id, })
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        return response["id"]

    def get_snapshot_id_by_name(self, volume_id, name):
        r, response = self._send_get_request(
            "/volume",
            params={
                "name": "eq.%s" % name,
                "protection_data->>source_id": "eq.%s" % volume_id,
                "type": "eq.Snapshot",
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore snapshots.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        try:
            snap_id = response[0].get("id")
            return snap_id
        except IndexError:
            msg = (_("PowerStore snapshot %(snapshot_name)s for volume "
                     "with id %(volume_id)s is not found.")
                   % {"snapshot_name": name,
                      "volume_id": volume_id, })
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def clone_volume_or_snapshot(self,
                                 name,
                                 entity_id,
                                 pp_id,
                                 entity="volume"):
        r, response = self._send_post_request(
            "/volume/%s/clone" % entity_id,
            payload={
                "name": name,
                "protection_policy_id": pp_id,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to create clone %(clone_name)s for "
                     "PowerStore %(entity)s with id %(entity_id)s.")
                   % {"clone_name": name,
                      "entity": entity,
                      "entity_id": entity_id, })
            LOG.error(msg)
            if ("messages" in response and
                    response["messages"][0]["code"] == TOO_MANY_SNAPS_ERROR):
                raise exception.SnapshotLimitReached(
                    set_limit=MAX_SNAPS_IN_VTREE)
            raise exception.VolumeBackendAPIException(data=msg)
        return response["id"]

    def get_all_hosts(self, protocol):
        r, response = self._send_get_request(
            "/host",
            params={
                "select": "id,name,host_initiators",
                "host_initiators->0->>port_type": "eq.%s" % protocol,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore hosts.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        return response

    def create_host(self, name, ports):
        r, response = self._send_post_request(
            "/host",
            payload={
                "name": name,
                "os_type": "Linux",
                "initiators": ports
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to create PowerStore host %s.") % name
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        return response

    def modify_host_initiators(self, host_id, **kwargs):
        r, response = self._send_patch_request(
            "/host/%s" % host_id,
            payload={
                **kwargs,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to modify initiators of PowerStore host "
                     "with id %s.") % host_id)
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def attach_volume_to_host(self, host_id, volume_id):
        r, response = self._send_post_request(
            "/volume/%s/attach" % volume_id,
            payload={
                "host_id": host_id,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to attach PowerStore volume %(volume_id)s "
                     "to host %(host_id)s.")
                   % {"volume_id": volume_id,
                      "host_id": host_id, })
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def get_volume_mapped_hosts(self, volume_id):
        r, response = self._send_get_request(
            "/host_volume_mapping",
            params={
                "volume_id": "eq.%s" % volume_id,
                "select": "host_id"
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore host volume mappings.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        mapped_hosts = [mapped_host["host_id"] for mapped_host in response]
        return mapped_hosts

    def get_volume_lun(self, host_id, volume_id):
        r, response = self._send_get_request(
            "/host_volume_mapping",
            params={
                "host_id": "eq.%s" % host_id,
                "volume_id": "eq.%s" % volume_id,
                "select": "logical_unit_number"
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore host volume mappings.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        try:
            logical_unit_number = response[0].get("logical_unit_number")
            return logical_unit_number
        except IndexError:
            msg = (_("PowerStore mapping of volume with id %(volume_id)s "
                     "to host %(host_id)s is not found.")
                   % {"volume_id": volume_id,
                      "host_id": host_id, })
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def get_fc_port(self):
        r, response = self._send_get_request(
            "/fc_port",
            params={
                "is_link_up": "eq.True",
                "select": "wwn"

            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore FC ports.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        return response

    def get_subsystem_nqn(self):
        r, response = self._send_get_request(
            "/cluster",
            params={
                "select": "nvm_subsystem_nqn"
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore NVMe subsystem NQN.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        try:
            nqn = response[0].get("nvm_subsystem_nqn")
            return nqn
        except IndexError:
            msg = _("PowerStore NVMe subsystem NQN is not found.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def get_ip_pool_address(self, protocol):
        params = {}
        if protocol == utils.PROTOCOL_ISCSI:
            params = {
                "purposes": "cs.{Storage_Iscsi_Target}",
                "select": "address,ip_port(target_iqn)"
            }
        elif protocol == utils.PROTOCOL_NVME:
            params = {
                "purposes": "cs.{Storage_NVMe_TCP_Port}",
                "select": "address"
            }
        r, response = self._send_get_request(
            "/ip_pool_address",
            params=params
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore IP pool addresses.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        return response

    def detach_volume_from_host(self, host_id, volume_id):
        r, response = self._send_post_request(
            "/volume/%s/detach" % volume_id,
            payload={
                "host_id": host_id,
            }
        )
        if r.status_code not in self.ok_codes:
            if r.status_code == requests.codes.not_found:
                LOG.warning("PowerStore volume with id %(volume_id)s is "
                            "not found. Ignoring error.",
                            {
                                "volume_id": volume_id,
                            })
            elif (
                    r.status_code == requests.codes.unprocessable and
                    any([
                        message["code"] == VOLUME_NOT_MAPPED_ERROR
                        for message in response["messages"]
                    ])
            ):
                LOG.warning("PowerStore volume with id %(volume_id)s is "
                            "not mapped to host with id %(host_id)s. "
                            "Ignoring error.",
                            {
                                "volume_id": volume_id,
                                "host_id": host_id,
                            })
            else:
                msg = (_("Failed to detach PowerStore volume %(volume_id)s "
                         "to host %(host_id)s.")
                       % {"volume_id": volume_id,
                          "host_id": host_id, })
                LOG.error(msg)
                raise exception.VolumeBackendAPIException(data=msg)

    def restore_from_snapshot(self, volume_id, snapshot_id):
        r, response = self._send_post_request(
            "/volume/%s/restore" % volume_id,
            payload={
                "from_snap_id": snapshot_id,
                "create_backup_snap": False,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to restore PowerStore volume with id "
                     "%(volume_id)s from snapshot with id %(snapshot_id)s.")
                   % {"volume_id": volume_id,
                      "snapshot_id": snapshot_id, })
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def get_protection_policy_id_by_name(self, name):
        r, response = self._send_get_request(
            "/policy",
            params={
                "name": "eq.%s" % name,
                "type": "eq.Protection",
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore Protection policies.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        try:
            pp_id = response[0].get("id")
            return pp_id
        except IndexError:
            msg = _("PowerStore Protection policy %s is not found.") % name
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def get_volume_replication_session_id(self, volume_id):
        r, response = self._send_get_request(
            "/replication_session",
            params={
                "local_resource_id": "eq.%s" % volume_id,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore Replication sessions.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        try:
            return response[0].get("id")
        except IndexError:
            msg = _("Replication session for PowerStore volume with "
                    "id %s is not found.") % volume_id
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def get_volume_id_by_name(self, name):
        r, response = self._send_get_request(
            "/volume",
            params={
                "name": "eq.%s" % name,
                "type": "in.(Primary,Clone)",
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore volumes.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        try:
            vol_id = response[0].get("id")
            return vol_id
        except IndexError:
            msg = _("PowerStore volume %s is not found.") % name
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def unassign_volume_protection_policy(self, volume_id):
        r, response = self._send_patch_request(
            "/volume/%s" % volume_id,
            payload={
                "protection_policy_id": "",
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to unassign Protection policy for PowerStore "
                     "volume with id %s.") % volume_id)
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    @cinder_utils.retry(exception.VolumeBackendAPIException,
                        interval=1, backoff_rate=3, retries=5)
    def wait_for_replication_session_deletion(self, rep_session_id):
        r, response = self._send_get_request(
            "/job",
            params={
                "resource_type": "eq.replication_session",
                "resource_action": "eq.delete",
                "resource_id": "eq.%s" % rep_session_id,
                "state": "eq.COMPLETED",
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore jobs.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        if not response:
            msg = _("PowerStore Replication session with "
                    "id %s is still exists.") % rep_session_id
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def failover_volume_replication_session(self, rep_session_id, is_failback):
        r, response = self._send_post_request(
            "/replication_session/%s/failover" % rep_session_id,
            payload={
                "is_planned": False,
                "force": is_failback,
            },
            params={
                "is_async": True,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to failover PowerStore replication session "
                     "with id %s.") % rep_session_id)
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        return response["id"]

    @cinder_utils.retry(exception.VolumeBackendAPIException,
                        interval=1, backoff_rate=3, retries=5)
    def wait_for_failover_completion(self, job_id):
        r, response = self._send_get_request(
            "/job/%s" % job_id,
            params={
                "select": "resource_action,resource_type,"
                          "resource_id,state,response_body",
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore job with id %s.") % job_id
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        elif (
                isinstance(response["response_body"], dict) and
                any([
                    message["code"] == SESSION_ALREADY_FAILED_OVER_ERROR
                    for message in
                    response["response_body"].get("messages", [])
                ])
        ):
            # Replication session is already in Failed-Over state.
            return True
        elif response["state"] == "COMPLETED":
            return True
        elif response["state"] in ["FAILED", "UNRECOVERABLE_FAILED"]:
            return False
        else:
            msg = _("Failover of PowerStore Replication session with id "
                    "%s is still in progress.") % response["resource_id"]
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def reprotect_volume_replication_session(self, rep_session_id):
        r, response = self._send_post_request(
            "/replication_session/%s/reprotect" % rep_session_id
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to reprotect PowerStore replication session "
                     "with id %s.") % rep_session_id)
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def create_vg(self, name):
        r, response = self._send_post_request(
            "/volume_group",
            payload={
                "name": name,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to create PowerStore volume group %s.") % name
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        return response["id"]

    def get_vg_id_by_name(self, name):
        r, response = self._send_get_request(
            "/volume_group",
            params={
                "name": "eq.%s" % name,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore volume groups.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        try:
            group_id = response[0].get("id")
            return group_id
        except IndexError:
            msg = _("PowerStore volume group %s is not found.") % name
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def add_volumes_to_vg(self, group_id, volume_ids):
        r, response = self._send_post_request(
            "/volume_group/%s/add_members" % group_id,
            payload={
                "volume_ids": volume_ids,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to add volumes to PowerStore volume group "
                     "with id %(group_id)s. Volumes: %(volume_ids)s.")
                   % {"group_id": group_id,
                      "volume_ids": volume_ids, })
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def remove_volumes_from_vg(self, group_id, volume_ids):
        r, response = self._send_post_request(
            "/volume_group/%s/remove_members" % group_id,
            payload={
                "volume_ids": volume_ids,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to remove volumes from PowerStore volume group "
                     "with id %(group_id)s. Volumes: %(volume_ids)s.")
                   % {"group_id": group_id,
                      "volume_ids": volume_ids, })
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def create_vg_snapshot(self, group_id, name):
        r, response = self._send_post_request(
            "/volume_group/%s/snapshot" % group_id,
            payload={
                "name": name,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to create snapshot %(snapshot_name)s for "
                     "PowerStore volume group with id %(group_id)s.")
                   % {"snapshot_name": name,
                      "group_id": group_id, })
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        return response["id"]

    def get_vg_snapshot_id_by_name(self, group_id, name):
        r, response = self._send_get_request(
            "/volume_group",
            params={
                "name": "eq.%s" % name,
                "protection_data->>source_id": "eq.%s" % group_id,
                "type": "eq.Snapshot",
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore volume groups snapshots.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        try:
            vg_snap_id = response[0].get("id")
            return vg_snap_id
        except IndexError:
            msg = (_("PowerStore snapshot %(snapshot_name)s for volume group"
                     "with id %(group_id)s is not found.")
                   % {"snapshot_name": name,
                      "group_id": group_id, })
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def clone_vg_or_vg_snapshot(self,
                                name,
                                entity_id,
                                entity="volume group"):
        r, response = self._send_post_request(
            "/volume_group/%s/clone" % entity_id,
            payload={
                "name": name,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to create clone %(clone_name)s for "
                     "PowerStore %(entity)s with id %(entity_id)s.")
                   % {"clone_name": name,
                      "entity": entity,
                      "entity_id": entity_id, })
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        return response["id"]

    def rename_volume(self, volume_id, name):
        r, response = self._send_patch_request(
            "/volume/%s" % volume_id,
            payload={
                "name": name,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to rename PowerStore volume with id %s.")
                   % volume_id)
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def get_array_version(self):
        r, response = self._send_get_request(
            "/software_installed",
            params={
                "select": "release_version",
                "is_cluster": "eq.True"
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore array version.")
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        return response[0].get("release_version")

    def get_volume_nguid(self, volume_id):
        r, response = self._send_get_request(
            "/volume/%s" % volume_id,
            params={
                "select": "nguid",
            }
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to query PowerStore volume with id %s.")
                   % volume_id)
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        nguid = response["nguid"].split('.')[1]
        return nguid

    def get_qos_policy_id_by_name(self, name):
        r, response = self._send_get_request(
            "/policy",
            params={
                "name": "eq.%s" % name,
                "type": "eq.QoS",
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to query PowerStore QoS policy "
                    "with name %s." % name)
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        if len(response) > 0:
            qos_policy_id = response[0].get("id")
            return qos_policy_id
        return None

    def create_qos_io_rule(self, io_rule_params):
        r, response = self._send_post_request(
            "/io_limit_rule",
            payload=io_rule_params
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to create PowerStore I/O limit "
                    "rule %s." % io_rule_params["name"])
            LOG.error(msg)
            if ("messages" in response and
                    (response["messages"][0]["code"] ==
                     QOS_IO_RULE_EXISTS_ERROR or
                     response["messages"][0]["code"] ==
                     QOS_UNEXPECTED_RESPONSE_ERROR)):
                raise (
                    powerstore_exception.
                    DellPowerStoreQoSIORuleExists(name=io_rule_params["name"]))
            raise exception.VolumeBackendAPIException(data=msg)
        return response["id"]

    def create_qos_policy(self, policy_params):
        r, response = self._send_post_request(
            "/policy",
            payload=policy_params
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to create PowerStore QoS "
                    "policy %s." % policy_params["name"])
            LOG.error(msg)
            if ("messages" in response and
                    (response["messages"][0]["code"] ==
                     QOS_POLICY_EXISTS_ERROR or
                     response["messages"][0]["code"] ==
                     QOS_UNEXPECTED_RESPONSE_ERROR)):
                raise (
                    powerstore_exception.
                    DellPowerStoreQoSPolicyExists(name=policy_params["name"]))
            raise exception.VolumeBackendAPIException(data=msg)
        return response["id"]

    def update_volume_with_qos_policy(self, provider_id, qos_policy_id):
        r, response = self._send_patch_request(
            "/volume/%s" % provider_id,
            payload={
                "qos_performance_policy_id": qos_policy_id,
            }
        )
        if r.status_code not in self.ok_codes:
            msg = _("Failed to update PowerStore volume %(volume_id)s with "
                    "QoS policy %(policy_id)s."
                    % {"volume_id": provider_id,
                       "policy_id": qos_policy_id})
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

    def update_qos_io_rule(self, io_rule_name, io_rule_params):
        r, response = self._send_patch_request(
            "/io_limit_rule/name:%s" % io_rule_name,
            payload=io_rule_params
        )
        if r.status_code not in self.ok_codes:
            msg = (_("Failed to update PowerStore I/O limit rule %s.")
                   % io_rule_name)
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
