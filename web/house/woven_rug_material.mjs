// Real woven linen detail replaces an almost-flat neutral jacquard albedo.
// Reuse the existing Poly Haven CC0 rough_linen maps without new textures.
// Appearance reference (not its CAD/photos): IKEA LOHALS flatwoven jute rug,
// https://www.ikea.com/gb/en/p/lohals-rug-flatwoven-natural-00277395/
export const WOVEN_RUG_SOURCE = Object.freeze({
  oldLinearMean:Object.freeze([.40661888464052304,.40661888464052304,.40661888464052304]),
  linenLinearMean:Object.freeze([.28683863245698965,.4099622396172606,.6156103467848851]),
  // Exact per-channel ratio keeps each existing rug's average linear albedo.
  compensation:Object.freeze([1.417587586293816,.9918447245779053,.6605134022911563]),
  metresPerUvTile:2/3,
  sharedTextureRepeat:2,
  effectiveMapCoverageMetres:1/3,
  roughness:.98,
  normalStrength:.65,
});

export function createWovenRugMaterial(T,linen,color='#c4b49a'){
  const material=linen.clone();
  material.color.copy(new T.Color(color));
  material.color.multiply(new T.Color().setRGB(...WOVEN_RUG_SOURCE.compensation));
  material.roughnessMap=null;material.roughness=WOVEN_RUG_SOURCE.roughness;
  material.normalScale.set(WOVEN_RUG_SOURCE.normalStrength,WOVEN_RUG_SOURCE.normalStrength);
  material.metalness=0;
  material.userData.wovenRug={source:'Poly Haven rough_linen, existing shared maps',
    colourPolicy:'Compensated mean linear albedo matches prior neutral jacquard source; fine-scale reflectance/normal differs.',
    effectiveMapCoverageMetres:WOVEN_RUG_SOURCE.effectiveMapCoverageMetres};
  return material;
}

// Keep the existing geometry and UV2 lightmap. Align ordinary UVs across the
// body and raised stitching; independent local box projections repeat a sliver
// at every seam and look like rectangular boards rather than continuous weave.
export function alignRugTextureUv(geometry,position,origin,metresPerUvTile=2/3){
  if(!(metresPerUvTile>0)||!Number.isFinite(metresPerUvTile))throw new Error('Invalid rug texture coverage');
  const p=geometry.attributes.position,n=geometry.attributes.normal,uv=geometry.attributes.uv;
  if(!p||!n||!uv)return;
  const delta=position.map((v,i)=>v-origin[i]);
  for(let i=0;i<p.count;i++){
    const x=Math.abs(n.getX(i)),y=Math.abs(n.getY(i)),z=Math.abs(n.getZ(i));
    const u=x>y&&x>z?p.getZ(i)+delta[2]:p.getX(i)+delta[0];
    const v=y>x&&y>z?p.getZ(i)+delta[2]:p.getY(i)+delta[1];
    uv.setXY(i,u/metresPerUvTile,v/metresPerUvTile);
  }
  uv.needsUpdate=true;
}

// One flat cloth body and one continuous sewn perimeter: no transverse bars.
// Positions remain inside the prior rug footprint and body height. The hem's
// small raised edge replaces twelve 3mm stripes, so a fresh geometry bake is due.
export function createWovenRugGeometries(RoundedBoxGeometry,mergeGeometries,width,depth){
  if(![width,depth].every(v=>Number.isFinite(v)&&v>.15))throw new Error('Invalid rug dimensions');
  const body=new RoundedBoxGeometry(width,.018,depth,2,.006);
  const edge=.022,hemWidth=.018,hemHeight=.0025;
  const parts=[];
  for(const z of [-depth/2+edge,depth/2-edge]){
    const geometry=new RoundedBoxGeometry(width-edge*2,hemHeight,hemWidth,2,.00075);
    geometry.translate(0,.0105,z);parts.push(geometry);
  }
  for(const x of [-width/2+edge,width/2-edge]){
    const geometry=new RoundedBoxGeometry(hemWidth,hemHeight,depth-edge*2,2,.00075);
    geometry.translate(x,.0105,0);parts.push(geometry);
  }
  const hem=mergeGeometries(parts,false);
  for(const part of parts)part.dispose();
  if(!hem){body.dispose();throw new Error('Rug hem geometry could not merge');}
  alignRugTextureUv(body,[0,.021,0],[0,0,0]);
  alignRugTextureUv(hem,[0,.021,0],[0,0,0]);
  body.computeBoundingBox();hem.computeBoundingBox();
  return {body,hem};
}
