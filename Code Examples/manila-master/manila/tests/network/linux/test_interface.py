# Copyright 2014 Mirantis Inc.
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

from unittest import mock

from manila.network.linux import interface
from manila.network.linux import ip_lib
from manila import test
from manila.tests import conf_fixture
from manila.tests import fake_network
from manila import utils


class BaseChild(interface.LinuxInterfaceDriver):
    def plug(self, *args):
        pass

    def unplug(self, *args):
        pass


FakeSubnet = {
    'cidr': '192.168.1.1/24',
}


FakeAllocation = {
    'subnet': FakeSubnet,
    'ip_address': '192.168.1.2',
    'ip_version': 4,
}


FakePort = {
    'id': 'abcdef01-1234-5678-90ab-ba0987654321',
    'fixed_ips': [FakeAllocation],
    'device_id': 'cccccccc-cccc-cccc-cccc-cccccccccccc',
}


class TestBase(test.TestCase):
    def setUp(self):
        super(TestBase, self).setUp()
        self.conf = conf_fixture.CONF
        self.conf.register_opts(interface.OPTS)
        self.ip_dev_p = mock.patch.object(ip_lib, 'IPDevice')
        self.ip_dev = self.ip_dev_p.start()
        self.ip_p = mock.patch.object(ip_lib, 'IPWrapper')
        self.ip = self.ip_p.start()
        self.device_exists_p = mock.patch.object(ip_lib, 'device_exists')
        self.device_exists = self.device_exists_p.start()
        self.addCleanup(self.ip_dev_p.stop)
        self.addCleanup(self.ip_p.stop)
        self.addCleanup(self.device_exists_p.stop)


class TestABCDriver(TestBase):

    def test_verify_abs_class_has_abs_methods(self):

        class ICanNotBeInstancetiated(interface.LinuxInterfaceDriver):
            pass

        try:
            # pylint: disable=abstract-class-instantiated
            ICanNotBeInstancetiated()
        except TypeError:
            pass
        except Exception as e:
            self.fail("Unexpected exception thrown: '%s'" % e)
        else:
            self.fail("ExpectedException 'TypeError' not thrown.")

    def test_get_device_name(self):
        bc = BaseChild()
        device_name = bc.get_device_name(FakePort)
        self.assertEqual('tapabcdef01-12', device_name)

    def test_l3_init(self):
        addresses = [dict(ip_version=4, scope='global',
                          dynamic=False, cidr='172.16.77.240/24')]
        self.ip_dev().addr.list = mock.Mock(return_value=addresses)

        bc = BaseChild()
        self.mock_object(bc, '_remove_outdated_interfaces')

        ns = '12345678-1234-5678-90ab-ba0987654321'
        bc.init_l3('tap0', ['192.168.1.2/24'], namespace=ns,
                   clear_cidrs=['192.168.0.0/16'])
        self.ip_dev.assert_has_calls(
            [mock.call('tap0', namespace=ns),
             mock.call().route.clear_outdated_routes('192.168.0.0/16'),
             mock.call().addr.list(scope='global', filters=['permanent']),
             mock.call().addr.add(4, '192.168.1.2/24', '192.168.1.255'),
             mock.call().addr.delete(4, '172.16.77.240/24'),
             mock.call().route.pullup_route('tap0')])
        bc._remove_outdated_interfaces.assert_called_with(self.ip_dev())

    def test__remove_outdated_interfaces(self):
        device = fake_network.FakeDevice(
            'foobarquuz', [dict(ip_version=4, cidr='1.0.0.0/27')])
        devices = [fake_network.FakeDevice('foobar')]
        self.ip().get_devices = mock.Mock(return_value=devices)

        bc = BaseChild()
        self.mock_object(bc, 'unplug')

        bc._remove_outdated_interfaces(device)
        bc.unplug.assert_called_once_with('foobar')

    def test__get_set_of_device_cidrs(self):
        device = fake_network.FakeDevice('foo')
        expected = set(('1.0.0.0/27', '2.0.0.0/27'))

        bc = BaseChild()
        result = bc._get_set_of_device_cidrs(device)

        self.assertEqual(expected, result)

    def test__get_set_of_device_cidrs_exception(self):
        device = fake_network.FakeDevice('foo')
        self.mock_object(device.addr, 'list', mock.Mock(
            side_effect=Exception('foo does not exist')))

        bc = BaseChild()
        result = bc._get_set_of_device_cidrs(device)

        self.assertEqual(set(), result)


class TestNoopInterfaceDriver(TestBase):

    def test_init_l3(self):
        self.ip.assert_not_called()
        self.ip_dev.assert_not_called()

    def test_plug(self):
        self.ip.assert_not_called()
        self.ip_dev.assert_not_called()

    def test_unplug(self):
        self.ip.assert_not_called()
        self.ip_dev.assert_not_called()


