"""CI fixture networking must work while private home services stay isolated."""
import pytest
from tools.ci_home_landlock import BIND, CONNECT, PROTECTED_PORTS, tcp_rules


def test_ephemeral_listener_can_rebind_its_allocated_port():
    rules = dict(tcp_rules(32768, 60999))
    assert rules[0] == BIND
    for port in (32768, 49152, 60999):
        assert rules[port] & BIND
        assert rules[port] & CONNECT


def test_private_services_have_no_bind_or_connect_grant():
    rules = dict(tcp_rules(32768, 60999))
    assert PROTECTED_PORTS.isdisjoint(rules)
    assert {8803, 25569}.issubset(PROTECTED_PORTS)  # Product game viewer and server.
    assert 8799 not in rules  # Private browser, as well as VM/admin services.
    assert 80 in rules and rules[80] == CONNECT
    assert rules[443] == CONNECT
    for port in range(8765, 8770):
        assert rules[port] == BIND | CONNECT
    assert 8770 not in rules
    assert 32767 not in rules
    assert 61000 not in rules


@pytest.mark.parametrize("low,high", [(0, 40000), (40000, 32768), (32768, 65536),
                                        (8000, 9000), (8820, 8820)])
def test_invalid_or_private_overlapping_range_fails_closed(low, high):
    with pytest.raises(RuntimeError):
        list(tcp_rules(low, high))
