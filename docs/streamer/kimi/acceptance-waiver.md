# Acceptance: the owner's mouth waiver (2026-10-24, coordinator)

Owner: "Per la bocca lasciamo perdere per ora e la stessa cosa vale anche per la felpa". Pre-commit review of the waiver in `scripts/streamer_acceptance.py` (kimi-k3.1-pro, 59 s):

**APPROVE.** This is a verdict waiver, not an evidence waiver:

- `mouth_motion` is still evaluated; its underlying status, explanation, metrics, and highlights remain intact.
- Reports label it `(waived)`, include the dated owner rationale, and count waivers separately.
- Only non-waived criteria determine the verdict and exit code; `--no-waivers` restores strict judgement.
- `head_motion` remains required, and no unwarranted hoodie waiver is added.
- Tests cover both the real head-only rig passing **with a visible `FAIL (waived)`** and failing under `--no-waivers`.

No corrections needed.
