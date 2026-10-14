"""The migration stop guard must never act on unrelated account pods."""
import pytest

from tools.private_home_recovery_guard import AUTHORIZED_PODS, verify_authorized_pod


@pytest.mark.parametrize("pod,name", AUTHORIZED_PODS.items())
def test_exact_authorized_migration_identity(pod, name):
    verify_authorized_pod(pod, {"id": pod, "name": name})


@pytest.mark.parametrize("pod,state", [
    ("80lf8giw6ft61v", {"id": "80lf8giw6ft61v", "name": "sub01-home-private-recovery"}),
    ("713u6mnmxu4y1a", {"id": "713u6mnmxu4y1a", "name": "sub01-home-private-recovery"}),
    ("unrelated", {"id": "unrelated", "name": "sub01-home-private-migration-20261014"}),
    ("5ldnm4vax9kelh", {"id": "different", "name": "sub01-home-private-migration-20261014"}),
    ("5ldnm4vax9kelh", {"id": "5ldnm4vax9kelh", "name": "wrong-name"}),
])
def test_reject_other_pods_and_mismatched_identity(pod, state):
    with pytest.raises(RuntimeError, match="Unauthorized"):
        verify_authorized_pod(pod, state)
