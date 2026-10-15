"""Controller play on the sofa, minimal closure for CURRENT origin/main (Python gates only; private; source only).

Depends only on files that exist unchanged on origin/main plus files that are NEW there:
  - tools/controller_clip_contract.py        (main, unchanged)  the four pinned Gaming clip constants;
  - tools/validate_unreal_seat_contact.py    (main, unchanged)  bands, regions and patch rule (median + 50% coverage);
  - tools/unreal_controller_play_runtime.py  (new on main)      the native C++ fragment and its additive install().

It never imports tools/fit_controller_grip.py, never uses a branch-only constant of the seat validator and never
edits the seat validator's rules. The runtime module's own `evidence` CLI uses the branch seat validator's
MIN_SUPPORT_VERTICES; on main that attribute does not exist, so that CLI fails closed (AttributeError, no evidence
written). Use THIS module's `evidence` command instead.

Sofa contact gate (controller-owned, applied per region and per sample over the whole captured Gaming clip):
  1. main's rule unchanged, the same comparisons validate_unreal_seat_contact.validate() makes: patch over its
     surface >= MIN_PATCH_VERTICES, deepest point >= the band's lower edge (no penetration beyond the cushion's
     compression / no sole below the floor), MEDIAN gap <= the band's upper edge and >= MIN_BAND_COVERAGE (50%) of
     the patch inside the band. Soles included: nothing is relaxed for a raised heel;
  2. AND a local support patch: >= SUPPORT_MIN_VERTICES vertices inside the band. SUPPORT_MIN_VERTICES reuses main's
     MIN_PATCH_VERTICES (12): a contact patch must itself be at least as large as the smallest patch main accepts
     over a surface, so a few grazing vertices of a large patch never count as support. This is an ADDITIONAL
     per-patch requirement; it never replaces the median/coverage rule and is never applied as whole-seat validation.
Every row must also carry main's full metric set (selected/facing/over/band vertices, min/p10/p50/p90/max gap).

Nothing here writes config except `config`, which writes `+ValidatedHandsPostures=Gaming` ONLY when accepted
evidence for THIS sofa report and the exact derived-clip import row exist. The installer never writes it, and the
native ControllerPlayReady() additionally needs root's native runtime proof (native-controller-play-runtime-proof.json).

    python3 tools/controller_play_minimal.py evidence <UE project> GRIP.json SOFA_CONTACT.json PLACEMENT.json
    python3 tools/controller_play_minimal.py config   <UE project> IMPORT_REPORT.json OUT.ini
    python3 tools/controller_play_minimal.py status   <UE project>
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller_clip_contract as contract  # noqa: E402
import validate_unreal_seat_contact as seat_contact  # noqa: E402
import unreal_controller_play_runtime as runtime  # noqa: E402

PINS = ('ROLE', 'CLIP_OBJECT_PATH', 'CLIP_FRAMES', 'GAMING_FBX_SHA256')
for _pin in PINS:
    if getattr(runtime, _pin) != getattr(contract, _pin):
        raise ImportError(f'controller runtime {_pin} differs from tools/controller_clip_contract.py')
ROLE, CLIP_OBJECT_PATH, CLIP_FRAMES, GAMING_FBX_SHA256 = (getattr(contract, p) for p in PINS)

SUPPORT_MIN_VERTICES = seat_contact.MIN_PATCH_VERTICES
METRICS = ('selectedVertices', 'facingVertices', 'overSurfaceVertices', 'bandVertices',
           'minGapCm', 'p10GapCm', 'p50GapCm', 'p90GapCm', 'maxGapCm')
MIN_RATE_HZ = 30


def _finite(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def check_region(name: str, r: dict, time) -> dict:
    """One patch at one sample: main's rule unchanged AND the local support patch. Raises ValueError."""
    if not all(_finite(r.get(k)) for k in METRICS):
        raise ValueError(f'SofaContactIncomplete: {name} lacks a finite {"/".join(METRICS)} at {time}')
    low, high = seat_contact.band(name)
    over = r['overSurfaceVertices']
    if over < seat_contact.MIN_PATCH_VERTICES:
        raise ValueError(f'{name}: only {over} downward-facing vertices over the surface at {time}')
    coverage = r['bandVertices'] / over
    if r['minGapCm'] < low:
        raise ValueError(f'{name}: penetration {r["minGapCm"]:.3f} cm below {low} cm at {time}')
    if r['p50GapCm'] > high or coverage < seat_contact.MIN_BAND_COVERAGE:
        raise ValueError(f'{name}: gap, median {r["p50GapCm"]:.3f} cm, {coverage:.0%} of the patch in contact at {time}')
    if r['bandVertices'] < SUPPORT_MIN_VERTICES:
        raise ValueError(f'{name}: support patch of {r["bandVertices"]} vertices within {low}..{high} cm '
                         f'(< {SUPPORT_MIN_VERTICES}) at {time}')
    return {'coverage': coverage}


