"""Assemble self-contained, verified indirect+occluded-sky candidate. Never install.
Blender --background --python tools/combine_home_sky.py -- BASE_DIR SKY_DIR DEST.
BASE_DIR has source.glb, architecture.glb and original day/night directories.
SKY_DIR contains the finished world-only direct sky bake.json and indirect.exr.
"""
import sys,json,hashlib,shutil
from pathlib import Path
import bpy,numpy as np
sys.path.insert(0,str(Path(__file__).parent))
from home_sky_contract import validate_sky_pair,validate_night,validate_radiance_bounds
base,sky,destination=map(Path,sys.argv[sys.argv.index('--')+1:])
base,sky,destination=base.resolve(),sky.resolve(),destination.resolve()
if destination==base or destination.is_relative_to(base) or destination==sky or destination.is_relative_to(sky):
    raise ValueError('Candidate output must not overwrite original bake directories')
indirect=json.loads((base/'day/bake.json').read_text());direct=json.loads((sky/'bake.json').read_text());night=json.loads((base/'night/bake.json').read_text())
matched=validate_sky_pair(indirect,direct);validate_night(indirect,night)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for name,key in [('source.glb','source_sha256'),('architecture.glb','atlas_sha256')]:
    if sha(base/name)!=matched[key]:raise ValueError('Geometry hash mismatch: '+name)
inputs=[(base/'day/indirect.exr',indirect),(sky/'indirect.exr',direct),(base/'night/indirect.exr',night)]
for path,record in inputs:
    if sha(path)!=record.get('output_sha256'):raise ValueError('Raw bake hash mismatch: '+str(path))
arrays=[];sizes=[]
for path,record in inputs[:2]:
    img=bpy.data.images.load(str(path),check_existing=False);sizes.append(tuple(img.size))
    if sizes[-1]!=(matched['width'],matched['height']):raise ValueError('Image dimensions differ from atlas')
    array=np.empty(len(img.pixels),dtype=np.float32);img.pixels.foreach_get(array);array=array.reshape(-1,4)
    validate_radiance_bounds(float(array[:,:3].min()),float(array[:,:3].max()),bool(np.isfinite(array).all()))
    arrays.append(array)
combined=arrays[0].copy();combined[:,:3]+=arrays[1][:,:3];combined[:,3]=1
validate_radiance_bounds(float(combined[:,:3].min()),float(combined[:,:3].max()),bool(np.isfinite(combined).all()))
destination.mkdir(parents=True,exist_ok=False)
for name in ['source.glb','architecture.glb']:shutil.copy2(base/name,destination/name)
components=[]
for role,path,record in [('indirect',inputs[0][0],indirect),('sky-direct',inputs[1][0],direct)]:
    folder=destination/'day/components'/role;folder.mkdir(parents=True)
    shutil.copy2(path,folder/'indirect.exr');shutil.copy2(path.parent/'bake.json',folder/'bake.json')
    components.append({'role':role,'manifest_file':str((folder/'bake.json').relative_to(destination/'day')),'raw_file':str((folder/'indirect.exr').relative_to(destination/'day')),'manifest_sha256':sha(folder/'bake.json'),'raw_sha256':sha(folder/'indirect.exr')})
shutil.copytree(base/'night',destination/'night')
img=bpy.data.images.new('Combined indirect plus world direct sky',*sizes[0],alpha=False,float_buffer=True);img.colorspace_settings.name='Non-Color';img.pixels.foreach_set(combined.reshape(-1));img.update()
output=destination/'day/combined.exr';img.filepath_raw=str(output);img.file_format='OPEN_EXR';img.save()
# Re-decode output to verify the sum written to disk, not only the in-memory recipe.
check=bpy.data.images.load(str(output),check_existing=False);decoded=np.empty(len(check.pixels),dtype=np.float32);check.pixels.foreach_get(decoded);decoded=decoded.reshape(-1,4)
if not np.array_equal(decoded[:,:3],combined[:,:3]):raise ValueError('Stored EXR is not the exact float32 component sum')
manifest=dict(matched,mode='day',finished=True,direct=True,indirect=True,surface_albedo=False,combined_world_sky=True,kind='Linear float32 sum: original GI21 indirect + world-only visibility-aware DIRECT sky diffuse radiance. No practical/direct-sun duplication; no albedo.',components=components,output_file='combined.exr',output_sha256=sha(output),sum_verified=True,sum_operation='float32 indirectRGB + directSkyRGB; no grading/scaling',night_source_sha256=sha(base/'night/indirect.exr'),night_preserved_sha256=sha(destination/'night/indirect.exr'),assembler='tools/combine_home_sky.py',assembler_sha256=sha(Path(__file__)))
assert manifest['night_source_sha256']==manifest['night_preserved_sha256']
(destination/'day/bake.json').write_text(json.dumps(manifest,indent=2)+'\n')
scene=bpy.context.scene;scene.render.image_settings.file_format='HDR';scene.render.image_settings.color_mode='RGB';scene.view_settings.view_transform='Raw';img.save_render(str(destination/'day/combined.hdr'),scene=scene)
print('VERIFIED_SKY_COMBINATION',json.dumps(manifest),flush=True)
