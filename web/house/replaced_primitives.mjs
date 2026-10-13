// Find the procedural home.js primitives that an original asset replaces, from
// the literal calls its sidecar lists in `replaces_home_js` (tools/build_home_bath_*.py).
// home.js marks them replaceable synchronously (so batchArchitecture keeps them
// separate) and hides them only after the asset has loaded; on any mismatch the
// primitives simply stay. Pure: works on any objects with position + geometry.

// The bathroom fallbacks, verbatim from tools/build_home_bath_fixtures.py
// FIXTURES[*].replaces_home_js (tests/js/replaced_primitives_check.mjs checks
// both the generator and the home.js literals).
export const BATH_FALLBACK_CALLS = Object.freeze({
  vanity: Object.freeze([
    'box(0.62, 0.66, 0.48, -3.5, 3.36, 1.1, M.wood, 0.02);',
    'box(0.68, 0.1, 0.5, -3.5, 3.73, 1.1, M.white, 0.04);',
    'cylinder(0.12, 0.05, -3.5, 3.81, 1.1, M.white);',
    'beam([-3.5, 3.8, 0.92], [-3.5, 4.01, 0.92], 0.017, M.brass);',
    'beam([-3.5, 4.01, 0.92], [-3.5, 4.01, 1.04], 0.017, M.brass);',
  ]),
  toilet: Object.freeze([
    'box(0.42, 0.42, 0.6, -2.9, 3.24, 2.23, M.white, 0.11);',
    'box(0.43, 0.64, 0.18, -2.9, 3.47, 2.49, M.white, 0.07);',
    'box(0.36, 0.04, 0.46, -2.9, 3.48, 2.18, M.cream, 0.08);',
  ]),
});

const NUM = String.raw`\s*(-?\d*\.?\d+)\s*`;
const BOX = new RegExp(String.raw`^(?:const\s+\w+\s*=\s*)?box\(${Array(6).fill(NUM).join(',')}(?:,[^)]*)?\);?$`);
const CYL = new RegExp(String.raw`^(?:const\s+\w+\s*=\s*)?cylinder\(${Array(5).fill(NUM).join(',')}(?:,[^)]*)?\);?$`);
const VEC = String.raw`\[${NUM},${NUM},${NUM}\]`;
const BEAM = new RegExp(String.raw`^(?:const\s+\w+\s*=\s*)?beam\(\s*${VEC}\s*,\s*${VEC}\s*,${NUM}(?:,[^)]*)?\);?$`);

// {kind, position [x,y,z], size [sx,sy,sz] in the mesh's local frame}
export function parsePrimitiveCall(call) {
  const text = String(call).trim();
  let m = BOX.exec(text);
  if (m) {
    const [w, h, d, x, y, z] = m.slice(1, 7).map(Number);
    return {kind: 'box', position: [x, y, z], size: [w, h, d]};
  }
  m = CYL.exec(text);
  if (m) {
    const [r, h, x, y, z] = m.slice(1, 6).map(Number);
    return {kind: 'cylinder', position: [x, y, z], size: [2 * r, h, 2 * r]};
  }
  m = BEAM.exec(text);
  if (m) {
    const v = m.slice(1, 8).map(Number), a = v.slice(0, 3), b = v.slice(3, 6), r = v[6];
    const length = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
    return {kind: 'beam', position: a.map((p, i) => (p + b[i]) / 2), size: [2 * r, length, 2 * r]};
  }
  throw new Error('Not a home.js primitive call: ' + text);
}

function localSize(object) {
  const g = object.geometry;
  if (!g) return null;
  // Faceted cylinders are narrower than 2r across their flats: use the radius.
  const p = g.parameters;
  if (Number.isFinite(p?.radiusTop) && Number.isFinite(p?.height)) return [2 * p.radiusTop, p.height, 2 * p.radiusTop];
  if (!g.boundingBox && g.computeBoundingBox) g.computeBoundingBox();
  const b = g.boundingBox;
  return b ? [b.max.x - b.min.x, b.max.y - b.min.y, b.max.z - b.min.z] : null;
}

const close = (a, b, tolerance) => a.every((v, i) => Math.abs(v - b[i]) <= tolerance);

// Exactly one mesh per call, or throw (never hide something ambiguous).
export function findReplacedPrimitives(objects, calls, {tolerance = 1e-4} = {}) {
  if (!Array.isArray(calls) || !calls.length) throw new Error('No replaced primitives listed');
  const used = new Set();
  return calls.map(call => {
    const want = parsePrimitiveCall(call);
    const found = objects.filter(o => o && o.isMesh && !used.has(o) && o.position &&
      close([o.position.x, o.position.y, o.position.z], want.position, tolerance) &&
      (() => { const s = localSize(o); return s && close(s, want.size, tolerance); })());
    if (found.length !== 1) throw new Error(`Expected one primitive for ${call}, found ${found.length}`);
    used.add(found[0]);
    return found[0];
  });
}

// Same list as the loaded sidecar? (A rebuilt sidecar for a moved fallback
// must not hide the wrong objects.)
export function sameCalls(sidecarCalls, expected) {
  const norm = list => (Array.isArray(list) ? list : []).map(s => String(s).trim());
  const a = norm(sidecarCalls), b = norm(expected);
  return a.length === b.length && a.every((s, i) => s === b[i]);
}