def validate_sofa_contact(data: dict) -> dict:
    """Whole captured Gaming clip at >= 30 Hz on the measured sofa seat and floor, every region every sample."""
    rows, duration = data.get('samples', []), data.get('clip_duration_s')
    if not _finite(duration) or duration <= 0 or not isinstance(rows, list) or len(rows) < int(duration * MIN_RATE_HZ):
        raise ValueError('SofaContactIncomplete: samples must cover the whole clip at >= 30 Hz')
    worst, last = {}, -math.inf
    for row in rows:
        t = row.get('time')
        if not _finite(t) or t <= last or t < 0 or t > duration + 1e-6:
            raise ValueError('SofaContactIncomplete: sample times must be finite, increasing and inside the clip')
        last = t
        if row.get('invalidInfluences') != 0:
            raise ValueError('SofaContactIncomplete: invalid imported skin influences')
        regions = {r.get('region'): r for r in row.get('regions', [])}
        if set(regions) != set(seat_contact.REGIONS) or len(row.get('regions', [])) != len(seat_contact.REGIONS):
            raise ValueError('SofaContactIncomplete: buttocks, both posterior thighs and both soles required')
        for name in seat_contact.REGIONS:
            r = regions[name]
            c = check_region(name, r, t)
            w = worst.setdefault(name, {'min_gap_cm': math.inf, 'max_median_gap_cm': -math.inf, 'min_coverage': 1.,
                                        'min_band_vertices': math.inf})
            w['min_gap_cm'] = min(w['min_gap_cm'], r['minGapCm'])
            w['max_median_gap_cm'] = max(w['max_median_gap_cm'], r['p50GapCm'])
            w['min_coverage'] = min(w['min_coverage'], c['coverage'])
            w['min_band_vertices'] = min(w['min_band_vertices'], r['bandVertices'])
    interval = 1. / MIN_RATE_HZ + 1e-6
    times = [r['time'] for r in rows]
    if (times[0] > interval or duration-times[-1] > interval
            or any(b-a > interval for a, b in zip(times, times[1:]))):
        raise ValueError('SofaContactIncomplete: unmeasured clip interval exceeds 1/30 s')
    return {'samples': len(rows), 'worst': worst, 'passed': True,
            'rule': 'main validate_unreal_seat_contact patch rule (median + 50% coverage) AND >= '
                    f'{SUPPORT_MIN_VERTICES} band vertices per patch'}


def validate_grip(report: dict) -> dict:
    """Only the DERIVED grip clip report (the clip the native side plays); raw fits/searches are refused."""
    if report.get('schema') != runtime.DERIVED_SCHEMA:
        raise ValueError('GripUnmeasured: native play needs the derived grip clip report')
    return runtime.validate_derived(report)


