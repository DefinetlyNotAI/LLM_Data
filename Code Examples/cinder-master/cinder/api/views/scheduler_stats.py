# Copyright (C) 2014 eBay Inc.
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

from cinder.api import common


class ViewBuilder(common.ViewBuilder):
    """Model scheduler-stats API responses as a python dictionary."""

    _collection_name = "scheduler-stats"

    def __init__(self):
        """Initialize view builder."""
        super(ViewBuilder, self).__init__()

    def summary(self, request, pool):
        """Summary view of a single pool."""
        return {
            'pool': {
                'name': pool.get('name'),
            }
        }

    def detail(self, request, pool):
        """Detailed view of a single pool."""
        # Internally storage_protocol can be a list with all the variants (eg.
        # FC, fibre_channel), but we return a single value to users.  The first
        # value is the preferred variant.
        capabilities = pool.get('capabilities')
        if capabilities:
            protocol = capabilities.get('storage_protocol')
            if isinstance(protocol, list):
                capabilities = capabilities.copy()
                capabilities['storage_protocol'] = protocol[0]

        return {
            'pool': {
                'name': pool.get('name'),
                'capabilities': capabilities,
            }
        }

    def pools(self, request, pools, detail):
        """Detailed/Summary view of a list of pools seen by scheduler."""
        if detail:
            plist = [self.detail(request, pool)['pool'] for pool in pools]
        else:
            plist = [self.summary(request, pool)['pool'] for pool in pools]
        pools_dict = dict(pools=plist)

        return pools_dict
