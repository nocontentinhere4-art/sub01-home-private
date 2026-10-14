// Read-only skin export for the private phone grip solver (tools/fit_phone_grip.py).
// Skins EVERY vertex of EVERY skinned primitive of the exact owner GLB with the exact
// captured clip (no retime, no finger/bone edit), then keeps the vertices that come within
// --radius cm of the right wrist on ANY sampled frame. The radius is a geometric reach bound,
// never a name filter. Coordinates are owner model-space centimetres expressed in the
// right-hand joint frame (rotation orthonormalised, joint scale excluded).
import fs from 'node:fs';
import crypto from 'node:crypto';
import { register } from 'node:module';
// Resolve the vendored loader's bare 'three' import to the same vendored build (no npm copy).
const vendorThree = new URL('../web/house/vendor/three.module.js', import.meta.url).href;
register('data:text/javascript,' + encodeURIComponent(`export async function resolve(s,c,n){return s==='three'?{url:${JSON.stringify(vendorThree)},shortCircuit:true}:n(s,c);}`));
const T = await import('../web/house/vendor/three.module.js');
const { GLTFLoader } = await import('../web/house/vendor/GLTFLoader.js');
const { MeshoptDecoder } = await import('../web/house/vendor/meshopt_decoder.module.js');

globalThis.ProgressEvent ??= class { constructor(type, init) { Object.assign(this, init); } };
const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith('--') ? a.push([v.slice(2), all[i + 1]]) : 0, a), []));
for (const key of ['owner', 'clip', 'out']) if (!args[key]) throw new Error(`--${key} required`);
const radius = Number(args.radius ?? 40), fps = Number(args.fps ?? 30), poseTime = Number(args['pose-time'] ?? 4);
if (!(radius > 0 && radius <= 80 && fps > 0 && fps <= 60 && Number.isFinite(poseTime))) throw new Error('Bounded radius/fps/pose time required');

const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
async function load(path) {
  // Geometry, inverse binds, transforms and animation are untouched; only image decoding is skipped.
  const input = fs.readFileSync(path), jsonSize = input.readUInt32LE(12);
  const data = JSON.parse(input.subarray(20, 20 + jsonSize).toString());
  data.materials = data.materials?.map(m => ({ name: m.name }));
  delete data.textures; delete data.images;
  data.extensionsRequired = data.extensionsRequired?.filter(e => e !== 'EXT_texture_webp');
  const json = Buffer.from(JSON.stringify(data)), padded = Buffer.alloc(Math.ceil(json.length / 4) * 4, 32); json.copy(padded);
  const binary = input.subarray(20 + jsonSize), glb = Buffer.alloc(20 + padded.length + binary.length);
  glb.writeUInt32LE(0x46546c67, 0); glb.writeUInt32LE(2, 4); glb.writeUInt32LE(glb.length, 8);
  glb.writeUInt32LE(padded.length, 12); glb.writeUInt32LE(0x4e4f534a, 16); padded.copy(glb, 20); binary.copy(glb, 20 + padded.length);
  return { gltf: await loader.parseAsync(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength), ''), sha256: sha(input) };
}

const owner = await load(args.owner), capture = await load(args.clip);
if (capture.gltf.animations.length !== 1) throw new Error('Exactly one captured clip required');
const clip = capture.gltf.animations[0], scene = owner.gltf.scene;
const mixer = new T.AnimationMixer(scene); mixer.clipAction(clip).play();
const bound = clip.tracks.filter(t => scene.getObjectByName(t.name.split('.')[0])).length;
if (bound !== clip.tracks.length) throw new Error(`Clip tracks not bound to owner joints ${bound}/${clip.tracks.length}`);
const joint = n => { const o = scene.getObjectByName('mixamorig' + n); if (!o) throw new Error('Missing joint ' + n); return o; };
const wristJoint = joint('RightHand'), headJoint = joint('Head'), armJoints = ['RightShoulder', 'RightArm', 'RightForeArm'].map(joint);
const meshes = []; scene.traverse(o => { if (o.isSkinnedMesh) meshes.push(o); });
if (!meshes.length) throw new Error('No skinned owner mesh');

const times = []; for (let f = 0; f * (1 / fps) < clip.duration - 1e-6; f++) times.push(f / fps);
if (!times.some(t => Math.abs(t - poseTime) < 1e-6) && poseTime <= clip.duration) times.push(poseTime);
times.sort((a, b) => a - b);

