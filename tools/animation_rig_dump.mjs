// CPU-only, read-only dump of a GLB rig for tools/animation_rig_audit.py.
// Decodes EXT_meshopt_compression with the vendored decoder; never writes into the repository
// unless explicitly told to. Output: nodes (name, parent, children, raw TRS/matrix), skins
// (joints + inverse bind matrices) and every animation channel (times + values, decoded floats).
// node tools/animation_rig_dump.mjs INPUT.glb OUTPUT.json
import fs from 'node:fs';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {MeshoptDecoder} from '../web/house/vendor/meshopt_decoder.module.js';

await MeshoptDecoder.ready;

function readGLB(path) {
  const raw = fs.readFileSync(path);
  assert.equal(raw.toString('ascii', 0, 4), 'glTF');
  assert.equal(raw.readUInt32LE(4), 2);
  let doc, bin;
  for (let p = 12; p < raw.length;) {
    const size = raw.readUInt32LE(p), kind = raw.readUInt32LE(p + 4), chunk = raw.subarray(p + 8, p + 8 + size);
    if (kind === 0x4e4f534a) doc = JSON.parse(chunk.toString());
    if (kind === 0x004e4942) bin = chunk;
    p += 8 + size;
  }
  assert(doc, 'Missing JSON chunk');
  return {doc, bin, sha256: crypto.createHash('sha256').update(raw).digest('hex'), cache: new Map()};
}

function viewBytes(file, index) {
  if (file.cache.has(index)) return file.cache.get(index);
  const view = file.doc.bufferViews[index], c = view.extensions?.EXT_meshopt_compression;
  let bytes;
  if (c) {
    assert.equal(c.buffer, 0, 'External compressed buffers unsupported');
    bytes = Buffer.alloc(c.count * c.byteStride);
    MeshoptDecoder.decodeGltfBuffer(bytes, c.count, c.byteStride, file.bin.subarray(c.byteOffset || 0, (c.byteOffset || 0) + c.byteLength), c.mode, c.filter || 'NONE');
  } else {
    assert.equal(view.buffer, 0, 'External buffers unsupported');
    bytes = file.bin.subarray(view.byteOffset || 0, (view.byteOffset || 0) + view.byteLength);
  }
  file.cache.set(index, bytes);
  return bytes;
}

function accessor(file, index) {
  const a = file.doc.accessors[index];
  assert(!a.sparse, 'Sparse accessor unsupported');
  const n = {SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT4: 16}[a.type];
  const reader = {5126: ['readFloatLE', 4, 0], 5122: ['readInt16LE', 2, 32767], 5120: ['readInt8', 1, 127],
    5123: ['readUInt16LE', 2, 65535], 5121: ['readUInt8', 1, 255]}[a.componentType];
  assert(reader, 'Unsupported component type ' + a.componentType);
  const [fn, size, norm] = reader;
  const bytes = viewBytes(file, a.bufferView), stride = file.doc.bufferViews[a.bufferView].byteStride || n * size;
  const out = [];
  for (let i = 0; i < a.count; i++) {
    const v = [];
    for (let j = 0; j < n; j++) {
      let x = bytes[fn]((a.byteOffset || 0) + i * stride + j * size);
      if (norm && a.normalized) x = Math.max(x / norm, -1);
      v.push(x);
    }
    assert(v.every(Number.isFinite), 'Non-finite accessor value');
    out.push(v);
  }
  return out;
}

const [input, output] = process.argv.slice(2);
assert(input && output, 'Usage: node tools/animation_rig_dump.mjs INPUT.glb OUTPUT.json');
const file = readGLB(input), doc = file.doc;
const parents = new Map();
(doc.nodes || []).forEach((n, i) => (n.children || []).forEach(c => parents.set(c, i)));
const result = {
  source: input,
  sha256: file.sha256,
  extensionsUsed: doc.extensionsUsed || [],
  sceneRoots: doc.scenes?.[doc.scene || 0]?.nodes || [],
  nodes: (doc.nodes || []).map((n, i) => ({
    name: n.name || '', parent: parents.has(i) ? parents.get(i) : null, children: n.children || [],
    translation: n.translation || null, rotation: n.rotation || null, scale: n.scale || null, matrix: n.matrix || null,
    mesh: n.mesh ?? null, skin: n.skin ?? null,
  })),
  skins: (doc.skins || []).map(s => ({joints: s.joints, skeleton: s.skeleton ?? null,
    inverseBindMatrices: s.inverseBindMatrices === undefined ? null : accessor(file, s.inverseBindMatrices)})),
  animations: (doc.animations || []).map(a => ({
    name: a.name || '',
    channels: a.channels.map(c => {
      const s = a.samplers[c.sampler];
      return {node: c.target.node, path: c.target.path, interpolation: s.interpolation || 'LINEAR',
        times: accessor(file, s.input).map(v => v[0]), values: accessor(file, s.output)};
    }),
  })),
};
// Optional: --vertices REGEX dumps bind-space vertices of skinned meshes whose dominant joint name
// matches REGEX (position, 4 joint node indices, 4 weights). Geometry is only read, never changed.
const vi = process.argv.indexOf('--vertices');
if (vi > 0) {
  const pattern = new RegExp(process.argv[vi + 1]);
  result.skinVertices = [];
  (doc.nodes || []).forEach((n, nodeIndex) => {
    if (n.skin === undefined || n.mesh === undefined) return;
    const joints = doc.skins[n.skin].joints;
    doc.meshes[n.mesh].primitives.forEach(p => {
      if (p.attributes.JOINTS_0 === undefined) return;
      const pos = accessor(file, p.attributes.POSITION), js = accessor(file, p.attributes.JOINTS_0), ws = accessor(file, p.attributes.WEIGHTS_0);
      for (let i = 0; i < pos.length; i++) {
        let best = 0;
        for (let k = 1; k < 4; k++) if (ws[i][k] > ws[i][best]) best = k;
        const dominant = joints[js[i][best]];
        if (!pattern.test(doc.nodes[dominant].name || '')) continue;
        result.skinVertices.push({mesh: nodeIndex, p: pos[i], j: js[i].map(x => joints[x]), w: ws[i]});
      }
    });
  });
}
fs.writeFileSync(output, JSON.stringify(result));
console.log(JSON.stringify({input, output, nodes: result.nodes.length, skins: result.skins.length,
  animations: result.animations.map(a => [a.name, a.channels.length])}));
