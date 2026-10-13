"""The private home's environment: every paid integration off, except the eye (owner decision 2026-10-13).

The eye may use the owner's Replicate token from the private environment (the shell, or the git-ignored .env), but
only through SUB01_EYE_REPLICATE_TOKEN, which nothing but eye.py reads. REPLICATE_API_TOKEN itself stays blank, so the
browser's eyes (eyes.py), the diary text and every other integration stay unpaid. The eye's daily cap stays the
existing one (costs.EYE_USD_PER_DAY, $1.00) or lower, and the eye spends only while he sleeps or is outside
(live_server.run_eye). The token is never printed or logged.
"""
import os
from pathlib import Path

EYE_TOKEN_ENV = "SUB01_EYE_REPLICATE_TOKEN"     # eye.EYE_TOKEN_ENV (not imported: this runs before the server's env)
EYE_CAP_MAX_USD = 1.00                          # costs.EYE_USD_PER_DAY: the existing cap, never raised here
PAID_OFF = ("ANTHROPIC_API_KEY", "REPLICATE_API_TOKEN", "OPENROUTER_API_KEY", "OPENAI_API_KEY")


def dotenv_value(path, key):
    """KEY=VALUE from a git-ignored .env file, without putting anything else into the environment."""
    p = Path(path)
    if not p.is_file():
        return ""
    for line in p.read_text(errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return ""


def private_eye_token(environ, env_file):
    """The eye's token from the private environment: SUB01_EYE_REPLICATE_TOKEN, else REPLICATE_API_TOKEN (shell),
    else REPLICATE_API_TOKEN in the .env file. Empty when there is none."""
    return (environ.get(EYE_TOKEN_ENV) or environ.get("REPLICATE_API_TOKEN")
            or dotenv_value(env_file, EYE_TOKEN_ENV) or dotenv_value(env_file, "REPLICATE_API_TOKEN") or "").strip()


def capped_eye_usd(environ):
    """The eye's daily cap as costs.eye_cap() would read it, clamped to the existing $1.00 (never raised)."""
    for name in ("SUB01_EYE_USD_PER_DAY", "SUB01_CAP_EYE_USD"):
        raw = environ.get(name)
        if raw:
            try:
                return min(EYE_CAP_MAX_USD, max(0.0, float(raw)))
            except ValueError:
                break
    return EYE_CAP_MAX_USD


def eye_env(environ, env_file, enabled=True):
    """The variables to set for the private home's eye: (updates, eye_on). Every paid key stays blank; the eye gets
    its own token only when enabled and one exists."""
    token = private_eye_token(environ, env_file) if enabled else ""
    cap = f"{capped_eye_usd(environ):.2f}"
    updates = {k: "" for k in PAID_OFF}
    updates.update({EYE_TOKEN_ENV: token, "SUB01_EYE_USD_PER_DAY": cap, "SUB01_CAP_EYE_USD": cap})
    return updates, bool(token)
