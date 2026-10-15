"""Reject any source finish packet that changes the installed kitchen geometry."""
import copy,hashlib
OLD_SHA='accd954c120a60f4eb68bd869fe2f1b578517880d71b82e673af5834c32fb79d'
WOOD={'baseColorFactor':[.38,.315,.235,1],'metallicFactor':0,'roughnessFactor':.7}
HARDWARE={'baseColorFactor':[.016,.019,.021,1],'metallicFactor':.3,'roughnessFactor':.42}
def validate_material_only_variant(original,original_binary,variant,variant_binary):
 restored=copy.deepcopy(variant);restored['materials']=copy.deepcopy(original['materials'])
 if restored!=original or bytes(original_binary)!=bytes(variant_binary):
  raise ValueError('Every vertex, UV, image, hierarchy and hinge must remain exact')
 if len(original['meshes'])!=152 or len(variant['materials'])!=3:
  raise ValueError('Exact installed 152-part kitchen with three source materials required')
 for index,m in enumerate(variant['materials']):
  p=m['pbrMetallicRoughness'];expected=WOOD if index==0 else HARDWARE
  if any(p.get(k)!=v for k,v in expected.items())or m.get('emissiveFactor',[0,0,0])!=[0,0,0]:
   raise ValueError('Exact reviewed satin oak/black hardware source factors required')
  if index==0 and m.get('normalTexture',{}).get('scale')!=.34:
   raise ValueError('Reviewed photographed wood normal scale required')
 return {'all152_geometry_uv_and_images_exact':True,'all_hierarchy_and_hinges_exact':True,'material_only':True,'native_ready':False}