def build_evidence(sofa_text: str, grip: dict, contact: dict, placement: dict) -> dict:
    """Same evidence schema the native loader reads; `accepted` only from the gates above."""
    sofa = json.loads(sofa_text)
    _, area = runtime.sofa_seat_triangles(sofa)
    g = validate_grip(grip)
    c = validate_sofa_contact(contact)
    a, yaw, body, body_yaw = (placement.get(k) for k in ('approach_cm', 'yaw_deg', 'body_offset_cm', 'body_yaw_deg'))
    fp = placement.get('sofa_footprint_cm', {})
    if not (isinstance(a, list) and len(a) == 2 and isinstance(body, list) and len(body) == 3
            and all(_finite(v) for v in (*a, *body, yaw, body_yaw))
            and isinstance(fp.get('min'), list) and isinstance(fp.get('max'), list) and len(fp['min']) == 2
            and len(fp['max']) == 2 and all(_finite(v) for v in (*fp['min'], *fp['max']))):
        raise ValueError('PlacementMissing: approach/yaw/body offset/footprint must be finite measured numbers')
    clearance = runtime.capsule_clearance(a, fp['min'], fp['max'])
    if clearance <= 0:
        raise ValueError(f'CapsuleInsideSofa: standing capsule overlaps the sofa footprint by {-clearance:.2f} cm')
    t, q = runtime.ue_grip(g['controller_in_right_hand_gltf'])
    return {'schema': runtime.EVIDENCE_SCHEMA, 'clip_object_path': CLIP_OBJECT_PATH, 'grip_clip_sha256': g['grip_clip_sha256'],
            'label': runtime.DERIVED_LABEL, 'sofa_revision': str(runtime.play_id(sofa_text)), 'seat_area_cm2': area,
            'approach_cm': a, 'yaw_deg': yaw, 'body_offset_cm': body, 'body_yaw_deg': body_yaw,
            'capsule_clearance_cm': clearance, 'grip_offset_cm': t, 'grip_rotation_xyzw': q, 'grip_frames': g['frames'],
            'grip_report_sha256': hashlib.sha256(json.dumps(grip, sort_keys=True).encode()).hexdigest(),
            'seat_contact': c, 'time_mapping': 'native AnimSequence t = glTF key t - 1/30 s',
            'grip_gates_passed': True, 'seat_contact_passed': True, 'accepted': True, 'verified': False,
            'gate_module': 'tools/controller_play_minimal.py',
            'note': 'Measured gates passed; ControllerPlayReady() still needs the native runtime proof; visual review separate.'}


def write_evidence(project: Path, grip_path: Path, contact_path: Path, placement_path: Path) -> Path:
    audit = Path(project) / 'private-audit'
    sofa = audit / runtime.SOFA_REPORT
    if not sofa.is_file():
        raise ValueError(f'SofaUnmeasured: {sofa} does not exist (run the native sofa audit first)')
    ev = build_evidence(sofa.read_text(), json.loads(Path(grip_path).read_text()),
                        json.loads(Path(contact_path).read_text()), json.loads(Path(placement_path).read_text()))
    out = audit / runtime.EVIDENCE
    out.write_text(json.dumps(ev, indent=2) + '\n')
    return out


def config_fragment(project: Path, import_report: dict):
    return runtime.config_fragment(project, import_report)


def status(project: Path) -> dict:
    """What the native loader would find (mirror; read-only). ready is false unless every proof file passes."""
    audit = Path(project) / 'private-audit'
    out = {'sofa_report': (audit / runtime.SOFA_REPORT).is_file(), 'evidence': False, 'runtime_proof': False,
           'controller_asset_receipt': (audit / runtime.CONTROLLER_ASSET_RECEIPT).is_file(), 'refusals': {}}
    try:
        sofa_text, ev_text = (audit / runtime.SOFA_REPORT).read_text(), (audit / runtime.EVIDENCE).read_text()
        ev = json.loads(ev_text)
        out['evidence'] = (ev.get('schema') == runtime.EVIDENCE_SCHEMA and ev.get('accepted') is True
                           and ev.get('sofa_revision') == str(runtime.play_id(sofa_text)))
        runtime.validate_runtime_proof((audit / runtime.RUNTIME_PROOF).read_text(), ev_text)
        out['runtime_proof'] = True
    except (OSError, ValueError) as error:
        out['refusals']['proof'] = str(error)
    out['ready_python_mirror'] = bool(out['evidence'] and out['runtime_proof'] and out['controller_asset_receipt'])
    return out


def main(argv) -> int:
    if len(argv) == 5 and argv[0] == 'evidence':
        print(write_evidence(Path(argv[1]), Path(argv[2]), Path(argv[3]), Path(argv[4])))
        return 0
    if len(argv) == 4 and argv[0] == 'config':
        text, refusals = config_fragment(Path(argv[1]), json.loads(Path(argv[2]).read_text()))
        if text:
            Path(argv[3]).write_text(text)
        print(json.dumps({'written': bool(text), 'refusals': refusals}, indent=2))
        return 0 if text else 3
    if len(argv) == 2 and argv[0] == 'status':
        print(json.dumps(status(Path(argv[1])), indent=2))
        return 0
    raise SystemExit(__doc__)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
