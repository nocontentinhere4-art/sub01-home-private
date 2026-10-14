const { installItemRendering } = require('./item_rendering.cjs');
// Preserve pinned upstream geometry; use its existing assets and real readiness.
function terrainReady() {
  const world = globalThis.sub01MinecraftViewer?.world;
  return Boolean(world && Object.keys(world.loadedChunks || {}).length > 0 &&
    world.sectionsOutstanding?.size === 0 && (globalThis.sub01ItemTexturesOutstanding || 0) === 0 && (globalThis.sub01PendingItemMetadata?.size || 0) === 0 && world.material?.map?.image?.width > 0 &&
    Object.values(world.sectionMeshs || {}).some(mesh => mesh.geometry?.attributes?.position?.count > 0));
}
function instrumentViewerBundle(bundle) {
  const marker = 'const u=new r(l);';
  if (typeof bundle !== 'string' || bundle.indexOf(marker) < 0 || bundle.indexOf(marker) !== bundle.lastIndexOf(marker))
    throw new Error('Pinned viewer entry point changed; real terrain readiness unavailable');
  return bundle.replace(marker, marker + 'globalThis.sub01MinecraftViewer=u;globalThis.sub01TerrainReady=' + terrainReady.toString() + ';(' + installItemRendering.toString() + ')(u);');
}
module.exports = { instrumentViewerBundle, terrainReady };
