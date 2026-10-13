"""Guarded direct-only world-sky diagnostic on exact GI21 geometry/atlas.
No installation or edits to existing indirect maps. CPU only.
"""
from pathlib import Path
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'tools/bake_home_indirect.py').is_file())
BASE=ROOT/'tools/bake_home_indirect.py'
def once(s,old,new):
 if s.count(old)!=1:raise RuntimeError('Existing bake recipe contract changed: '+old[:90])
 return s.replace(old,new,1)
s=BASE.read_text()
s=once(s,"parser.add_argument('--seed',type=int,default=0)","parser.add_argument('--seed',type=int,default=0)\nparser.add_argument('--reference-manifest',type=Path,required=True)")
s=once(s,'source,atlas,output=options.source,options.atlas,options.output',"""source,atlas,output=options.source,options.atlas,options.output
assert options.mode=='day', 'World-only direct sky is a daylight pass'
sys.path.insert(0,str(Path(__file__).parent))
from home_sky_contract import validate_recipe
reference=json.loads(options.reference_manifest.read_text())
validate_recipe(reference,hashlib.sha256(source.read_bytes()).hexdigest(),hashlib.sha256(atlas.read_bytes()).hexdigest(),options.samples,options.threads,options.seed)
if output.resolve() in {options.reference_manifest.resolve().parent,source.resolve().parent/'day',source.resolve().parent/'night'}:
    raise ValueError('Sky output must not overwrite original day/night indirect data')""")
s=once(s,'scene = bpy.context.scene',"""# Eliminate emissive material contribution as well as all light objects.
for material in bpy.data.materials:
    if not material.use_nodes:continue
    for node in material.node_tree.nodes:
        key='Emission Strength' if node.type=='BSDF_PRINCIPLED' else 'Strength' if node.type=='EMISSION' else None
        if key and key in node.inputs:
            socket=node.inputs[key]
            for link in list(socket.links):material.node_tree.links.remove(link)
            socket.default_value=0
scene = bpy.context.scene""")
s=once(s,'if mode == "day":\n    for i, z', 'if False:  # World sky only: no area/window emitters.\n    for i, z')
s=once(s,'scene.render.bake.use_pass_direct = False','scene.render.bake.use_pass_direct = True')
s=once(s,'scene.render.bake.use_pass_indirect = True','scene.render.bake.use_pass_indirect = False')
s=once(s,"'direct':False,'indirect':True,'surface_albedo':False", "'direct':True,'indirect':False,'surface_albedo':False,'world_rgb':[.76,.84,1.0],'world_strength':.12,'world_only':True,'emissive_materials_disabled':True,'source_recipe':'tools/bake_home_indirect.py','guarded_wrapper':'tools/bake_home_sky.py','reference_manifest_sha256':hashlib.sha256(options.reference_manifest.read_bytes()).hexdigest(),'source_recipe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()")
s=once(s,"'kind':'Cycles diffuse indirect radiance with receiver albedo excluded and source-material colored interreflection; runtime PI conversion unchanged'", "'kind':'World-only direct diffuse sky radiance; no indirect duplication, receiver albedo excluded; all lights and emissive shaders disabled; same GI21 atlas, runtime PI conversion unchanged'")
s=once(s,'print(f"BAKE_START',"assert not any(o.type=='LIGHT' for o in scene.objects), 'World-only pass must contain zero light objects'\nprint(f\"BAKE_START")
exec(compile(s,str(BASE),'exec'),dict(globals(),__file__=str(BASE)))
