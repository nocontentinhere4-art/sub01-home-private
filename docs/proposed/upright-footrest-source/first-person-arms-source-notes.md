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
