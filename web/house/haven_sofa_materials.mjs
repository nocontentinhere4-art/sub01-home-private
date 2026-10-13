// Preserve the licensed source's actual cloth/wood appearance and PBR channels.
export function createHavenSofaMaterials(T, loader, assetRoot, anisotropy = 4) {
  const load = (name, color = false) => {
    const texture = loader.load(assetRoot + 'haven-sofa/maps/' + name + '.jpg');
    texture.flipY = false; // Preserve the source glTF texture coordinate convention.
    texture.wrapS = texture.wrapT = T.RepeatWrapping;
    texture.anisotropy = anisotropy;
    if (color) texture.colorSpace = T.SRGBColorSpace;
    return texture;
  };
  const linen = new T.MeshPhysicalMaterial({
    map: load('linen_basecolor', true), normalMap: load('linen_normal'),
    roughnessMap: load('linen_roughness'), roughness: 1, metalness: 0,
    normalScale: new T.Vector2(.43, .43), side: T.DoubleSide,
    sheen: 1, sheenColor: new T.Color(1, 1, 1), sheenRoughness: .5,
  });
  const legs = new T.MeshPhysicalMaterial({
    map: load('walnut_basecolor', true), normalMap: load('walnut_normal'),
    roughnessMap: load('walnut_roughness'), roughness: 1, metalness: 0,
    normalScale: new T.Vector2(.30, .30), side: T.DoubleSide,
    clearcoat: .18, clearcoatRoughness: .34,
  });
  const seams = new T.MeshStandardMaterial({
    color: new T.Color().setRGB(.43, .36, .26), roughness: .84, side: T.DoubleSide,
  });
  const felt = new T.MeshStandardMaterial({
    color: new T.Color().setRGB(.025, .022, .020), roughness: .92, side: T.DoubleSide,
  });
  return {Haven_linen: linen, Haven_legs: legs, Haven_seams: seams, Haven_felt: felt};
}
