"""Build the approved original tailored-cloth sofa for the private house.

Reuses the original reproducible sofa generator with explicit guarded edits.
Adds supported cloth-face topology and millimetre-scale foam/seam compression.
Default output is the private local sofa asset; --study writes ignored review
outputs instead. Studio images always remain ignored, never shipped to the app.
"""
import bmesh
import math
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STUDY='--study' in sys.argv
OUTPUT=ROOT/('out/sofa-reference/cloth-v2' if STUDY else 'web/house/assets/sofa-original')
OUTPUT.mkdir(parents=True,exist_ok=True)

def tailored_radius(name, original):
    # Keep the approved organic silhouette and the position of existing welts.
    return original

def cloth_detail(o,name,dims):
    if name=='Upholstered foundation':
        return
    mesh=bmesh.new();mesh.from_mesh(o.data)
    # Subdivide broad textile surfaces, not every tiny existing bevel face.
    long_edges=[edge for edge in mesh.edges if edge.calc_length()>.080]
    bmesh.ops.subdivide_edges(mesh,edges=long_edges,cuts=5,use_grid_fill=True)
    half=[d/2 for d in dims]
    for vertex in mesh.verts:
        x,y,z=vertex.co;u=x/half[0];v=y/half[1];w=z/half[2]
        if name=='Seat cushion' and z>half[2]*.65:
            # Slight central settled foam, with anchored sewn edges.
            vertex.co.z-=.0035*max(0,1-u*u)*max(0,1-v*v)
        elif name=='Back cushion' and y < -half[1]*.65:
            seam=math.exp(-((w+.60)/.22)**2)
            vertex.co.y+=.0025*seam*math.sin(17*u+2*w)**2*max(0,1-u*u)
        elif name=='Soft arm':
            if abs(x)>half[0]*.65:
                seam=math.exp(-((w+.5)/.28)**2)
                crease=.0022*seam*math.sin(19*v+2*w)**2*max(0,1-v*v)
                vertex.co.x-=math.copysign(crease,x)
            if z>half[2]*.65:
                crease=.0015*math.exp(-((abs(v)-.68)/.20)**2)*math.sin(13*u+v)**2*max(0,1-u*u)
                vertex.co.z-=crease
    mesh.normal_update();mesh.to_mesh(o.data);mesh.free();o.data.update()
    for face in o.data.polygons:face.use_smooth=True

def once(source,old,new):
    if source.count(old)!=1:raise RuntimeError('Original sofa generator contract changed: '+old[:80])
    return source.replace(old,new,1)

source=(ROOT/'tools/build_home_sofa.py').read_text()
source=once(source,"OUT=ROOT/'web/house/assets/sofa-original';OUT.mkdir(parents=True,exist_ok=True)",
            f"OUT=Path({str(OUTPUT)!r});OUT.mkdir(parents=True,exist_ok=True)")
source=once(source,"STUDIO=ROOT/'out/sofa-reference';STUDIO.mkdir(parents=True,exist_ok=True)",
            "STUDIO=ROOT/'out/sofa-reference/cloth-v2';STUDIO.mkdir(parents=True,exist_ok=True)")
source=once(source,"    b=o.modifiers.new('Soft sewn cushion radius','BEVEL');b.width=roundness;b.segments=5",
            "    b=o.modifiers.new('Soft sewn cushion radius','BEVEL');b.width=tailored_radius(name,roundness);b.segments=5")
source=once(source,"    # Keep larger faces stable, soften edges without turning seat into a balloon.",
            "    cloth_detail(o,name,dims)\n    # Supported cloth faces get physical normals, not a 0.73m2 face shaded only by its bevel corners.")
source=once(source,"    'geometry':'Original soft fabric sofa and two relaxed plain pillows. Adapted design/proportions, not manufacturer CAD.',",
            "    'geometry':'Original tailored cloth sofa: approved organic silhouette, selectively subdivided textile faces and 1.5–3.5mm seam/foam compression. Not a soft-body simulation or manufacturer CAD.',\n    'generator':'tools/build_home_sofa_cloth.py',\n    'geometry_revision':2,")
# Guarded execution of our trusted local original generator; active asset path
# was redirected above before any output operations are allowed.
exec(compile(source,str(ROOT/'tools/build_home_sofa.py'),'exec'),dict(globals(),__file__=str(ROOT/'tools/build_home_sofa.py')))
