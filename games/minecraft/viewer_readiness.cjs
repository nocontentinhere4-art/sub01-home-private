const { installItemRendering } = require('./item_rendering.cjs');
// Preserve pinned upstream geometry; use its existing assets and real readiness.
function terrainReady() {
  const world = globalThis.sub01MinecraftViewer?.world;
  return Boolean(world && Object.keys(world.loadedChunks || {}).length > 0 &&
    world.sectionsOutstanding?.size === 0 && (globalThis.sub01ItemTexturesOutstanding || 0) === 0 && (globalThis.sub01PendingItemMetadata?.size || 0) === 0 && world.material?.map?.image?.width > 0 &&
    Object.values(world.sectionMeshs || {}).some(mesh => mesh.geometry?.attributes?.position?.count > 0));
}
function createRenderBudget(renderer, viewer, controls, clock = () => performance.now()) {
  const budget = { target_fps: 15, attempts: 0, frames: 0, first_draw_ms: null,
    last_draw_ms: null, draw_duration_ms: 0, total_draw_ms: 0, vendor: null, renderer: null };
  try {
    const gl = renderer.getContext();
    const info = gl.getExtension('WEBGL_debug_renderer_info');
    budget.vendor = gl.getParameter(info ? info.UNMASKED_VENDOR_WEBGL : gl.VENDOR);
    budget.renderer = gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER);
  } catch (_) { /* No renderer claim if the actual context cannot report it. */ }
  return {
    draw() {
      budget.attempts++;
      const start = clock();
      if (!Number.isFinite(start) || (budget.last_draw_ms !== null && start - budget.last_draw_ms < 1000 / budget.target_fps)) return false;
      if (controls) controls.update();
      viewer.update();
      renderer.render(viewer.scene, viewer.camera);
      const end = clock();
      budget.draw_duration_ms = Number.isFinite(end) ? Math.max(0, end - start) : 0;
      budget.total_draw_ms += budget.draw_duration_ms;
      budget.first_draw_ms ??= start;
      budget.last_draw_ms = start;
      budget.frames++;
      return true;
    },
    diagnostics() {
      const elapsed = budget.last_draw_ms - budget.first_draw_ms;
      return { ...budget, observed_fps: budget.frames > 1 && elapsed > 0 ? (budget.frames - 1) * 1000 / elapsed : null };
    }
  };
}

function instrumentViewerBundle(bundle) {
  const marker = 'const u=new r(l);';
  if (typeof bundle !== 'string' || bundle.indexOf(marker) < 0 || bundle.indexOf(marker) !== bundle.lastIndexOf(marker))
    throw new Error('Pinned viewer entry point changed; real terrain readiness unavailable');
  const draw = '!function t(){window.requestAnimationFrame(t),h&&h.update(),u.update(),l.render(u.scene,u.camera)}()';
  if (bundle.indexOf(draw) < 0 || bundle.indexOf(draw) !== bundle.lastIndexOf(draw))
    throw new Error('Pinned viewer draw loop changed; bounded draw cadence unavailable');
  const capped = bundle.replace(draw, 'globalThis.sub01RenderBudget=(' + createRenderBudget.toString() + ')(l,u,h);globalThis.sub01RendererDiagnostics=()=>globalThis.sub01RenderBudget.diagnostics();!function t(){window.requestAnimationFrame(t),globalThis.sub01RenderBudget.draw()}()');
  return capped.replace(marker, marker + 'globalThis.sub01MinecraftViewer=u;globalThis.sub01TerrainReady=' + terrainReady.toString() + ';(' + installItemRendering.toString() + ')(u);');
}
module.exports = { instrumentViewerBundle, terrainReady, createRenderBudget };
