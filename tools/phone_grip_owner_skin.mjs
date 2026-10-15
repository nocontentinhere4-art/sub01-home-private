// Read-only owner skin data for tools/derive_phone_grip_clip.py (exact linear-blend skinning in numpy).
// Writes bind-space positions, four joint indices/weights per vertex, triangles, inverse bind matrices,
// bind/world matrices and the owner node hierarchy of the exact owner GLB. No geometry is changed.
import fs from 'node:fs';
import crypto from 'node:crypto';
import { register } from 'node:module';
const vendorThree = new URL('../web/house/vendor/three.module.js', import.meta.url).href;
register('data:text/javascript,' + encodeURIComponent(`export async function resolve(s,c,n){return s==='three'?{url:${JSON.stringify(vendorThree)},shortCircuit:true}:n(s,c);}`));
const T = await import('../web/house/vendor/three.module.js');
const { GLTFLoader } = await import('../web/house/vendor/GLTFLoader.js');
const { MeshoptDecoder } = await import('../web/house/vendor/meshopt_decoder.module.js');
globalThis.ProgressEvent ??= class { constructor(type, init) { Object.assign(this, init); } };

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith('--') ? a.push([v.slice(2), all[i + 1]]) : 0, a), []));
if (!args.owner || !args.out) throw new Error('--owner and --out required');
const input = fs.readFileSync(args.owner), jsonSize = input.readUInt32LE(12);
const data = JSON.parse(input.subarray(20, 20 + jsonSize).toString());
const nodes = data.nodes.map((n, i) => ({ index: i, name: n.name ?? '', children: n.children ?? [], translation: n.translation ?? [0, 0, 0], rotation: n.rotation ?? [0, 0, 0, 1], scale: n.scale ?? [1, 1, 1], mesh: n.mesh ?? null, skin: n.skin ?? null }));
data.materials = data.materials?.map(m => ({ name: m.name })); delete data.textures; delete data.images;
data.extensionsRequired = data.extensionsRequired?.filter(e => e !== 'EXT_texture_webp');
const json = Buffer.from(JSON.stringify(data)), padded = Buffer.alloc(Math.ceil(json.length / 4) * 4, 32); json.copy(padded);
const binary = input.subarray(20 + jsonSize), glb = Buffer.alloc(20 + padded.length + binary.length);
glb.writeUInt32LE(0x46546c67, 0); glb.writeUInt32LE(2, 4); glb.writeUInt32LE(glb.length, 8);
glb.writeUInt32LE(padded.length, 12); glb.writeUInt32LE(0x4e4f534a, 16); padded.copy(glb, 20); binary.copy(glb, 20 + padded.length);
const gltf = await new GLTFLoader().setMeshoptDecoder(MeshoptDecoder).parseAsync(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength), '');
gltf.scene.updateMatrixWorld(true);
const meshes = []; gltf.scene.traverse(o => { if (o.isSkinnedMesh) meshes.push(o); });
const bones = meshes[0].skeleton.bones;
for (const m of meshes) if (m.skeleton.bones.some((b, i) => b !== bones[i])) throw new Error('Meshes must share one skeleton');
let total = 0; const pos = [], idx = [], wts = [], tris = [], meshOf = [];
meshes.forEach((m, k) => {
  const g = m.geometry, p = g.attributes.position, si = g.attributes.skinIndex, sw = g.attributes.skinWeight;
  for (let i = 0; i < p.count; i++) {
    pos.push(p.getX(i), p.getY(i), p.getZ(i));
    for (let c = 0; c < 4; c++) { idx.push(si.getComponent(i, c)); wts.push(sw.getComponent(i, c)); }
    meshOf.push(k);
  }
  const n = g.index ? g.index.count : p.count;
  for (let i = 0; i < n; i++) tris.push(total + (g.index ? g.index.getX(i) : i));
  total += p.count;
});
const f32 = a => Buffer.from(new Float32Array(a).buffer), u16 = a => Buffer.from(new Uint16Array(a).buffer), u32 = a => Buffer.from(new Uint32Array(a).buffer), u8 = a => Buffer.from(new Uint8Array(a).buffer);
const bin = Buffer.concat([f32(pos), u16(idx), f32(wts), u32(tris), u8(meshOf)]);
fs.writeFileSync(args.out + '.bin', bin);
fs.writeFileSync(args.out + '.json', JSON.stringify({
  schema: 'sub01.owner-skin-data.v1', owner: args.owner, sha256: crypto.createHash('sha256').update(input).digest('hex'),
  vertices: total, triangles: tris.length / 3, meshes: meshes.map(m => m.name),
  meshWorld: meshes.map(m => m.matrixWorld.toArray()), bindMatrix: meshes.map(m => m.bindMatrix.toArray()),
  joints: bones.map(b => b.name), jointNodes: bones.map(b => nodes.findIndex(n => n.name.replace(/[^\w-]/g, '') === b.name || n.name === b.name)),
  boneInverses: meshes[0].skeleton.boneInverses.map(m => m.toArray()), nodes,
  layout: ['float32 bindPosition[v][3]', 'uint16 joint[v][4]', 'float32 weight[v][4]', 'uint32 triangle[t][3]', 'uint8 mesh[v]'],
  matrices: 'three.js column-major toArray()'
}));
console.log(JSON.stringify({ vertices: total, triangles: tris.length / 3, joints: bones.length }));
