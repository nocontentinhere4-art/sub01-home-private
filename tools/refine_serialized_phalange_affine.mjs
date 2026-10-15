// Preserve captured directions through the actual serialized affine parents.
// Legacy near-uniform float32 scales must not be silently treated as scalars.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {Matrix4,Quaternion,Vector3} from '../web/house/vendor/three.core.js';
import {loadGLB,values,Appender} from './gltf_binary_patch.mjs';

export function affineDirectionRotation(parent,rotation,scale,childTranslation,desiredWorld){
 const before=new Vector3().fromArray(childTranslation).multiply(new Vector3().fromArray(scale)).applyQuaternion(rotation).normalize();
 const desired=desiredWorld.clone().transformDirection(parent.clone().invert());
 return new Quaternion().setFromUnitVectors(before,desired).multiply(rotation).normalize();
}
const normalize=n=>(n||'').replace(/^mixamorig[:_]?/i,'');
function clip(file){
 const parents=new Map();file.doc.nodes.forEach((n,i)=>(n.children||[]).forEach(c=>parents.set(c,i)));
 const names=new Map(file.doc.nodes.map((n,i)=>[normalize(n.name),i]));
 const animation=file.doc.animations.at(-1),tracks=animation.channels.map(c=>{
  const s=animation.samplers[c.sampler];assert(!s.interpolation||['LINEAR','STEP'].includes(s.interpolation));
  return {node:c.target.node,path:c.target.path,times:values(file,s.input).flat(),values:values(file,s.output),interpolation:s.interpolation||'LINEAR'};
 });
 function pose(time){return file.doc.nodes.map((node,i)=>{
  assert(!node.matrix,'Explicit TRS animation required');
  const p={t:(node.translation||[0,0,0]).slice(),r:(node.rotation||[0,0,0,1]).slice(),s:(node.scale||[1,1,1]).slice()};
  for(const track of tracks.filter(t=>t.node===i)){
   let hi=track.times.findIndex(t=>t>=time),value;
   if(hi<0)value=track.values.at(-1);
   else if(!hi||track.times[hi]===time)value=track.values[hi];
   else if(track.interpolation==='STEP')value=track.values[hi-1];
   else{const lo=hi-1,u=(time-track.times[lo])/(track.times[hi]-track.times[lo]);value=track.path==='rotation'?new Quaternion().fromArray(track.values[lo]).normalize().slerp(new Quaternion().fromArray(track.values[hi]).normalize(),u).toArray():track.values[lo].map((v,k)=>v+(track.values[hi][k]-v)*u);}
   p[{translation:'t',rotation:'r',scale:'s'}[track.path]]=value.slice();
  }return p;
 });}
 function world(local){
  const cache=new Map();
  const get=i=>{if(!cache.has(i)){const n=local[i],m=new Matrix4().compose(new Vector3().fromArray(n.t),new Quaternion().fromArray(n.r).normalize(),new Vector3().fromArray(n.s));if(parents.has(i))m.premultiply(get(parents.get(i)));cache.set(i,m);}return cache.get(i);};
  const invalidate=i=>{cache.delete(i);for(const c of file.doc.nodes[i].children||[])invalidate(c);};
  return {get,invalidate};
 }
 return {file,parents,names,animation,tracks,pose,world};
}
function palm(c,w,side){
 const point=n=>new Vector3().setFromMatrixPosition(w.get(c.names.get(side+n)));
 const i=point('HandIndex1'),p=point('HandPinky1'),h=point('Hand'),x=i.clone().sub(p).normalize();
 const y=i.clone().add(p).multiplyScalar(.5).sub(h);y.addScaledVector(x,-y.dot(x)).normalize();
 return [x,y,new Vector3().crossVectors(x,y).normalize()];
}
export function refine(sourcePath,inputPath,outputPath){
 const source=clip(loadGLB(sourcePath)),target=clip(loadGLB(inputPath)),writer=new Appender(target.file);
 const tracks=target.tracks.filter(t=>/Hand(Thumb|Index|Middle|Ring|Pinky)[1-3]$/.test(normalize(target.file.doc.nodes[t.node].name)));
 assert.equal(tracks.length,30);assert(tracks.every(t=>t.path==='rotation'));
 const times=tracks[0].times;assert(times.length>1);
 const output=new Map(tracks.map(t=>[t.node,[]]));let maximumCorrectionRadians=0;
 for(const time of times){
  const sp=source.pose(time),tp=target.pose(time),sw=source.world(sp),tw=target.world(tp);
  for(const side of ['Left','Right']){
   const sb=palm(source,sw,side),tb=palm(target,tw,side);
   for(const finger of ['Thumb','Index','Middle','Ring','Pinky'])for(let segment=1;segment<=3;segment++){
    const name=side+'Hand'+finger+segment,child=side+'Hand'+finger+(segment+1),s=source.names.get(name),sc=source.names.get(child),t=target.names.get(name),tc=target.names.get(child);
    assert(target.parents.get(tc)===t&&source.parents.get(sc)===s);
    const direction=new Vector3().setFromMatrixPosition(sw.get(sc)).sub(new Vector3().setFromMatrixPosition(sw.get(s))).normalize();
    const desired=new Vector3();for(let k=0;k<3;k++)desired.addScaledVector(tb[k],direction.dot(sb[k]));desired.normalize();
    const previous=new Quaternion().fromArray(tp[t].r).normalize(),next=affineDirectionRotation(tw.get(target.parents.get(t)),previous,tp[t].s,tp[tc].t,desired);
    maximumCorrectionRadians=Math.max(maximumCorrectionRadians,previous.angleTo(next));tp[t].r=next.toArray();tw.invalidate(t);output.get(t).push(tp[t].r);
   }
  }
 }
 const a=writer.doc.animations.at(-1);
 for(const channel of a.channels)if(output.has(channel.target.node)){
  const sampler=a.samplers[channel.sampler];assert.equal(channel.target.path,'rotation');
  sampler.output=writer.accessor(output.get(channel.target.node),'VEC4');
 }
 writer.finish(outputPath);
 const hash=raw=>crypto.createHash('sha256').update(raw).digest('hex');
 const report={schema:'sub01.serialized-affine-finger-direction-refinement.v1',sourceSha256:hash(source.file.raw),inputSha256:hash(target.file.raw),outputSha256:hash(fs.readFileSync(outputPath)),frames:times.length,channels:30,maximumCorrectionRadians,originalGeometrySkinMaterialsRestBodyTracksUnchanged:true,method:'Full actual serialized parent affine inverse; captured palm-frame segment direction, minimal rotation correction only. No scalar approximation of near-uniform float32 parent scales.',nativeAccepted:false,contactAccepted:false};
 fs.writeFileSync(outputPath+'.affine.json',JSON.stringify(report,null,2)+'\n');return report;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){const[source,input,output]=process.argv.slice(2);assert(source&&input&&output);console.log(JSON.stringify(refine(source,input,output)));}
