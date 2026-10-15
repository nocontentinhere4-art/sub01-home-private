// Independent serialized bind-space comparison; does not certify hand contacts.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {Matrix4, Quaternion, Vector3} from '../web/house/vendor/three.core.js';
const [beforePath, afterPath, output] = process.argv.slice(2);
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const normalize=s=>s.replace(/^mixamorig[:_]?/i,'');
const finger=s=>/Hand(Thumb|Index|Middle|Ring|Pinky)[1-4]$/.test(s);
function read(path){
 const raw=fs.readFileSync(path);assert.equal(raw.toString('ascii',0,4),'glTF');
 let doc,bin;
 for(let i=12;i<raw.length;){const n=raw.readUInt32LE(i),type=raw.readUInt32LE(i+4);if(type===0x4e4f534a)doc=JSON.parse(raw.toString('utf8',i+8,i+8+n));if(type===0x004e4942)bin=raw.subarray(i+8,i+8+n);i+=8+n;}
 assert.equal(doc.skins.length,1);const skin=doc.skins[0];assert.equal(skin.joints.length,65);
 const parents=new Map();doc.nodes.forEach((n,i)=>(n.children||[]).forEach(c=>parents.set(c,i)));
 const worlds=new Map();function world(i){if(worlds.has(i))return worlds.get(i);const n=doc.nodes[i];let m=n.matrix?new Matrix4().fromArray(n.matrix):new Matrix4().compose(new Vector3().fromArray(n.translation||[0,0,0]),new Quaternion().fromArray(n.rotation||[0,0,0,1]),new Vector3().fromArray(n.scale||[1,1,1]));if(parents.has(i))m.premultiply(world(parents.get(i)));worlds.set(i,m);return m;}
 const meshNodes=doc.nodes.map((n,i)=>n.skin===0?i:null).filter(i=>i!==null);assert(meshNodes.length>=1);
 const meshWorld=world(meshNodes[0]);
 for(const i of meshNodes)assert(Math.max(...world(i).elements.map((v,k)=>Math.abs(v-meshWorld.elements[k])))<1e-7,'Skinned mesh objects use different bind frames; explicit per-mesh proof required');
 const a=doc.accessors[skin.inverseBindMatrices],v=doc.bufferViews[a.bufferView];assert.equal(a.type,'MAT4');assert.equal(a.componentType,5126);assert.equal(a.count,65);assert(!v.extensions&&!a.sparse);
 const start=(v.byteOffset||0)+(a.byteOffset||0),stride=v.byteStride||64;
 // glTF final world skinning is jointWorld * inverseBind * position:
 // meshWorld cancels its inverse in the skin matrix. Never infer physical
 // shrinkage solely from the skinned mesh's container scale.
 const joints=new Map();skin.joints.forEach((node,i)=>{const name=normalize(doc.nodes[node].name);assert(!joints.has(name));const values=Array.from({length:16},(_,k)=>bin.readFloatLE(start+i*stride+k*4));const bind=new Matrix4().fromArray(values).invert();const parent=parents.has(node)?normalize(doc.nodes[parents.get(node)].name||''):null;joints.set(name,{node,parent,bind:bind.elements,nodeWorld:world(node).elements});});
 return {sha256:hash(raw),joints,meshWorld:meshWorld.elements};
}
const before=read(beforePath),after=read(afterPath),rows=[];
assert.deepEqual([...after.joints.keys()].sort(),[...before.joints.keys()].sort());
for(const [name,b]of before.joints){const a=after.joints.get(name);if(before.joints.has(b.parent))assert.equal(a.parent,b.parent,'Changed joint parent '+name);const bindError=Math.max(...b.bind.map((v,i)=>Math.abs(v-a.bind[i])));const nodeError=Math.max(...b.nodeWorld.map((v,i)=>Math.abs(v-a.nodeWorld[i])));rows.push({name,anatomical_finger_rest_intentionally_updated:finger(name),max_bind_matrix_error:bindError,max_node_world_error:nodeError});}
const body=rows.filter(r=>!r.anatomical_finger_rest_intentionally_updated);assert.equal(body.length,25);
const report={schema:'sub01.independent-owner65-serialized-bind.v1',before_sha256:before.sha256,after_sha256:after.sha256,same65_names:true,before_mesh_node_world:before.meshWorld,after_mesh_node_world:after.meshWorld,skin_world_formula:'jointWorld * inverseBind * meshPosition; meshWorld container cancels, no shrinkage inferred from container scale alone',nonfinger_joint_count:body.length,nonfinger_max_bind_error:Math.max(...body.map(r=>r.max_bind_matrix_error)),joints:rows,native_or_contact_accepted:false};
report.nonfinger_binds_preserved=report.nonfinger_max_bind_error<2e-5;
fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
assert(report.nonfinger_binds_preserved,'Serialized body bind spaces changed; inspect actual report, do not widen tolerance');
console.log(JSON.stringify({passed:true,nonfinger_joints:25,max_bind_error:report.nonfinger_max_bind_error}));
