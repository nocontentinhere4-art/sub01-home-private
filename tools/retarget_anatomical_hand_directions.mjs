// Transfer measured captured phalange directions, compensating the new mesh's
// already curved rest. No mesh deformation/weights are authored by this tool.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {Quaternion,Vector3,Matrix4} from '../web/house/vendor/three.core.js';
import {read,accessor,relativeHandRotation} from './retarget_relaxed_hand_motion.mjs';
import {writeGLB} from './uncompress_unreal_glb.mjs';
const normalize=n=>(n||'').replace(/^mixamorig[:_]?/i,'');
const q=v=>new Quaternion().fromArray(v).normalize();
const vector=v=>new Vector3(...v);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const unit=v=>{assert(v.length()>1e-9,'Degenerate anatomical direction');return v.clone().normalize();};

export function directionFrame(direction,normal){
 const x=unit(direction),y=normal.clone().addScaledVector(x,-normal.dot(x));
 assert(y.length()>1e-6,'Anatomical normal parallel to segment');y.normalize();
 return new Quaternion().setFromRotationMatrix(new Matrix4().makeBasis(x,y,new Vector3().crossVectors(x,y))).normalize();
}
export function calibrateSegment(sourceDirection,sourceDorsal,targetDirection,targetDorsal){
 return directionFrame(sourceDirection,sourceDorsal).multiply(directionFrame(targetDirection,targetDorsal).invert()).normalize();
}
function rest(f){return f.doc.nodes.map(n=>({r:n.rotation||[0,0,0,1],t:n.translation||[0,0,0],s:n.scale||[1,1,1]}));}
export function worldPose(f,local){
 const result=[],visiting=new Set();
 function get(i){if(result[i])return result[i];assert(!visiting.has(i));visiting.add(i);
  const n=f.doc.nodes[i],s=local[i].s||n.scale||[1,1,1];assert(s.every(x=>Number.isFinite(x)&&x>0)&&Math.max(...s)-Math.min(...s)<1e-6);
  const parent=f.parents.has(i)?get(f.parents.get(i)):null,rotation=q(local[i].r),position=vector(local[i].t);
  assert([...local[i].r,...local[i].t].every(Number.isFinite));
  if(parent){position.multiplyScalar(parent.s).applyQuaternion(parent.r).add(parent.p);rotation.premultiply(parent.r);}
  result[i]={r:rotation.normalize(),p:position,s:s[0]*(parent?.s||1)};visiting.delete(i);return result[i];
 }f.doc.nodes.forEach((_,i)=>get(i));return result;
}
function palm(f,w,side){
 const hand=f.names.get(side+'Hand'),index=f.names.get(side+'HandIndex1'),pinky=f.names.get(side+'HandPinky1');
 assert([hand,index,pinky].every(Number.isInteger),'Required anatomical palm landmarks absent');
 const across=w[index].p.clone().sub(w[pinky].p),forward=w[index].p.clone().add(w[pinky].p).multiplyScalar(.5).sub(w[hand].p);
 return directionFrame(across,forward);
}
function tracks(f){
 const a=f.doc.animations?.[0];assert(a,'Recorded source animation required');const result=new Map();
 for(const c of a.channels){
  assert(['rotation','translation','scale'].includes(c.target.path));
  const s=a.samplers[c.sampler];assert(['LINEAR','STEP',undefined].includes(s.interpolation));
  const times=accessor(f,s.input).map(v=>v[0]),values=accessor(f,s.output);
  assert(times.length===values.length&&times.every((v,i)=>v>=0&&(!i||v>times[i-1])));
  const key=c.target.node+':'+c.target.path;assert(!result.has(key));result.set(key,{times,values,path:c.target.path,interpolation:s.interpolation||'LINEAR'});
 }return result;
}
function sample(t,time){
 let hi=t.times.findIndex(v=>v>=time);if(hi<0)return t.values.at(-1);if(!hi||t.times[hi]===time)return t.values[hi];
 const lo=hi-1,alpha=(time-t.times[lo])/(t.times[hi]-t.times[lo]);if(t.interpolation==='STEP')return t.values[lo];
 return t.path==='rotation'?q(t.values[lo]).slerp(q(t.values[hi]),alpha).toArray():t.values[lo].map((v,i)=>v+(t.values[hi][i]-v)*alpha);
}
function localAt(f,ts,time){
 const local=rest(f);for(const [key,t]of ts){const [i,path]=key.split(':');local[Number(i)][{rotation:'r',translation:'t',scale:'s'}[path]]=sample(t,time);}return local;
}

