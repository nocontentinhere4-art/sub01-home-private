"""Validate bounded native geometry snapshots; report bone-origin/AABB distances.

This tool does not acquire poses or correlate JPEGs, and cannot establish skin
contact or tuning completeness. It checks supplied acquisition metadata only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def vector(value):
    require(isinstance(value, list) and len(value) == 3, "XYZ must have three coordinates")
    require(all(type(v) in (int, float) and math.isfinite(v) for v in value), "non-finite XYZ")
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def analyse(document):
    require(document.get("schema") == "sub01.contact-geometry.v1", "unknown schema")
    require(document.get("geometry_only") is True, "geometry-only declaration required")
    require(document.get("jpeg_correlated") is False, "JPEG correlation is outside this protocol")
    require(document.get("overflow") is False, "overflow or missing overflow status")
    require(document.get("acquisition_complete") is True, "incomplete acquisition")
    samples = document.get("samples")
    require(isinstance(samples, list) and 0 < len(samples) <= 32, "sample budget exceeded or empty")
    require(sha(document.get("input_manifest_sha256")), "missing input manifest digest")
    require(sha(document.get("engine_build_manifest_sha256")), "missing engine build digest")
    seen_ids = set()
    previous_frame = previous_pose = -1
    results = []
    acquisition_identity = None
    for sample in samples:
        capture = sample.get("capture_id")
        require(isinstance(capture, str) and capture and capture not in seen_ids, "duplicate/missing capture ID")
        seen_ids.add(capture)
        frame, pose = sample.get("game_frame"), sample.get("pose_serial")
        require(integer(frame) and integer(pose, 1), "invalid frame/pose identity")
        require(frame > previous_frame and pose > previous_pose, "non-increasing frame/pose identity")
        require(sample.get("finalized_frame") == frame and sample.get("published_frame") == frame,
                "pose publication/finalization does not match capture tick")
        require(sample.get("finalized_pose_serial") == pose, "finalization serial mismatch")
        previous_frame, previous_pose = frame, pose
        require(sample.get("coordinate_space") == "world_cm", "world centimetres required")
        tuning = sample.get("effective_tuning")
        require(isinstance(tuning, dict) and tuning, "missing supplied tuning mapping")
        require(sample.get("effective_tuning_sha256") == digest(tuning), "effective tuning digest mismatch")
        require(sha(sample.get("source_tuning_sha256")), "missing source tuning digest")
        clip = sample.get("clip")
        require(isinstance(clip, dict) and isinstance(clip.get("path"), str) and clip["path"], "missing clip")
        require(sha(clip.get("package_sha256")) and sha(clip.get("evaluator_sha256")), "missing clip/evaluator revision")
        require(integer(clip.get("loop_count")) and integer(clip.get("replay_seed")), "missing loop count/replay seed")
        require(type(clip.get("seconds")) in (int, float) and math.isfinite(clip["seconds"]) and clip["seconds"] >= 0,
                "invalid evaluation time")
        identity = (sample["effective_tuning_sha256"], sample["source_tuning_sha256"],
                    clip["path"], clip["package_sha256"], clip["evaluator_sha256"], clip["replay_seed"])
        if acquisition_identity is None:
            acquisition_identity = identity
        require(identity == acquisition_identity, "immutable acquisition identity drift")
        bones, keys = sample.get("bones"), sample.get("keys")
        require(isinstance(bones, list) and 0 < len(bones) <= 32, "bone budget exceeded or empty")
        require(isinstance(keys, list) and 0 < len(keys) <= 128, "key budget exceeded or empty")
        require(len({b.get("name") for b in bones}) == len(bones), "duplicate bone")
        require(len({k.get("name") for k in keys}) == len(keys), "duplicate key component")
        required = document.get("required_bones")
        require(isinstance(required, list) and 0 < len(required) <= 32, "missing required bone manifest")
        require(set(required) == {b.get("name") for b in bones}, "missing or unexpected bone")
        tips = []
        for bone in bones:
            require(isinstance(bone.get("name"), str) and bone["name"], "invalid bone name")
            location = vector(bone.get("world_xyz"))
            if bone.get("role") == "terminal_finger":
                tips.append((bone["name"], location))
        require(len(tips) == 10, "ten actual configured terminal finger bones required")
        bounds = []
        for key in keys:
            require(isinstance(key.get("name"), str) and key["name"], "invalid key name")
            require(key.get("bounds_source") == "CalcBounds(GetComponentToWorld()).GetBox()", "nominal bounds refused")
            lo, hi = vector(key.get("world_aabb_min")), vector(key.get("world_aabb_max"))
            require(all(a <= b for a, b in zip(lo, hi)), "inverted bounds")
            bounds.append((key["name"], lo, hi))
        distances = []
        for name, point in tips:
            candidates = []
            for key_name, lo, hi in bounds:
                separation = [max(a - p, 0, p - b) for p, a, b in zip(point, lo, hi)]
                candidates.append((math.sqrt(sum(d*d for d in separation)), key_name))
            distance, nearest = min(candidates)
            distances.append({"bone": name, "nearest_key_component": nearest,
                              "bone_origin_to_world_aabb_cm": distance})
        results.append({"capture_id": capture, "game_frame": frame, "pose_serial": pose,
                        "clip_seconds": clip["seconds"], "distances": distances})
    return {"schema": "sub01.contact-geometry-analysis.v1", "geometry_structure_validated": True,
            "skin_contact_accepted": False, "jpeg_correlated": False, "tuning_completeness_validated": False,
            "interpretation": "Supplied structure/hash consistency only, not independent acquisition authenticity. Bone origins versus world axis-aligned bounds; zero distance is not skin contact.",
            "samples": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    require(args.input.stat().st_size <= 16 * 1024 * 1024, "input exceeds 16 MiB")
    def reject_constant(value):
        raise ValueError("non-finite JSON constant: " + value)
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result
    result = analyse(json.loads(args.input.read_text(), parse_constant=reject_constant,
                                object_pairs_hook=unique_object))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
