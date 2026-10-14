"""Offline evaluation of NATIVE support-contact captures into the evidence/proof files the native adapters read.

    python3 tools/native_support_contact_evidence.py bed  <project> CAPTURE.json
    python3 tools/native_support_contact_evidence.py sofa <project> CAPTURE.json [--grip GRIP.json]
    python3 tools/native_support_contact_evidence.py grip <project> CAPTURE.json
    python3 tools/native_support_contact_evidence.py check CAPTURE.json        # schema/coverage only, writes nothing

Captures are produced on the server by tools/unreal_native_support_capture.py (the imported clips evaluated on the
actual owner mesh by the renderer's native AnalyzeCapturedSeatSkin / the additive AnalyzeCapturedControllerGrip).
This file only reads those observations; it never creates one. Each command ALWAYS writes an evaluation record
(private-audit/native-<kind>-contact-evaluation.json, accepted true/false, every refusal) and writes the adapter's
input ONLY when the observations exist and every gate passes:

  bed  -> private-audit/native-life-bed-evidence.json   (tools/unreal_life_clips_runtime.py validate_bed / the C++
          LoadLifeClips: schema sub01.native-life-bed-evidence.v1, bed_revision = life_id(native-bed-surface.json
          text), approach_cm [x, y], yaw_deg, accepted)
  sofa -> private-audit/native-sofa-contact.json + native-sofa-placement.json   (the SOFA_CONTACT / PLACEMENT inputs
          of `unreal_controller_play_runtime.py evidence`; with --grip it also runs that command's write_evidence)
  grip -> private-audit/native-controller-play-runtime-proof.json   (validate_runtime_proof / the C++
          LoadControllerPlay: schema, accepted, clip_object_path, evidence_revision = play_id(evidence text),
          frames_measured >= 152, frames_passing == frames_measured, max_penetration_cm >= -0.3, native_capture.sha256)

Gates (constants imported, none invented):
  * seat rule of tools/validate_unreal_seat_contact.py: SEAT_BAND_CM (-2.5..+0.5), MIN_PATCH_VERTICES,
    MIN_SUPPORT_VERTICES; coverage >= 30 Hz over the whole clip (unreal_controller_play_runtime.validate_sofa_contact);
  * bed: non-penetration of every seat-band region over the mattress in every LieDown/SleepLoop/GetUp sample; the
    buttocks (Hips-dominant downward skin) is a local support patch on the mattress in every SleepLoop sample, the
    last LieDown sample and the first GetUp sample. Posterior thighs and soles are reported, not gated (knees may be
    up while lying, as tools/fit_bed_placement.py INFO_PATCHES; the soles stand on the floor only at the ends);
  * sofa: unreal_controller_play_runtime.validate_sofa_contact itself (buttocks, both thighs, both soles);
  * grip: tools/fit_controller_grip.py PALM_BAND_CM (-0.3..+0.3), PENETRATION_LIMIT_CM, MIN_SUPPORT_VERTICES per
    palm per frame, and no hand vertex deeper than the limit. The thumb/index feature gates of the derived-clip
    report are NOT measured natively; the proof says so.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_unreal_seat_contact as seat  # noqa: E402  (read-only: bands and patch minimums)
import unreal_life_clips_runtime as life  # noqa: E402  (read-only: life_id, mattress reader, BED_ROLES)
import unreal_controller_play_runtime as controller  # noqa: E402  (read-only: play_id, gates, file names)

CAPTURE_SCHEMA = 'sub01.native-support-contact-capture.v1'
EVALUATION_SCHEMA = 'sub01.native-support-contact-evaluation.v1'
NATIVE_OBSERVATIONS = ('native_editor_clip_evaluation', 'native_live_capture')
SEAT_ANALYZER = 'USub01HomeHandsInstance::AnalyzeCapturedSeatSkin'
GRIP_ANALYZER = 'USub01HomeHandsInstance::AnalyzeCapturedControllerGrip'
MIN_RATE_HZ = 30                     # unreal_controller_play_runtime.validate_sofa_contact: int(duration * 30) samples
BED_EVIDENCE_SCHEMA = 'sub01.native-life-bed-evidence.v1'
BED_EVIDENCE = 'native-life-bed-evidence.json'
BED_SURFACE = 'native-bed-surface.json'
SOFA_CONTACT = 'native-sofa-contact.json'
SOFA_PLACEMENT = 'native-sofa-placement.json'
BED_SUPPORT_REGION = 'buttocks'
BED_REPORTED_REGIONS = ('left_posterior_thigh', 'right_posterior_thigh', 'left_sole', 'right_sole')
SIDES = ('left', 'right')
GRIP_KEYS = ('palmVertices', 'palmNearVertices', 'palmBandVertices', 'palmMinGapCm', 'handVertices', 'handNearVertices',
             'handPenetratingVertices', 'handMinSignedCm')


class Refused(ValueError):
    pass


def _finite(*values):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ capture checks (shared)
def check_capture(capture: dict, kind: str) -> None:
    """Schema, kind, a NATIVE observation by the expected analyzer, and at least one sample. Raises Refused."""
    if not isinstance(capture, dict) or capture.get('schema') != CAPTURE_SCHEMA:
        raise Refused('NoObservations: not a native support-contact capture')
    if capture.get('kind') != kind:
        raise Refused(f'NoObservations: capture kind {capture.get("kind")!r} is not {kind!r}')
    if capture.get('observation') not in NATIVE_OBSERVATIONS:
        raise Refused('NoObservations: the capture is not a native observation (editor clip evaluation or live capture)')
    want = GRIP_ANALYZER if kind == 'controller_grip' else SEAT_ANALYZER
    if capture.get('analyzer') != want:
        raise Refused(f'NoObservations: analyzer must be {want}')
    if not capture.get('samples'):
        raise Refused('NoObservations: the capture holds no native samples')
    if capture.get('errors'):
        raise Refused('NoObservations: the capture recorded errors: ' + '; '.join(map(str, capture['errors']))[:400])


def clip_rows(capture: dict, role: str):
    """(clip, rows) for one role: rows in time order covering the whole clip at >= MIN_RATE_HZ."""
    clips = [c for c in capture.get('clips', []) if c.get('role') == role]
    if len(clips) != 1:
        raise Refused(f'CoverageIncomplete: expected one {role} clip record, got {len(clips)}')
    clip = clips[0]
    duration = clip.get('duration_s')
    if not _finite(duration) or duration <= 0:
        raise Refused(f'CoverageIncomplete: {role} duration must be a positive measured number')
    rows = [r for r in capture['samples'] if r.get('role') == role]
    if len(rows) < int(duration * MIN_RATE_HZ):
        raise Refused(f'CoverageIncomplete: {role} has {len(rows)} samples < {int(duration * MIN_RATE_HZ)} (>= {MIN_RATE_HZ} Hz over {duration:.4f} s)')
    times = [r.get('time') for r in rows]
    if not all(_finite(t) for t in times) or any(b <= a for a, b in zip(times, times[1:])) \
            or times[0] < -1e-6 or times[-1] > duration + 1e-6:
        raise Refused(f'CoverageIncomplete: {role} sample times are not increasing within the clip')
    if times[0] > 1.0 / MIN_RATE_HZ + 1e-6 or duration - times[-1] > 1.0 / MIN_RATE_HZ + 1e-6:
        raise Refused(f'CoverageIncomplete: {role} samples do not reach both ends of the clip')
    return clip, rows


def seat_regions(row: dict) -> dict:
    """The analyzer row's five regions (exactly), every metric finite, influences valid. Raises Refused."""
    if 'error' in row:
        raise Refused(f'AnalyzerError: {row["error"]} at {row.get("time")}')
    if row.get('invalidInfluences') != 0:
        raise Refused(f'InvalidInfluences at {row.get("time")}')
    regions = {r.get('region'): r for r in row.get('regions', [])}
    if set(regions) != set(seat.REGIONS) or len(row.get('regions', [])) != len(seat.REGIONS):
        raise Refused(f'CoverageIncomplete: buttocks, both posterior thighs and both soles required at {row.get("time")}')
    for r in regions.values():
        for key in ('selectedVertices', 'facingVertices', 'overSurfaceVertices', 'bandVertices', 'minGapCm', 'p50GapCm'):
            if not _finite(r.get(key)):
                raise Refused(f'NonfiniteMetric: {r.get("region")}.{key} at {row.get("time")}')
    return regions


