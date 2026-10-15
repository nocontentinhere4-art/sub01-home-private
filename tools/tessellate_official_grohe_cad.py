"""Faithful official GROHE Concetto32663003 STEP tessellation; source mm, 0.1mm deflection."""
import json,hashlib
from pathlib import Path
from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID,TopAbs_FACE,TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
ROOT=Path('/workspace/sub01-home-private/official-grohe-concetto-r1');source=ROOT/'source/grohe-32663003.stp'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='72cecffe4e0a473068f6d6fc6a837bb6f9638cb9a64acd2197a7d2f8f375aff6'
r=STEPControl_Reader();assert r.ReadFile(str(source))==IFSelect_RetDone;r.TransferRoots();shape=r.OneShape()
mesher=BRepMesh_IncrementalMesh(shape,.1,False,.08,False);mesher.Perform();assert mesher.IsDone()
solids=[];ex=TopExp_Explorer(shape,TopAbs_SOLID)
while ex.More():solids.append(TopoDS.Solid(ex.Current()));ex.Next()
if not solids:solids=[shape]
parts=[]
for si,solid in enumerate(solids):
 vertices=[];faces=[];face_ranges=[];ex=TopExp_Explorer(solid,TopAbs_FACE)
 while ex.More():
  f=TopoDS.Face(ex.Current());loc=TopLoc_Location();tri=BRep_Tool.Triangulation_s(f,loc)
  if tri is not None:
   start=len(vertices);tr=loc.Transformation();vertices.extend([[p.X()/1000,p.Y()/1000,p.Z()/1000]for p in(tri.Node(i).Transformed(tr)for i in range(1,tri.NbNodes()+1))])
   first=len(faces)
   for i in range(1,tri.NbTriangles()+1):
    a,b,c=tri.Triangle(i).Get();ids=[start+a-1,start+b-1,start+c-1]
    if f.Orientation()==TopAbs_REVERSED:ids.reverse()
    faces.append(ids)
   face_ranges.append([first,len(faces)])
  ex.Next()
 if faces:parts.append({'name':f'GroheConcetto_{si:03}','vertices_m':vertices,'faces':faces,'source_cad_face_triangle_ranges':face_ranges})
points=[p for part in parts for p in part['vertices_m']];bounds=[[min(p[i]for p in points)for i in range(3)],[max(p[i]for p in points)for i in range(3)]]
report={'schema':'sub01.official-grohe-step-tessellation.v1','manufacturer':'GROHE AG','product':'Concetto32663003','original_step_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'deflection_mm':.1,'angular_deflection_radians':.08,'source_units':'mm','physical_conversion_only':.001,'geometry_reconstructed':False,'parts':parts,'bounds_m':bounds,'triangles':sum(len(p['faces'])for p in parts),'license':'Official manufacturer architecture/CAD download; not CC0; private candidate'}
(ROOT/'tessellated-cad.json').write_text(json.dumps(report));print('OFFICIAL_CAD_TESSELLATED',len(parts),report['triangles'],bounds,flush=True)
