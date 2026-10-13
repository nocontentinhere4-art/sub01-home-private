// CPU-only rest-delta retarget. No renderer, IK hand poses, or synthetic finger motion.
// node tools/retarget_first_person.mjs SOURCE.glb TARGET_SKIN.glb OUTPUT.glb [--clip NAME]
// Diagnostic only: --canonicalize changes initial T reference to skin bind A pose; do not use for runtime retarget without pose QA.
// node tools/retarget_first_person.mjs --canonicalize TARGET.glb OWNER.glb
// node tools/retarget_first_person.mjs --self-test web/room/char_mixamo.glb
import fs from 'node:fs';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {Matrix4, Quaternion, Vector3} from '../web/house/vendor/three.core.js';
import {MeshoptDecoder} from '../web/house/vendor/meshopt_decoder.module.js';
await MeshoptDecoder.ready;
const eps=1e-5, I=new Matrix4(), identity=new Quaternion();
const canonical=name=>(name||'').replace(/^mixamorig[:_]?/i,'');
const finger=name=>/Hand(Thumb|Index|Middle|Ring|Pinky)[1-4]$/.test(canonical(name));
const hash=buffer=>crypto.createHash('sha256').update(buffer).digest('hex');

function readGLB(path){
 const raw=fs.readFileSync(path);assert.equal(raw.toString('ascii',0,4),'glTF');assert.equal(raw.readUInt32LE(4),2);assert.equal(raw.readUInt32LE(8),raw.length);
 let doc,bin;for(let offset=12;offset<raw.length;){const size=raw.readUInt32LE(offset),type=raw.readUInt32LE(offset+4);const data=raw.subarray(offset+8,offset+8+size);if(type===0x4e4f534a)doc=JSON.parse(data.toString());if(type===0x004e4942)bin=data;offset+=8+size;}
 assert(doc&&bin,'Missing JSON/binary chunks');return{doc,bin,sha:hash(raw),decoded:new Map()};
}
function accessor(file,index){
 const a=file.doc.accessors[index],view=file.doc.bufferViews[a.bufferView];
 assert(!a.sparse,'Sparse animation accessor requires explicit conversion');
 let binary=file.bin,baseOffset=view.byteOffset||0;const compression=view.extensions?.EXT_meshopt_compression;
 if(compression){assert.equal(compression.buffer,0,'External compressed buffers unsupported');if(!file.decoded.has(a.bufferView)){const output=Buffer.alloc(compression.count*compression.byteStride);MeshoptDecoder.decodeGltfBuffer(output,compression.count,compression.byteStride,file.bin.subarray(compression.byteOffset,compression.byteOffset+compression.byteLength),compression.mode,compression.filter||'NONE');file.decoded.set(a.bufferView,output);}binary=file.decoded.get(a.bufferView);baseOffset=0;}else assert.equal(view.buffer,0,'External buffers unsupported');
 const count={SCALAR:1,VEC2:2,VEC3:3,VEC4:4,MAT4:16}[a.type];assert.equal(a.componentType,5126,'Animation/matrix accessor must be float32');
 const stride=view.byteStride||count*4,start=baseOffset+(a.byteOffset||0),out=[];
 for(let i=0;i<a.count;i++){const v=[];for(let j=0;j<count;j++)v.push(binary.readFloatLE(start+i*stride+j*4));assert(v.every(Number.isFinite),'Non-finite accessor');out.push(v);}return out;
}
function transform(node){
 const matrix=node.matrix?new Matrix4().fromArray(node.matrix):new Matrix4().compose(new Vector3().fromArray(node.translation||[0,0,0]),new Quaternion().fromArray(node.rotation||[0,0,0,1]),new Vector3().fromArray(node.scale||[1,1,1]));
 assert(matrix.elements.every(Number.isFinite),'Non-finite rest matrix');assert(matrix.determinant()>0,'Mirrored/singular rig transform is not supported');
 const p=new Vector3(),q=new Quaternion(),s=new Vector3();matrix.decompose(p,q,s);
 assert(Math.max(s.x,s.y,s.z)-Math.min(s.x,s.y,s.z)<eps*Math.max(1,s.length()),'Nonuniform rig scale cannot be rotated with quaternions');
 assert(Math.max(...new Matrix4().compose(p,q,s).elements.map((x,i)=>Math.abs(x-matrix.elements[i])))<eps,'Shear/non-TRS matrix rejected');
 assert(Math.abs(q.length()-1)<eps,'Non-unit rest quaternion');q.normalize();return{p,q,s};
}
function rig(file){
 const nodes=file.doc.nodes,parents=new Map();nodes.forEach((n,i)=>(n.children||[]).forEach(c=>{assert(!parents.has(c),'Multiple node parents');parents.set(c,i);}));
 const order=[],seen=new Set(),active=new Set();function visit(i){assert(!active.has(i),'Rig cycle');if(seen.has(i))return;active.add(i);if(parents.has(i))visit(parents.get(i));active.delete(i);seen.add(i);order.push(i);}nodes.forEach((_,i)=>visit(i));
 const local=nodes.map(transform),rest=fk({nodes,parents,order,local},local);
 const joints=new Set(file.doc.skins?.flatMap(s=>s.joints)||nodes.map((n,i)=>/^mixamorig[:_]?/i.test(n.name||'')?i:null).filter(i=>i!==null));
 const names=new Map();for(const i of joints){const n=canonical(nodes[i].name);assert(n&&!names.has(n),'Duplicate/unnamed joint');names.set(n,i);}
 return{file,nodes,parents,order,local,rest,joints,names};
}
function fk(r,local){
 const world=[];for(const i of r.order){const l=local[i],m=new Matrix4().compose(l.p,l.q,l.s);world[i]=r.parents.has(i)?world[r.parents.get(i)].clone().multiply(m):m;}
 const p=[],q=[],s=[];world.forEach((m,i)=>{p[i]=new Vector3();q[i]=new Quaternion();s[i]=new Vector3();m.decompose(p[i],q[i],s[i]);});return{world,p,q,s};
}
function required(r,name){assert(r.names.has(name),'Missing bone '+name);return r.names.get(name);}
function basis(r){
 const hips=required(r,'Hips'),chest=required(r,'Spine2'),left=required(r,'LeftUpLeg'),right=required(r,'RightUpLeg');
 const x=r.rest.p[right].clone().sub(r.rest.p[left]);assert(x.length()>.02,'Degenerate hip lateral axis');x.normalize();
 const y=r.rest.p[chest].clone().sub(r.rest.p[hips]);y.addScaledVector(x,-y.dot(x));assert(y.length()>.05,'Degenerate hips/chest up axis');y.normalize();
 const z=x.clone().cross(y).normalize();const m=new Matrix4().makeBasis(x,y,z);assert(Math.abs(m.determinant()-1)<eps,'Invalid anatomical forward basis');
 return{q:new Quaternion().setFromRotationMatrix(m),right:x.toArray(),up:y.toArray(),forward:z.toArray()};
}
function height(r){const h=r.rest.p[required(r,'Hips')],l=r.rest.p[required(r,'LeftFoot')],rr=r.rest.p[required(r,'RightFoot')];const up=new Vector3().fromArray(basis(r).up);const value=h.clone().sub(l.clone().add(rr).multiplyScalar(.5)).dot(up);assert(value>.1,'Invalid anatomical leg height');return value;}
function bindAudit(r,strict=false){
 const reports=[];for(const [skinIndex,skin] of (r.file.doc.skins||[]).entries()){assert(skin.inverseBindMatrices!==undefined,'Target skin has no inverse bind matrices');const matrices=accessor(r.file,skin.inverseBindMatrices);for(const values of matrices){assert(values.every(Number.isFinite),'Nonfinite inverse bind matrix');assert(new Matrix4().fromArray(values).determinant()>0,'Mirrored/singular inverse bind matrix');}assert.equal(matrices.length,skin.joints.length);
  const meshOwners=r.nodes.map((n,i)=>n.skin===skinIndex?i:null).filter(i=>i!==null);assert(meshOwners.length,'Skin has no mesh owners');let common,error=0,expectedError=0;skin.joints.forEach((joint,index)=>{const product=r.rest.world[joint].clone().multiply(new Matrix4().fromArray(matrices[index]));if(!common)common=product;for(const mi of meshOwners)expectedError=Math.max(expectedError,...product.elements.map((v,i)=>Math.abs(v-r.rest.world[mi].elements[i])));error=Math.max(error,...product.elements.map((v,i)=>Math.abs(v-common.elements[i])));});
  if(strict){assert(error<.002,'Target node rest transforms disagree with inverse bind matrices: '+error);assert(expectedError<.002,'Joint-world × IBM differs from mesh-world: '+expectedError);}reports.push({initialPoseMayDifferFromBind:true,equivalenceRequired:strict,joints:skin.joints.length,meshOwners:meshOwners.length,maxCommonBindMatrixError:error,maxExpectedMeshBindMatrixError:expectedError,commonBindMatrix:common.elements});}
 return reports;
}
function repairBindRest(r){
 const before=bindAudit(r,false),desired=new Map(),repairs=[];
 for(const [skinIndex,skin] of (r.file.doc.skins||[]).entries()){
  const meshes=r.nodes.map((n,i)=>n.skin===skinIndex?i:null).filter(i=>i!==null);assert(meshes.length,'Skin has no mesh owner');const meshWorld=r.rest.world[meshes[0]];
  for(const mi of meshes)assert(Math.max(...meshWorld.elements.map((v,i)=>Math.abs(v-r.rest.world[mi].elements[i])))<eps,'Skin meshes have different bind spaces');
  const inverse=accessor(r.file,skin.inverseBindMatrices);skin.joints.forEach((joint,i)=>{const w=meshWorld.clone().multiply(new Matrix4().fromArray(inverse[i]).invert());if(desired.has(joint))assert(Math.max(...w.elements.map((v,i)=>Math.abs(v-desired.get(joint).elements[i])))<eps,'Conflicting skin bind matrix');desired.set(joint,w);});
 }
 assert(desired.size,'Cannot repair animation-only target');const local=localClone(r),world=[];
 for(const i of r.order){const parent=r.parents.get(i),pw=parent===undefined?I:world[parent];if(desired.has(i)){local[i]=transform({matrix:pw.clone().invert().multiply(desired.get(i)).elements});repairs.push({name:r.nodes[i].name,localTranslationDelta:local[i].p.distanceTo(r.local[i].p),localRotationDeltaDegrees:local[i].q.angleTo(r.local[i].q)*180/Math.PI});}const l=local[i];world[i]=pw.clone().multiply(new Matrix4().compose(l.p,l.q,l.s));}
 r.local=local;r.rest=fk(r,local);return{originalBindAudit:before,correctedBindAudit:bindAudit(r,true),repairs,diagnosticBindPoseOnly:true};
}
function mappedParent(r,index){let p=r.parents.get(index);while(p!==undefined&&!r.joints.has(p))p=r.parents.get(p);return p===undefined?null:canonical(r.nodes[p].name);}
function mapping(src,tgt){
 const pairs=[];for(const ti of tgt.joints){const name=canonical(tgt.nodes[ti].name);assert(src.names.has(name),'Missing source joint '+name);const si=src.names.get(name);assert.equal(mappedParent(src,si),mappedParent(tgt,ti),'Anatomical hierarchy differs at '+name);pairs.push({name,si,ti,finger:finger(name)});}
 const fingers=pairs.filter(p=>p.finger);assert.equal(fingers.length,40,'Require all 40 Mixamo thumb/finger segments including endpoints');
 return pairs;
}
function localClone(r){return r.local.map(l=>({p:l.p.clone(),q:l.q.clone(),s:l.s.clone()}));}
function retargetPose(src,tgt,pairs,srcPose,alignment,scale){
 const local=localClone(tgt),world=[],source=fk(src,srcPose),byTarget=new Map(pairs.map(p=>[p.ti,p]));
 const ai=alignment.clone().invert(),hips=required(tgt,'Hips'),srcHips=required(src,'Hips');
 for(const ti of tgt.order){const parent=tgt.parents.get(ti),pw=parent===undefined?I:world[parent],pair=byTarget.get(ti);
  if(pair){
   const delta=alignment.clone().multiply(source.q[pair.si]).multiply(src.rest.q[pair.si].clone().invert()).multiply(ai);
   const desired=delta.multiply(tgt.rest.q[ti]);const parentQ=new Quaternion(),discardP=new Vector3(),discardS=new Vector3();pw.decompose(discardP,parentQ,discardS);
   local[ti].q=parentQ.invert().multiply(desired).normalize();
   if(ti===hips){const goal=tgt.rest.p[ti].clone().add(source.p[srcHips].clone().sub(src.rest.p[srcHips]).applyQuaternion(alignment).multiplyScalar(scale));local[ti].p=goal.applyMatrix4(pw.clone().invert());}
  }
  const l=local[ti];world[ti]=pw.clone().multiply(new Matrix4().compose(l.p,l.q,l.s));
 }
 return{local,state:fk(tgt,local)};
}
function tracks(file,animation){
 return animation.channels.map(c=>{const sampler=animation.samplers[c.sampler];assert(['LINEAR','STEP',undefined].includes(sampler.interpolation),'Cubic animation needs explicit conversion before retarget');assert(['rotation','translation','scale'].includes(c.target.path),'Unsupported target path');const times=accessor(file,sampler.input).map(v=>v[0]),values=accessor(file,sampler.output);assert(times.length===values.length&&times.every((t,i)=>i===0||t>=times[i-1]),'Invalid keyframe times');return{node:c.target.node,path:c.target.path,interpolation:sampler.interpolation||'LINEAR',times,values};});
}
function sample(r,channels,time){
 const local=localClone(r);for(const track of channels){let hi=track.times.findIndex(t=>t>=time);if(hi<0)hi=track.times.length-1;const lo=track.times[hi]===time?hi:Math.max(0,hi-1);const alpha=track.interpolation==='STEP'||hi===lo?0:Math.max(0,Math.min(1,(time-track.times[lo])/(track.times[hi]-track.times[lo])));const a=track.values[lo],b=track.values[hi],l=local[track.node];
  if(track.path==='rotation')l.q=new Quaternion().fromArray(a).slerp(new Quaternion().fromArray(b),alpha).normalize();
  else if(track.path==='translation')l.p=new Vector3().fromArray(a).lerp(new Vector3().fromArray(b),alpha);
  else {l.s=new Vector3().fromArray(a).lerp(new Vector3().fromArray(b),alpha);assert(l.s.distanceTo(r.local[track.node].s)<eps,'Animated scale changes are rejected');}}
 return local;
}
function verifyPose(tgt,pairs,pose){let lengthError=0;for(const pair of pairs){const parent=tgt.parents.get(pair.ti);if(parent===undefined)continue;const length=pose.state.p[pair.ti].distanceTo(pose.state.p[parent]),rest=tgt.rest.p[pair.ti].distanceTo(tgt.rest.p[parent]);if(pair.name!=='Hips')lengthError=Math.max(lengthError,Math.abs(length-rest));assert(Math.abs(pose.local[pair.ti].q.length()-1)<eps,'Invalid output quaternion');if(pair.name!=='Hips')assert(pose.local[pair.ti].p.distanceTo(tgt.local[pair.ti].p)<eps,'Changed target rest translation');}assert(lengthError<eps,'Target bone lengths changed');return lengthError;}
function writeContainer(path,doc,binary){
 let json=Buffer.from(JSON.stringify(doc));json=Buffer.concat([json,Buffer.alloc((4-json.length%4)%4,32)]);const header=Buffer.alloc(20),binHeader=Buffer.alloc(8);header.write('glTF');header.writeUInt32LE(2,4);header.writeUInt32LE(28+json.length+binary.length,8);header.writeUInt32LE(json.length,12);header.writeUInt32LE(0x4e4f534a,16);binHeader.writeUInt32LE(binary.length,0);binHeader.writeUInt32LE(0x004e4942,4);fs.writeFileSync(path,Buffer.concat([header,json,binHeader,binary]));
}
function canonicalize(input,output){
 const file=readGLB(input),r=rig(file),repair=repairBindRest(r),doc=structuredClone(file.doc);
 for(const i of r.joints){const node=doc.nodes[i],local=r.local[i];delete node.matrix;node.translation=local.p.toArray();node.rotation=local.q.toArray();node.scale=local.s.toArray();}
 doc.asset.generator=(doc.asset.generator||'')+'; SUB01 diagnostic inverse-bind pose';writeContainer(output,doc,file.bin);
 const corrected=readGLB(output),canonical=rig(corrected),bind=bindAudit(canonical);assert.equal(hash(corrected.bin),hash(file.bin),'Geometry/weights/IBMs/texture binary changed');assert.deepEqual(corrected.doc.skins,file.doc.skins,'Skin assignments/IBMs changed');
 const audit={source:input,output,sourceSHA256:file.sha,outputSHA256:corrected.sha,binarySHA256:hash(file.bin),initialPoseVsBindDifference:Math.max(...repair.originalBindAudit.map(x=>x.maxCommonBindMatrixError)),correction:'jointWorld=meshWorld*inverse(inverseBindMatrix); jointLocal=inverse(correctedParentWorld)*jointWorld',originalGeometryWeightsIBMsTexturesUnchanged:true,diagnosticBindPoseOnly:true,runtimeAccepted:false,initialPoseCanDifferFromSkinBind:true,visualQAPending:true,repair,validatedBind:bind};fs.writeFileSync(output+'.audit.json',JSON.stringify(audit,null,2)+'\n');console.log(JSON.stringify({owner:output,initialPoseVsBindDifference:audit.initialPoseVsBindDifference,correctedMaxError:Math.max(...bind.map(b=>b.maxCommonBindMatrixError)),binaryUnchanged:true}));
}
function writeAnimation(path,tgt,pairs,times,poses,name){
 const keep=new Set();for(const pair of pairs)for(let i=pair.ti;i!==undefined;i=tgt.parents.get(i))keep.add(i);const indices=tgt.order.filter(i=>keep.has(i)),map=new Map(indices.map((i,n)=>[i,n]));
 const doc={asset:{version:'2.0',generator:'SUB01 validated world rest-delta retarget'},scene:0,scenes:[{nodes:indices.filter(i=>!keep.has(tgt.parents.get(i))).map(i=>map.get(i))}],nodes:indices.map(i=>{const l=tgt.local[i];return{name:tgt.nodes[i].name,translation:tgt.nodes[i].translation||l.p.toArray(),rotation:tgt.nodes[i].rotation||l.q.toArray(),scale:tgt.nodes[i].scale||l.s.toArray(),children:(tgt.nodes[i].children||[]).filter(c=>keep.has(c)).map(c=>map.get(c))};}),bufferViews:[],accessors:[],animations:[{name,samplers:[],channels:[]}],buffers:[]};
 const chunks=[];let bytes=0;function add(values,type){const flat=values.flat(),buffer=Buffer.alloc(flat.length*4);flat.forEach((v,i)=>buffer.writeFloatLE(v,i*4));const view=doc.bufferViews.length;doc.bufferViews.push({buffer:0,byteOffset:bytes,byteLength:buffer.length});chunks.push(buffer);bytes+=buffer.length;const count=values.length,accessor={bufferView:view,componentType:5126,count,type};if(type==='SCALAR'){accessor.min=[Math.min(...flat)];accessor.max=[Math.max(...flat)];}doc.accessors.push(accessor);return doc.accessors.length-1;}
 const timeIndex=add(times.map(t=>[t]),'SCALAR'),animation=doc.animations[0];
 function channel(pair,path,values,type){const output=add(values,type);const sampler=animation.samplers.length;animation.samplers.push({input:timeIndex,output,interpolation:'LINEAR'});animation.channels.push({sampler,target:{node:map.get(pair.ti),path}});}
 for(const pair of pairs){let prev;const rotations=poses.map(p=>{const q=p.local[pair.ti].q.clone();if(prev&&prev.dot(q)<0)q.set(-q.x,-q.y,-q.z,-q.w);prev=q;return q.toArray();});channel(pair,'rotation',rotations,'VEC4');if(pair.name==='Hips')channel(pair,'translation',poses.map(p=>p.local[pair.ti].p.toArray()),'VEC3');}
 doc.buffers=[{byteLength:bytes}];writeContainer(path,doc,Buffer.concat(chunks));return doc;
}
function checks(src,tgt,pairs,alignment,scale){
 const pose=retargetPose(src,tgt,pairs,localClone(src),alignment,scale);let restError=0;for(const pair of pairs){restError=Math.max(restError,pose.local[pair.ti].q.angleTo(tgt.local[pair.ti].q),pose.local[pair.ti].p.distanceTo(tgt.local[pair.ti].p));}assert(restError<eps,'No-motion source failed to recover target rest');return{noMotionRestMaxError:restError,boneLengthMaxError:verifyPose(tgt,pairs,pose)};
}
function selfTest(path){const target=rig(readGLB(path));const pairs=mapping(target,target);bindAudit(target);checks(target,target,pairs,identity,1);
 const pose=localClone(target),fingerPair=pairs.find(p=>p.name==='RightHandIndex2');pose[fingerPair.ti].q.multiply(new Quaternion().setFromAxisAngle(new Vector3(1,0,0),.3));const result=retargetPose(target,target,pairs,pose,identity,1);for(const pair of pairs)assert(result.local[pair.ti].q.angleTo(pose[pair.si].q)<eps,'Identity retarget changed captured pose');verifyPose(target,pairs,result);
 const translated=localClone(target),hips=required(target,'Hips');translated[hips].p.add(new Vector3(1,2,3));const translatedResult=retargetPose(target,target,pairs,translated,identity,1);assert(translatedResult.local[hips].p.distanceTo(translated[hips].p)<eps,'Identity hip delta changed');
 const different=rig(readGLB(path));different.local[required(different,'Spine')].q.multiply(new Quaternion().setFromAxisAngle(new Vector3(0,0,1),.2));different.rest=fk(different,different.local);const otherBasis=basis(different),targetBasis=basis(target),alignment=targetBasis.q.clone().multiply(otherBasis.q.clone().invert());checks(different,target,mapping(different,target),alignment,height(target)/height(different));
 const scaled=rig(readGLB(path));const wrapper=scaled.order.find(i=>!scaled.joints.has(i)&&scaled.nodes[i].name==='mixamo');assert(wrapper!==undefined);scaled.local[wrapper].s.multiplyScalar(2);scaled.rest=fk(scaled,scaled.local);const scaledPose=localClone(scaled),scaledHips=required(scaled,'Hips');scaledPose[scaledHips].p.x+=10;const scaledResult=retargetPose(scaled,target,mapping(scaled,target),scaledPose,identity,height(target)/height(scaled));assert(Math.abs(scaledResult.local[hips].p.x-target.local[hips].p.x-10)<eps,'Leg-height world delta scale failed');verifyPose(target,pairs,scaledResult);
 const missing={...target,names:new Map(target.names)};missing.names.delete('RightHandIndex4');assert.throws(()=>mapping(missing,target),/Missing source joint/);assert.throws(()=>transform({scale:[-1,1,1]}),/Mirrored/);
 console.log('PASS identity captured finger rotation, rest/no-motion on different rest axes, scaled world hip translation, full finger mapping and missing-finger rejection, inverse-bind integrity (not bind-pose equivalence) and unchanged reference bone lengths');}

