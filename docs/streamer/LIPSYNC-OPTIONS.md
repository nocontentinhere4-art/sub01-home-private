# Lip sync for SUB-01: the realistic options (2026-10-23)

Weighed from Kimi's consultation (`kimi/priorities.md`, section 3; decisions in `kimi/DECISIONS.md` B14-B15) against
what exists. Free assets only; no purchase; the character keeps his identity (he is not a copy of any real person or
streamer, and a new head must not make him one).

## What exists today (facts)

- Mesh `AnatomicalOwner`: 65 Mixamo bones (Hips ... Neck, Head, HeadTop_End, four finger bones per finger), **no jaw,
  mouth, eyelid or facial bone, no morph target** (name-table scan, `tools/native_streamer_visual_v2/README.md`).
- The voice server already publishes `<streamer-dir>/mouth.json` at 25 Hz while speaking: `open` 0..1 is the RMS of the
  20 ms block being written to the FIFO right now, normalised per utterance, closed below 8 %, 20 ms attack / 80 ms
  release (`docs/streamer/VOICE.md`). It comes from the voice PCM only, never from browser or game audio.
- The native mouth layer (`install_mouth.py`) polls that file at up to 30 Hz and applies `2 deg x open` of Head pitch
  as emphasis; **if the skeleton has a bone named `Jaw`/`jaw`/`JawRoot` (or ending in `Jaw`) it rotates that bone by
  `12 deg x open` instead** and the receipt says `mouth_rig: jaw_bone`. So the driver side of option D is built; the
  missing piece is the bone in the mesh.
- Delivery shot: the `face` camera is a fixed webcam on the monitor, FOV 70, face and shoulders slightly from above;
  in the program it is a PiP or the full frame (W6 live layouts). The mouth is a few dozen pixels wide at PiP size.
- The pod has Blender for the body/clip work (`run-unreal-home-import.sh` pipeline); the skeletal mesh must keep its
  Skeleton asset so the Desk7 clips, Walk/Idle and the seat fix keep working.

## The options

| | D. Jaw bone on the existing head | A. Free rigged head (MPFB2/MakeHuman) | B. MetaHuman head on the Mixamo body | C. 2D mouth in the head texture |
|---|---|---|---|---|
| Work | Blender: add `Jaw` child of `Head`, pivot near the ear canal, weight chin + lower lip + lower teeth region with a soft gradient to the cheeks; split the lips if sealed; dark mouth bag; FBX export; reimport onto the same Skeleton (UE merges the new bone); verify clips; tune the angle | Generate an adult head, match scale, skin and neck, cut and attach at the neck, keep the body skeleton, build 6-8 visemes + blink, write a curve driver from the cue timeline | Fit a MetaHuman head, hide the original head, transfer neck/head motion, match skin at the seam, drive facial curves live, add procedural blink and brow motion | Export UVs, paint 6-8 mouth states, isolate the head material, blend by cue |
| Hours | **24-32** (4 h geometry prototype first) | 45-80 | 70-110 | 12-20 if the mouth has clean unique UVs |
| Quality at facecam size | 2-3/5: the sealed-mouth problem disappears; still a hinge, no lips shaping | 3/5, 4/5 with art time; real lip shapes and blinks | 4-5/5 if seam and proportions work; the only option that survives a sustained close-up | 1-2/5: paint, no opening, shading mismatch; wrong on a realistic face |
| Free downloads | Blender only | Blender, MPFB2 + MakeHuman assets (check each asset pack's licence), Rigify | Epic's MetaHuman tools for the installed UE version, a free preset head, Epic's sample control rigs; no MetaHuman Animator, no iPhone, no marketplace pack | Blender, Krita or GIMP |
| Identity risk | none: same face | high: a different face, neck seam, hair mismatch | high: a different, generic face; fails the "keeps his identity" rule unless the owner asks for a new look | none |
| Main failure | the head mesh may have no lip split or interior: opening tears the lip region (the 4 h prototype answers this) | a working head that is no longer him | seam, proportions, skin and hair mismatch; UE version and EULA checks | mouth image appears elsewhere (mirrored UVs), looks painted |
| Driver | `mouth.json` envelope, already wired | cue timeline (Rhubarb) to visemes | cue timeline to MetaHuman curves | cue timeline to texture index |
| Verdict | **do first** | v2 candidate if the owner wants real lips and accepts a new face | v2 only if close-up realism becomes a requirement and the owner accepts the face change | reject for this character |

## Timing: envelope now, Rhubarb later

Kimi recommends Rhubarb Lip Sync (free, MIT, per-utterance WAV to timed mouth shapes A-H + X) and warns against
"unsmoothed amplitude chatter". Our envelope is not raw amplitude: it is block RMS with 20/80 ms smoothing, a per-utterance
normalisation and a closed threshold, from the voice only. With **one jaw bone** every viseme collapses to an opening
amount anyway; Rhubarb's gain is closure timing on plosives, which the 80 ms release already approximates. Decision:

1. Jaw bone driven by `mouth.json` as it is (zero new code in the voice path; the native layer is built).
2. Measure the offset in a recording: the frame where the jaw first opens against `speech/timeline.jsonl` `start_utc`
   (the audio and the game frames go through the same ffmpeg); target within 80 ms. If the jaw leads or lags by a constant
   amount, delay the file write or the voice path by that amount (W3), not by editing the animation.
3. Rhubarb only when a visemed head exists (A or B): then the voice server runs it per sentence after synthesis (it
   adds a fraction of the 2.8-5 s synthesis time per line) and publishes the cue list next to `mouth.json`; the `phonetic`
   recogniser is fast and English-only, which matches the voice.

## Recommendation and plan (option D, about 28 hours)

1. **Geometry prototype, 4 h, go/no-go.** Export the skeletal mesh (or open the source FBX) in Blender. Check: are the
   lips two separate edge loops or one sealed surface; is there any interior; how many loops around the mouth. If the
   lips are sealed and the mouth region has fewer than 3 loops, stop here and report: a jaw on that head deforms the face,
   and the honest fallback is the current head emphasis plus shot size (the face stays a third of the frame).
2. **Jaw bone and weights, 8 h.** `Jaw` under `Head`, pivot at the temporomandibular joint (ear level, just in front of
   the ear, both sides symmetric), rotation about the local lateral axis only. Weights: 1.0 chin and lower-lip centre,
   falling to 0 at the nasolabial line and the jaw angle; the upper lip, nose and cheeks keep 0. No sideways motion.
3. **Mouth bag, 4 h, only if the opening shows the inside of the head.** A dark cavity with a near-black, low-roughness
   material; teeth optional (a simple white strip reads as teeth at this size).
4. **Export and reimport, 6 h.** FBX with the full skeleton + the new bone; reimport the skeletal mesh on the existing
   Skeleton (the Skeleton asset accepts the added bone; existing animations have no `Jaw` track so they keep playing).
   Verify on the pod: `SUB01_STREAMER_VISUAL_MOUTH_READY rig=jaw_bone`, Walk/Idle in the live game, the Desk7 loops and the
   seat fix (`pelvis_world` unchanged), the `face` camera framing unchanged.
5. **Tuning, 6 h.** The native layer's `12 deg x open` is the maximum; if it reads as a ventriloquist, lower the constant
   in the installer to 8-10. Review 20 varied lines (plosives, long vowels, a short "yes", the octopus material) at the
   actual PiP size and at full frame; mouth closed in silence and at the end of each line; no reaction to game sound.

Blinks matter more than lips for a close-up and are the same technique (two eyelid bones, ~8 h, driven by a jittered
3-6 s timer in the native layer): plan them right after the jaw, before any thought of a new head.
