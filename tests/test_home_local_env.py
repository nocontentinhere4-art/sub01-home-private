"""scripts/start_home_local.py: the eye may use the owner's Replicate token (owner, 2026-10-13), within the existing
cap; every other paid integration stays off and the token is never printed."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import home_local_env as H  # noqa: E402

SECRET = "r8_fake_secret_for_tests"


def test_token_from_shell_goes_to_the_eye_only(tmp_path):
    env = {"REPLICATE_API_TOKEN": SECRET, "ANTHROPIC_API_KEY": "a", "OPENROUTER_API_KEY": "o", "OPENAI_API_KEY": "x"}
    updates, on = H.eye_env(env, tmp_path / ".env")
    assert on and updates[H.EYE_TOKEN_ENV] == SECRET
    for k in H.PAID_OFF:
        assert updates[k] == "", k                      # REPLICATE_API_TOKEN itself stays blank: eyes.py, diary unpaid
    assert updates["SUB01_EYE_USD_PER_DAY"] == updates["SUB01_CAP_EYE_USD"] == "1.00"


def test_token_from_the_private_dotenv(tmp_path):
    (tmp_path / ".env").write_text(f"# private\nOTHER=1\nexport REPLICATE_API_TOKEN='{SECRET}'\n")
    updates, on = H.eye_env({}, tmp_path / ".env")
    assert on and updates[H.EYE_TOKEN_ENV] == SECRET


def test_no_token_or_no_eye_keeps_it_off(tmp_path):
    assert H.eye_env({}, tmp_path / "missing.env") == ({**{k: "" for k in H.PAID_OFF}, H.EYE_TOKEN_ENV: "",
                                                        "SUB01_EYE_USD_PER_DAY": "1.00", "SUB01_CAP_EYE_USD": "1.00"},
                                                       False)
    updates, on = H.eye_env({"REPLICATE_API_TOKEN": SECRET}, tmp_path / ".env", enabled=False)
    assert not on and updates[H.EYE_TOKEN_ENV] == ""


def test_cap_is_never_raised():
    assert H.capped_eye_usd({"SUB01_EYE_USD_PER_DAY": "5"}) == 1.0
    assert H.capped_eye_usd({"SUB01_CAP_EYE_USD": "0.25"}) == 0.25
    assert H.capped_eye_usd({"SUB01_EYE_USD_PER_DAY": "nonsense"}) == 1.0
    assert H.capped_eye_usd({"SUB01_CAP_EYE_USD": "-3"}) == 0.0


def test_start_script_wires_the_eye_without_logging_the_token():
    src = (ROOT / "scripts" / "start_home_local.py").read_text()
    blank = src.index("REPLICATE_API_TOKEN=''")
    assert src.index("eye_env(os.environ") < blank < src.index("os.environ.update(_eye_updates)")
    assert "server_args.append('--eye')" in src and "--no-eye" in src
    assert "'--host', '127.0.0.1'" in src
    for line in src.splitlines():                       # nothing printed carries the token or the updates dict
        if "print(" in line:
            assert "_eye_updates" not in line and "TOKEN" not in line


def test_only_the_eye_reads_the_eye_token():
    hits = sorted(str(p.relative_to(ROOT)) for p in ROOT.glob("*.py") if H.EYE_TOKEN_ENV in p.read_text())
    assert hits == ["eye.py"]
    import eye
    assert eye.EYE_TOKEN_ENV == H.EYE_TOKEN_ENV
