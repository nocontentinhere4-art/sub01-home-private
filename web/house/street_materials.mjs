import {metricBoxUv} from './material_uv.mjs';
// Poly Haven CC0 scans. Packed diffuse/linear-roughness keeps each surface to
// two shared textures instead of three. See asset manifest for source hashes.
export function createStreetMaterials(T,{lite=false,manager}={}) {
  const loader=new T.TextureLoader(manager),size=lite?512:1024;
  function material(id,tileMetres,normalStrength){
    const root='/house/assets/residential-street-pbr/'+id;
    const map=loader.load(`${root}-color-rough-${size}.webp`);
    const normalMap=loader.load(`${root}-normal-${size}.webp`);
    map.colorSpace=T.SRGBColorSpace;normalMap.colorSpace=T.NoColorSpace;
    for(const texture of [map,normalMap]){texture.wrapS=texture.wrapT=T.RepeatWrapping;texture.anisotropy=lite?2:4;}
    const mat=new T.MeshStandardMaterial({map,normalMap,roughness:1,normalScale:new T.Vector2(normalStrength,normalStrength)});
    mat.userData.tileMetres=tileMetres;
    mat.onBeforeCompile=shader=>{
      const from='#include <roughnessmap_fragment>';
      if(!shader.fragmentShader.includes(from))throw new Error('Street roughness shader contract changed');
      shader.fragmentShader=shader.fragmentShader.replace(from,from+'\nroughnessFactor *= texture2D(map,vMapUv).a;');
    };
    mat.customProgramCacheKey=()=> 'street-packed-linear-roughness-v1';
    return mat;
  }
  return {pavement:material('concrete_pavement',1.8,.55),asphalt:material('asphalt_02',3,.4)};
}
export function streetMetricUv(geometry,position,tileMetres){
  metricBoxUv(geometry,tileMetres);
  const normal=geometry.attributes.normal,uv=geometry.attributes.uv;
  for(let i=0;i<normal.count;i++){
    const x=Math.abs(normal.getX(i)),y=Math.abs(normal.getY(i)),z=Math.abs(normal.getZ(i));
    uv.setXY(i,uv.getX(i)+(x>y&&x>z?position[2]:position[0])/tileMetres,
      uv.getY(i)+(y>x&&y>z?position[2]:position[1])/tileMetres);
  }
  uv.needsUpdate=true;
}
