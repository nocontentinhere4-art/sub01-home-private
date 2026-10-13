// Retire only successful, permanently hidden placeholders. Visible failures,
// interactive/protected objects and shared live material/texture Sources survive.
const materials=o=>[o.material].flat().filter(Boolean);
function textures(material){
 const found=new Set();const add=value=>{if(value?.isTexture)found.add(value);};
 for(const value of Object.values(material))add(value);
 for(const uniform of Object.values(material.uniforms||{})){add(uniform.value);if(Array.isArray(uniform.value))for(const value of uniform.value)add(value);}
 return found;
}
function storage(geometry){
 return [...Object.values(geometry.attributes||{}),geometry.index,...Object.values(geometry.morphAttributes||{}).flat()].filter(Boolean).map(attribute=>attribute.isInterleavedBufferAttribute?attribute.data:attribute);
}
export function inspectReplacedAssets(scene,{protectedObjects=[],retainedGeometries=[],retainedMaterials=[],extraTextures=[]}={}){
 const protectedSet=new Set(protectedObjects),candidates=[];
 scene.traverse(o=>{if(o.isMesh&&o.visible===false&&o.userData.replaceable&&!protectedSet.has(o))candidates.push(o);});
 const retiring=new Set(candidates),liveGeometry=new Set(retainedGeometries),liveMaterials=new Set(retainedMaterials),liveSources=new Set(),liveImages=new Set();
 scene.traverse(o=>{if(retiring.has(o))return;if(o.geometry)liveGeometry.add(o.geometry);for(const m of materials(o))liveMaterials.add(m);});
 const liveStorage=new Set(),liveArrays=new Set(),liveBuffers=new Set();
 const keepArray=array=>{if(!array)return;liveArrays.add(array);if(array.buffer)liveBuffers.add(array.buffer);};
 for(const g of liveGeometry)for(const item of storage(g)){liveStorage.add(item);keepArray(item.array);}
 const keepImage=image=>{if(!image)return;liveImages.add(image);if(Array.isArray(image)){for(const face of image)keepImage(face);}else keepArray(image.data);};
 const keep=t=>{if(!t?.isTexture)return;liveSources.add(t.source||t);keepImage(t.image);};
 for(const m of liveMaterials)for(const t of textures(m))keep(t);
 keep(scene.environment);keep(scene.background);for(const t of extraTextures)keep(t);
 const geometry=new Set(),material=new Set(),texture=new Set(),sharedGeometry=new Set();
 for(const o of candidates){
  if(o.geometry&&!liveGeometry.has(o.geometry)){
   // Three removes GPU attributes on geometry.dispose(). Distinct geometries
   // may still share an attribute, interleaved data, or a backing allocation.
   const shared=storage(o.geometry).some(item=>liveStorage.has(item)||liveArrays.has(item.array)||(item.array?.buffer&&liveBuffers.has(item.array.buffer)));
   if(shared)sharedGeometry.add(o.geometry);else geometry.add(o.geometry);
  }
  for(const m of materials(o)){
   if(liveMaterials.has(m))continue;material.add(m);
   for(const t of textures(m))if(!liveSources.has(t.source||t)&&!liveImages.has(t.image))texture.add(t);
  }
 }
 const buffers=new Set();let geometryBytes=0;
 for(const g of geometry)for(const item of storage(g)){
  // Typed-array views can share even disjoint sections of one allocation.
  // Count the allocation once, and never count one retained by a live owner.
  const buffer=item.array?.buffer;if(!buffer||liveBuffers.has(buffer)||buffers.has(buffer))continue;
  buffers.add(buffer);geometryBytes+=buffer.byteLength;
 }
 return{candidates,geometry,material,texture,report:{hiddenReplacementMeshes:candidates.length,exclusiveGeometries:geometry.size,
  geometryStorageSharedWithLive:sharedGeometry.size,detachedGeometryBytes:geometryBytes,exclusiveMaterials:material.size,exclusiveTextureObjects:texture.size,
  scope:'Detached geometry is unique CPU backing-array allocation eligible for reclamation, not measured driver/GPU memory. Geometry disposal is skipped for live attribute/interleaved/array-buffer aliases. Texture disposal only when no remaining owner shares Source/image.'}};
}
export function retireReplacedAssets(scene,{replacementAssetsSettled=false,...options}={}){
 if(!replacementAssetsSettled)throw new Error('Replacement assets must settle before fallback retirement');
 const plan=inspectReplacedAssets(scene,options);
 for(const mesh of plan.candidates){mesh.removeFromParent();mesh.geometry=null;mesh.material=null;mesh.userData.retiredFallback=true;}
 for(const geometry of plan.geometry)geometry.dispose();
 for(const material of plan.material)material.dispose();
 const images=new Set();
 for(const texture of plan.texture){texture.dispose();if(texture.image?.close&&!images.has(texture.image)){images.add(texture.image);texture.image.close();}}
 return plan.report;
}
export async function releaseStartupModelCache(cache,{startupComplete=false}={}){
 if(!startupComplete)throw new Error('Model clones must finish before releasing startup cache');
 const entries=[...cache.entries()];await Promise.allSettled(entries.map(([,promise])=>promise));let removed=0;
 for(const[key,promise]of entries)if(cache.get(key)===promise){cache.delete(key);removed++;}
 return{releasedEntries:removed,scope:'Only cached original graph/parser references released; no clone geometry, material or texture is disposed.'};
}