class TestOVSInterfaceDriver(TestBase):

    def test_get_device_name(self):
        br = interface.OVSInterfaceDriver()
        device_name = br.get_device_name(FakePort)
        self.assertEqual('tapabcdef01-12', device_name)

    def test_plug_no_ns(self):
        self._test_plug()

    def test_plug_with_ns(self):
        self._test_plug(namespace='01234567-1234-1234-99')

    def test_plug_alt_bridge(self):
        self._test_plug(bridge='br-foo')

    def _test_plug(self, additional_expectation=None, bridge=None,
                   namespace=None):
        if additional_expectation is None:
            additional_expectation = []
        if not bridge:
            bridge = 'br-int'

        def device_exists(dev, namespace=None):
            return dev == bridge

        vsctl_cmd = ['ovs-vsctl', '--', '--may-exist', 'add-port',
                     bridge, 'tap0', '--', 'set', 'Interface', 'tap0',
                     'type=internal', '--', 'set', 'Interface', 'tap0',
                     'external-ids:iface-id=port-1234', '--', 'set',
                     'Interface', 'tap0',
                     'external-ids:iface-status=active', '--', 'set',
                     'Interface', 'tap0',
                     'external-ids:attached-mac=aa:bb:cc:dd:ee:ff']

        with mock.patch.object(utils, 'execute') as execute:
            ovs = interface.OVSInterfaceDriver()
            self.device_exists.side_effect = device_exists
            ovs.plug('tap0',
                     'port-1234',
                     'aa:bb:cc:dd:ee:ff',
                     bridge=bridge,
                     namespace=namespace)
            execute.assert_called_once_with(*vsctl_cmd, run_as_root=True)

        expected = [mock.call(),
                    mock.call().device('tap0'),
                    mock.call().device().link.set_address('aa:bb:cc:dd:ee:ff')]
        expected.extend(additional_expectation)
        if namespace:
            expected.extend(
                [mock.call().ensure_namespace(namespace),
                 mock.call().ensure_namespace().add_device_to_namespace(
                     mock.ANY)])
        expected.extend([mock.call().device().link.set_up()])

        self.ip.assert_has_calls(expected)

    def test_plug_reset_mac(self):
        fake_mac_addr = 'aa:bb:cc:dd:ee:ff'
        self.device_exists.return_value = True

        self.ip().device().link.address = mock.Mock(return_value=fake_mac_addr)
        ovs = interface.OVSInterfaceDriver()
        ovs.plug('tap0',
                 'port-1234',
                 'ff:ee:dd:cc:bb:aa',
                 bridge='br-int')
        expected = [mock.call(),
                    mock.call().device('tap0'),
                    mock.call().device().link.set_address('ff:ee:dd:cc:bb:aa'),
                    mock.call().device().link.set_up()]
        self.ip.assert_has_calls(expected)

    def test_unplug(self, bridge=None):
        if not bridge:
            bridge = 'br-int'
        with mock.patch('manila.network.linux.ovs_lib.OVSBridge') as ovs_br:
            ovs = interface.OVSInterfaceDriver()
            ovs.unplug('tap0')
            ovs_br.assert_has_calls([mock.call(bridge),
                                     mock.call().delete_port('tap0')])


class TestBridgeInterfaceDriver(TestBase):
    def test_get_device_name(self):
        br = interface.BridgeInterfaceDriver()
        device_name = br.get_device_name(FakePort)
        self.assertEqual('ns-abcdef01-12', device_name)

    def test_plug_no_ns(self):
        self._test_plug()

    def test_plug_with_ns(self):
        self._test_plug(namespace='01234567-1234-1234-99')

    def _test_plug(self, namespace=None, mtu=None):
        def device_exists(device, root_helper=None, namespace=None):
            return device.startswith('brq')

        root_veth = mock.Mock()
        ns_veth = mock.Mock()

        self.ip().add_veth = mock.Mock(return_value=(root_veth, ns_veth))

        self.device_exists.side_effect = device_exists
        br = interface.BridgeInterfaceDriver()
        mac_address = 'aa:bb:cc:dd:ee:ff'
        br.plug('ns-0',
                'port-1234',
                mac_address,
                namespace=namespace)

        ip_calls = [mock.call(),
                    mock.call().add_veth('tap0', 'ns-0', namespace2=namespace)]
        ns_veth.assert_has_calls([mock.call.link.set_address(mac_address)])

        self.ip.assert_has_calls(ip_calls)

        root_veth.assert_has_calls([mock.call.link.set_up()])
        ns_veth.assert_has_calls([mock.call.link.set_up()])

    def test_plug_dev_exists(self):
        self.device_exists.return_value = True
        with mock.patch('manila.network.linux.interface.LOG.warning') as log:
            br = interface.BridgeInterfaceDriver()
            br.plug('port-1234',
                    'tap0',
                    'aa:bb:cc:dd:ee:ff')
            self.ip_dev.assert_has_calls([])
            self.assertEqual(1, log.call_count)

    def test_unplug_no_device(self):
        self.device_exists.return_value = False
        self.ip_dev().link.delete.side_effect = RuntimeError
        with mock.patch('manila.network.linux.interface.LOG') as log:
            br = interface.BridgeInterfaceDriver()
            br.unplug('tap0')
            [mock.call(), mock.call('tap0'), mock.call().link.delete()]
            self.assertEqual(1, log.error.call_count)

    def test_unplug(self):
        self.device_exists.return_value = True
        with mock.patch('manila.network.linux.interface.LOG.debug') as log:
            br = interface.BridgeInterfaceDriver()
            br.unplug('tap0')
            self.assertTrue(log.called)
        self.ip_dev.assert_has_calls([mock.call('tap0', None),
                                      mock.call().link.delete()])
