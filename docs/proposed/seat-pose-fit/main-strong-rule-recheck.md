# Seated fits rechecked under main's strong seat-patch rule

This is a recheck only. It changes no clip, verdict field or importer pin.

- Validator: `origin/main:tools/validate_unreal_seat_contact.py`, sha256 `dd95f1b1a8c3fc9a7d08b6d599985b86440c84752d85ae9f12fa8d480397a18f`. The tool imports those bytes from a temporary copy and refuses them if the sha256 differs (`tools/recheck_seat_fit_main_rule.py`, `tests/test_recheck_seat_fit_main_rule.py`).
- Rule, applied per sample to every patch, soles included: over-surface vertices ≥ 12, minimum gap ≥ band low, median gap ≤ band high, and in-band coverage ≥ 0.5. The seat band is −2.5..+0.5 cm and the sole band is 0..+1 cm.
- Measurement: the fitter's own read-back of each committed GLB on the actual chair. The recomputed lowest gaps reproduce the stored report values to within 5e-5 cm. Each gated frame is judged by main's `validate()`. DeskTyping is judged as its 301 native samples directly. Every other frame is judged as a constant 301-sample block, because main's `validate()` requires exactly 301 samples.

## Result: every clip fails, on every gated frame

| Clip | Gated frames | Failing | Worst median (buttocks) | Worst coverage (buttocks) | Worst min gap (all patches) | Worst sole median |
|---|---|---|---|---|---|---|
| SeatedIdle | 126 | 126 | 4.89 cm (f44) | 1.3% (f41) | −2.10 cm, R thigh (f17), in band | 8.04 cm L (f30) |
| SitDown_seated | 18 | 18 | 4.49 cm (f56) | 6.5% (f52) | −2.05 cm, R thigh (f67), in band | 8.03 cm L (f67) |
| GetUp_seated | 8 | 8 | 4.50 cm (f14) | 3.2% (f10) | −2.27 cm, R thigh (f7), in band | 8.11 cm L (f7) |
| DeskTyping_seated | 301 | 301 | 3.36 cm (f130) | 11.2% (f130) | −1.36 cm, L thigh (f26), in band | 7.96 cm L (f10) |
| SitToType_seated | 37 | 37 | 3.90 cm (f21) | 5.9% (f23) | −2.06 cm, R thigh (f22), in band | 8.04 cm L (f0) |
| TypeToSit_seated | 29 | 29 | 4.16 cm (f16) | 3.8% (f15) | −2.09 cm, R thigh (f14), in band | 8.03 cm L (f26) |

Main's minimum-gap condition and its over-surface condition never fail. The median and coverage conditions fail for the buttocks and both soles on every gated frame of every clip. They also fail for both posterior thighs on every gated frame, with one exception: the right thigh in SitToType fails on 21 of 37 frames. The JSON lists each patch, condition and frame, with main's own failure message per frame.

## Nearest correction

No pelvis depth or other rigid vertical shift can make these clips pass:

- **Buttocks:** on every gated frame of every clip, the median minus the minimum gap is wider than the 3 cm seat band (3.5–4.8 cm). A shift that brings the median down to +0.5 cm pushes the deepest point below −2.5 cm.
- **Soles:** the median minus the minimum is 6.5–8.0 cm against a 1 cm band. This is the captured toe plant with the heel raised.
- **Thighs:** in SeatedIdle, SitDown and GetUp, the posterior thighs are also wider than the band on every frame.

To pass main's rule, one of these is needed:

- A pose change that flattens the contact: less pelvis roll-under or a flatter thigh line, and heel-down feet with the ankle re-posed rather than raised.
- A modelled cushion or soft-tissue compression.
- A root decision on the rule itself.

Root decides which.
