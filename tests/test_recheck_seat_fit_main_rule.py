"""The seat-fit recheck judges with origin/main's validator bytes (sha256 pinned), never the branch file."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import recheck_seat_fit_main_rule as R  # noqa: E402

PINNED = 'dd95f1b1a8c3fc9a7d08b6d599985b86440c84752d85ae9f12fa8d480397a18f'


def _main_bytes():
    try:
        return R.main_validator_bytes()
    except subprocess.CalledProcessError:
        pytest.skip('origin/main is not available in this checkout')


def test_pin_is_mains_validator_bytes():
    assert R.MAIN_VALIDATOR_SHA256 == PINNED
    assert hashlib.sha256(_main_bytes()).hexdigest() == PINNED


def test_branch_file_is_not_what_the_recheck_imports():
    branch = (ROOT / 'tools/validate_unreal_seat_contact.py').read_bytes()
    V = R.load_main_validator(_main_bytes())
    assert V.__name__ == 'main_validate_unreal_seat_contact'
    assert V.SOURCE_SHA256 == PINNED
    assert not hasattr(V, 'MIN_SUPPORT_VERTICES')            # the branch's local-support constant
    if hashlib.sha256(branch).hexdigest() != PINNED:
        assert Path(V.__file__).read_bytes() != branch


def test_altered_bytes_are_refused():
    with pytest.raises(ValueError, match='pinned'):
        R.load_main_validator(_main_bytes() + b'\n# altered\n')


def _row(name, low, med, band, over=100):
    return {'region': name, 'selectedVertices': over, 'facingVertices': over, 'overSurfaceVertices': over,
            'bandVertices': band, 'minGapCm': low, 'p10GapCm': med, 'p50GapCm': med, 'p90GapCm': med, 'maxGapCm': med}


def test_judge_frame_applies_mains_median_and_coverage():
    V = R.load_main_validator(_main_bytes())
    good = [_row(n, 0., .2, 80) for n in V.SEAT_REGIONS] + [_row(n, .1, .5, 80) for n in V.SOLE_REGIONS]
    assert R.judge_frame(V, good) is None
    floating = [dict(r) for r in good]
    floating[0].update(p50GapCm=2., bandVertices=20)         # lowest point touches, most of the patch floats
    assert 'median' in R.judge_frame(V, floating)
    raised_heel = [dict(r) for r in good]
    raised_heel[3].update(p50GapCm=6., bandVertices=10)      # toes touch, heel up: fails main's sole rule
    assert 'left_sole' in R.judge_frame(V, raised_heel)


def test_committed_recheck_records_the_pinned_validator():
    path = ROOT / 'docs/proposed/seat-pose-fit/main-strong-rule-recheck.json'
    if not path.exists():
        pytest.skip('no committed recheck')
    doc = json.loads(path.read_text())
    assert doc['main_validator']['sha256'] == PINNED
    assert doc['recheck_only'] is True and doc['changes_verdicts_or_pins'] is False
    for c in doc['clips'].values():
        assert c['pass_main_rule'] == (c['failing_frame_count'] == 0)
