// Read-only resource estimates, not a driver VRAM measurement. Called by QA,
// never changes visibility, camera, materials, asset quality or renderer state.
export function sceneBudget(scene,renderer,extraTextures=[]) {
  const geometry=new Set(),buffers=new Set(),sources=new Map();let geometryBytes=0,meshTriangles=0,meshInstances=0;
  function texture(t,role='texture'){
    if(!t?.isTexture)return;
    const source=t.source||t;
    // Three shares GPU storage for a Source only when upload/sampler cache keys
    // match. repeat/offset are matrix uniforms, so do not duplicate image bytes.
    const key=[t.wrapS,t.wrapT,t.magFilter,t.minFilter,t.anisotropy,t.format,t.internalFormat,t.type,t.generateMipmaps,t.premultiplyAlpha,t.flipY,t.unpackAlignment,t.colorSpace].join('|');
    if(!sources.has(source))sources.set(source,new Map());
    const variants=sources.get(source);
    const safeRole=/^[A-Za-z0-9_. -]{1,80}$/.test(role)?role:'texture';
    if(variants.has(key)){variants.get(key).roles.add(safeRole);return;}
    let bytes=0,known=true;
    const dimensions=[];
    const images=Array.isArray(t.image)?t.image:[t.image];
    for(let image of images){image=image?.image||image;let w=image?.naturalWidth||image?.width,h=image?.naturalHeight||image?.height;
      if(!w||!h){known=false;continue;}
      const channels=t.format===1022?3:t.format===1028?1:t.format===1030?2:4;
      const component=t.type===1015?4:t.type===1016?2:(image.data?.BYTES_PER_ELEMENT||1);
      dimensions.push({width:w,height:h,depth:image.depth||1,channels,componentBytes:component});
      const depth=image.depth||1;bytes+=w*h*depth*channels*component;
      if(t.generateMipmaps)while(w>1||h>1){w=Math.max(1,Math.floor(w/2));h=Math.max(1,Math.floor(h/2));bytes+=w*h*depth*channels*component;}
    }
    // Never inspect image.src, URLs, query strings or encoded image payloads.
    variants.set(key,{bytes,known,compressed:!!t.isCompressedTexture,dimensions,mipmaps:!!t.generateMipmaps,roles:new Set([safeRole])});
  }
  scene.traverse(object=>{
    if(object.isMesh){
      meshInstances++;
      meshTriangles+=(object.geometry.index?.count||object.geometry.attributes.position?.count||0)/3*(object.isInstancedMesh?object.count:1);
      const g=object.geometry;if(!geometry.has(g)){geometry.add(g);
        for(const attribute of [...Object.values(g.attributes),g.index,...Object.values(g.morphAttributes||{}).flat()]){
          if(!attribute)continue;const buffer=attribute.isInterleavedBufferAttribute?attribute.data:attribute;
          if(buffers.has(buffer))continue;buffers.add(buffer);geometryBytes+=buffer.array?.byteLength||0;
        }
      }
    }
    for(const material of Array.isArray(object.material)?object.material:[object.material])if(material){
      for(const [field,value] of Object.entries(material))texture(value,field);
      for(const [field,uniform] of Object.entries(material.uniforms||{})){texture(uniform.value,`uniform.${field}`);if(Array.isArray(uniform.value))for(const value of uniform.value)texture(value,`uniform.${field}`);}
    }
  });
  texture(scene.environment,'environment');texture(scene.background,'background');
  for(const value of extraTextures)texture(value,'extraTexture');
  const records=[...sources.values()].flatMap(variants=>[...variants.values()]);
  return {meshInstances,sceneTriangles:meshTriangles,uniqueGeometries:geometry.size,geometryBytes,
    decodedTextureBytes:records.reduce((sum,r)=>sum+r.bytes,0),uniqueTextureSources:sources.size,uploadVariants:records.length,
    unknownTextureVariants:records.filter(r=>!r.known).length,compressedTextureVariants:records.filter(r=>r.compressed).length,
    largestTextureUploads:records.slice().sort((a,b)=>b.bytes-a.bytes).slice(0,12).map(r=>({bytes:r.bytes,dimensions:r.dimensions,mipmaps:r.mipmaps,roles:[...r.roles].sort(),compressed:r.compressed})),
    actualFrameTriangles:renderer?.info?.render?.triangles??null,actualFrameCalls:renderer?.info?.render?.calls??null,
    actualRendererTextures:renderer?.info?.memory?.textures??null,
    limits:'Scene-resource estimate includes offscreen/hidden resources; driver, framebuffers and unreferenced decoded images excluded. Frame counters may include shadow/composite passes.'};
}
