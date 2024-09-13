# Copyright (c) 2013 - 2015 EMC Corporation.
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

import urllib.parse

from cinder import context
from cinder import exception
from cinder.tests.unit import fake_constants as fake
from cinder.tests.unit import fake_volume
from cinder.tests.unit.volume.drivers.dell_emc import powerflex
from cinder.tests.unit.volume.drivers.dell_emc.powerflex import mocks
from cinder.volume import configuration
from cinder.volume.drivers.dell_emc.powerflex import utils as flex_utils


class TestDeleteVolume(powerflex.TestPowerFlexDriver):
    """Test cases for ``PowerFlexDriver.delete_volume()``"""
    def setUp(self):
        """Setup a test case environment.

        Creates a fake volume object and sets up the required API responses.
        """
        super(TestDeleteVolume, self).setUp()
        ctx = context.RequestContext('fake', 'fake', auth_token=True)

        self.volume = fake_volume.fake_volume_obj(
            ctx, **{'provider_id': fake.PROVIDER_ID})

        self.volume_name_2x_enc = urllib.parse.quote(
            urllib.parse.quote(flex_utils.id_to_base64(self.volume.id))
        )

        self.HTTPS_MOCK_RESPONSES = {
            self.RESPONSE_MODE.Valid: {
                'instances/Volume::' + self.volume.provider_id: {},
                'types/Volume/instances/getByName::' +
                self.volume_name_2x_enc: self.volume.id,
                'instances/Volume::{}/action/removeMappedSdc'.format(
                    self.volume.provider_id): self.volume.provider_id,
                'instances/Volume::{}/action/removeVolume'.format(
                    self.volume.provider_id
                ): self.volume.provider_id,
            },
            self.RESPONSE_MODE.BadStatus: {
                'instances/Volume::' + self.volume.provider_id:
                    self.BAD_STATUS_RESPONSE,
                'types/Volume/instances/getByName::' +
                self.volume_name_2x_enc: mocks.MockHTTPSResponse(
                    {
                        'errorCode': 401,
                        'message': 'BadStatus Volume Test',
                    }, 401
                ),
                'instances/Volume::{}/action/removeVolume'.format(
                    self.volume.provider_id
                ): mocks.MockHTTPSResponse(
                    {
                        'errorCode': 401,
                        'message': 'BadStatus Volume Test',
                    }, 401
                ),
            },
        }

    def test_bad_login_and_volume(self):
        self.set_https_response_mode(self.RESPONSE_MODE.BadStatus)
        self.assertRaises(exception.VolumeBackendAPIException,
                          self.driver.delete_volume,
                          self.volume)

    def test_delete_volume(self):
        """Setting the unmap volume before delete flag for tests """
        self.override_config('powerflex_unmap_volume_before_deletion', True,
                             configuration.SHARED_CONF_GROUP)
        self.driver.delete_volume(self.volume)
