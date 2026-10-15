"""Independent public DXF six-body inventory versus real STEP tessellation bounds."""
import json,math,itertools,hashlib
from pathlib import Path
R=Path('/workspace/sub01-home-private/official-grohe-concetto-r1')
s=(R/'source/grohe-32663003-3d.dxf').read_text(errors='replace').splitlines();pairs=[(s[i].strip(),s[i+1].strip())for i in range(0,len(s)-1,2)];entities=[];e=[]
for k,v in pairs:
 if k=='0':
  if e:entities.append(e)
  e=[(k,v)]
 else:e.append((k,v))
blocks={};name=None
for row in entities:
 d=dict(row);kind=d['0']
 if kind=='BLOCK':name=d['2'];blocks[name]=[]
 elif kind=='ENDBLK':name=None
 elif kind=='VERTEX'and name and int(d.get('70','0'))&64:blocks[name].append([float(d.get(k,'0'))for k in('10','20','30')])
insert_names=[]
for row in entities:
 d=dict(row)
 if d['0']=='INSERT':
  assert all(abs(float(d.get(k,'0')))<1e-9 for k in('10','20','30','50'))
  assert all(float(d.get(k,'1'))==1 for k in('41','42','43'));insert_names.append(d['2'])
dxf=[{'name':n,'bounds_mm':[[min(p[i]for p in blocks[n])for i in range(3)],[max(p[i]for p in blocks[n])for i in range(3)]]}for n in insert_names]
cad=json.loads((R/'tessellated-cad.json').read_text());step=[{'name':p['name'],'bounds_mm':[[min(v[i]for v in p['vertices_m'])*1000 for i in range(3)],[max(v[i]for v in p['vertices_m'])*1000 for i in range(3)]]}for p in cad['parts']]
assert len(dxf)==len(step)==6
cost=lambda a,b:max(abs(x-y)for la,lb in zip(a['bounds_mm'],b['bounds_mm'])for x,y in zip(la,lb))
perm=min(itertools.permutations(range(6)),key=lambda p:sum(cost(step[i],dxf[p[i]])for i in range(6)))
rows=[{'step':step[i],'independent_official_DXF':dxf[perm[i]],'max_bounds_difference_mm':cost(step[i],dxf[perm[i]])}for i in range(6)]
result={'schema':'sub01.official-grohe-independent-cad-inventory.v1','step_reader_warning':'One unresolved reference emitted by OCP STEP reader; no silent omission assumed','independent_public_DXF_mesh_bodies':6,'step_tessellated_bodies':6,'correspondence':rows,'max_bounds_difference_mm':max(r['max_bounds_difference_mm']for r in rows),'complete_six_body_coverage_evidence':max(r['max_bounds_difference_mm']for r in rows)<1,'geometry_edited':False}
(R/'output/independent-official-cad-inventory.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
