"""Failure-mode unit checks; none of these are native runtime acceptance."""
from scripts.private_home_acceptance import Observer, frame_tag, CORE


def snapshot(private=False):
    health = dict(nativeIdentity=[12, 34], nativeAlive=True, privacy=private,
                  captureEnabled=not private, inputEnabled=not private, viewMode='live')
    home = dict(privacy=private, activity='play_console', sequence=4,
                activity_ready=True, native_consumer=dict(required=True, physical_ready=True, fresh=True))
    pixels = b'\xff\xd8actual-sample-one'
    state = dict(home=home, life={'privacy': True} if private else {'activity': 'play_console'},
                 computer={'display': {'available': False}}, minecraft={} if private else dict(
                     status='ready', frame_kind='active', has_frame=True, frame_id=frame_tag(pixels),
                     observation={'connected': True, 'position': [1, 2, 3]}, controller=dict(
                         enabled=True, ready=True, pose_fresh=True, ack_input_id=3,
                         pose_received_utc=100.1, sequence=4, epoch='native', consumer_id='a', event_id='b')))
    receipt = dict(native_pid=12, native_start_ticks=34, captured_utc=100.1, physical_camera_private=private)
    return health, state, receipt, {'privacy': private, 'display': {'available': False}}, pixels


def test_no_fixtures_or_backend_positions_can_pass_release():
    o = Observer([12, 34], 100, 'release')
    for _ in range(3):
        o.sample(*snapshot(), now=100.2)
    assert not o.gates['physical_movement'] and not o.gates['controller_ack']
    assert not o.report()['release_accepted']
    o.gates.update({k: True for k in CORE})
    assert o.report()['missing'] == ['phone_physical_routine', 'bed_physical_routine', 'seated_transitions']


def test_stale_future_reused_and_restarted_privacy_receipts_fail_closed():
    for change in ({'captured_utc': 99.9}, {'captured_utc': 102}, {'native_start_ticks': 35}):
        o = Observer([12, 34], 100)
        h, s, p, pc, pixels = snapshot()
        p.update(change)
        o.sample(h, s, p, pc, pixels, now=100.2)
        assert o.report()['failures'] == ['privacy_evidence_unavailable']
        assert not o.gates['live_readiness']
    o = Observer([12, 34], 100)
    h, s, p, pc, pixels = snapshot()
    h['nativeIdentity'] = [12, 35]
    o.sample(h, s, p, pc, pixels, now=100.2)
    assert o.report()['failures'] == ['native_identity_changed']


def test_privacy_leaks_and_egress_are_observed_separately():
    o = Observer([12, 34], 100)
    o.sample(*snapshot(True), now=100.2)
    assert o.gates['privacy_blackout'] and not o.gates['privacy_egress']
    o.sample(*snapshot(), now=100.2)
    assert o.gates['privacy_egress']
    for field in ('captureEnabled', 'inputEnabled'):
        o = Observer([12, 34], 100)
        h, s, p, pc, pixels = snapshot(True)
        h[field] = True
        o.sample(h, s, p, pc, pixels, now=100.2)
        assert o.report()['failures'] == ['privacy_capture_or_input_leak']
    o = Observer([12, 34], 100)
    h, s, p, pc, pixels = snapshot(True)
    s['minecraft'] = {'controller': {'ack_input_id': 123}}
    o.sample(h, s, p, pc, pixels, now=100.2)
    assert o.report()['failures'] == ['privacy_observer_leak']


def test_controller_ack_needs_current_world_pixels_and_physical_validator():
    o = Observer([12, 34], 100)
    h, s, p, pc, pixels = snapshot()
    o.sample(h, s, p, pc, pixels, now=100.2, controller_verified=True)
    assert not o.gates['minecraft_world_frame'] and not o.gates['controller_ack']
    pixels = b'\xff\xd8actual-sample-two'
    o.sample(h, s, p, pc, pixels, now=100.2, controller_verified=True)
    assert not o.gates['minecraft_world_frame']  # ETag mismatch.
    s['minecraft']['frame_id'] = frame_tag(pixels)
    o.sample(h, s, p, pc, pixels, now=100.2)
    assert o.gates['minecraft_world_frame'] and not o.gates['controller_ack']
    s['minecraft']['controller']['sequence'] = 3
    o.sample(h, s, p, pc, pixels, now=100.2, controller_verified=True)
    assert not o.gates['controller_ack']
    s['minecraft']['controller']['sequence'] = 4
    o.sample(h, s, p, pc, pixels, now=100.2, controller_verified=True)
    assert o.gates['controller_ack']


def test_pc_serial_marker_cannot_pass_gui_input():
    o = Observer([12, 34], 100)
    h, s, p, _, pixels = snapshot()
    pc = dict(ready=True, privacy=False, output='marker',
              display=dict(kind='serial', available=True, frame_id='a'))
    proof = dict(native_pid=12, native_start_ticks=34, captured_utc=100.1,
                 schema='sub01-native-pc-gui-input-v1', transport='native-keyboard',
                 guest_frame_id='a', gui_input_acknowledged=True, rendered_marker_observed=True)
    o.sample(h, s, p, pc, pixels, b'\x89PNG\r\n\x1a\n', proof, now=100.2)
    assert not o.gates['pc_gui_frame'] and not o.gates['pc_gui_input']
    pc['display']['kind'] = 'graphical'
    proof['guest_frame_id'] = 'old'
    o.sample(h, s, p, pc, pixels, b'\x89PNG\r\n\x1a\n', proof, now=100.2)
    assert o.gates['pc_gui_frame'] and not o.gates['pc_gui_input']


def test_movement_requires_actual_different_native_checkpoints():
    o = Observer([12, 34], 100)
    o.movement('SUB01_ROUTE_CHECKPOINT name=desk pawn=X=1 Y=2 Z=3 floor=1')
    assert not o.gates['physical_movement']  # Diagnostic route excluded.
    o.movement('SUB01_LIVE_HOME_REACHED node=desk pawn=X=1.0 Y=2.0 Z=3.0 floor=1')
    o.movement('SUB01_LIVE_HOME_REACHED node=kitchen pawn=X=1.0 Y=2.0 Z=3.0 floor=1')
    assert not o.gates['physical_movement']
    o.movement('SUB01_LIVE_HOME_REACHED node=stair_bottom pawn=X=1.0 Y=22.0 Z=3.0 floor=1')
    assert o.gates['physical_movement']


def test_native_receipt_permissions_and_symlinks_cannot_be_bypassed(tmp_path):
    import json
    import os
    import pytest
    from scripts.private_home_acceptance import trusted_json, save_report
    path = tmp_path / 'report.json'
    save_report(path, {'native_pid': 12})
    assert path.stat().st_mode & 0o777 == 0o600
    assert trusted_json(path, os.getuid()) == {'native_pid': 12}
    with pytest.raises(ValueError):
        trusted_json(path, os.getuid() + 1)
    path.chmod(0o644)
    with pytest.raises(ValueError):
        trusted_json(path, os.getuid())
    path.chmod(0o600)
    link = tmp_path / 'link.json'
    link.symlink_to(path)
    with pytest.raises(OSError):
        trusted_json(link, os.getuid())
