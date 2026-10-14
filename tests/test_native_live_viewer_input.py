"""The live viewer can deliver physical controls, never arbitrary host commands."""
import pytest
import json
import time
from tools.pixel_streaming.native_live_viewer import LiveState, validate_input


@pytest.mark.parametrize("event", [
    {"action": "key", "code": "KeyW", "down": True},
    {"action": "key", "code": "Enter", "down": False},
    {"action": "mouse", "dx": -100, "dy": 100},
    {"action": "button", "button": 1, "down": True},
    {"action": "release"},
])
def test_allowed_physical_controls(event):
    assert validate_input(event) == event


@pytest.mark.parametrize("event", [
    {"action": "key", "code": "AltLeft", "down": True},
    {"action": "key", "code": "KeyW", "down": 1},
    {"action": "mouse", "dx": 101, "dy": 0},
    {"action": "mouse", "dx": True, "dy": 0},
    {"action": "button", "button": 2, "down": True},
    {"action": "release", "command": "anything"},
    {"action": "shell", "command": "anything"},
    [],
])
def test_unsupported_or_unbounded_input_is_rejected(event):
    with pytest.raises(ValueError):
        validate_input(event)


def test_capture_permission_cannot_survive_native_process_replacement(tmp_path):
    state = LiveState(time.time() + 30)
    state.private = tmp_path
    state.privacy = lambda: False
    flag = tmp_path / "native-viewer-capture-enabled"
    flag.write_text(json.dumps({"native_pid": 42, "native_start_ticks": 100}))
    state.native = lambda: (42, 100)
    assert state.enabled(flag.name)
    state.native = lambda: (42, 101)
    assert not state.enabled(flag.name)
    state.native = lambda: (43, 100)
    assert not state.enabled(flag.name)
    state.native = lambda: None
    assert not state.enabled(flag.name)


@pytest.mark.parametrize("content", ["", "[]", "not-json"])
def test_invalid_capture_permission_fails_closed(tmp_path, content):
    state = LiveState(time.time() + 30)
    state.private = tmp_path
    state.privacy = lambda: False
    state.native = lambda: (42, 100)
    flag = tmp_path / "native-viewer-capture-enabled"
    flag.write_text(content)
    assert not state.enabled(flag.name)


@pytest.mark.parametrize('value', [
    {'fov': 111}, {'fov': True}, {'hour': float('nan')},
    {'lamps': {'SUN': False}}, {'lamps': {'DeskLamp': 1}},
    {'lamps': {'Actor/Other': True}}, {'console': 'anything'},
])
def test_settings_cannot_address_unknown_actors_or_unbounded_camera(value):
    from tools.pixel_streaming.native_live_viewer import validate_settings
    with pytest.raises(ValueError):
        validate_settings(value, {'fov': True, 'hour': True, 'lamps': ['DeskLamp']})


def test_settings_require_actual_native_capability():
    from tools.pixel_streaming.native_live_viewer import validate_settings
    with pytest.raises(ValueError):
        validate_settings({'fov': 75}, {})
    assert validate_settings({'fov': 75, 'lamps': {'DeskLamp': False}},
                             {'fov': True, 'lamps': ['DeskLamp']})


def test_settings_receipt_is_invalid_after_native_replacement(tmp_path):
    state = LiveState(time.time() + 30)
    state.private = tmp_path
    state.privacy = lambda: False
    (tmp_path/'native-view-settings-receipt.json').write_text(json.dumps({
        'native_pid': 42, 'native_start_ticks': 100,
        'capabilities': {'fov': True}, 'values': {'fov': 75},
    }))
    state.native = lambda: (42, 100)
    assert state.settings_receipt()['capabilities']['fov']
    state.native = lambda: (42, 101)
    assert state.settings_receipt() is None


@pytest.mark.parametrize("privacy", [True, None])
def test_canonical_privacy_or_unknown_blocks_pixels_and_input(tmp_path, privacy):
    state = LiveState(time.time()+30)
    state.private = tmp_path
    state.native = lambda: (42,100)
    state.privacy = lambda: privacy
    state.latest_frame = b'previous real frame'
    for name in ('native-viewer-capture-enabled','native-viewer-input-enabled'):
        (tmp_path/name).write_text(json.dumps({'native_pid':42,'native_start_ticks':100}))
        assert not state.enabled(name)
    assert state.latest_frame == b''


@pytest.mark.parametrize('document', [None, [], {'privacy': False},
    {'target':'bed','sequence':1,'activity':'sleep','privacy':0},
    {'target':'bed','sequence':True,'activity':'sleep','privacy':False}])
