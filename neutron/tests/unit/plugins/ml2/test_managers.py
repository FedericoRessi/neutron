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

from oslo_log import log
import sys

import mock
import six

from neutron.plugins.ml2 import driver_api
from neutron.plugins.ml2 import managers
from neutron.tests import base


class TestMechanismManager(base.DietTestCase):

    def setUp(self):
        super(TestMechanismManager, self).setUp()

        self.cfg = mocked_cfg = mock.Mock()
        mocked_cfg.CONF.ml2.mechanism_drivers = []
        mock.patch.object(managers, 'cfg', mocked_cfg).start()

        self.log = mocked_log = mock.Mock(specs=log.KeywordArgumentAdapter)
        mock.patch.object(managers, 'LOG', mocked_log).start()

        self.exceptions = exceptions = []
        self.log.exception = mock.Mock(
            side_effect=lambda *args: exceptions.append(sys.exc_info()))
        self.addCleanup(self.raise_reported_exception)

    def raise_reported_exception(self):
        for exc_type, exc_value, exc_trace in self.exceptions:
            try:
                raise six.reraise(exc_type, exc_value, exc_trace)
            finally:
                self.exceptions = self.exceptions[1:]

    def create_manager(self, drivers):
        manager = managers.MechanismManager()
        manager.ordered_mech_drivers = drivers
        return manager

    def create_segment(self, segment_id='SEGMENT'):
        return {driver_api.SEGMENTATION_ID: segment_id}

    def create_segments(self, segment_ids):
        return [self.create_segment(segment_id) for segment_id in segment_ids]

    def test_bind_port_with_no_drivers(self):
        given_manager = self.create_manager(drivers=[])
        given_context = mock_port_context()

        # When manager try binding port whithout drivers
        given_manager.bind_port(given_context)

        # Then it should not hit the _prepare_to_bind
        given_context._prepare_to_bind.assert_not_called()
        self.log.error.assert_called_once_with(
            'Failed to bind port %(port)s on host %(host)s for vnic_type '
            '%(vnic_type)s using segments %(segments)s',
            {'vnic_type': 'VNIC_TYPE', 'port': 'CURRENT_ID', 'segments': [],
             'host': 'HOST'})

    def test_bind_port_level_existing(self):
        given_driver = mock_mechanism_driver()
        given_segment = self.create_segment('SEGMENT')
        given_manager = self.create_manager(drivers=[given_driver])
        given_binding_level = mock_binding_level(
            driver=given_driver, segment_id='SEGMENT')
        given_context = mock_port_context(
            network_segments=[given_segment],
            binding_levels=[given_binding_level])

        # When manager try binding port using given driver and context
        given_manager.bind_port(given_context)

        # Then it should not hit the _prepare_to_bind
        given_context._prepare_to_bind.assert_not_called()
        # Then it should not ask driver to bind port
        given_driver.obj.bind_port.assert_not_called()
        self.log.error.assert_called_once_with(
            'Failed to bind port %(port)s on host %(host)s for vnic_type '
            '%(vnic_type)s using segments %(segments)s',
            {'vnic_type': 'VNIC_TYPE', 'port': 'CURRENT_ID',
             'segments': [given_segment], 'host': 'HOST'})

    def test_bind_port_with_one_driver_failing_to_bound(self):
        given_driver = mock_mechanism_driver()
        given_manager = self.create_manager(drivers=[given_driver])
        given_context = mock_port_context()

        # When manager try binding port using given driver and context
        given_manager.bind_port(given_context)

        # Then it should ask driver to bind port
        given_driver.obj.bind_port.assert_called_once_with(given_context)
        self.log.error.assert_called_once_with(
            'Failed to bind port %(port)s on host %(host)s for vnic_type '
            '%(vnic_type)s using segments %(segments)s',
            {'vnic_type': 'VNIC_TYPE', 'port': 'CURRENT_ID', 'segments': [],
             'host': 'HOST'})

    def test_bind_port_with_one_driver_and_one_segment_having_success(self):
        given_driver = mock_mechanism_driver()
        given_manager = self.create_manager(
            drivers=[given_driver])
        given_binding_levels = []
        given_context = mock_port_context(
            new_bound_segment='NEW_SEGMENT',
            binding_levels=given_binding_levels)

        # When manager try binding port using given driver and context
        given_manager.bind_port(given_context)

        # Then it should not ask driver to bind port
        given_driver.obj.bind_port.assert_called_once_with(given_context)
        # Then a new binding level is pushed
        new_building_level = given_binding_levels.pop()
        given_context._push_binding_level.assert_called_once_with(
            new_building_level)
        self.assertEqual(given_driver.name, new_building_level.driver)
        self.assertEqual('NEW_SEGMENT', new_building_level.segment_id)
        # Then no error or warning are reported
        self.log.error.assert_not_called()
        self.log.warning.assert_not_called()

    def test_bind_port_with_one_driver_failing_up_to_max_levels(self):
        """Tes bind port don't loop forever when a driver doesn't support
        binding remaining segments.

        This test simulates a condition that would cause bind_port mechanism
        looping up to reaching stack limits if max_levels check would not be
        performed.
        """

        given_segment = self.create_segment(segment_id='SEGMENT1')
        given_driver = mock_mechanism_driver()
        given_manager = self.create_manager(drivers=[given_driver])
        given_context = mock_port_context(
            network_segments=[given_segment],
            # bound segment
            new_bound_segment=given_segment[driver_api.SEGMENTATION_ID],
            # remaining segments
            next_segments_to_bind=[given_segment])

        # When manager try to bind port using given driver and context
        given_manager.bind_port(given_context)

        # Then it should not ask driver to try to bind port up to
        # MAX_BINDING_LEVELS times
        self.assertEqual(
            [mock.call(given_context)] * managers.MAX_BINDING_LEVELS,
            given_driver.obj.bind_port.mock_calls)

        # Then it fails reporting MAX_BINDING_LEVELS related error
        self.log.error.assert_has_calls([
            mock.call(
                'Exceeded maximum binding levels attempting to bind port '
                '%(port)s on host %(host)s',
                {'host': 'HOST', 'port': 'CURRENT_ID'}),
            mock.call(
                'Failed to bind port %(port)s on host %(host)s for vnic_type '
                '%(vnic_type)s using segments %(segments)s',
                {'segments': [given_segment], 'host': 'HOST',
                 'port': 'CURRENT_ID', 'vnic_type': 'VNIC_TYPE'})])

    def test_bind_port_with_one_driver_and_multi_segments_having_success(self):
        given_segments = self.create_segments(
            segment_ids=['SEGMENT1', 'SEGMENT2', 'SEGMENT3'])
        segment_enumeration = enumerate(given_segments)

        def bind_port(port_context):
            i, segment = next(segment_enumeration)
            port_context._new_bound_segment = segment[
                driver_api.SEGMENTATION_ID]
            port_context._next_segments_to_bind = given_segments[i + 1:]

        given_driver = mock_mechanism_driver(bind_port=bind_port)
        given_manager = self.create_manager(drivers=[given_driver])
        given_binding_levels = []
        given_context = mock_port_context(
            network_segments=given_segments,
            binding_levels=given_binding_levels)

        # When manager try to bind port using given driver and context
        given_manager.bind_port(given_context)

        # Then bind port is called for all segments
        self.assertEqual(
            [mock.call(given_context)] * len(given_segments),
            given_driver.obj.bind_port.mock_calls)
        # Then new binding level is pushed for every segment
        for level_id, level in enumerate(given_binding_levels):
            self.assertEqual(given_context.current['id'], level.port_id)
            self.assertEqual(given_context.host, level.host)
            self.assertEqual(level_id, level.level)
            self.assertIs(given_driver.name, level.driver)
            self.assertEqual(
                given_segments[level_id][driver_api.SEGMENTATION_ID],
                level.segment_id)
        self.assertEqual(
                [mock.call(level) for level in given_binding_levels],
                given_context._push_binding_level.mock_calls)

        self.log.error.assert_not_called()
        self.log.warning.assert_not_called()
        self.log.debug.assert_has_calls(
            [mock.call(
                'Attempting to bind port %(port)s on host %(host)s for '
                'vnic_type %(vnic_type)s with profile %(profile)s',
                {'vnic_type': 'VNIC_TYPE', 'port': 'CURRENT_ID',
                 'host': 'HOST', 'profile': mock.ANY}),
             mock.call(
                'Attempting to bind port %(port)s on host %(host)s at level '
                '%(level)s using segments %(segments)s',
                {'port': 'CURRENT_ID', 'host': 'HOST', 'level': 0,
                 'segments': given_segments}),
             mock.call(
                'Attempting to bind port %(port)s on host %(host)s at level '
                '%(level)s using segments %(segments)s',
                {'port': 'CURRENT_ID', 'host': 'HOST', 'level': 1,
                 'segments': given_segments[1:]}),
             mock.call(
                'Attempting to bind port %(port)s on host %(host)s at level '
                '%(level)s using segments %(segments)s',
                {'port': 'CURRENT_ID', 'host': 'HOST', 'level': 2,
                 'segments': given_segments[2:]}),
             mock.call(
                'Bound port: %(port)s, host: %(host)s, vif_type: %(vif_type)s,'
                ' vif_details: %(vif_details)s,'
                ' binding_levels: %(binding_levels)s',
                {'port': 'CURRENT_ID', 'host': 'HOST',
                 'binding_levels': mock.ANY, 'vif_type': mock.ANY,
                 'vif_details': mock.ANY})])

    def test_bind_port_with_one_driver_failing_bind_port(self):
        given_segments = self.create_manager(
            ['SEGMENT1', 'SEGMENT2', 'SEGMENT3'])
        given_driver = mock_mechanism_driver(bind_port=RuntimeError)
        given_context = mock_port_context(network_segments=given_segments)
        given_manager = self.create_manager(drivers=[given_driver])

        given_manager.bind_port(given_context)

        given_driver.obj.bind_port.assert_called_once_with(given_context)
        self.log.exception.assert_called_once_with(
            'Mechanism driver %s failed in bind_port', given_driver.name)
        self.assertRaises(RuntimeError, self.raise_reported_exception)


