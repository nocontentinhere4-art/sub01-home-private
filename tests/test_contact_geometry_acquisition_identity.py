import copy
import unittest
from tools.native_streamer_visual_v2.contact_geometry_analyse import analyse, digest


def fixture():
    tuning = {"supplied_field": 1}
    sample = {"capture_id": "one", "game_frame": 1, "pose_serial": 1,
              "finalized_frame": 1, "published_frame": 1, "finalized_pose_serial": 1,
              "coordinate_space": "world_cm", "effective_tuning": tuning,
              "effective_tuning_sha256": digest(tuning), "source_tuning_sha256": "a" * 64,
              "clip": {"path": "/clip", "package_sha256": "b" * 64,
                       "evaluator_sha256": "c" * 64, "loop_count": 0, "replay_seed": 3, "seconds": 0},
              "bones": [{"name": str(i), "role": "terminal_finger", "world_xyz": [0, 0, 0]} for i in range(10)],
              "keys": [{"name": "key", "bounds_source": "CalcBounds(GetComponentToWorld()).GetBox()",
                        "world_aabb_min": [0, 0, 0], "world_aabb_max": [1, 1, 1]}]}
    second = copy.deepcopy(sample)
    second.update(capture_id="two", game_frame=2, pose_serial=2, finalized_frame=2,
                  published_frame=2, finalized_pose_serial=2)
    return {"schema": "sub01.contact-geometry.v1", "geometry_only": True, "jpeg_correlated": False,
            "overflow": False, "acquisition_complete": True, "input_manifest_sha256": "d" * 64,
            "engine_build_manifest_sha256": "e" * 64, "required_bones": [str(i) for i in range(10)],
            "samples": [sample, second]}


class AcquisitionIdentityTests(unittest.TestCase):
    def test_supplied_mapping_does_not_claim_completeness(self):
        self.assertFalse(analyse(fixture())["tuning_completeness_validated"])

    def test_recomputed_tuning_digest_does_not_allow_drift(self):
        doc = fixture()
        second = doc["samples"][1]
        second["effective_tuning"]["supplied_field"] = 2
        second["effective_tuning_sha256"] = digest(second["effective_tuning"])
        with self.assertRaisesRegex(ValueError, "identity drift"):
            analyse(doc)

    def test_source_and_clip_identity_drift(self):
        for key in ["source_tuning_sha256", "package_sha256", "evaluator_sha256", "replay_seed"]:
            with self.subTest(key=key):
                doc = fixture()
                target = doc["samples"][1] if key == "source_tuning_sha256" else doc["samples"][1]["clip"]
                target[key] = 4 if key == "replay_seed" else "f" * 64
                with self.assertRaisesRegex(ValueError, "identity drift"):
                    analyse(doc)
