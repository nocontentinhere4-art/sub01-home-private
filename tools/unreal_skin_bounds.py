"""Never infer a runtime body from zero/unbuilt skeletal bounds."""
import math

def valid_extent(extent):
    return len(extent)==3 and all(math.isfinite(v)and v>0 for v in extent)

def select_built_primary(rows):
    candidates=[row for row in rows if valid_extent(row['row'].get('bounds_extent_cm',[]))]
    if not candidates:return None
    return max(candidates,key=lambda row:math.prod(row['row']['bounds_extent_cm']))

def source_body_candidate(doc,rows,canonical):
    sources=[]
    for index,mesh in enumerate(doc['meshes']):
        count=sum(doc['accessors'][p['attributes']['POSITION']]['count']for p in mesh['primitives'])
        names={canonical(mesh.get('name',''))}|{canonical(n.get('name',''))for n in doc.get('nodes',[])if n.get('mesh')==index}
        sources.append((count,names))
    _,names=max(sources,key=lambda item:item[0])
    matches=[row for row in rows if any(name and name in canonical(row['mesh'].get_name())for name in names)]
    return matches[0]if len(matches)==1 else None
