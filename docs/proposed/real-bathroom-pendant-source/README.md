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
bounds. A subsequent full-triangle surface audit against original955 and genuine WC source found no forbidden overlaps:36 contacts lie exactly on the measured canopy/roof boundary, and every fixture point is below that plane. The initial whole-face-only predicate incorrectly rejected side faces touching the roof at an edge; its preserved failed report was corrected using the actual plane boundary, without moving geometry or permitting penetration. Other owned native assets and containment/native collision validation remain pending.

The bulb position is measured in the JSON; it is not an installed light. Nothing
has been imported into the native map or exposed publicly. The material's source
emission is preserved; a later native fixture integration must bind an independent
switched light/emission, and verify actual ON/OFF pictures and privacy. Do not
claim the bathroom lighting is fixed from this source bundle alone.

Generator: tools/build_reference_bathroom_pendant.py. First attempt's missing
Blender Python path was corrected; successful source build is the server r2
folder recorded by the coordinator. No rendering, GPU reset, live device or map
change occurred during this authoring pass.

## Three-part native candidate

`split-v3/` is the same actual fixture separated in Blender by material into
Glass / Metal / Globe, so a native integration can preserve canopy shadows while
letting the diffuse globe emit light without trapping it inside an opaque shadow
shell. Both glass transmission/shadows and switching still need native review.
No native light is installed by this source operation.

`tools/verify_pendant_material_split.py` independently compared all5602 world
triangle corners, corner UVs/normals, PBR material factors, image bytes and sampler
assignments: exact semantic parity with the measured one-part candidate. Texture
indices are correctly resolved through actual image/sampler bindings; export
reordering is not a material change. Geometry is identical, so the original
surface collision proof applies to these same world triangles.

## Prepared native integration, not yet executed

The importer prepares a names-only GLB copy whose three mesh names match the
explicit role identifiers. It verifies all other document fields and binary bytes
stay exact, then binds actual imported owned mesh identities and full world
triangles rather than relying on display labels. Prepared-input SHA and imported
inventory are retained. Original scene actors stay unchanged; failures detach
new actors and quarantine their assets without deleting referenced packages.

The optional native sixth lamp is BathroomCeiling (5.5cd/3000K), independently
switched through the existing private settings UI when the actual imported lamp
exists. Metal casts shadows; glass and diffuse globe transmit this point light.
Its source emission uses a per-component runtime MID, leaving imported materials
unchanged. Older maps retain five available lamps. Source tests pass; actual
Editor import, native compilation and ON/OFF/visual acceptance are pending.
