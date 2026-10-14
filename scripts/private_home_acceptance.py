#!/usr/bin/env python3
"""Read-only acceptance observer for the existing private native session.

Never starts services, sends controls, changes activity or grants readiness.
Exit 0 means the requested gates were observed in this run. Missing evidence
is exit 2; collection errors are exit 1. A core pass is never a home release.
"""
import argparse
import asyncio
import json
import math
import os
import re
import stat
import sys
import time
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aiohttp import ClientSession, ClientTimeout
from home_minecraft import frame_tag
from home_minecraft_input import native_process, PROJECT
from home_minecraft_controller import ControllerEvidence
from scripts.home_device_proxy import loopback_origin

CORE = ('native_session', 'physical_movement', 'live_readiness', 'privacy_blackout',
        'privacy_egress', 'pc_gui_frame', 'pc_gui_input', 'minecraft_world_frame', 'controller_ack')
# These have no release-quality native acceptance collector yet. Fail closed.
RELEASE = CORE + ('phone_physical_routine', 'bed_physical_routine', 'seated_transitions')
REACHED = re.compile(r'SUB01_LIVE_HOME_REACHED node=(\w+) pawn=X=([-\d.]+) Y=([-\d.]+) Z=([-\d.]+) floor=1')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def save_report(path, report):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(report, stream, indent=2)
        stream.write('\n')
    temporary.replace(target)  # temporary starts with mode 0600


