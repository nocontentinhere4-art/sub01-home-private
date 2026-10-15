"""Only neutral exposure correction for unchanged official manufacturer table source."""
import bpy,sys
from pathlib import Path
from mathutils import Vector
ROOT=Path('/workspace/sub01-home-private/manufacturer-around-large-r1');OUT=ROOT/'output'
bpy.ops.wm.open_mainfile(filepath=str(OUT/'muuto-around-large.blend'))
source=Path('/home/unreal/runtime-tools/build_manufacturer_around_large_blender.py').read_text();tail=source.split('# Source-only neutral photographic review;',1)[1];tail='# Source-only neutral photographic review;'+tail
tail=tail.replace("scene.world=bpy.data.worlds.new", "scene.view_settings.exposure=-1.8;scene.world=bpy.data.worlds.new").replace("'manufacturer-large-three-quarter'","'manufacturer-large-three-quarter-r2'").replace("'manufacturer-large-rim-detail'","'manufacturer-large-rim-detail-r2'")
exec(compile(tail,'unchanged-source-review-only','exec'))
