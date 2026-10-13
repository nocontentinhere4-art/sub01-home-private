import { readFile } from 'node:fs/promises';
import { GLTFLoader } from '../../web/house/vendor/GLTFLoader.js';
import { MeshoptDecoder } from '../../web/house/vendor/meshopt_decoder.module.js';
// CPU-load production meshes and captures, omitting only browser image decoding.
// The compressed geometry, inverse binds, transforms and animation stay intact.
globalThis.ProgressEvent ??= class { constructor(type, init) { Object.assign(this, init); } };
const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
export async function productionGlb(url) {
  const input = await readFile(new URL(url.startsWith('/room/') || url.startsWith('/house/') ? '../../web' + url : '../../' + url, import.meta.url));
  const jsonSize = input.readUInt32LE(12);
  const data = JSON.parse(input.subarray(20, 20 + jsonSize).toString());
  data.materials = data.materials?.map(() => ({}));
  delete data.textures; delete data.images;
  data.extensionsRequired = data.extensionsRequired?.filter(e => e !== 'EXT_texture_webp');
  const json = Buffer.from(JSON.stringify(data));
  const padded = Buffer.alloc(Math.ceil(json.length / 4) * 4, 32); json.copy(padded);
  const binary = input.subarray(20 + jsonSize);
  const glb = Buffer.alloc(20 + padded.length + binary.length);
  glb.writeUInt32LE(0x46546c67, 0); glb.writeUInt32LE(2, 4); glb.writeUInt32LE(glb.length, 8);
  glb.writeUInt32LE(padded.length, 12); glb.writeUInt32LE(0x4e4f534a, 16);
  padded.copy(glb, 20); binary.copy(glb, 20 + padded.length);
  return loader.parseAsync(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength), '');
}
