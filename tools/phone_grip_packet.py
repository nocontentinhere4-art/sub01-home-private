"""Derived phone-grip review packet: contract check + manifest for root's native VISUAL review (never acceptance).

Proves, from bytes alone, that the derived clip is reviewable on the actual owner exactly like the capture:
* the raw capture docs/proposed/phone-capture/texting.glb is unchanged (sha pinned);
* the derived GLB has the same nodes, rest TRS, 66 channels (65 owner-joint rotations + Hips translation),
  the same 557-key input bytes, and every NON-edited channel's output bytes identical to the capture;
* edited channels are rotations of exactly the joints the report lists;
* every channel targets one of the owner's 65 skin joints (owner GLB JSON, no decoding);
* the report, audit and mount belong to this exact GLB.
Writes packet.json with hashes and the server-only native review steps. readiness stays false.

    python tools/phone_grip_packet.py check|write [--dir docs/proposed/phone-grip-derived]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from phone_rig import read_glb  # noqa: E402

SOURCE = ROOT/'docs/proposed/phone-capture/texting.glb'
SOURCE_SHA256 = '8a6dfc041cd4768016c6348dfb90f1275cab4c09cfe6083537fb88ba6d11ae75'
OWNER = ROOT/'web/room/char_mixamo.glb'
OWNER_SHA256 = '7609eccbe81631c00d123e69c54241597e28861d1dc947999425cd6c3257adbb'
DIR = ROOT/'docs/proposed/phone-grip-derived'
KEYS, CHANNELS, OWNER_JOINTS = 557, 66, 65


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def output_bytes(doc, binary, channel):
    anim = doc['animations'][0]
    acc = doc['accessors'][anim['samplers'][channel['sampler']]['output']]
    view = doc['bufferViews'][acc['bufferView']]
    start = view.get('byteOffset', 0)+acc.get('byteOffset', 0)
    return binary[start:start+view['byteLength']-acc.get('byteOffset', 0)]


def check(folder=DIR):
    folder = Path(folder)
    glb, report_path, audit_path = folder/'SUB01_PhoneGrip_derived.glb', folder/'SUB01_PhoneGrip_derived.report.json', folder/'SUB01_PhoneGrip_derived.audit.json'
    errors = []
    if sha(SOURCE) != SOURCE_SHA256:
        errors.append('raw capture changed')
    if sha(OWNER) != OWNER_SHA256:
        errors.append('owner changed')
    sdoc, sbin, _ = read_glb(SOURCE)
    ddoc, dbin, dsha = read_glb(glb)
    report = json.loads(report_path.read_text())
    audit = json.loads(audit_path.read_text())
    if report['output']['sha256'] != dsha:
        errors.append('report is not for this GLB')
    if audit['clip']['sha256'] != dsha or audit['owner']['sha256'] != OWNER_SHA256:
        errors.append('audit is not for this GLB/owner')
    if [n.get('name') for n in sdoc['nodes']] != [n.get('name') for n in ddoc['nodes']] or \
            any({k: n.get(k) for k in ('translation', 'rotation', 'scale', 'children')} != {k: m.get(k) for k in ('translation', 'rotation', 'scale', 'children')}
                for n, m in zip(sdoc['nodes'], ddoc['nodes'])):
        errors.append('node hierarchy or rest TRS differs')
    sa, da = sdoc['animations'][0], ddoc['animations'][0]
    if len(da['channels']) != CHANNELS or len(sa['channels']) != CHANNELS:
        errors.append('channel count')
    inputs = {da['samplers'][c['sampler']]['input'] for c in da['channels']}
    if len(inputs) != 1 or ddoc['accessors'][next(iter(inputs))]['count'] != KEYS:
        errors.append('key input')
    else:
        i = next(iter(inputs))
        acc_s, acc_d = sdoc['accessors'][i], ddoc['accessors'][i]
        vs, vd = sdoc['bufferViews'][acc_s['bufferView']], ddoc['bufferViews'][acc_d['bufferView']]
        if sbin[vs.get('byteOffset', 0):vs.get('byteOffset', 0)+vs['byteLength']] != dbin[vd.get('byteOffset', 0):vd.get('byteOffset', 0)+vd['byteLength']]:
            errors.append('key time bytes changed')
    edited = set(report['output'].get('edited_joints') or ddoc['asset']['extras']['edited_joints'])
    changed = []
    for cs, cd in zip(sa['channels'], da['channels']):
        name = ddoc['nodes'][cd['target']['node']]['name']
        if cs['target'] != cd['target']:
            errors.append(f'channel target differs {name}')
        if output_bytes(sdoc, sbin, cs) != output_bytes(ddoc, dbin, cd):
            changed.append(name)
            if cd['target']['path'] != 'rotation':
                errors.append(f'non-rotation channel changed {name}')
    if set(changed) != edited:
        errors.append(f'changed channels {sorted(set(changed) ^ edited)} differ from the edited list')
    odoc = json.loads(OWNER.read_bytes()[20:20+int.from_bytes(OWNER.read_bytes()[12:16], 'little')])
    joints = {odoc['nodes'][j]['name'] for j in odoc['skins'][0]['joints']}
    if len(joints) != OWNER_JOINTS:
        errors.append('owner joint contract')
    targets = {ddoc['nodes'][c['target']['node']]['name'] for c in da['channels']}
    if not targets <= joints:
        errors.append(f'channels outside owner joints {sorted(targets-joints)}')
    extras = ddoc['asset'].get('extras', {})
    if extras.get('label') != 'derived_from_capture' or extras.get('verified') is not False:
        errors.append('derived label/verified flag')
    if report.get('verified') is not False or any(report['gates'].values()) or any(audit['native_gates'].values()):
        errors.append('a gate or verified flag is not false')
    return {'ok': not errors, 'errors': errors, 'derived_sha256': dsha, 'changed_channels': sorted(changed),
            'report': report, 'audit': audit, 'report_sha256': sha(report_path), 'audit_sha256': sha(audit_path), 'glb': glb}


def manifest(result):
    r, a = result['report'], result['audit']
    s, h = a['summary']['all_frames'], a['summary']['hold_window']
    return {
        'schema': 'sub01.phone-grip-review-packet.v1', 'purpose': 'native VISUAL review only', 'ready': False, 'verified': False,
        'gates': {'native_import': False, 'native_contact': False, 'visual_acceptance': False, 'activity_binding': False},
        'label': 'derived_from_capture', 'original_capture_invariance': 'NOT APPLICABLE (derived)',
        'files': {'derived_glb': {'path': str(result['glb'].relative_to(ROOT)), 'sha256': result['derived_sha256']},
                  'report': {'path': 'docs/proposed/phone-grip-derived/SUB01_PhoneGrip_derived.report.json', 'sha256': result['report_sha256']},
                  'audit': {'path': 'docs/proposed/phone-grip-derived/SUB01_PhoneGrip_derived.audit.json', 'sha256': result['audit_sha256']},
                  'raw_capture_unchanged': {'path': str(SOURCE.relative_to(ROOT)), 'sha256': SOURCE_SHA256},
                  'owner': {'path': str(OWNER.relative_to(ROOT)), 'sha256': OWNER_SHA256, 'skin_joints': OWNER_JOINTS}},
        'contract': {'keys': KEYS, 'fps': 30, 'channels': CHANNELS, 'changed_rotation_channels': result['changed_channels'],
                     'bone_length_max_error_cm': r['bone_length_max_error_cm'], 'untouched_channels_byte_identical': True},
        'mount': {'frame': r['phone_mount']['frame'], 'gltf_right_hand_local': r['phone_mount']['gltf_right_hand_local'],
                  'phoneGripCandidate': r['phone_mount']['ue_phoneGripCandidate'],
                  'assembly': 'original five-part phone (tools/unreal_phone_grip_diagnostic.py PARTS), materials and live screen unchanged',
                  'wrist_correction': 'none at runtime: the RightHand correction is baked into the derived clip'},
        'taps': {'rule': r['thumb']['rule'], 'count': r['thumb']['tap_count'], 'events': r['thumb']['tap_events'],
                 'audit_glass_events': len(a['summary']['thumb_glass_events'])},
        'audit_summary': {'all_frames': {g: s[g] for g in ('fingers_palm', 'thumb', 'forearm', 'body')} | {'frames_supported': s['frames_supported']},
                          'hold_window': {g: h[g]['max_depth_cm'] for g in ('fingers_palm', 'thumb', 'forearm', 'body')} |
                          {'screen_to_eye_angle_deg': h['screen_to_eye_angle_deg'], 'screen_upright_deg': h['screen_upright_deg'],
                           'screen_visible_fraction_min_mean': h['screen_visible_fraction_min_mean']}},
        'known_open_items': ['fingers/palm (thenar) skin exceeds the 0.15 cm compression band on some unsampled frames (see audit)',
                             'palm carries little: finger-pads-behind + thumb-in-front hold, not a full palm cradle',
                             'native import, contact, visual acceptance and activity binding are not done'],
        'native_review_steps_server_only': [
            'python tools/phone_grip_packet.py check',
            'node tools/uncompress_unreal_glb.mjs web/room/char_mixamo.glb OWNER.glb',
            'node tools/merge_unreal_skin_clips.mjs OWNER.glb MERGED.glb docs/proposed/phone-grip-derived/SUB01_PhoneGrip_derived.glb',
            'blender -b --python tools/export_unreal_phone_grip_fbx.py -- MERGED.glb <project>/SourceAssets/PhoneFBX',
            'import <project>/SourceAssets/PhoneFBX/PhoneGrip.fbx onto the EXISTING owner USkeleton with root\'s import tooling (e.g. a phone copy of unreal_import_gaming_grip.py); never replace the original SUB01_Phone asset',
            'review with the existing private phone grip diagnostic: Phone role, the derived clip, -Sub01PhoneMountCm/-Sub01PhoneMountEuler from phoneGripCandidate, no -Sub01PhoneWristCorrection',
            'judge actual first-person hand + live screen pixels; readiness stays false until root\'s native proof']}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('action', choices=('check', 'write'))
    ap.add_argument('--dir', type=Path, default=DIR)
    args = ap.parse_args(argv)
    result = check(args.dir)
    print(json.dumps({k: result[k] for k in ('ok', 'errors', 'derived_sha256', 'changed_channels')}, indent=1))
    if not result['ok']:
        return 1
    if args.action == 'write':
        (args.dir/'packet.json').write_text(json.dumps(manifest(result), indent=1)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
