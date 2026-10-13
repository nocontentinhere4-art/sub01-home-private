// Static receivers whose validated daylight map contains occluded sky DIRECT
// plus indirect diffuse. Dynamic objects keep the normal Three lighting path.
// Local shader substitution only: never mutate global Three ShaderChunks.
function replaceOnce(source,needle,replacement,label){
  if(source.split(needle).length!==2)throw new Error(`Unsupported Three shader source: ${label}`);
  return source.replace(needle,replacement);
}
export function bakedReceiverChunks(T){
  const original=T.ShaderChunk;
  let begin=replaceOnce(original.lights_fragment_begin,
    'vec3 irradiance = getAmbientLightIrradiance( ambientLightColor );',
    'vec3 irradiance = vec3( 0.0 ); // Occluded sky diffuse comes from the validated map.', 'ambient diffuse');
  begin=replaceOnce(begin,
    'irradiance += getHemisphereLightIrradiance( hemisphereLights[ i ], geometryNormal );',
    '// Baked static receiver: no unoccluded hemisphere diffuse.', 'hemisphere diffuse');
  // iblIrradiance is ALSO used for specular multiscattering and sheen. Keep its
  // sampling and remove only its diffuse addition inside the physical BRDF.
  const physical=replaceOnce(original.lights_physical_pars_fragment,
    'reflectedLight.indirectDiffuse += diffuse * cosineWeightedIrradiance;',
    '// Baked static receiver: diffuse IBL comes from the occluded daylight map.', 'diffuse IBL');
  const maps=replaceOnce(original.lights_fragment_maps,
    'irradiance += lightMapIrradiance;',
    'irradiance += lightMapIrradiance + texture2D(homeNightLightMap, vLightMapUv).rgb * homeNightLightIntensity;', 'day/night map');
  return{begin,physical,maps};
}
export function patchBakedReceiverShader(T,shader,{nightLightMap,nightLightIntensity,materialGradeOak=null}={}){
  if(!nightLightMap||!nightLightIntensity)throw new TypeError('Shared night map/intensity uniforms required');
  const chunks=bakedReceiverChunks(T);
  let fragment=replaceOnce(shader.fragmentShader,'#include <lights_fragment_begin>',chunks.begin,'receiver lights begin include');
  fragment=replaceOnce(fragment,'#include <lights_physical_pars_fragment>',chunks.physical,'receiver physical include');
  fragment=replaceOnce(fragment,'#include <lights_fragment_maps>',chunks.maps,'receiver maps include');
  shader.fragmentShader='uniform sampler2D homeNightLightMap;\nuniform float homeNightLightIntensity;\n'+fragment;
  shader.uniforms.homeNightLightMap=nightLightMap;
  shader.uniforms.homeNightLightIntensity=nightLightIntensity;
  if(materialGradeOak)materialGradeOak(shader);
}
export function configureBakedReceiverLighting(T,material,{
  occludedDayReady=false,nightLightMap,nightLightIntensity,materialGradeOak=null,
}={}){
  if(!occludedDayReady)throw new Error('Validated occluded direct-sky + indirect daylight map required before switching lighting');
  if(!material?.isMeshStandardMaterial||!material.lightMap)
    throw new TypeError('Only actual Standard/Physical lightMap receivers may use baked diffuse lighting');
  bakedReceiverChunks(T); // Fail before attaching a callback if Three changed.
  const graded=!!material.userData.lightOak;
  if(graded&&!materialGradeOak)throw new TypeError('Existing oak grading callback required');
  material.onBeforeCompile=shader=>patchBakedReceiverShader(T,shader,{
    nightLightMap,nightLightIntensity,materialGradeOak:graded?materialGradeOak:null,
  });
  material.customProgramCacheKey=()=> 'private-occluded-baked-diffuse-v1'+(graded?'-oak':'');
  material.needsUpdate=true;
  return material;
}
