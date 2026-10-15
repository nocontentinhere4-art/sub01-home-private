// Offline interchange with an independently installed CozyClay studio.
// This does not generate motion or assert hand contact / native acceptance.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';

const args=process.argv.slice(2);
const inPlace=args.at(-1)==='--in-place';if(inPlace)args.pop();
assert.equal(args.length,4,'Usage: node tools/bake_cozy_motion.mjs COZY_PACKAGE MOTION.npz OWNER.glb OUT.glb');
const [cozy,motionPath,ownerPath,outPath]=args.map(p=>path.resolve(p));
const moduleAt=p=>import(pathToFileURL(path.join(cozy,p)).href);
const THREE=await moduleAt('node_modules/three/build/three.module.js');
const {decodeMotionNpz}=await moduleAt('src/ardy/npz.js');
const {applyMotionFrame,prepOf}=await moduleAt('src/ardy/playback.js');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const raw=fs.readFileSync(ownerPath),motionRaw=fs.readFileSync(motionPath);
assert.equal(raw.toString('ascii',0,4),'glTF');
assert.equal(raw.readUInt32LE(4),2);assert.equal(raw.readUInt32LE(8),raw.length);
let doc,bin;
for(let o=12;o<raw.length;){
 const length=raw.readUInt32LE(o),kind=raw.readUInt32LE(o+4),data=raw.subarray(o+8,o+8+length);
 if(kind===0x4e4f534a)doc=JSON.parse(data.toString());
 else if(kind===0x004e4942)bin=data;
 else throw new Error('Unexpected GLB chunk');
 o+=8+length;
}
assert(doc&&bin&&!doc.buffers[0].uri,'Require self-contained owner GLB');
assert(doc.buffers.slice(1).every(b=>!b.uri&&b.extensions?.EXT_meshopt_compression?.fallback===true),'Unexpected external/additional owner buffer');
const joints=new Set(doc.skins.flatMap(s=>s.joints));
const nodes=doc.nodes.map((n,i)=>{
 const o=joints.has(i)?new THREE.Bone():new THREE.Object3D();o.name=n.name||`node${i}`;
 if(n.matrix)new THREE.Matrix4().fromArray(n.matrix).decompose(o.position,o.quaternion,o.scale);
 else {o.position.fromArray(n.translation||[0,0,0]);o.quaternion.fromArray(n.rotation||[0,0,0,1]);o.scale.fromArray(n.scale||[1,1,1]);}
 assert(o.position.toArray().concat(o.quaternion.toArray(),o.scale.toArray()).every(Number.isFinite));
 return o;
});
doc.nodes.forEach((n,i)=>(n.children||[]).forEach(c=>nodes[i].add(nodes[c])));
const hips=nodes.find(n=>n.name.replace(/^mixamorig[:_]?/i,'')==='Hips');
assert(hips?.parent,'Owner has no skeletal root');
const rig=hips.parent,bind=new Map();
rig.traverse(o=>{if(o.isBone)bind.set(o,{x:o.quaternion.x,y:o.quaternion.y,z:o.quaternion.z,w:o.quaternion.w,position:o.position.clone()});});
rig.userData.poseBind=bind;
const initial=nodes.map(n=>({p:n.position.clone(),q:n.quaternion.clone(),s:n.scale.clone()}));
const motion=await decodeMotionNpz(motionRaw);
assert(motion.frames>=2&&motion.frames<=24000);
const prep=prepOf(rig),mapped=new Set(prep.bones.filter(Boolean));
assert(rig.quaternion.angleTo(new THREE.Quaternion())<1e-6,'In-place yaw requires an unrotated owner skeletal container');
assert.equal(mapped.size,20,'Unexpected CozyClay mapping: review upstream before baking');
const index=new Map(nodes.map((n,i)=>[n,i]));
const affected=[...mapped].map(n=>index.get(n));
const rotations=new Map(affected.map(i=>[i,[]])),translations=new Map(affected.map(i=>[i,[]]));
let maxFingerLocalChange=0,maxUnmappedLocalChange=0,maxQuaternionNormError=0;
for(let frame=0;frame<motion.frames;frame++){
 applyMotionFrame(rig,motion,frame);
 if(inPlace){
  // Physical CharacterMovement owns travel and heading in the home. Remove
  // source horizontal root travel/yaw, while retaining vertical gait motion.
  const r=frame*27*9,yaw=Math.atan2(motion.rotMats[r+2],motion.rotMats[r+8]);
  hips.position.x=initial[index.get(hips)].p.x;hips.position.z=initial[index.get(hips)].p.z;
  hips.quaternion.premultiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),-yaw));
 }
 for(const i of affected){
  const n=nodes[i],q=n.quaternion.toArray(),t=n.position.toArray();
  assert(q.concat(t).every(Number.isFinite),'Nonfinite baked transform');
  maxQuaternionNormError=Math.max(maxQuaternionNormError,Math.abs(n.quaternion.length()-1));
  if(frame){const previous=rotations.get(i).slice(-4);if(previous.reduce((s,v,j)=>s+v*q[j],0)<0)for(let j=0;j<4;j++)q[j]*=-1;}
  rotations.get(i).push(...q);translations.get(i).push(...t);
 }
 for(const i of joints){
  if(mapped.has(nodes[i]))continue;
  const n=nodes[i],before=initial[i],delta=n.position.distanceTo(before.p)+n.quaternion.angleTo(before.q)+n.scale.distanceTo(before.s);
  maxUnmappedLocalChange=Math.max(maxUnmappedLocalChange,delta);
  if(/Hand(Thumb|Index|Middle|Ring|Pinky)/.test(n.name))maxFingerLocalChange=Math.max(maxFingerLocalChange,delta);
 }
}
assert(maxUnmappedLocalChange<1e-6,'Upstream modified an unmapped local transform; explicit adapter review required');
assert(maxQuaternionNormError<1e-5,'Nonunit baked quaternion');
const pieces=[bin];let offset=bin.length;
doc.bufferViews??=[];doc.accessors??=[];
function append(values,type,min,max){
 const bytes=Buffer.alloc(values.length*4);values.forEach((v,i)=>bytes.writeFloatLE(v,i*4));
 const view=doc.bufferViews.length;doc.bufferViews.push({buffer:0,byteOffset:offset,byteLength:bytes.length});pieces.push(bytes);offset+=bytes.length;
 const accessor=doc.accessors.length,item={bufferView:view,componentType:5126,count:values.length/({SCALAR:1,VEC3:3,VEC4:4}[type]),type};
 if(min)item.min=min;if(max)item.max=max;doc.accessors.push(item);return accessor;
}
const times=Array.from({length:motion.frames},(_,f)=>f/motion.fps),input=append(times,'SCALAR',[0],[times.at(-1)]);
const animation={name:'CozyClay body candidate — hands require separate contact layer',samplers:[],channels:[],extras:{motionSourceSha256:hash(motionRaw),nativeAccepted:false,handContactAccepted:false}};
for(const i of affected)for(const [targetPath,type,values]of[['rotation','VEC4',rotations.get(i)],['translation','VEC3',translations.get(i)]]){
 const sampler=animation.samplers.length;animation.samplers.push({input,output:append(values,type),interpolation:'LINEAR'});animation.channels.push({sampler,target:{node:i,path:targetPath}});
}
doc.animations=[animation];doc.buffers[0].byteLength=offset;
const binary=Buffer.concat(pieces),json=Buffer.from(JSON.stringify(doc)),padded=Buffer.concat([json,Buffer.alloc((4-json.length%4)%4,0x20)]);
const header=Buffer.alloc(20),bh=Buffer.alloc(8);header.write('glTF');header.writeUInt32LE(2,4);header.writeUInt32LE(28+padded.length+binary.length,8);header.writeUInt32LE(padded.length,12);header.writeUInt32LE(0x4e4f534a,16);bh.writeUInt32LE(binary.length);bh.writeUInt32LE(0x004e4942,4);
const output=Buffer.concat([header,padded,bh,binary]);assert.equal(output.length,output.readUInt32LE(8));
assert(output.subarray(28+padded.length,28+padded.length+bin.length).equals(bin),'Original mesh/skin/image bytes changed');
fs.mkdirSync(path.dirname(outPath),{recursive:true});fs.writeFileSync(outPath,output);
const report={schema:'sub01.cozy-body-candidate.v1',cozyVersion:JSON.parse(fs.readFileSync(path.join(cozy,'package.json'))).version,motionSha256:hash(motionRaw),ownerSha256:hash(raw),outputSha256:hash(output),frames:motion.frames,fps:motion.fps,durationSeconds:times.at(-1),mappedBodyBones:affected.map(i=>nodes[i].name),originalMeshSkinAndTextureBinaryPreserved:true,originalNodeRestTransformsPreserved:true,maxUnmappedLocalChange,maxFingerLocalChange,maxQuaternionNormError,wristAndFingerMotionGenerated:false,handContactAccepted:false,nativeImported:false,nativeVisualAccepted:false,source:'CozyClay upstream playback, external package retained under its own license',limitations:['CozyClay cskel27 playback intentionally leaves wrists and fingers in their reference pose','A passing interchange check is not acceptance of the rendered character or native interaction','Root trajectory must be aligned to measured house waypoints and physical navigation before runtime use']};
report.rootMotionPolicy=inPlace?'in-place XZ/yaw, physical CharacterMovement must own world travel':'original source trajectory, review only';
fs.writeFileSync(outPath+'.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
