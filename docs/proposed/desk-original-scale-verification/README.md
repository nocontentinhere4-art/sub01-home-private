# desk-original-scale: independent verification (status: proposal in_progress at 22:51 UTC; `ready: false`)

Verifier: `tools/verify_ergonomic_layout_refit.py` (desk-variant input, commits 28f6269 / 6d5413b). The LINEA140 is rebuilt
independently from origin/main `originalsource.glb` (sha 99bdf3fd...) at the variant scale; the solver geometry JSON is not read.

Desk at uniform scale 1.0, translation [2.1, .025, -3.02] m: top **78.0**, slab bottom **75.20**, apron bottom **72.10**,
worktop x 140..280, y -334.5..-269.5 (scale 1.086: top 84.5, x 133.97..286.03, y -337.30..-266.70).

`desk-items-verification.json` (planned_layout of the proposal; monitor/lamp as declared and with the brief's -6.5 cm):

* keyboard (8, 14.202, -6.6) and mouse (0, 9.05 assumed, -6.6): PASS on the 78.0 top, original footprints, slab margins 2.25 / 2.0 cm, gap 2.45 cm.
* monitor stand: the proposal declares no offset, so it floats 6.5 cm (FAIL). Lowered -6.5 it sits at 0.0, but its unchanged
  footprint (y -334.5..-325.5) is flush with the scale-1.0 rear edge (-334.5): over the eased edge, 0 cm margin -> FAIL.
  Needs a forward move of at least ~1.3 cm (1 cm margin + eased edge) with the screen.
* clamp lamp: the scaled grommet moves (158.95, -325.89) -> (163.0, -324.0); the lamp pin at its old XY drifts 4.47 cm
  vs the 0.62 cm radial clearance -> FAIL (it needs the XY move with the grommet as well as -6.5 cm).
* no footprint overlaps among stand / lamp / keyboard / mouse.

`full-verification-9f4e199-layout-at-scale1.*` + `comparison.md`: the full verifier (body, chair, clips) with the 9f4e199
layout and clips at the scale-1.0 desk and devices -6.5 cm (the variant has no final clips yet). The body is identical,
so elbows read 6.5 cm higher above the top (left median -0.16 -> 6.34; right 2.11 -> 8.61) while the hands stay 6.5 cm
above the lowered keyboard; that layout's keyboard/mouse also overhang the smaller desk's front edge (FAIL). It shows the
geometric effect only; it is not a verification of the variant's solve, which must be re-run when its proposal is final.
