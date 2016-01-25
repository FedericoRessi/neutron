# Copyright (c) 2016 IBM Corp.
#
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

import mock

from neutron.plugins.ml2 import driver_api as api
from neutron.plugins.ml2 import managers
from neutron.tests.unit.plugins.ml2 import test_plugin


class TestManagers(test_plugin.Ml2PluginV2TestCase):

    def test_bind_port_level_existing(self):
        manager = managers.MechanismManager()
        context = mock.MagicMock()
        bindinglevel = mock.Mock()
        bindinglevel.driver = 'fake_driver'
        bindinglevel.segment_id = 'fake_seg_id'
        context._binding_levels = [bindinglevel]
        manager.ordered_mech_drivers = ['fake_driver']
        segments_to_bind = [{api.SEGMENTATION_ID: 'fake_seg_id'}]
        manager._bind_port_level(context, 0, segments_to_bind)
        # Code should not hit the _prepare_to_bind
        self.assertFalse(context._prepare_to_bind.called)