const args=process.argv.slice(2);if(args[0]==='--canonicalize'){assert(args[1]&&args[2],'Need input/output owner paths');canonicalize(args[1],args[2]);}else if(args[0]==='--self-test'){selfTest(args[1]||'web/room/char_mixamo.glb');}else{
 assert(args.length>=3,'Usage: SOURCE.glb TARGET.glb OUTPUT.glb [--clip NAME]');const[srcPath,tgtPath,outPath]=args,sourceFile=readGLB(srcPath),targetFile=readGLB(tgtPath),src=rig(sourceFile),tgt=rig(targetFile),pairs=mapping(src,tgt),sb=basis(src),tb=basis(tgt),alignment=tb.q.clone().multiply(sb.q.clone().invert()),scale=height(tgt)/height(src),bind=bindAudit(tgt);
 const requested=args.includes('--clip')?args[args.indexOf('--clip')+1]:undefined,animation=requested?sourceFile.doc.animations.find(a=>a.name===requested):sourceFile.doc.animations?.[0];assert(animation,'Requested source animation not found');
 const channels=tracks(sourceFile,animation),times=[...new Set(channels.flatMap(t=>t.times))].sort((a,b)=>a-b);assert(times.length>=2,'Need an actual captured animation');
 const sourceContacts=times.map(time=>{const frame=fk(src,sample(src,channels,time));return{left:frame.p[required(src,'LeftHand')].toArray(),right:frame.p[required(src,'RightHand')].toArray(),gap:frame.p[required(src,'LeftHand')].distanceTo(frame.p[required(src,'RightHand')])};});
 const sourceCaptureContacts={wristGapRange:[Math.min(...sourceContacts.map(x=>x.gap)),Math.max(...sourceContacts.map(x=>x.gap))],leftMean:sourceContacts.reduce((sum,x)=>sum.map((v,i)=>v+x.left[i]/sourceContacts.length),[0,0,0]),rightMean:sourceContacts.reduce((sum,x)=>sum.map((v,i)=>v+x.right[i]/sourceContacts.length),[0,0,0])};
 const restChecks=checks(src,tgt,pairs,alignment,scale),poses=times.map(t=>retargetPose(src,tgt,pairs,sample(src,channels,t),alignment,scale));let boneError=0;for(const pose of poses)boneError=Math.max(boneError,verifyPose(tgt,pairs,pose));
 const anatomyAxes=pairs.map(p=>{const child=pairs.find(c=>mappedParent(tgt,c.ti)===p.name);let directionAudit=null;if(child){const sourceDirection=src.rest.p[child.si].clone().sub(src.rest.p[p.si]),targetDirection=tgt.rest.p[child.ti].clone().sub(tgt.rest.p[p.ti]);if(sourceDirection.length()>1e-6&&targetDirection.length()>1e-6)directionAudit={sourceRestDirection:sourceDirection.clone().normalize().toArray(),targetRestDirection:targetDirection.clone().normalize().toArray(),alignedDifferenceDegrees:sourceDirection.normalize().applyQuaternion(alignment).angleTo(targetDirection.normalize())*180/Math.PI,child:child.name};}return{name:p.name,sourceRestWorld:src.rest.world[p.si].elements,targetRestWorld:tgt.rest.world[p.ti].elements,alignedRestAxisDifferenceDegrees:src.rest.q[p.si].clone().premultiply(alignment).angleTo(tgt.rest.q[p.ti])*180/Math.PI,anatomicalChildDirection:directionAudit};});
 writeAnimation(outPath,tgt,pairs,times,poses,animation.name||'Captured retarget');const audit={algorithm:'Aligned world rest delta; QtargetWorld=C QsrcWorld inverse(QsrcRestWorld) inverse(C) QtargetRestWorld',source:srcPath,target:tgtPath,sourceSHA256:sourceFile.sha,targetSHA256:targetFile.sha,outputSHA256:hash(fs.readFileSync(outPath)),boneMapping:pairs.map(p=>({name:p.name,sourceNode:p.si,targetNode:p.ti,finger:p.finger})),fullFingerSegments:40,sourceBasis:sb,targetBasis:tb,alignmentQuaternion:alignment.toArray(),legHeightScale:scale,sourceLegHeight:height(src),targetLegHeight:height(tgt),matrixValidation:'Finite positive-determinant uniform-scale TRS; no shear; anatomical parents/child directions and inverse-bind integrity checked. Initial node pose is intentionally allowed to differ from skin bind pose.',sourceCaptureContacts,targetBind:bind,targetReference:'Original node reference transforms; glTF initial pose may differ from inverse-bind pose',anatomyAxes,checks:{...restChecks,sampledBoneLengthMaxError:boneError},frames:times.length,duration:times.at(-1)-times[0],sourceFingerChannels:channels.filter(t=>finger(src.nodes[t.node].name)).length,movingSourceFingerChannels:channels.filter(t=>finger(src.nodes[t.node].name)&&t.values.some(v=>v.some((x,i)=>Math.abs(x-t.values[0][i])>1e-5))).length,proceduralMotionAdded:false,mouseCaptureClaimed:false};fs.writeFileSync(outPath+'.audit.json',JSON.stringify(audit,null,2)+'\n');console.log(JSON.stringify({output:outPath,frames:audit.frames,duration:audit.duration,scale,sourceFingerChannels:audit.sourceFingerChannels,checks:audit.checks}));
}
