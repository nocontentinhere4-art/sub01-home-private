// Existing licensed clean oak scan; no new bitmaps and no weathered-wood bleach.
export const CLEAN_OAK_MATCH = Object.freeze({
  sourceCoverageMetres:1.83,
  previousLinearMean:Object.freeze([.23135028684471906,.1539212166805123,.08553477523730248]),
  oakLinearMean:Object.freeze([.3598337552625335,.211141722613843,.09835921550917433]),
  factors:Object.freeze([.6429365879694269,.728994794468068,.8696162814487305]),
});
export function createCleanKitchenOak(T,architectureOak){
  const material=architectureOak.clone();
  material.color.setRGB(...CLEAN_OAK_MATCH.factors);
  // Inherit validated architecture-oak roughness/normal maps, rather than
  // compensating stained albedo with arbitrary normal/roughness multipliers.
  material.userData.lightOak=false;
  material.userData.cleanOak=true;
  material.userData.albedoPolicy='Full-scan average linear albedo matched to prior graded wood; actual spatial grain differs.';
  return material;
}
export function cleanKitchenBoxUv(geometry,worldPosition){
  const p=geometry.attributes.position,n=geometry.attributes.normal,uv=geometry.attributes.uv;
  const coverage=CLEAN_OAK_MATCH.sourceCoverageMetres;
  if(!p||!n||!uv)return;
  for(let i=0;i<p.count;i++){
    const x=Math.abs(n.getX(i)),y=Math.abs(n.getY(i)),z=Math.abs(n.getZ(i));
    const u=x>y&&x>z?p.getZ(i)+worldPosition[2]:p.getX(i)+worldPosition[0];
    const v=y>x&&y>z?p.getZ(i)+worldPosition[2]:p.getY(i)+worldPosition[1];
    uv.setXY(i,u/coverage,v/coverage);
  }
  uv.needsUpdate=true;
}
