# First-person arms source candidate

This independent source candidate does not change the full-body owner, seating
rules, capsule, native assets, or readiness flags.

The owner is the explicitly derived shoulder repair
`831790a62b81e7e2faa5a201e04740d0911c5bfebd49aa03b124808521e3a2b1`.
The captured `typing` action remains the canonical owner's 495 keys / 16.4667 s.
The chosen mesh retains 88,592 original triangles using at least 50% total arm
chain weight at all three corners, plus **every** triangle touching a vertex with
any original Hand/Finger weight. No cap, invented triangle, reskin, bone, inverse
bind matrix, UV, texture, or finger pose was added. The original binary prefix is
preserved; only new index buffers select the visible source surfaces.

The resulting GPU candidate is
`/workspace/sub01-home-private/fp-arms-candidate-r1/SUB01_FirstPersonArms_SourceCandidate.glb`,
SHA256 `a862cbd3457c2b25da227c0eea2e04dcd8fe1f637115da0ccc69fbcf888ad154`.
`arms-mask-phase-audit.json.gz` records exact retained original triangle IDs and
new cut edges. `arms-source-packet.json` records construction and eye-path proof.

At FOV75 / 16:9 / near1 cm, the selected new sleeve cuts are outside the actual
captured iris/head frustum at additional downlooks 0,20,35,50 degrees over all
495 keys. **At 65 degrees, cuts become visible in 135 keys** (up to 106 edges).
This limitation is preserved. This is a source-camera calculation, not native
camera or visual acceptance.

The unadjusted source capture fails real surface contact at its explicitly
recorded historical body placement. `arms-real-surface-contact.json` measures
actual full-home955 keycap node187 and curved mouse237, not their boxes or an
under-mouse plane. Left fingers are below key tops by over1 mm in 474 keys
(worst10.116 cm), right in268 (worst7.200 cm). The right hand's original action
alternates mouse-side and keys, with active finger motion in both phases.
Mouse unsigned proximity does not establish penetration-free contact: its source
mesh has open/nonmanifold edges. This candidate is **not** ready for native import
or promoted as accepted typing. A separate, explicitly derived arm correction
must preserve original finger locals and lengths, prove actual surface contact,
and pass source view/collision review first.

The frustum clipping, protected hand-face selection, new-boundary identification,
and behind-camera rejection passed four geometric tests in the bounded GPU job.
The original full-body pose/anatomy/seating checks remain unchanged and pending.

## Explicit R2 contact trial (not accepted)

`arms-contact-fit-trial-r2.json` records the measured trial. It preserves all65
bone lengths to7.5e-14 cm, original captured finger local matrices to7.1e-14,
and untouched joint worlds exactly. The owned animation-only source SHA is
`1653694aca1925e12b5244b72039054c2a80cd1d0a2566566b7c98a224da9c83`.
All495 left-hand keys and291 right-hand key-phase samples place the distal
minimum at actual keytop+0.08 cm. Wrist displacement remains below15 cm.
There are112 right-arm reach failures and3 mouse-upper-surface penetration
samples. Thus contact is not accepted and no FBX/native integration follows.

The local polar hand carry preserves the complete authored hand stretch tensor.
The shared helper's scalar column normalization caused7.6e-7 cm finger-length
drift in the refused first trial; the bound was not relaxed. R2 original finger
motion is matrix-equivalent; a separate exact-row helper also preserves the
original quaternion float32 bytes/signs for future accepted derivatives.

`FPS-contact-source-r2-uvcorrect/` contains actual CPU source views, with explicit
skinning into exact retained triangles and original PBR/UV. The preview converts
glTF V to Blender1-V; original source UV bytes remain unchanged. Frame150 shows
both hands over keys. Frame045 exposes the right hand left of the mouse; this
is a visible defect. Diagnostic studio lighting and captured source iris/head
camera are not the native Game. No sleeve cut appears at the tested35-degree
additional downlook. Complete arm/desk/device collisions are still pending.
