import assert from'node:assert/strict';import*as T from'../../web/house/vendor/three.module.js';
import{inspectReplacedAssets,retireReplacedAssets,releaseStartupModelCache}from'../../web/house/replaced_asset_cleanup.mjs';
const scene=new T.Scene(),sourceImage={width:1024,height:1024,closed:0,close(){this.closed++;}},shared=new T.Texture(sourceImage);
const activeMaterial=new T.MeshStandardMaterial({map:shared.clone()}),oldMaterial=new T.MeshStandardMaterial({map:shared});
const live=new T.Mesh(new T.BoxGeometry(),activeMaterial);scene.add(live);
const retired=new T.Mesh(new T.BoxGeometry(),oldMaterial);retired.userData.replaceable=true;retired.visible=false;scene.add(retired);
const exclusiveImage={width:512,height:512,closed:0,close(){this.closed++;}},exclusive=new T.Texture(exclusiveImage),exclusiveMaterial=new T.MeshStandardMaterial({map:exclusive});
const oldOnly=new T.Mesh(new T.BoxGeometry(),exclusiveMaterial);oldOnly.visible=false;oldOnly.userData.replaceable=true;scene.add(oldOnly);
const failed=new T.Mesh(new T.BoxGeometry(),new T.MeshStandardMaterial());failed.userData.replaceable=true;scene.add(failed);
const protectedOld=new T.Mesh(live.geometry,activeMaterial);protectedOld.visible=false;protectedOld.userData.replaceable=true;scene.add(protectedOld);
const ordinaryHidden=new T.Mesh(new T.BoxGeometry(),new T.MeshStandardMaterial());ordinaryHidden.visible=false;scene.add(ordinaryHidden);
const options={protectedObjects:[protectedOld]},plan=inspectReplacedAssets(scene,options);
assert.equal(plan.report.hiddenReplacementMeshes,2);assert.equal(plan.report.exclusiveGeometries,2);assert.equal(plan.report.exclusiveTextureObjects,1);assert.equal(sourceImage.closed,0);assert.equal(retired.parent,scene,'inspection is read-only');
let sharedDisposed=0,exclusiveDisposed=0,liveGeometryDisposed=0;shared.addEventListener('dispose',()=>sharedDisposed++);exclusive.addEventListener('dispose',()=>exclusiveDisposed++);live.geometry.addEventListener('dispose',()=>liveGeometryDisposed++);
assert.throws(()=>retireReplacedAssets(scene,options),/settle/);
retireReplacedAssets(scene,{...options,replacementAssetsSettled:true});
assert.equal(retired.parent,null);assert.equal(retired.geometry,null);assert.equal(retired.material,null);assert.equal(oldOnly.parent,null);assert.equal(exclusiveDisposed,1);assert.equal(exclusiveImage.closed,1);
assert.equal(sharedDisposed,0);assert.equal(sourceImage.closed,0);assert.equal(liveGeometryDisposed,0);assert.equal(live.material.map.source,shared.source);
assert.equal(failed.parent,scene,'visible replacement failure stays functional');assert.equal(protectedOld.parent,scene);assert.equal(ordinaryHidden.parent,scene);
// Explicitly retained templates/night maps are owners even outside scene nodes.
const extraScene=new T.Scene(),night=new T.Texture(),template=new T.MeshStandardMaterial({map:night});const m=new T.Mesh(new T.BoxGeometry(),template);m.visible=false;m.userData.replaceable=true;extraScene.add(m);
let templateDisposals=0;template.addEventListener('dispose',()=>templateDisposals++);retireReplacedAssets(extraScene,{replacementAssetsSettled:true,retainedMaterials:[template],extraTextures:[night]});assert.equal(templateDisposals,0);
// Distinct geometry identities do not imply distinct GPU attributes/CPU storage.
function aliasCase(oldGeometry,activeGeometry,{extraTextures=[],retainedGeometries=[]}={}){
 const s=new T.Scene(),oldMesh=new T.Mesh(oldGeometry,new T.MeshStandardMaterial());oldMesh.visible=false;oldMesh.userData.replaceable=true;s.add(oldMesh);
 if(activeGeometry)s.add(new T.Mesh(activeGeometry,new T.MeshStandardMaterial()));
 let disposal=0;oldGeometry.addEventListener('dispose',()=>disposal++);
 const p=inspectReplacedAssets(s,{extraTextures,retainedGeometries});assert.equal(p.report.exclusiveGeometries,0);assert.equal(p.report.geometryStorageSharedWithLive,1);assert.equal(p.report.detachedGeometryBytes,0);
 retireReplacedAssets(s,{replacementAssetsSettled:true,extraTextures,retainedGeometries});assert.equal(disposal,0);assert.equal(oldMesh.parent,null);
}
const attribute=new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0],3);
aliasCase(new T.BufferGeometry().setAttribute('position',attribute),new T.BufferGeometry().setAttribute('position',attribute));
const array=new Float32Array(9);
aliasCase(new T.BufferGeometry().setAttribute('position',new T.BufferAttribute(array,3)),new T.BufferGeometry().setAttribute('position',new T.BufferAttribute(array,3)));
const backing=new ArrayBuffer(72);
aliasCase(new T.BufferGeometry().setAttribute('position',new T.BufferAttribute(new Float32Array(backing,0,9),3)),new T.BufferGeometry().setAttribute('position',new T.BufferAttribute(new Float32Array(backing,36,9),3)));
const indices=new T.BufferAttribute(new Uint16Array([0,1,2]),1);
aliasCase(new T.BufferGeometry().setIndex(indices),new T.BufferGeometry().setIndex(indices));
const interleaved=new T.InterleavedBuffer(new Float32Array(18),6);
aliasCase(new T.BufferGeometry().setAttribute('position',new T.InterleavedBufferAttribute(interleaved,3,0)),new T.BufferGeometry().setAttribute('normal',new T.InterleavedBufferAttribute(interleaved,3,3)));
const interleavedBacking=new ArrayBuffer(144);
aliasCase(new T.BufferGeometry().setAttribute('position',new T.InterleavedBufferAttribute(new T.InterleavedBuffer(new Float32Array(interleavedBacking,0,18),6),3,0)),new T.BufferGeometry().setAttribute('position',new T.InterleavedBufferAttribute(new T.InterleavedBuffer(new Float32Array(interleavedBacking,72,18),6),3,0)));
const textureBacking=new ArrayBuffer(48),dataTexture=new T.DataTexture(new Uint8Array(textureBacking),3,4);
aliasCase(new T.BufferGeometry().setAttribute('position',new T.BufferAttribute(new Float32Array(textureBacking),3)),null,{extraTextures:[dataTexture]});
const retainedAttribute=new T.Float32BufferAttribute([0,0,0],3);
aliasCase(new T.BufferGeometry().setAttribute('position',retainedAttribute),null,{retainedGeometries:[new T.BufferGeometry().setAttribute('position',retainedAttribute)]});
const morphAttribute=new T.Float32BufferAttribute([0,0,0],3),oldMorph=new T.BufferGeometry(),liveMorph=new T.BufferGeometry();oldMorph.morphAttributes.position=[morphAttribute];liveMorph.morphAttributes.position=[morphAttribute];aliasCase(oldMorph,liveMorph);
// Two retiring wrappers may share one allocation: dispose both, count bytes once.
const retiredScene=new T.Scene(),retiredBacking=new ArrayBuffer(72);let retiredDisposals=0;
for(let offset=0;offset<=36;offset+=36){const g=new T.BufferGeometry().setAttribute('position',new T.BufferAttribute(new Float32Array(retiredBacking,offset,9),3));g.addEventListener('dispose',()=>retiredDisposals++);const mesh=new T.Mesh(g,new T.MeshStandardMaterial());mesh.visible=false;mesh.userData.replaceable=true;retiredScene.add(mesh);}
const retiredPlan=inspectReplacedAssets(retiredScene);assert.equal(retiredPlan.report.exclusiveGeometries,2);assert.equal(retiredPlan.report.detachedGeometryBytes,72);retireReplacedAssets(retiredScene,{replacementAssetsSettled:true});assert.equal(retiredDisposals,2);
// Cache release never disposes resources still used by actual instantiated clones.
const geometry=new T.BoxGeometry(),material=new T.MeshStandardMaterial(),original=new T.Scene();original.add(new T.Mesh(geometry,material));const clone=original.clone(true);let disposed=0;geometry.addEventListener('dispose',()=>disposed++);
const cache=new Map([['model',Promise.resolve({scene:original})]]);await assert.rejects(()=>releaseStartupModelCache(cache),/finish/);
const result=await releaseStartupModelCache(cache,{startupComplete:true});assert.equal(result.releasedEntries,1);assert.equal(cache.size,0);assert.equal(clone.children[0].geometry,geometry);assert.equal(disposed,0);
let finish;const old=new Promise(resolve=>{finish=resolve;});cache.set('replace',old);const clearing=releaseStartupModelCache(cache,{startupComplete:true});const newer=Promise.resolve({scene:clone});cache.set('replace',newer);finish({scene:original});await clearing;assert.equal(cache.get('replace'),newer,'new cache replacement must not be removed by old clear');
console.log('PASS: readonly ownership plan; hidden successful-placeholder only; live Source/image and distinct-geometry attribute/index/morph/interleaved/typed-array/backing-buffer aliases survive; retired allocations counted once; protected/failed/dynamic objects survive; retained templates/nightmaps/geometry protected; settled cache release never disposes active clones/new entries');
