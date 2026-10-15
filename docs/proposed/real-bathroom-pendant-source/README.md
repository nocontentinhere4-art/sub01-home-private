# Real bathroom pendant — source candidate

Built in Blender4.5.3 on the existing private4090, 2026-10-15. Source is the cached
[Poly Haven modern ceiling lamp](https://polyhaven.com/a/modern_ceiling_lamp_01),
CC0. It is a modeled asset, not described as scanned or manufacturer CAD.

The packed editable Blender file and self-contained GLB retain all5602 original
triangles, three materials, three embedded PBR images and UVs. Only the thin cable
is shortened axially from34cm to3cm; the canopy/globe remain real size. The actual
original roof underside (source node158, triangle42) was measured at nine canopy
points, all5.949999809m. Lowest fixture point leaves2.25595m above the real
bathroom floor. The body stays clear of the dry-zone walls/shower by its measured
bounds. Full source/native collision validation is still pending.

The bulb position is measured in the JSON; it is not an installed light. Nothing
has been imported into the native map or exposed publicly. The material's source
emission is preserved; a later native fixture integration must bind an independent
switched light/emission, and verify actual ON/OFF pictures and privacy. Do not
claim the bathroom lighting is fixed from this source bundle alone.

Generator: tools/build_reference_bathroom_pendant.py. First attempt's missing
Blender Python path was corrected; successful source build is the server r2
folder recorded by the coordinator. No rendering, GPU reset, live device or map
change occurred during this authoring pass.
