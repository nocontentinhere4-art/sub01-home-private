// Recorded motion relative to an explicitly reviewed relaxed baseline.
// Does not infer contact, repair weights, or certify a natural deformation.
import fs from 'node:fs';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {Quaternion} from '../web/house/vendor/three.core.js';

const Q=v=>{
 assert(v.length===4&&v.every(Number.isFinite),'Finite XYZW quaternion required');
 const q=new Quaternion().fromArray(v);assert(q.lengthSq()>1e-12,'Zero quaternion cannot define a joint frame');
 return q.normalize();
};
const key=n=>(n||'').replace(/^mixamorig[:_]?/i,'');
const selected=n=>/^(Left|Right)Hand(?:(?:Thumb|Index|Middle|Ring|Pinky)[1-4])?$/.test(key(n));
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');

export function relativeHandRotation(targetRest, sourceBaseline, sourcePose, sourceBaselineWorld, targetRestWorld){
 const axis=Q(targetRestWorld).invert().multiply(Q(sourceBaselineWorld));
 const delta=Q(sourceBaseline).invert().multiply(Q(sourcePose));
 return Q(targetRest).multiply(axis).multiply(delta).multiply(axis.clone().invert()).normalize().toArray();
}

function read(file){
 const raw=fs.readFileSync(file);assert.equal(raw.toString('ascii',0,4),'glTF');
 assert.equal(raw.readUInt32LE(4),2);assert.equal(raw.readUInt32LE(8),raw.length);
 let doc,bin;
 for(let p=12;p<raw.length;){const size=raw.readUInt32LE(p),type=raw.readUInt32LE(p+4);
  assert(p+8+size<=raw.length);const data=raw.subarray(p+8,p+8+size);
  if(type===0x4e4f534a)doc=JSON.parse(data.toString());else if(type===0x004e4942)bin=data;
  else throw Error('Unsupported GLB chunk');p+=8+size;
 }
 assert(doc&&bin&&doc.buffers.length===1&&!doc.buffers[0].uri,'Self-contained decoded GLB required');
 assert(!doc.extensionsRequired?.length,'Decode required extensions first');
 assert(doc.nodes.every(n=>!n.matrix),'Export explicit node TRS first; matrix nodes need reviewed decomposition');
 const parents=new Map();doc.nodes.forEach((n,i)=>(n.children||[]).forEach(c=>{assert(!parents.has(c),'Multiple parents');parents.set(c,i);}));
 const names=new Map();doc.nodes.forEach((n,i)=>{if(selected(n.name)){assert(!names.has(key(n.name)),'Duplicate hand name');names.set(key(n.name),i);}});
 return {raw,doc,bin,parents,names};
}
function accessor(f,i){
 const a=f.doc.accessors[i],v=f.doc.bufferViews[a.bufferView],width={SCALAR:1,VEC4:4}[a.type];
 assert(width&&a.componentType===5126&&!a.sparse&&!v.extensions&&v.buffer===0,'Decoded float accessor required');
 const start=(v.byteOffset||0)+(a.byteOffset||0),stride=v.byteStride||width*4;
 assert(start+(a.count-1)*stride+width*4<=f.bin.length);
 return Array.from({length:a.count},(_,j)=>Array.from({length:width},(_,k)=>{
  const x=f.bin.readFloatLE(start+j*stride+k*4);assert(Number.isFinite(x));return x;
 }));
}
function worldRotations(f,local){
 const cache=new Map(),visiting=new Set();
 function get(i){if(cache.has(i))return cache.get(i);assert(!visiting.has(i),'Cyclic hierarchy');visiting.add(i);
  const scale=f.doc.nodes[i].scale||[1,1,1];
  assert(scale.every(x=>x>0)&&Math.max(...scale)-Math.min(...scale)<1e-6,'Nonuniform or reflected rest frame unsupported');
  const q=f.parents.has(i)?get(f.parents.get(i)).clone().multiply(Q(local[i])):Q(local[i]);
  cache.set(i,q.normalize());visiting.delete(i);return q;
 }return f.doc.nodes.map((_,i)=>get(i).toArray());
}
function sample(track,time){
 const {times,values}=track;let hi=times.findIndex(t=>t>=time);if(hi<0)return values.at(-1);
 if(hi===0||times[hi]===time)return values[hi];const lo=hi-1;
 return Q(values[lo]).slerp(Q(values[hi]),(time-times[lo])/(times[hi]-times[lo])).toArray();
}
export function retarget(sourcePath,targetPath,outPath,baselineSeconds){
 assert(Number.isFinite(baselineSeconds)&&baselineSeconds>=0,'An explicit reviewed baseline time is required');
 const src=read(sourcePath),dst=read(targetPath),animation=src.doc.animations?.[0];assert(animation,'Source has no clip');
 const tracks=new Map();
 for(const ch of animation.channels){if(ch.target.path!=='rotation')continue;
  const s=animation.samplers[ch.sampler];assert(['LINEAR',undefined].includes(s.interpolation));
  const times=accessor(src,s.input).map(x=>x[0]),values=accessor(src,s.output);
  assert(values.length===times.length&&values.every(q=>q.length===4&&Math.abs(Q(q).length()-1)<1e-6));
  assert(times.length>0&&times.every((x,i)=>x>=0&&(!i||x>times[i-1])),'Invalid sample times');
  assert(!tracks.has(ch.target.node),'Duplicate rotation track');tracks.set(ch.target.node,{times,values});
 }
 const baselineLocal=src.doc.nodes.map((n,i)=>tracks.has(i)?sample(tracks.get(i),baselineSeconds):(n.rotation||[0,0,0,1]));
 const targetLocal=dst.doc.nodes.map(n=>n.rotation||[0,0,0,1]);
 const srcWorld=worldRotations(src,baselineLocal),dstWorld=worldRotations(dst,targetLocal);
 const rows=[],newAnim={name:'Recorded hand variation relative to reviewed relaxed baseline',channels:[],samplers:[],extras:{baselineSeconds,nativeAccepted:false,contactAccepted:false}};
 const parts=[dst.bin];let offset=dst.bin.length;
 function append(values,type){const width=type==='SCALAR'?1:4,flat=values.flat(),bytes=Buffer.alloc(flat.length*4);
  flat.forEach((v,i)=>bytes.writeFloatLE(v,i*4));const vi=dst.doc.bufferViews.length;
  dst.doc.bufferViews.push({buffer:0,byteOffset:offset,byteLength:bytes.length});parts.push(bytes);offset+=bytes.length;
  const ai=dst.doc.accessors.length;dst.doc.accessors.push({bufferView:vi,componentType:5126,count:flat.length/width,type,...(type==='SCALAR'?{min:[flat[0]],max:[flat.at(-1)]}:{})});return ai;
 }
 for(const [name,si] of src.names){
  if(!tracks.has(si))continue;const ti=dst.names.get(name);assert(ti!==undefined,'Missing target '+name);
  const tr=tracks.get(si);assert(baselineSeconds>=tr.times[0]&&baselineSeconds<=tr.times.at(-1),'Baseline outside '+name);
  let previous;const values=tr.values.map(q=>{
   const out=Q(relativeHandRotation(targetLocal[ti],baselineLocal[si],q,srcWorld[si],dstWorld[ti]));
   if(previous&&previous.dot(out)<0)out.set(-out.x,-out.y,-out.z,-out.w);previous=out;return out.toArray();
  });
  const baselineError=Q(relativeHandRotation(targetLocal[ti],baselineLocal[si],baselineLocal[si],srcWorld[si],dstWorld[ti])).angleTo(Q(targetLocal[ti]));
  assert(baselineError<1e-6,'Baseline must preserve actual new rest pose');
  const input=append(tr.times,'SCALAR'),output=append(values,'VEC4'),sampler=newAnim.samplers.length;
  newAnim.samplers.push({input,output,interpolation:'LINEAR'});newAnim.channels.push({sampler,target:{node:ti,path:'rotation'}});
  rows.push({name,sourceNode:si,targetNode:ti,baselineErrorRadians:baselineError,frames:values.length});
 }
 assert(rows.some(r=>r.name.startsWith('LeftHand'))&&rows.some(r=>r.name.startsWith('RightHand')),'Both hands required');
 assert(rows.length>=32,'Incomplete two-hand articulated capture');
 // A separate clip: no existing target/body animation is replaced or silently mixed.
 dst.doc.animations??=[];dst.doc.animations.push(newAnim);dst.doc.buffers[0].byteLength=offset;
 const binary=Buffer.concat(parts),json=Buffer.from(JSON.stringify(dst.doc)),padding=Buffer.alloc((4-json.length%4)%4,32);
 const head=Buffer.alloc(20),bh=Buffer.alloc(8);head.write('glTF');head.writeUInt32LE(2,4);head.writeUInt32LE(28+json.length+padding.length+binary.length,8);
 head.writeUInt32LE(json.length+padding.length,12);head.writeUInt32LE(0x4e4f534a,16);bh.writeUInt32LE(binary.length);bh.writeUInt32LE(0x004e4942,4);
 const out=Buffer.concat([head,json,padding,bh,binary]);fs.writeFileSync(outPath,out);
 const report={schema:'sub01.relaxed-baseline-hand-retarget.v1',sourceSha256:hash(src.raw),targetSha256:hash(dst.raw),outputSha256:hash(out),baselineSeconds,rows,
  originalTargetBinaryPrefixExact:binary.subarray(0,dst.bin.length).equals(dst.bin),targetRestAndWeightsUnchanged:true,
  translationsAndBodyUntouched:true,loopingApplied:false,nativeAccepted:false,contactAccepted:false,
  limitations:['Baseline time must be visually reviewed as relaxed, not automatically assumed','This transfers angular variation only, not object grips or fingertip targets','Skin deformation, joint axes and native contact require independent rendered checks']};
 fs.writeFileSync(outPath+'.json',JSON.stringify(report,null,2)+'\n');return report;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const args=process.argv.slice(2);assert.equal(args.length,4,'Usage: SOURCE.glb TARGET.glb OUT.glb REVIEWED_BASELINE_SECONDS');
 const result=retarget(args[0],args[1],args[2],Number(args[3]));console.log(JSON.stringify({outputSha256:result.outputSha256,handChannels:result.rows.length,contactAccepted:false}));
}