def support_patch(r: dict, name: str):
    """validate_unreal_seat_contact's local-support-patch rule for one region row; returns the refusal or None."""
    low, high = seat.band(name)
    if r['overSurfaceVertices'] < seat.MIN_PATCH_VERTICES:
        return f'{name}: only {r["overSurfaceVertices"]} downward-facing vertices over the surface'
    if r['minGapCm'] < low:
        return f'{name}: penetration {r["minGapCm"]:.3f} cm below {low} cm'
    if r['minGapCm'] > high or r['bandVertices'] < seat.MIN_SUPPORT_VERTICES:
        return f'{name}: no support patch (lowest {r["minGapCm"]:.3f} cm, {r["bandVertices"]} vertices within {low}..{high} cm)'
    return None


def _worst(acc: dict, name: str, r: dict):
    w = acc.setdefault(name, {'min_gap_cm': math.inf, 'max_p50_gap_cm': -math.inf, 'min_band_vertices': math.inf,
                              'min_over_surface_vertices': math.inf})
    if r['overSurfaceVertices'] > 0:
        w['min_gap_cm'] = min(w['min_gap_cm'], r['minGapCm'])
        w['max_p50_gap_cm'] = max(w['max_p50_gap_cm'], r['p50GapCm'])
    w['min_band_vertices'] = min(w['min_band_vertices'], r['bandVertices'])
    w['min_over_surface_vertices'] = min(w['min_over_surface_vertices'], r['overSurfaceVertices'])


