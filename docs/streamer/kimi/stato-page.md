# Kimi review (2026-10-24 ~14:25 UTC): the owner progress page STATO-20261024.md

Question: `q-stato-page.txt` (model `kimi-k3.1-pro`, 306 s; attached the page and HANDOFF.md). Answer, verbatim:

1. **Director speed guard:** listed under “Cosa è stato fatto”, but HANDOFF says only “fix in review”. Remove the claimed operational 0.95x/three-check/10-minute behaviour or provide newer deployment/validation evidence.

2. **v22:** ruling out `bMainViewFamily` as useless contradicts HANDOFF. v22 still explicitly includes that A/B, capture IDs/timestamps, separate Vulkan A/Bs and tracing.

3. **RunPod balance guard:** “poi riparte” is misleading. The API block ends around 00:05 UTC, but the paused process requires manual `kill -CONT 63`; HANDOFF schedules a 00:20 reminder.

4. **Privacy cut:** HANDOFF records `webcam_only` as set at 12:22 and does not establish the claimed director-confirmed typing interlock. Do not present the whole automatic workflow as verified.

5. **Open work omitted from “Cosa manca”:** the HLS and monitor-feed sidecars are not yet supervised; the pre-publication private embed/platform test is also absent.

No secrets, tokens, emails or obvious personal data appear in the supplied Markdown. Image contents could not be inspected from the provided material.

## Applied
1. The guard was deployed at 12:22 (commit dd15704) and relaunched a 0.76x run at 12:32 (director log `speed_restart`):
   HANDOFF was stale and now says so; the page states the evidence.
2. The page now says the engine-source finding makes `bMainViewFamily` likely useless and that it is to be re-decided
   with Kimi when v22 is scoped; HANDOFF notes the same.
3. The page says the guard does not restart by itself and is resumed by hand after the block (reminder 00:20 UTC).
4. The privacy cut is described as implemented and covered by automated tests, not yet proven live.
5. Added to "Cosa manca": supervising the HLS and monitor-feed sidecars, and the private embed test on the site before
   any publication.
