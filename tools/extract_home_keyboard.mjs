// Extract the owner's existing CC0 keyboard without shipping or loading the old room.
import fs from "node:fs";
import * as T from "three";
import { GLTFLoader } from "../web/house/vendor/GLTFLoader.js";
import { GLTFExporter } from "../web/house/vendor/GLTFExporter.js";
import { MeshoptDecoder } from "../web/house/vendor/meshopt_decoder.module.js";
const data = fs.readFileSync("web/room/room_clean.glb");
const len = data.readUInt32LE(12),
  doc = JSON.parse(data.subarray(20, 20 + len));
function stripTextures(value) {
  if (!value || typeof value !== "object") return;
  for (const key of Object.keys(value)) {
    if (key.toLowerCase().includes("texture")) delete value[key];
    else stripTextures(value[key]);
  }
}
for (const m of doc.materials || []) stripTextures(m);
// Binary geometry remains pinned to the existing room; texture references are not needed for its coloured keys.
const json = Buffer.from(JSON.stringify(doc));
const padded = Buffer.alloc(Math.ceil(json.length / 4) * 4, 32);
json.copy(padded);
const bin = data.subarray(20 + len);
const header = Buffer.alloc(20);
header.write("glTF");
header.writeUInt32LE(2, 4);
header.writeUInt32LE(20 + padded.length + bin.length, 8);
header.writeUInt32LE(padded.length, 12);
header.write("JSON", 16);
const rebuilt = Buffer.concat([header, padded, bin]);
const loader = new GLTFLoader();
loader.setMeshoptDecoder(MeshoptDecoder);
const gltf = await loader.parseAsync(
  rebuilt.buffer.slice(rebuilt.byteOffset, rebuilt.byteOffset + rebuilt.length),
  "",
);
gltf.scene.updateMatrixWorld(true);
const source = gltf.scene.getObjectByName("room_static");
if (!source) throw new Error("Missing room_static source");
const box = new T.Box3(
  new T.Vector3(-1.26, 0.9725, -1.055),
  new T.Vector3(-0.88, 1.012, -0.885),
);
const point = new T.Vector3(),
  result = new T.Group();
let triangles = 0;
source.traverse((mesh) => {
  if (!mesh.isMesh || !mesh.geometry.index) return;
  const g = mesh.geometry,
    p = g.attributes.position,
    ix = g.index,
    selected = [];
  const inside = (i) =>
    box.containsPoint(
      point.fromBufferAttribute(p, i).applyMatrix4(mesh.matrixWorld),
    );
  for (let t = 0; t < ix.count; t += 3) {
    const ids = [ix.getX(t), ix.getX(t + 1), ix.getX(t + 2)];
    if (ids.every(inside)) selected.push(...ids);
  }
  if (!selected.length) return;
  const ids = [...new Set(selected)],
    remap = new Map(ids.map((id, i) => [id, i])),
    out = new T.BufferGeometry();
  for (const [key, attribute] of Object.entries(g.attributes)) {
    const array = new Float32Array(ids.length * attribute.itemSize),
      get = ["getX", "getY", "getZ", "getW"];
    for (let i = 0; i < ids.length; i++)
      for (let j = 0; j < attribute.itemSize; j++)
        array[i * attribute.itemSize + j] = attribute[get[j]](ids[i]);
    out.setAttribute(key, new T.BufferAttribute(array, attribute.itemSize));
  }
  out.setIndex(selected.map((i) => remap.get(i)));
  out.applyMatrix4(mesh.matrixWorld);
  result.add(new T.Mesh(out, mesh.material));
  triangles += selected.length / 3;
});
const bounds = new T.Box3().setFromObject(result),
  size = bounds.getSize(new T.Vector3()),
  center = bounds.getCenter(new T.Vector3());
if (
  triangles < 100 ||
  size.x < 0.3 ||
  size.x > 0.4 ||
  size.y > 0.05 ||
  size.z > 0.18
)
  throw new Error("Keyboard extraction bounds are wrong");
for (const child of result.children)
  child.geometry.translate(-center.x, -bounds.min.y, -center.z);
class Reader {
  readAsArrayBuffer(blob) {
    blob.arrayBuffer().then((b) => {
      this.result = b;
      this.onloadend?.();
    });
  }
}
globalThis.FileReader = Reader;
const out = await new GLTFExporter().parseAsync(result, { binary: true });
fs.mkdirSync("web/house/assets/keyboard", { recursive: true });
fs.writeFileSync("web/house/assets/keyboard/keyboard.glb", Buffer.from(out));
console.log(
  "Keyboard extracted:",
  triangles,
  "triangles,",
  size.toArray(),
  "metres,",
  out.byteLength,
  "bytes",
);
