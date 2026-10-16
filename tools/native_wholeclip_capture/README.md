# Isolated native diagnostic — successful offline capture, no live contact acceptance

The first two authorized processes failed before producing frames: missing genuine AnimationData/ControlRig dependencies, then duplicate world initialization in this harness. Their refusal records remain preserved in `docs/proposed/native-wholeclip-capture/`.

A new explicit human instruction at 2026-10-16 02:07:09 UTC separately authorized one minimal repair, an incremental build capped at 180 seconds, and one capture capped at 120 seconds. The only C++ change removes the second `InitializeNewWorld` after `CreateWorld`. Source SHA256 is `1b35521e2623e37bfea86dd0813d4ee2a2d4ec580cf5935ddd5c0a33b3aa397e`.

The incremental build succeeded in 66.53 seconds. Module SHA256 is `a8d107a9246a999f4d371bb12ac8f958f2cdc48abc01a7b58463f734158891d1`. The single new commandlet exited with result 0 at 02:11:02 UTC. Capture computation took 6.796 seconds, plus engine startup. No further build or process was launched.

Actual output directory on the existing private pod:

`/workspace/sub01-private-wholeclip-diagnostic-20261016/Sub01WholeClipWitness/capture-output-human-world-repair`

- `capture-report.json`: 152 evaluated samples at 30 Hz, inclusive 0..5.033333333 seconds, actual component poses, body transforms, clip times and evaluation stamps.
- `static-witness.json`: 72,720 selected imported LOD0 vertex identities, sections, global/local vertex indices, raw weights and five independently selected region memberships.
- `posed-position-normal-f32le.bin`: eight-byte `SUB01SK1`, followed by each frame's selected-vertex order, six float32 little-endian values per vertex (world XYZ centimetres and posed normal XYZ). Exact size 265,282,568 bytes.

Validation found 152 distinct evaluation stamps, distinct actual poses, zero render-binding position mismatches, and 9,880 native-render position comparisons with maximum difference 0.0000177541 cm. The engine frame counter is reported honestly and may remain constant inside a commandlet. Four ACL compression-settings warnings are retained in the engine log; the commandlet rebuilt compression and exited with zero errors.

The durable actual hash/identity verification is `docs/proposed/native-wholeclip-capture/actual-authorized-world-repair-verification.json`. All 24 source/copied assets remained hash-identical. Live Game 225250, candidate Editor 203351 and guard 145 remained the exact original processes, and live/candidate map hashes remained unchanged.

This is an offline native capture producer. It does not prove body-to-seat alignment, fixture contact, physical controller use, impulse completion or a live Minecraft demo. Every seat/contact/live readiness field remains false. PC animation was not imported: no complete compatible R9-preserving PC candidate passed.
