// Surface detail for furnishings that tools/home_asset_audit.py flags as flat,
// using only bitmaps the house already loads. Every function reuses existing
// Texture objects (never clones or loads images) and never moves vertices.
//
// Roughness factors keep each part's previous mean roughness. three.js
// computes roughness = factor * map.g and clamps it to 1, so each factor solves
// mean(min(1, factor * g)) = previous constant over the actual map (green channel).
// tests/test_furnishing_detail_factors.py recomputes them from the JPEGs.
export const FURNISHING_DETAIL = Object.freeze({
  queenBedOak: Object.freeze({
    // Prepared CC0 queen bed wood UVs measure .99 UV/m (area-weighted), i.e. one
    // tile per metre; the shared home_oak_veneer scan covers 1.83 m per tile.
    sourceUvPerMetre: 1,
    scanCoverageMetres: 1.83,
    previousRoughness: .82,
    roughnessFactor: Object.freeze({full: 1.58172, lite: 1.56785}),
    color: '#e7dcc9',
  }),
  havenSeams: Object.freeze({
    // Seams already share the linen panels' UV space: 2.08 vs 2.17 UV/m.
    previousRoughness: .84,
    roughnessFactor: Object.freeze({full: 1.06686, lite: 1.06675}),
  }),
  wovenRug: Object.freeze({
    previousRoughness: .98,
    // 76% (full) / 63% (lite) of texels clamp at 1: the restored variation is subtle.
    roughnessFactor: Object.freeze({full: 1.54693, lite: 1.42715}),
  }),
});

function tierFactor(entry, tier) {
  const value = entry.roughnessFactor[tier];
  if (!Number.isFinite(value)) throw new Error('Unknown texture tier: ' + tier);
  return value;
}

// Queen bed wood (meshes whose source material is not upholstery): shared clean
// architecture-oak colour/normal/roughness maps at the physical 1.83 m scan
// density. Only the primary `uv` channel is rescaled; `uv1` (baked light) and
// positions stay untouched. Idempotent per geometry.
export function applyQueenBedOak(material, geometry, architectureOak, tier = 'full') {
  const spec = FURNISHING_DETAIL.queenBedOak;
  if (!architectureOak?.map || !architectureOak.normalMap || !architectureOak.roughnessMap)
    throw new Error('Queen bed oak needs the shared architecture oak maps');
  material.map = architectureOak.map;
  material.normalMap = architectureOak.normalMap;
  material.normalScale.copy(architectureOak.normalScale);
  material.roughnessMap = architectureOak.roughnessMap;
  material.roughness = tierFactor(spec, tier);
  material.color.set(spec.color);
  material.userData.queenBedOak = 'shared home_oak_veneer maps; mean roughness ' + spec.previousRoughness;
  const uv = geometry.attributes.uv;
  if (uv && !geometry.userData.queenBedOakUv) {
    const scale = 1 / (spec.sourceUvPerMetre * spec.scanCoverageMetres);
    for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * scale, uv.getY(i) * scale);
    uv.needsUpdate = true;
    geometry.userData.queenBedOakUv = true;
  }
  material.needsUpdate = true;
  return material;
}

// Haven sofa welts/cords keep the licensed flat flax albedo but gain the same
// linen weave relief/roughness texture objects as the panels they edge.
export function applyHavenSeamDetail(materials, tier = 'full') {
  const {Haven_linen: linen, Haven_seams: seams} = materials;
  if (!linen?.normalMap || !linen.roughnessMap || !seams) throw new Error('Haven linen maps are required');
  seams.normalMap = linen.normalMap;
  seams.normalScale.copy(linen.normalScale);
  seams.roughnessMap = linen.roughnessMap;
  seams.roughness = tierFactor(FURNISHING_DETAIL.havenSeams, tier);
  seams.needsUpdate = true;
  return seams;
}

// Opt-in: give a woven rug (from createWovenRugMaterial) back the shared
// rough_linen roughness map while keeping its .98 mean.
export function restoreRugScannedRoughness(material, linen, tier = 'full') {
  if (!linen?.roughnessMap) throw new Error('Shared linen roughness map is required');
  material.roughnessMap = linen.roughnessMap;
  material.roughness = tierFactor(FURNISHING_DETAIL.wovenRug, tier);
  if (material.userData.wovenRug) material.userData.wovenRug.roughness = 'scanned map, mean .98';
  material.needsUpdate = true;
  return material;
}
