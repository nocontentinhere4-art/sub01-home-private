// CPU-only format conversion. Never changes geometry, rig, captured motion or pixels.
import fs from 'node:fs';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import {MeshoptDecoder} from '../web/house/vendor/meshopt_decoder.module.js';
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
export function readGLB(path){
 const raw=fs.readFileSync(path);assert.equal(raw.toString('ascii',0,4),'glTF');assert.equal(raw.readUInt32LE(4),2);assert.equal(raw.readUInt32LE(8),raw.length);
 let doc,bin;for(let p=12;p<raw.length;){const size=raw.readUInt32LE(p),kind=raw.readUInt32LE(p+4),chunk=raw.subarray(p+8,p+8+size);if(kind===0x4e4f534a)doc=JSON.parse(chunk);if(kind===0x004e4942)bin=chunk;p+=8+size;}assert(doc&&bin);return{doc,bin,sha:hash(raw)};
}
export function writeGLB(path,doc,bin){
 const json=Buffer.from(JSON.stringify(doc));const jp=Buffer.concat([json,Buffer.alloc((-json.length)&3,32)]),bp=Buffer.concat([bin,Buffer.alloc((-bin.length)&3)]);
 const header=Buffer.alloc(12);header.write('glTF');header.writeUInt32LE(2,4);header.writeUInt32LE(28+jp.length+bp.length,8);
 const chunk=(data,kind)=>{const h=Buffer.alloc(8);h.writeUInt32LE(data.length);h.writeUInt32LE(kind,4);return Buffer.concat([h,data]);};
 fs.writeFileSync(path,Buffer.concat([header,chunk(jp,0x4e4f534a),chunk(bp,0x004e4942)]));
}
export async function viewBytes(file,index){
 const view=file.doc.bufferViews[index],c=view.extensions?.EXT_meshopt_compression;
 if(c){await MeshoptDecoder.ready;assert.equal(c.buffer,0);const result=Buffer.alloc(c.count*c.byteStride);MeshoptDecoder.decodeGltfBuffer(result,c.count,c.byteStride,file.bin.subarray(c.byteOffset,c.byteOffset+c.byteLength),c.mode,c.filter||'NONE');assert.equal(result.length,view.byteLength);return result;}
 assert.equal(view.buffer,0,'Unexpected external/nonexistent fallback buffer');return file.bin.subarray(view.byteOffset||0,(view.byteOffset||0)+view.byteLength);
}
export async function accessorHashes(file){
 const result=[],cache=new Map(),width={5120:1,5121:1,5122:2,5123:2,5125:4,5126:4},components={SCALAR:1,VEC2:2,VEC3:3,VEC4:4,MAT4:16};
 for(const a of file.doc.accessors||[]){
  assert(!a.sparse,'Sparse accessor must be explicitly expanded before conversion');assert(components[a.type]&&width[a.componentType],'Unsupported accessor packing');
  if(!cache.has(a.bufferView))cache.set(a.bufferView,await viewBytes(file,a.bufferView));const bytes=cache.get(a.bufferView),item=width[a.componentType]*components[a.type],stride=file.doc.bufferViews[a.bufferView].byteStride||item;
  const logical=Buffer.alloc(a.count*item);for(let i=0;i<a.count;i++){const start=(a.byteOffset||0)+i*stride;assert(start+item<=bytes.length);bytes.copy(logical,i*item,start,start+item);}
  result.push({type:a.type,componentType:a.componentType,count:a.count,normalized:!!a.normalized,sha256:hash(logical)});
 }return result;
}
const imagePython=[
 "import sys,io,json,hashlib,struct",
 "from PIL import Image",
 "image=Image.open(io.BytesIO(sys.stdin.buffer.read()))",
 "rgba=image.convert('RGBA')",
 "output=io.BytesIO();rgba.save(output,format='PNG')",
 "roundtrip=Image.open(io.BytesIO(output.getvalue())).convert('RGBA')",
 "assert rgba.tobytes()==roundtrip.tobytes()",
 "meta=json.dumps({'width':rgba.width,'height':rgba.height,'decoded_rgba_sha256':hashlib.sha256(rgba.tobytes()).hexdigest()}).encode()",
 "sys.stdout.buffer.write(struct.pack('<I',len(meta))+meta+output.getvalue())",
].join('\n');
export async function uncompress(input,output,{imageInterpreter='python3'}={}){
 const file=readGLB(input),before=await accessorHashes(file),doc=structuredClone(file.doc),views=[],images=[],chunks=[];let size=0,decodedViews=0;
 for(let i=0;i<doc.bufferViews.length;i++){const bytes=await viewBytes(file,i),view=doc.bufferViews[i];if(view.extensions?.EXT_meshopt_compression)decodedViews++;
  views.push(bytes);if(view.extensions){delete view.extensions.EXT_meshopt_compression;if(!Object.keys(view.extensions).length)delete view.extensions;}}
 for(const [i,image]of (doc.images||[]).entries()){
  assert(image.bufferView!==undefined,'External images require explicit packaging');
  if(image.mimeType==='image/webp'){
   const p=spawnSync(imageInterpreter,['-c',imagePython],{input:views[image.bufferView],maxBuffer:64*1024*1024});assert.equal(p.status,0,'WebP lossless pixel conversion failed: '+p.stderr?.toString());
   const length=p.stdout.readUInt32LE(0),meta=JSON.parse(p.stdout.subarray(4,4+length));views[image.bufferView]=p.stdout.subarray(4+length);image.mimeType='image/png';images.push({image:i,...meta});
  }
 }
 for(const t of doc.textures||[]){const source=t.extensions?.EXT_texture_webp?.source;if(source!==undefined){t.source=source;delete t.extensions.EXT_texture_webp;if(!Object.keys(t.extensions).length)delete t.extensions;}}
 for(const key of ['extensionsUsed','extensionsRequired'])if(doc[key]){doc[key]=doc[key].filter(x=>!['EXT_meshopt_compression','EXT_texture_webp'].includes(x));if(!doc[key].length)delete doc[key];}
 for(const [i,view]of doc.bufferViews.entries()){const bytes=views[i];view.buffer=0;view.byteOffset=size;view.byteLength=bytes.length;chunks.push(bytes);size+=bytes.length;const pad=(-size)&3;if(pad){chunks.push(Buffer.alloc(pad));size+=pad;}}
 doc.buffers=[{byteLength:size}];writeGLB(output,doc,Buffer.concat(chunks));
 const decoded=readGLB(output),after=await accessorHashes(decoded);assert.deepEqual(after,before,'Geometry/joints/weights/IBM/motion accessor values changed');assert.deepEqual(doc.nodes,file.doc.nodes);assert.deepEqual(doc.skins,file.doc.skins);assert.deepEqual(doc.animations,file.doc.animations);assert.deepEqual(doc.meshes,file.doc.meshes);
 const audit={source_sha256:file.sha,output_sha256:decoded.sha,decoded_meshopt_views:decodedViews,accessors:before.length,all_accessor_values_unchanged:true,node_skin_animation_mesh_graphs_unchanged:true,lossless_webp_to_png:images,required_extensions:doc.extensionsRequired||[],scope:'Format conversion only; UE import/render/retarget/contact acceptance remains pending'};
 fs.writeFileSync(output+'.audit.json',JSON.stringify(audit,null,2)+'\n');return audit;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const [input,output,...options]=process.argv.slice(2);assert(input&&output,'Usage INPUT.glb OUTPUT.glb [--image-python PATH]');
 const p=options.indexOf('--image-python');const audit=await uncompress(input,output,{imageInterpreter:p>=0?options[p+1]:'python3'});console.log(JSON.stringify(audit));
}