export function retargetDirections(source,target,output,baselineSeconds=0,{preserveTargetBody=false}={}){
 const src=read(source),dst=read(target,{allowMaterialTransforms:true}),ts=tracks(src),srcRest=rest(src),dstRest=rest(dst);
 const swr=worldPose(src,srcRest),twr=worldPose(dst,dstRest),baseline=localAt(src,ts,baselineSeconds),sbw=worldPose(src,baseline);
 const times=[...new Set([...ts.values()].flatMap(t=>t.times))].sort((a,b)=>a-b);
 const bodyTracks=preserveTargetBody?tracks(dst):null,bodyAnimation=preserveTargetBody?structuredClone(dst.doc.animations[0]):null;
 if(bodyTracks){assert([...bodyTracks.keys()].every(key=>!segmentsFingerName(dst.doc.nodes[Number(key.split(':')[0])].name)),'Body source must not contain obsolete finger channels');const bodyTimes=[...bodyTracks.values()].flatMap(t=>t.times);assert(Math.abs(Math.max(...bodyTimes)-times.at(-1))<1e-4,'Captured body/finger clocks must match explicitly');}
 assert(times.length>=2&&times.length<=24000&&baselineSeconds>=times[0]&&baselineSeconds<=times.at(-1));
 const palms={},segments=[];
 for(const side of ['Left','Right']){
  const si=src.names.get(side+'Hand'),ti=dst.names.get(side+'Hand');assert(Number.isInteger(si)&&Number.isInteger(ti));
  palms[side]={si,ti,sr:palm(src,swr,side),tr:palm(dst,twr,side)};
  for(const finger of ['Thumb','Index','Middle','Ring','Pinky'])for(let k=1;k<=3;k++){
   const name=side+'Hand'+finger+k,childName=side+'Hand'+finger+(k+1);
   const s=src.names.get(name),t=dst.names.get(name),sc=src.names.get(childName),tc=dst.names.get(childName);
   assert([s,t,sc,tc].every(Number.isInteger),'Incomplete phalange chain '+name);
   assert(src.parents.get(sc)===s&&dst.parents.get(tc)===t,'Direct phalange hierarchy required');
   const sd=vector(srcRest[sc].t),td=vector(dstRest[tc].t);
   const sn=new Vector3(0,0,1).applyQuaternion(palms[side].sr).applyQuaternion(swr[s].r.clone().invert());
   const tn=new Vector3(0,0,1).applyQuaternion(palms[side].tr).applyQuaternion(twr[t].r.clone().invert());
   segments.push({side,name,s,t,sc,tc,sourceRestDirection:unit(sd),sourceDorsal:sn,targetDirection:td,targetDorsal:tn,maxSourceLocalDirectionVariationRadians:0,maxDirectionErrorRadians:0});
  }
 }
 const channels=new Map([...(preserveTargetBody?[]:Object.values(palms).map(p=>p.ti)),...segments.map(s=>s.t)].map(i=>[i,[]]));
 let maxDirectionError=0;
 for(const time of times){
  const sl=localAt(src,ts,time),sw=worldPose(src,sl),tl=bodyTracks?localAt(dst,bodyTracks,time):rest(dst),desired=new Map(),targetPalms={};
  for(const side of ['Left','Right']){
   const p=palms[side];if(!preserveTargetBody)tl[p.ti].r=relativeHandRotation(dstRest[p.ti].r,baseline[p.si].r,sl[p.si].r,sbw[p.si].r.toArray(),twr[p.ti].r.toArray());
  }
  const wristWorld=worldPose(dst,tl);
  for(const side of ['Left','Right']){
   const p=palms[side];
   const sp=sw[p.si].r.clone().multiply(swr[p.si].r.clone().invert()).multiply(p.sr);
   const tp=wristWorld[p.ti].r.clone().multiply(twr[p.ti].r.clone().invert()).multiply(p.tr);
   targetPalms[side]={source:sp,target:tp};
  }
  for(const s of segments){
   // Original FBX exports may contain sampled child translations. Use their
   // actual recorded direction, retaining the target's own segment length.
   const direction=vector(sl[s.sc].t),calibration=calibrateSegment(direction,s.sourceDorsal,s.targetDirection,s.targetDorsal);
   s.maxSourceLocalDirectionVariationRadians=Math.max(s.maxSourceLocalDirectionVariationRadians,s.sourceRestDirection.angleTo(unit(direction)));
   const p=targetPalms[s.side];desired.set(s.t,p.target.clone().multiply(p.source.clone().invert()).multiply(sw[s.s].r).multiply(calibration).normalize());
  }
  // Convert desired world frames back through actual target parent frames.
  const solved=[];
  function solve(i){if(solved[i])return solved[i];const parent=dst.parents.has(i)?solve(dst.parents.get(i)):null;
   if(desired.has(i))tl[i].r=(parent?parent.clone().invert().multiply(desired.get(i)):desired.get(i)).normalize().toArray();
   solved[i]=parent?parent.clone().multiply(q(tl[i].r)):q(tl[i].r);return solved[i];
  }dst.doc.nodes.forEach((_,i)=>solve(i));
  const tw=worldPose(dst,tl);
  for(const s of segments){
   const p=targetPalms[s.side],observed=unit(tw[s.tc].p.clone().sub(tw[s.t].p));
   const expected=unit(sw[s.sc].p.clone().sub(sw[s.s].p)).applyQuaternion(p.source.clone().invert()).applyQuaternion(p.target);
   const error=observed.angleTo(expected);assert(error<1e-5,'Post-FK phalange direction differs '+s.name);
   s.maxDirectionErrorRadians=Math.max(s.maxDirectionErrorRadians,error);maxDirectionError=Math.max(maxDirectionError,error);
  }
  for(const [i,values]of channels){const next=q(tl[i].r),last=values.slice(-4);if(last.length&&q(last).dot(next)<0)next.set(-next.x,-next.y,-next.z,-next.w);values.push(...next.toArray());}
 }
 const parts=[dst.bin];let offset=dst.bin.length;
 function append(values,type){const bytes=Buffer.alloc(values.length*4);values.forEach((v,i)=>bytes.writeFloatLE(v,i*4));
  const vi=dst.doc.bufferViews.length;dst.doc.bufferViews.push({buffer:0,byteOffset:offset,byteLength:bytes.length});parts.push(bytes);offset+=bytes.length;
  const ai=dst.doc.accessors.length;dst.doc.accessors.push({bufferView:vi,componentType:5126,type,count:values.length/(type==='SCALAR'?1:4),...(type==='SCALAR'?{min:[values[0]],max:[values.at(-1)]}:{})});return ai;
 }
 const input=append(times,'SCALAR'),animation={name:'Captured anatomical phalange directions, rest curvature compensated',samplers:[],channels:[]};
 for(const [i,values]of channels){const sampler=animation.samplers.length;animation.samplers.push({input,output:append(values,'VEC4'),interpolation:'LINEAR'});animation.channels.push({sampler,target:{node:i,path:'rotation'}});}
 if(bodyAnimation){const offset=bodyAnimation.samplers.length;animation.channels=bodyAnimation.channels.concat(animation.channels.map(c=>({...c,sampler:c.sampler+offset})));animation.samplers=bodyAnimation.samplers.concat(animation.samplers);animation.name='Original captured body and anatomically corrected fingers';}
 dst.doc.animations??=[];dst.doc.animations.push(animation);dst.doc.buffers[0].byteLength=offset;
 writeGLB(output,dst.doc,Buffer.concat(parts));
 const report={schema:'sub01.captured-anatomical-direction-retarget.v1',sourceSha256:sha(src.raw),targetSha256:sha(dst.raw),outputSha256:sha(fs.readFileSync(output)),
  frames:times.length,durationSeconds:times.at(-1),wristBaselineSeconds:baselineSeconds,handChannels:channels.size,segments:segments.map(({name,maxDirectionErrorRadians,maxSourceLocalDirectionVariationRadians})=>({name,maxDirectionErrorRadians,maxSourceLocalDirectionVariationRadians})),maxPostFKDirectionErrorRadians:maxDirectionError,
  sourceGeometryWeightsAndTargetRestUnchanged:true,nondeformingEndpointRotationsHeldAtRest:true,noAuthoredFingerCurl:true,originalBodyChannelsPreserved:preserveTargetBody,
  visualAccepted:false,nativeImported:false,contactAccepted:false,
  limitations:['Wrist baseline still requires reviewed owner cuff alignment','Twist is transported from the captured bone and anatomical dorsal frames; skin deformation must be rendered','Matching measured segment directions does not establish fingertip contact or self-intersection freedom']};
 fs.writeFileSync(output+'.json',JSON.stringify(report,null,2)+'\n');return report;
}
function segmentsFingerName(name){return /Hand(Thumb|Index|Middle|Ring|Pinky)[1-4]$/.test(normalize(name));}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const [source,target,out,baseline,flag]=process.argv.slice(2);assert(source&&target&&out&&baseline!==undefined,'SOURCE.glb TARGET.glb OUT.glb WRIST_BASELINE_SECONDS [--preserve-target-body]');assert(flag===undefined||flag==='--preserve-target-body');const r=retargetDirections(source,target,out,Number(baseline),{preserveTargetBody:flag==='--preserve-target-body'});console.log(JSON.stringify({outputSha256:r.outputSha256,frames:r.frames,channels:r.handChannels,maxDirectionErrorRadians:r.maxPostFKDirectionErrorRadians}));}