// Frame of a joint in model-space cm: rotation (orthonormal) and origin.
function frameOf(o) {
  o.updateWorldMatrix(true, false);
  const p = new T.Vector3(), q = new T.Quaternion(), s = new T.Vector3();
  o.matrixWorld.decompose(p, q, s);
  return { position: p.multiplyScalar(100), quaternion: q.normalize() };
}
// Dominant influence label per vertex: reporting only, never a contact claim.
const jointNames = meshes[0].skeleton.bones.map(b => b.name);
for (const m of meshes) if (m.skeleton.bones.map(b => b.name).join() !== jointNames.join()) throw new Error('Mixed skeletons');

const offsets = []; let total = 0;
for (const m of meshes) { offsets.push(total); total += m.geometry.attributes.position.count; }
const perFrame = [], wrists = [], heads = [], arms = [], v = new T.Vector3();
const keep = new Uint8Array(total);
for (const t of times) {
  mixer.setTime(t); scene.updateMatrixWorld(true);
  for (const m of meshes) m.skeleton.update();
  const w = frameOf(wristJoint), inv = w.quaternion.clone().invert();
  wrists.push({ time: t, position: w.position.toArray(), quaternion: w.quaternion.toArray() });
  arms.push(armJoints.map(j => frameOf(j).position.toArray()));
  const h = frameOf(headJoint); heads.push({ position: h.position.toArray(), quaternion: h.quaternion.toArray() });
  const out = new Float32Array(total * 3);
  meshes.forEach((m, k) => {
    const pos = m.geometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i); m.applyBoneTransform(i, v); v.applyMatrix4(m.matrixWorld).multiplyScalar(100);
      v.sub(w.position).applyQuaternion(inv);
      const g = offsets[k] + i; out.set([v.x, v.y, v.z], g * 3);
      if (v.length() <= radius) keep[g] = 1;
    }
  });
  perFrame.push(out);
}
const kept = []; for (let g = 0; g < total; g++) if (keep[g]) kept.push(g);
const remap = new Int32Array(total).fill(-1); kept.forEach((g, i) => { remap[g] = i; });
const triangles = [], labels = new Uint8Array(kept.length), meshIndex = new Uint8Array(kept.length);
meshes.forEach((m, k) => {
  const idx = m.geometry.index, sk = m.geometry.attributes.skinIndex, sw = m.geometry.attributes.skinWeight;
  for (let i = 0; i < m.geometry.attributes.position.count; i++) {
    const r = remap[offsets[k] + i]; if (r < 0) continue;
    let best = 0, bw = -1; for (let c = 0; c < 4; c++) if (sw.getComponent(i, c) > bw) { bw = sw.getComponent(i, c); best = sk.getComponent(i, c); }
    labels[r] = best; meshIndex[r] = k;
  }
  const n = idx ? idx.count : m.geometry.attributes.position.count;
  for (let i = 0; i < n; i += 3) {
    const a = idx ? idx.getX(i) : i, b = idx ? idx.getX(i + 1) : i + 1, c = idx ? idx.getX(i + 2) : i + 2;
    const ra = remap[offsets[k] + a], rb = remap[offsets[k] + b], rc = remap[offsets[k] + c];
    if (ra >= 0 && rb >= 0 && rc >= 0) triangles.push(ra, rb, rc);
  }
});
const positions = new Float32Array(times.length * kept.length * 3);
perFrame.forEach((frame, f) => kept.forEach((g, i) => positions.set(frame.subarray(g * 3, g * 3 + 3), (f * kept.length + i) * 3)));
const tri = new Uint32Array(triangles);
const bin = Buffer.concat([Buffer.from(positions.buffer), Buffer.from(tri.buffer), Buffer.from(labels.buffer), Buffer.from(meshIndex.buffer)]);
fs.writeFileSync(args.out + '.bin', bin);
fs.writeFileSync(args.out + '.json', JSON.stringify({
  schema: 'sub01.phone-grip-hand-export.v1', units: 'cm', frame: 'owner model space expressed in right-hand joint frame',
  owner: { path: args.owner, sha256: owner.sha256, meshes: meshes.map(m => m.name), vertices: total },
  clip: { path: args.clip, sha256: capture.sha256, name: clip.name, duration: clip.duration, tracks: clip.tracks.length },
  radiusCm: radius, fps, poseTime, times, frames: times.length, vertices: kept.length, triangles: tri.length / 3,
  joints: jointNames, wrists, heads, arms, armJoints: ['RightShoulder', 'RightArm', 'RightForeArm'], binarySha256: sha(bin),
  layout: ['float32 positions[frames][vertices][3]', 'uint32 triangles[triangles][3]', 'uint8 dominantJoint[vertices]', 'uint8 meshIndex[vertices]'],
  modified: { bones: false, fingers: false, clip: false }
}));
console.log(JSON.stringify({ frames: times.length, vertices: kept.length, triangles: tri.length / 3, total }));