def _clean(obj):
    """JSON-safe (inf -> None)."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


# ------------------------------------------------------------------ bed
def evaluate_bed(bed_text: str, capture: dict, capture_sha256: str = '') -> dict:
    """Gate a native bed capture against THIS bed report. Returns the evidence dict; raises Refused."""
    check_capture(capture, 'bed')
    bed = json.loads(bed_text)
    tris = life.mattress_triangles(bed)                       # BedUnmeasured on errors / no triangles
    area = life.mattress_area_cm2(tris)
    if area < life.MIN_MATTRESS_AREA_CM2:
        raise Refused(f'BedUnmeasured: mattress area {area:.0f} cm2 is not a bed')
    revision = str(life.life_id(bed_text))
    if str(capture.get('surface_report', {}).get('revision')) != revision:
        raise Refused('BedRevisionMismatch: the capture was measured against another native-bed-surface.json')
    placement = capture.get('placement', {})
    approach, yaw = placement.get('approach_cm'), placement.get('yaw_deg')
    if not (isinstance(approach, list) and len(approach) == 2 and _finite(*approach, yaw)):
        raise Refused('BedPlacementMissing: approach_cm [x, y] and yaw_deg must be finite measured numbers')
    worst, failures, rows_checked = {}, [], 0
    by_role = {}
    for role in life.BED_ROLES:
        clip, rows = clip_rows(capture, role)
        by_role[role] = rows
        for row in rows:
            regions = seat_regions(row)
            rows_checked += 1
            for name in seat.SEAT_REGIONS:                     # non-penetration wherever skin is over the mattress
                r = regions[name]
                _worst(worst, name, r)
                if r['overSurfaceVertices'] > 0 and r['minGapCm'] < seat.SEAT_BAND_CM[0]:
                    failures.append(f'{role} t={row["time"]:.4f}: {name} penetrates {r["minGapCm"]:.3f} cm below {seat.SEAT_BAND_CM[0]} cm')
            for name in seat.SOLE_REGIONS:
                _worst(worst, name, regions[name])
    supported = [('SleepLoop', r) for r in by_role['SleepLoop']] + [('LieDown', by_role['LieDown'][-1]), ('GetUp', by_role['GetUp'][0])]
    for role, row in supported:
        why = support_patch(seat_regions(row)[BED_SUPPORT_REGION], BED_SUPPORT_REGION)
        if why:
            failures.append(f'{role} t={row["time"]:.4f}: {why}')
    if failures:
        raise Refused(f'BedContactFailed: {len(failures)} failing observations; first: ' + '; '.join(failures[:5]))
    return _clean({'schema': BED_EVIDENCE_SCHEMA, 'bed_revision': revision, 'approach_cm': approach, 'yaw_deg': yaw,
                   'accepted': True, 'observation': capture['observation'], 'analyzer': capture['analyzer'],
                   'capture_sha256': capture_sha256, 'mattress_area_cm2': round(area, 3), 'samples': rows_checked,
                   'gates': {'non_penetration': 'every seat-band region over the mattress, every sample, >= %.1f cm' % seat.SEAT_BAND_CM[0],
                             'support': 'buttocks local support patch (%s cm, >= %d vertices) in every SleepLoop sample, last LieDown, first GetUp'
                                        % (seat.SEAT_BAND_CM, seat.MIN_SUPPORT_VERTICES),
                             'reported_not_gated': list(BED_REPORTED_REGIONS)},
                   'worst': worst, 'placement': placement,
                   'not_verified': ['first-person visual review', 'duvet handling while asleep', 'capsule return sweep (root motion)'],
                   'native_bed_verified': False})


# ------------------------------------------------------------------ sofa
def evaluate_sofa(sofa_text: str, capture: dict, capture_sha256: str = ''):
    """Gate a native sofa capture against THIS sofa report. Returns (contact, placement); raises Refused."""
    check_capture(capture, 'sofa')
    sofa = json.loads(sofa_text)
    _, area = controller.sofa_seat_triangles(sofa)            # SofaUnmeasured on errors / small seat
    if str(capture.get('surface_report', {}).get('revision')) != str(controller.play_id(sofa_text)):
        raise Refused('SofaRevisionMismatch: the capture was measured against another native-sofa-surface.json')
    clip, rows = clip_rows(capture, controller.ROLE)
    if clip.get('object_path') != controller.CLIP_OBJECT_PATH:
        raise Refused(f'ClipMismatch: sofa contact must play {controller.CLIP_OBJECT_PATH}')
    for row in rows:
        seat_regions(row)
    contact = {'schema': 'sub01.native-sofa-contact.v1', 'clip_duration_s': clip['duration_s'], 'clip_object_path': clip['object_path'],
               'observation': capture['observation'], 'analyzer': capture['analyzer'], 'capture_sha256': capture_sha256,
               'sofa_revision': str(controller.play_id(sofa_text)), 'floor_cm': capture.get('floor_cm'),
               'samples': [{'time': r['time'], 'invalidInfluences': r['invalidInfluences'], 'regions': r['regions']} for r in rows]}
    try:
        gate = controller.validate_sofa_contact(contact)       # the controller adapter's own gate, unchanged
    except (ValueError, KeyError, TypeError) as error:
        raise Refused(f'SofaContactFailed: {error}') from error
    contact['gate'] = _clean(gate)
    p = capture.get('placement', {})
    bounds = sofa.get('sofa', {}).get('component_world_bounds_cm', {})
    if not (isinstance(bounds.get('min'), list) and isinstance(bounds.get('max'), list) and _finite(*bounds['min'][:2], *bounds['max'][:2])):
        raise Refused('PlacementMissing: the native sofa report has no measured component_world_bounds_cm footprint')
    placement = {'approach_cm': p.get('approach_cm'), 'yaw_deg': p.get('yaw_deg'), 'body_offset_cm': p.get('body_offset_cm'),
                 'body_yaw_deg': p.get('body_yaw_deg'),
                 'sofa_footprint_cm': {'min': bounds['min'][:2], 'max': bounds['max'][:2]},
                 'footprint_basis': 'native-sofa-surface.json sofa.component_world_bounds_cm (measured component bounds)',
                 'capture_sha256': capture_sha256}
    a, body = placement['approach_cm'], placement['body_offset_cm']
    if not (isinstance(a, list) and len(a) == 2 and isinstance(body, list) and len(body) == 3
            and _finite(*a, *body, placement['yaw_deg'], placement['body_yaw_deg'])):
        raise Refused('PlacementMissing: approach/yaw/body offset/body yaw must be finite measured numbers')
    clearance = controller.capsule_clearance(a, placement['sofa_footprint_cm']['min'], placement['sofa_footprint_cm']['max'])
    if clearance <= 0:
        raise Refused(f'CapsuleInsideSofa: standing capsule overlaps the measured footprint by {-clearance:.2f} cm')
    placement['capsule_clearance_cm'] = clearance
    contact['seat_area_cm2'] = area
    return contact, placement


# ------------------------------------------------------------------ controller grip (runtime proof)
def evaluate_grip(evidence_text: str, capture: dict, capture_rel: str, capture_sha256: str) -> dict:
    """Gate a native per-frame grip capture against THIS accepted controller evidence. Returns the proof; raises Refused."""
    import fit_controller_grip as fit   # lazy: numpy-backed module, never imported inside the editor
    check_capture(capture, 'controller_grip')
    ev = json.loads(evidence_text)
    if ev.get('schema') != controller.EVIDENCE_SCHEMA or ev.get('accepted') is not True:
        raise Refused('EvidenceMissing: the controller play evidence is not accepted')
    revision = str(controller.play_id(evidence_text))
    if str(capture.get('evidence_revision')) != revision:
        raise Refused('EvidenceRevisionMismatch: the capture used another controller evidence')
    clip = (capture.get('clips') or [{}])[0]
    if clip.get('object_path') != controller.CLIP_OBJECT_PATH or len(capture.get('clips', [])) != 1:
        raise Refused(f'ClipMismatch: the grip capture must play exactly {controller.CLIP_OBJECT_PATH}')
    rows = capture['samples']
    frames = [r.get('frame') for r in rows]
    if len(set(frames)) != len(frames) or not all(isinstance(f, int) for f in frames) or len(rows) < controller.CLIP_FRAMES:
        raise Refused(f'CoverageIncomplete: {len(rows)} distinct native frames < {controller.CLIP_FRAMES}')
    low, high = fit.PALM_BAND_CM
    limit = fit.PENETRATION_LIMIT_CM
    passing, deepest, failures, worst = 0, math.inf, [], {}
    for row in rows:
        if 'error' in row or row.get('invalidInfluences') != 0:
            raise Refused(f'AnalyzerError: frame {row.get("frame")}: {row.get("error", "invalid influences")}')
        hands = {h.get('side'): h for h in row.get('hands', [])}
        if set(hands) != set(SIDES) or len(row.get('hands', [])) != 2:
            raise Refused(f'CoverageIncomplete: both hands required at frame {row.get("frame")}')
        ok = True
        for side, h in hands.items():
            if not _finite(*(h.get(k) for k in GRIP_KEYS)):
                raise Refused(f'NonfiniteMetric: {side} hand at frame {row.get("frame")}')
            deepest = min(deepest, h['handMinSignedCm'])
            w = worst.setdefault(side, {'min_palm_gap_cm': math.inf, 'max_palm_gap_cm': -math.inf, 'min_palm_band_vertices': math.inf,
                                        'min_hand_signed_cm': math.inf, 'max_penetrating_vertices': 0})
            w['min_palm_gap_cm'] = min(w['min_palm_gap_cm'], h['palmMinGapCm'])
            w['max_palm_gap_cm'] = max(w['max_palm_gap_cm'], h['palmMinGapCm'])
            w['min_palm_band_vertices'] = min(w['min_palm_band_vertices'], h['palmBandVertices'])
            w['min_hand_signed_cm'] = min(w['min_hand_signed_cm'], h['handMinSignedCm'])
            w['max_penetrating_vertices'] = max(w['max_penetrating_vertices'], h['handPenetratingVertices'])
            why = None
            if h['palmMinGapCm'] < low or h['palmMinGapCm'] > high or h['palmBandVertices'] < fit.MIN_SUPPORT_VERTICES:
                why = f'{side} palm: lowest {h["palmMinGapCm"]:.3f} cm, {h["palmBandVertices"]} vertices within {low}..{high} cm'
            elif h['handMinSignedCm'] < limit or h['handPenetratingVertices'] > 0:
                why = f'{side} hand penetrates {h["handMinSignedCm"]:.3f} cm ({h["handPenetratingVertices"]} vertices beyond {limit} cm)'
            if why:
                ok = False
                failures.append(f'frame {row["frame"]}: {why}')
        passing += ok
    proof = {'schema': controller.RUNTIME_PROOF_SCHEMA, 'accepted': passing == len(rows), 'clip_object_path': controller.CLIP_OBJECT_PATH,
             'evidence_revision': revision, 'frames_measured': len(rows), 'frames_passing': passing,
             'max_penetration_cm': min(0.0, deepest), 'native_capture': {'path': capture_rel, 'sha256': capture_sha256},
             'observation': capture['observation'], 'analyzer': capture['analyzer'], 'worst': _clean(worst),
             'gates': {'palm_band_cm': [low, high], 'min_support_vertices': fit.MIN_SUPPORT_VERTICES, 'penetration_limit_cm': limit},
             'not_measured_natively': ['thumb/index feature gates of the derived-clip report', 'first-person visual review',
                                       'live Minecraft input correlation'],
             'verified': False}
    if not proof['accepted']:
        raise Refused(f'GripContactFailed: {passing}/{len(rows)} native frames pass; first: ' + '; '.join(failures[:5]))
    return proof


# ------------------------------------------------------------------ writers (evaluation always, evidence only on pass)
def _rel(project: Path, path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(project).resolve()))
    except ValueError:
        return str(Path(path).resolve())


def _record(audit: Path, kind: str, capture_path: Path, sha: str, accepted: bool, error: str = '', written=(), extra=None) -> Path:
    out = audit / f'native-{kind}-contact-evaluation.json'
    doc = {'schema': EVALUATION_SCHEMA, 'kind': kind, 'capture': str(capture_path), 'capture_sha256': sha, 'accepted': accepted,
           'ready': accepted, 'error': error, 'written': list(written), **(extra or {})}
    out.write_text(json.dumps(_clean(doc), indent=2) + '\n')
    return out


def _load_capture(capture_path: Path):
    raw = Path(capture_path).read_bytes()
    return json.loads(raw), sha256_bytes(raw)


def write_bed(project: Path, capture_path: Path) -> dict:
    audit = Path(project) / 'private-audit'
    audit.mkdir(parents=True, exist_ok=True)
    capture, sha = _load_capture(capture_path)
    target = audit / BED_EVIDENCE
    try:
        surface = audit / BED_SURFACE
        if not surface.is_file():
            raise Refused(f'BedUnmeasured: {surface} does not exist (run tools/unreal_bed_surface_audit.py first)')
        evidence = evaluate_bed(surface.read_text(), capture, sha)
        life.validate_bed(surface.read_text(), evidence)          # the adapter's own reader accepts it
    except (Refused, ValueError, KeyError, TypeError) as error:
        stale = target.is_file()
        _record(audit, 'bed', capture_path, sha, False, str(error),
                extra={'existing_evidence_untouched': stale} if stale else None)
        return {'accepted': False, 'error': str(error)}
    target.write_text(json.dumps(evidence, indent=2) + '\n')
    _record(audit, 'bed', capture_path, sha, True, written=[str(target)])
    return {'accepted': True, 'written': [str(target)]}


def write_sofa(project: Path, capture_path: Path, grip_path: Path | None = None) -> dict:
    audit = Path(project) / 'private-audit'
    audit.mkdir(parents=True, exist_ok=True)
    capture, sha = _load_capture(capture_path)
    try:
        surface = audit / controller.SOFA_REPORT
        if not surface.is_file():
            raise Refused(f'SofaUnmeasured: {surface} does not exist (run tools/unreal_sofa_surface_audit.py first)')
        contact, placement = evaluate_sofa(surface.read_text(), capture, sha)
    except (Refused, ValueError, KeyError, TypeError) as error:
        _record(audit, 'sofa', capture_path, sha, False, str(error))
        return {'accepted': False, 'error': str(error)}
    written = []
    for name, doc in ((SOFA_CONTACT, contact), (SOFA_PLACEMENT, placement)):
        (audit / name).write_text(json.dumps(_clean(doc), indent=2) + '\n')
        written.append(str(audit / name))
    result = {'accepted': True, 'written': written}
    if grip_path:
        try:
            written.append(str(controller.write_evidence(project, grip_path, audit / SOFA_CONTACT, audit / SOFA_PLACEMENT)))
        except (ValueError, KeyError, TypeError) as error:
            result['controller_evidence_refused'] = str(error)
    _record(audit, 'sofa', capture_path, sha, True, written=written,
            extra={'controller_evidence_refused': result.get('controller_evidence_refused')} if grip_path else None)
    return result


def write_grip(project: Path, capture_path: Path) -> dict:
    audit = Path(project) / 'private-audit'
    audit.mkdir(parents=True, exist_ok=True)
    capture, sha = _load_capture(capture_path)
    target = audit / controller.RUNTIME_PROOF
    try:
        evidence = audit / controller.EVIDENCE
        if not evidence.is_file():
            raise Refused(f'EvidenceMissing: {evidence} does not exist')
        text = evidence.read_text()
        proof = evaluate_grip(text, capture, _rel(project, capture_path), sha)
        proof_text = json.dumps(proof, indent=2) + '\n'
        controller.validate_runtime_proof(proof_text, text)          # the adapter's own reader accepts it
    except (Refused, ValueError, KeyError, TypeError) as error:
        _record(audit, 'controller-grip', capture_path, sha, False, str(error))
        return {'accepted': False, 'error': str(error)}
    target.write_text(proof_text)
    _record(audit, 'controller-grip', capture_path, sha, True, written=[str(target)])
    return {'accepted': True, 'written': [str(target)]}


def check(capture: dict) -> dict:
    kind = capture.get('kind')
    check_capture(capture, kind)
    if kind == 'bed':
        return {r: len(clip_rows(capture, r)[1]) for r in life.BED_ROLES}
    if kind == 'sofa':
        return {controller.ROLE: len(clip_rows(capture, controller.ROLE)[1])}
    return {'frames': len(capture['samples'])}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    for name in ('bed', 'sofa', 'grip'):
        s = sub.add_parser(name)
        s.add_argument('project', type=Path)
        s.add_argument('capture', type=Path)
        if name == 'sofa':
            s.add_argument('--grip', type=Path)
    c = sub.add_parser('check')
    c.add_argument('capture', type=Path)
    a = p.parse_args(argv)
    if a.cmd == 'check':
        try:
            result = {'ok': True, 'coverage': check(json.loads(a.capture.read_text()))}
        except Refused as error:
            result = {'ok': False, 'error': str(error)}
        print(json.dumps(result, indent=2))
        return 0 if result['ok'] else 3
    fn = {'bed': write_bed, 'grip': write_grip}.get(a.cmd)
    result = fn(a.project, a.capture) if fn else write_sofa(a.project, a.capture, a.grip)
    print(json.dumps(result, indent=2))
    return 0 if result['accepted'] else 3


if __name__ == '__main__':
    sys.exit(main())
