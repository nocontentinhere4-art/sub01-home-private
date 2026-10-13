"""Original coffee table revision 2: clean oak and physical grain mapping.

Uses original table generator with guarded source contracts. --study writes
ignored outputs; default writes actual private coffee-table assets. No topology
or vertex-position changes, no new images, no second material gamma grade.
"""
import sys
from pathlib import Path
ROOT=next((p for p in Path(__file__).resolve().parents if (p/'tools/build_home_coffee_table.py').is_file()),None)
if ROOT is None:raise RuntimeError('Original private house generator could not be located')
STUDY='--study' in sys.argv
OUTPUT=ROOT/('out/reference-design/prepared-clean-oak/table' if STUDY else 'web/house/assets/coffee-table-original')
def once(source,old,new):
 if source.count(old)!=1:raise RuntimeError('Original coffee table generator contract changed: '+old[:100])
 return source.replace(old,new,1)
source=(ROOT/'tools/build_home_coffee_table.py').read_text()
source=once(source,"OUT=ROOT/'web/house/assets/coffee-table-original';OUT.mkdir(parents=True,exist_ok=True)",f"OUT=Path({str(OUTPUT)!r});OUT.mkdir(parents=True,exist_ok=True)")
start=source.index("bsdf=oak.node_tree.nodes.get('Principled BSDF')")
end=source.index('parts=[]',start)
source=source[:start]+'''bsdf=oak.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Roughness'].default_value=.92
for filename,socket in [('diff.jpg','Base Color'),('rough.jpg','Roughness')]:
    image=bpy.data.images.load(str(ROOT/'web/house/assets/home_oak_veneer'/filename))
    if filename!='diff.jpg':image.colorspace_settings.name='Non-Color'
    texture=oak.node_tree.nodes.new('ShaderNodeTexImage');texture.image=image
    if filename=='diff.jpg':
        tint=oak.node_tree.nodes.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1
        tint.inputs[2].default_value=(.6429365879694269,.728994794468068,.8696162814487305,1)
        oak.node_tree.links.new(texture.outputs[0],tint.inputs[1]);oak.node_tree.links.new(tint.outputs[0],bsdf.inputs[socket])
    else:
        factor=oak.node_tree.nodes.new('ShaderNodeMath');factor.operation='MULTIPLY';factor.inputs[1].default_value=.92
        oak.node_tree.links.new(texture.outputs[0],factor.inputs[0]);oak.node_tree.links.new(factor.outputs[0],bsdf.inputs[socket])
'''+source[end:]
source=once(source,"            if abs(p.normal.z)>.5:uv=(v.x,v.y)\n            elif abs(p.normal.x)>.5:uv=(v.z,v.y)\n            else:uv=(v.z,v.x)",
'''            if abs(p.normal.z)>.5:uv=(v.y/1.83,v.x/1.83)
            elif abs(p.normal.x)>.5:
                uv=(v.z/1.83,v.y/1.83) if name=='Short recessed rail' else (v.y/1.83,v.z/1.83)
            else:
                uv=(v.z/1.83,v.x/1.83) if name in ['Solid oak top','Long recessed rail'] else (v.x/1.83,v.z/1.83)''')
source=once(source,"    'runtime_material':'Existing house M.kitchenOak (light-oak grade) or equivalent clone sharing existing CC0 fine_grained_wood maps; metric UVs.',",
"    'runtime_material':'Existing clean M.kitchenOak sharing CC0 home_oak_veneer maps, matched mean albedo, no second gamma grade; physical1.83m UVs, lengthwise top/vertical legs.',\n    'generator':'tools/build_home_coffee_table_clean_oak.py',\n    'material_revision':2,")
source=once(source,"    'texture_source':'https://polyhaven.com/a/fine_grained_wood','embedded_textures':False,","    'texture_source':'https://polyhaven.com/a/oak_veneer_01','embedded_textures':False,")
exec(compile(source,str(ROOT/'tools/build_home_coffee_table.py'),'exec'),dict(globals(),__file__=str(ROOT/'tools/build_home_coffee_table.py')))