def trusted_json(path, uid, limit=65536):
    """Protected native evidence only; credentials and arbitrary user files excluded."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_mode & 0o077 or info.st_size > limit:
            raise ValueError('Untrusted evidence file')
        value = json.loads(stream.read(limit + 1))
    if not isinstance(value, dict):
        raise ValueError('Evidence is not an object')
    return value


class Observer:
    def __init__(self, identity, started, profile='core'):
        self.identity = tuple(identity)
        self.started = started
        self.profile = profile
        self.gates = {name: False for name in RELEASE}
        self.failures = set()
        self.reached = []
        self.private_seen = False
        self.samples = 0
        self.last_frame = None
        self.world_frames = set()

    def receipt(self, value, now, ttl=1):
        return (isinstance(value, dict)
                and (value.get('native_pid'), value.get('native_start_ticks')) == self.identity
                and finite(value.get('captured_utc'))
                and self.started <= value['captured_utc']
                and -.05 <= now - value['captured_utc'] <= ttl)

    def movement(self, text):
        # Caller reads only newly appended bytes of the exact process's log.
        for match in REACHED.finditer(text):
            position = [float(v) for v in match.groups()[1:]]
            if all(finite(v) for v in position):
                self.reached.append((match.group(1), position))
        if len(self.reached) >= 2:
            self.gates['physical_movement'] = any(
                a[0] != b[0] and math.dist(a[1], b[1]) > 10
                for a, b in zip(self.reached, self.reached[1:]))

    def sample(self, health, state, privacy, pc, mc_pixels=None, pc_pixels=None, pc_proof=None, now=None, controller_verified=False):
        now = time.time() if now is None else now
        self.samples += 1
        if tuple(health.get('nativeIdentity') or ()) != self.identity or health.get('nativeAlive') is not True:
            self.failures.add('native_identity_changed')
            return
        self.gates['native_session'] = True
        home = state.get('home') or {}
        if not self.receipt(privacy, now) or type(health.get('privacy')) is not bool:
            self.failures.add('privacy_evidence_unavailable')
            return
        physical_private = privacy.get('physical_camera_private')
        if type(physical_private) is not bool:
            self.failures.add('privacy_evidence_unavailable')
            return
        private = physical_private or home.get('privacy') is True
        if private:
            self.private_seen = True
            if (pc.get('privacy') is not True or pc.get('output')
                    or (pc.get('display') or {}).get('available') is True):
                self.failures.add('privacy_guest_leak')
            if health.get('privacy') is not True or health.get('captureEnabled') is not False or health.get('inputEnabled') is not False:
                self.failures.add('privacy_capture_or_input_leak')
            elif home.get('privacy') is True and (
                    state.get('life') != {'privacy': True}
                    or (state.get('minecraft') or {}).get('frame_id')
                    or (state.get('minecraft') or {}).get('controller')
                    or (state.get('computer') or {}).get('output')
                    or (state.get('computer') or {}).get('display', {}).get('available') is True):
                self.failures.add('privacy_observer_leak')
            else:
                self.gates['privacy_blackout'] = True
            return
        if health.get('privacy') is not False or home.get('privacy') is not False:
            self.failures.add('privacy_disagreement')
            return
        if self.private_seen and health.get('captureEnabled') is True:
            self.gates['privacy_egress'] = True
        native = home.get('native_consumer') or {}
        self.gates['live_readiness'] |= (health.get('viewMode') == 'live'
            and native.get('required') is True and native.get('physical_ready') is True
            and native.get('fresh') is True and home.get('activity_ready') is True)
        display = pc.get('display') or {}
        if (pc.get('ready') is True and pc.get('privacy') is False
                and display.get('kind') == 'graphical' and display.get('available') is True
                and isinstance(display.get('frame_id'), str) and display['frame_id']
                and pc_pixels and pc_pixels.startswith(b'\x89PNG\r\n\x1a\n')):
            self.gates['pc_gui_frame'] = True
            # A standalone serial marker is deliberately insufficient.
            if (self.receipt(pc_proof, now, ttl=600)
                    and pc_proof.get('schema') == 'sub01-native-pc-gui-input-v1'
                    and pc_proof.get('transport') == 'native-keyboard'
                    and pc_proof.get('guest_frame_id') == display['frame_id']
                    and pc_proof.get('gui_input_acknowledged') is True
                    and pc_proof.get('rendered_marker_observed') is True):
                self.gates['pc_gui_input'] = True
        minecraft = state.get('minecraft') or {}
        current = minecraft.get('frame_id')
        observation = minecraft.get('observation') or {}
        if (minecraft.get('status') == 'ready' and minecraft.get('frame_kind') == 'active'
                and minecraft.get('has_frame') is True and observation.get('connected') is True
                and isinstance(observation.get('position'), list) and len(observation['position']) == 3
                and all(finite(v) for v in observation['position'])
                and mc_pixels and mc_pixels.startswith(b'\xff\xd8') and frame_tag(mc_pixels) == current):
            self.world_frames.add(current)
            self.gates['minecraft_world_frame'] = len(self.world_frames) >= 2
        controller = minecraft.get('controller') or {}
        stamp = controller.get('pose_received_utc')
        if (controller_verified and self.gates['minecraft_world_frame'] and home.get('activity') == 'play_console'
                and native.get('physical_ready') is True and controller.get('enabled') is True
                and controller.get('ready') is True and controller.get('pose_fresh') is True
                and type(controller.get('ack_input_id')) is int and controller['ack_input_id'] > 0
                and finite(stamp) and self.started <= stamp <= now and now - stamp <= .3
                and controller.get('sequence') == home.get('sequence')
                and controller.get('epoch') and controller.get('consumer_id') and controller.get('event_id')):
            self.gates['controller_ack'] = True

    def report(self):
        required = CORE if self.profile == 'core' else RELEASE
        passed = all(self.gates[name] for name in required) and not self.failures
        return {'schema': 'sub01-private-home-acceptance-v1', 'profile': self.profile,
                'scope': 'Observed existing runtime during this run; no source or fixture acceptance',
                'started_utc': self.started, 'native_identity': list(self.identity),
                'samples': self.samples, 'gates': self.gates,
                'failures': sorted(self.failures), 'missing': [k for k in required if not self.gates[k]],
                'passed': passed, 'release_accepted': passed and self.profile == 'release'}


async def observe(args):
    started = time.time()
    token = Path(args.token_file).read_text().strip()
    if not token:
        raise ValueError('Empty operator token')
    origins = {key: loopback_origin(getattr(args, key)) for key in ('home_origin', 'viewer_origin', 'pc_origin')}
    headers = {'X-Admin-Token': token}
    async with ClientSession(timeout=ClientTimeout(total=3), headers=headers) as session:
        async def get(origin, path, pixels=False):
            async with session.get(origin + path, allow_redirects=False) as response:
                if response.status != 200:
                    raise ValueError('Runtime observation endpoint unavailable')
                raw = await response.content.read(6 * 1024 * 1024 + 1)
                if len(raw) > 6 * 1024 * 1024:
                    raise ValueError('Observation response exceeds bound')
                return raw if pixels else json.loads(raw)
        health = await get(origins['viewer_origin'], '/health')
        if not finite(health.get('expiresEpoch')) or started >= health['expiresEpoch']:
            raise ValueError('Authorized native window unavailable')
        identity = health.get('nativeIdentity')
        if not isinstance(identity, list) or len(identity) != 2:
            raise ValueError('Actual native identity unavailable')
        uid, ticks, cmd = native_process(identity[0])
        if uid != args.native_uid or ticks != identity[1] or PROJECT.encode() not in cmd or b'-game' not in cmd:
            raise ValueError('Actual authorized native process unavailable')
        log = Path(args.native_log).resolve()
        # Tie the chosen log to the process command or its actual stdout file.
        cmd_logs = [Path(os.fsdecode(v.split(b'=', 1)[1])).resolve() for v in cmd if v.lower().startswith(b'-abslog=')]
        try:
            stdout_log = (Path('/proc') / str(identity[0]) / 'fd/1').resolve()
        except OSError:
            stdout_log = None
        if log not in cmd_logs and log != stdout_log:
            raise ValueError('Native log is not bound to the observed process')
        observer = Observer(identity, started, args.profile)
        with log.open() as stream:
            stream.seek(0, 2)  # Historic checkpoints never pass this run.
            log_identity = os.fstat(stream.fileno())
            until = time.monotonic() + min(args.seconds, health['expiresEpoch'] - time.time())
            while time.monotonic() < until:
                uid, ticks, cmd = native_process(identity[0])
                if uid != args.native_uid or ticks != identity[1] or PROJECT.encode() not in cmd or b'-game' not in cmd:
                    observer.failures.add('native_identity_changed'); break
                info = log.stat()
                if (info.st_dev, info.st_ino) != (log_identity.st_dev, log_identity.st_ino) or info.st_size < stream.tell():
                    observer.failures.add('native_log_rotated'); break
                observer.movement(stream.read(1024 * 1024))
                health = await get(origins['viewer_origin'], '/health')
                if not finite(health.get('expiresEpoch')) or time.time() >= health['expiresEpoch']:
                    observer.failures.add('window_expired'); break
                state = await get(origins['home_origin'], '/api/home')
                privacy = trusted_json(Path(args.private_dir) / 'native-view-privacy.json', args.native_uid)
                pc = await get(origins['pc_origin'], '/pc/state')
                mc_pixels = pc_pixels = proof = None
                if health.get('privacy') is True:
                    # GET refusal checks only; no input, capture process or service launch.
                    denied = [(origins['pc_origin'], '/pc/frame.png')]
                    if (state.get('home') or {}).get('privacy') is True:
                        denied += [(origins['home_origin'], '/api/home/minecraft/frame.jpg'),
                                   (origins['home_origin'], '/api/screen/desk.jpg'),
                                   (origins['home_origin'], '/api/screen/phone.jpg')]
                    for origin, path in denied:
                        async with session.get(origin + path, allow_redirects=False) as response:
                            if response.status != 409:
                                observer.failures.add('privacy_pixels_not_refused')
                if health.get('privacy') is False and (state.get('home') or {}).get('privacy') is False:
                    display = pc.get('display') or {}
                    if pc.get('privacy') is False and display.get('available') and display.get('frame_id'):
                        from urllib.parse import urlencode
                        pc_pixels = await get(origins['pc_origin'], '/pc/frame.png?' + urlencode({'revision': display['frame_id']}), True)
                        after = await get(origins['pc_origin'], '/pc/state')
                        if after.get('privacy') is not False or (after.get('display') or {}).get('frame_id') != display['frame_id']:
                            pc_pixels = None
                    if (state.get('minecraft') or {}).get('has_frame'):
                        mc_pixels = await get(origins['home_origin'], '/api/home/minecraft/frame.jpg', True)
                    if args.pc_gui_proof:
                        try:
                            proof = trusted_json(args.pc_gui_proof, args.native_uid)
                        except (OSError, ValueError):
                            pass
                # Reuse the controller owner's real physical-contact validator.
                home = state.get('home') or {}
                minecraft = state.get('minecraft') or {}
                controller = minecraft.get('controller') or {}
                proxy = SimpleNamespace(activity=home.get('activity'), console_game=home.get('console_game'),
                    target=home.get('destination'), sequence=home.get('sequence'),
                    privacy=lambda: home.get('privacy') is not False,
                    activity_ready=lambda activity: home.get('activity_ready') is True,
                    native_feedback=SimpleNamespace(required=(home.get('native_consumer') or {}).get('required') is True,
                                                    epoch=controller.get('epoch')))
                try:
                    owner = ControllerEvidence(path=Path(args.private_dir) / 'native-controller-grip.json', uid=args.native_uid)(proxy, minecraft.get('frame_id'))
                except (OSError, ValueError, TypeError, KeyError):
                    owner = None
                observer.sample(health, state, privacy, pc, mc_pixels, pc_pixels, proof,
                                controller_verified=bool(owner and owner[:2] == tuple(identity)))
                await asyncio.sleep(.1)
        report = observer.report()
        save_report(args.output, report)
        print(json.dumps(report))
        return 0 if report['passed'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home-origin', default='http://127.0.0.1:8820')
    parser.add_argument('--viewer-origin', default='http://127.0.0.1:8892')
    parser.add_argument('--pc-origin', default='http://127.0.0.1:8811')
    parser.add_argument('--token-file', required=True)
    parser.add_argument('--private-dir', default='/home/unreal/.sub01-private')
    parser.add_argument('--native-uid', type=int, default=1001)
    parser.add_argument('--native-log', required=True)
    parser.add_argument('--pc-gui-proof')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--profile', choices=('core', 'release'), default='core')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not finite(args.seconds) or not 1 <= args.seconds <= 600:
        parser.error('Observation window must be 1–600 seconds')
    try:
        return asyncio.run(observe(args))
    except Exception as error:
        # Never print endpoint bodies, token contents, guest text or raw state.
        print('Acceptance collection failed: ' + type(error).__name__, file=sys.stderr)
        save_report(args.output, {'schema': 'sub01-private-home-acceptance-v1',
            'profile': args.profile, 'passed': False, 'release_accepted': False,
            'collection_error': type(error).__name__})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