def mock_port_context(
        network_segments=None, binding_levels=None, new_bound_segment=None,
        next_segments_to_bind=None):
    if network_segments is None:
        network_segments = []
    if binding_levels is None:
        binding_levels = []
    if next_segments_to_bind is None:
        next_segments_to_bind = []

    given_binding = mock.Mock(vnic_type='VNIC_TYPE')
    given_network = mock.Mock(
        specs=driver_api.NetworkContext,
        network_segments=network_segments)
    push_binding_level = mock.Mock(
        side_effect=lambda level: binding_levels.append(level))
    pop_binding_level = mock.Mock(side_effect=binding_levels.pop)

    return mock.Mock(
        specs=driver_api.PortContext,
        current={'id': 'CURRENT_ID'},
        host='HOST',
        network=given_network,
        _binding=given_binding,
        _binding_levels=binding_levels,
        _new_bound_segment=new_bound_segment,
        _next_segments_to_bind=next_segments_to_bind,
        _push_binding_level=push_binding_level,
        _pop_binding_level=pop_binding_level)


def mock_binding_level(driver=None, segment_id="SEGMENT"):
    if driver is None:
        driver = mock_mechanism_driver()
    return mock.Mock(driver=driver, segment_id=segment_id)


def mock_mechanism_driver(name='DRIVER', bind_port=None):

    if bind_port is None:

        def bind_port(context):
            pass

    driver = mock.Mock(
        specs=driver_api.MechanismDriver,
        bind_port=mock.Mock(side_effect=bind_port))
    return mock.Mock(name=name, obj=driver)