def test_malformed_canonical_privacy_cannot_permit_video(document):
    from tools.pixel_streaming.native_live_viewer import canonical_privacy
    assert canonical_privacy(document) is None


@pytest.mark.parametrize('backend,physical,expected', [
    (False,False,False), (False,True,True), (True,False,True),
    (None,False,None), (False,None,None), (None,True,True),
    (True,None,True), (None,None,None), (True,True,True),
])
def test_manual_camera_privacy_cannot_be_cleared_by_public_backend(backend,physical,expected):
    from tools.pixel_streaming.native_live_viewer import combine_privacy
    assert combine_privacy(backend,physical) is expected


def test_native_camera_privacy_requires_fresh_current_process_receipt():
    from tools.pixel_streaming.native_live_viewer import native_camera_privacy
    receipt={'native_pid':42,'native_start_ticks':100,'captured_utc':500,
             'physical_camera_private':False}
    assert native_camera_privacy(receipt,(42,100),500.2) is False
    assert native_camera_privacy(receipt,(42,101),500.2) is None
    assert native_camera_privacy(receipt,(42,100),502) is None
    assert native_camera_privacy(receipt,(42,100),499) is None
    receipt['physical_camera_private']=True
    assert native_camera_privacy(receipt,(42,100),500.2) is True


@pytest.mark.parametrize('event,allowed', [
    ({'action':'key','code':'KeyW','down':True},True),
    ({'action':'key','code':'KeyS','down':False},True),
    ({'action':'mouse','dx':1,'dy':-1},True),
    ({'action':'release'},True),
    ({'action':'key','code':'KeyE','down':True},False),
    ({'action':'key','code':'Enter','down':True},False),
    ({'action':'button','button':1,'down':True},False),
])
def test_private_egress_is_movement_only(event,allowed):
    from tools.pixel_streaming.native_live_viewer import private_egress_event
    assert private_egress_event(validate_input(event)) is allowed


def test_egress_requires_known_backend_and_current_native_focus_revocation(tmp_path):
    state=LiveState(time.time()+30)
    state.private=tmp_path
    state.native=lambda:(42,100)
    state.privacy=lambda:True
    state.backend_privacy_value=False
    (tmp_path/'native-viewer-input-enabled').write_text(json.dumps({
        'native_pid':42,'native_start_ticks':100,'view_mode':'manual'}))
    receipt={'native_pid':42,'native_start_ticks':100,'captured_utc':time.time(),
             'physical_camera_private':True,'private_egress_ready':True}
    path=tmp_path/'native-view-privacy.json'
    path.write_text(json.dumps(receipt))
    assert state.can_private_egress()
    state.backend_privacy_value=None
    assert not state.can_private_egress()
    state.backend_privacy_value=False
    receipt['private_egress_ready']=False
    path.write_text(json.dumps(receipt))
    assert not state.can_private_egress()
    receipt['private_egress_ready']=True
    receipt['native_start_ticks']=99
    path.write_text(json.dumps(receipt))
    assert not state.can_private_egress()


@pytest.mark.parametrize('mode',['manual','live','diagnostic'])
def test_mode_requires_fresh_actual_native_ownership(mode):
    from tools.pixel_streaming.native_live_viewer import native_view_mode
    receipt={'native_pid':42,'native_start_ticks':100,'captured_utc':50.,'physical_camera_private':False,'view_mode':mode}
    assert native_view_mode(receipt,(42,100),50.)==mode
    assert native_view_mode(receipt,(42,101),50.) is None
    assert native_view_mode(receipt,(42,100),51.1) is None
    assert native_view_mode({**receipt,'view_mode':'invented'},(42,100),50.) is None
    assert native_view_mode({k:v for k,v in receipt.items() if k!='view_mode'},(42,100),50.) is None


def test_live_activity_uses_only_fresh_public_known_stage_and_allowlisted_labels():
    from tools.pixel_streaming.native_live_viewer import public_live_activity
    d={'source':{'status':'live'},'privacy':False,'brain':{'stage':'AWAKE','activity':'eat'}}
    assert public_live_activity(d)=={'awake':True,'activity':'Meal'}
    assert public_live_activity({**d,'brain':{'stage':'REM','activity':'sleep'}})=={'awake':False,'activity':'Rest'}
    assert public_live_activity({**d,'privacy':True}) is None
    assert public_live_activity({**d,'source':{'status':'stale'}}) is None
    assert public_live_activity({**d,'brain':{'stage':None,'activity':'sleep'}}) is None
    assert public_live_activity({**d,'brain':{'stage':'AWAKE','activity':'owner private note'}})=={'awake':True,'activity':None}
