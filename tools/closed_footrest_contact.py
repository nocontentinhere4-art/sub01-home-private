"""Footrest-only closed-component containment; no nearest-face sign shortcut.

Unsigned nearest distance still comes from actual mesh BVH. UV/normal-seam
vertices weld only at1e-9cm for topology; collision thresholds remain exactly0.
"""
from collections import Counter
import math


class ClosedFootrest:
    def __init__(self,triangles,node_ids):
        import numpy as np
        self.np=np;triangles=np.asarray(triangles,float);node_ids=np.asarray(node_ids,int)
        if len(triangles)!=len(node_ids)or not np.isfinite(triangles).all():raise ValueError('Finite actual triangles and exact part identities required')
        self.parts=[];self.proof=[]
        for node in sorted(set(node_ids.tolist())):
            tri=triangles[node_ids==node];edges=Counter();vertices={}
            for face in tri:
                ids=[]
                for p in face:
                    key=tuple(round(float(v),9)for v in p);vertices.setdefault(key,len(vertices));ids.append(vertices[key])
                if len(set(ids))!=3:raise ValueError('Degenerate physical footrest triangle '+str(node))
                for a,b in zip(ids,ids[1:]+ids[:1]):edges[tuple(sorted((a,b)))]+=1
            bad=[edge for edge,count in edges.items()if count!=2]
            if bad:raise ValueError('Footrest part is not closed/manifold '+str(node)+' badedges='+str(len(bad)))
            self.parts.append((node,tri,tri.min(axis=(0,1)),tri.max(axis=(0,1))))
            self.proof.append({'node':node,'triangles':len(tri),'welded_vertices':len(vertices),'boundary_or_nonmanifold_edges':0})
        if len(self.parts)!=19:raise ValueError('All19 physical footrest parts must be closed')

    def _ray(self,point,tri,direction):
        np=self.np;direction=np.asarray(direction,float);direction/=np.linalg.norm(direction)
        e1=tri[:,1]-tri[:,0];e2=tri[:,2]-tri[:,0];pvec=np.cross(direction,e2);det=np.einsum('ij,ij->i',e1,pvec)
        scale=np.linalg.norm(e1,axis=1)*np.linalg.norm(e2,axis=1)
        valid=np.abs(det)>32*np.finfo(float).eps*scale
        if not valid.any():return None
        e1,e2,pvec,det=e1[valid],e2[valid],pvec[valid],det[valid];tv=point-tri[valid,0]
        u=np.einsum('ij,ij->i',tv,pvec)/det;q=np.cross(tv,e1);v=np.einsum('j,ij->i',direction,q)/det;t=np.einsum('ij,ij->i',e2,q)/det
        possible=(t>0)&(u>=-1e-11)&(v>=-1e-11)&(u+v<=1+1e-11)
        # An edge/vertex ray is ambiguous, never silently interpreted as outside.
        # Retry another direction instead of advancing over a thin surface.
        if np.any(possible&((np.abs(u)<1e-11)|(np.abs(v)<1e-11)|(np.abs(1-u-v)<1e-11))):return None
        hits=(t>0)&(u>0)&(v>0)&(u+v<1)
        return bool(np.count_nonzero(hits)%2)

    def contains_part(self,point,node):
        np=self.np;point=np.asarray(point,float)
        matches=[p for p in self.parts if p[0]==node]
        if len(matches)!=1:raise ValueError('Exact footrest part identity required')
        _,tri,lo,hi=matches[0]
        if np.any(point<lo)or np.any(point>hi):return False
        votes=[]
        for direction in[(1,math.sqrt(2),math.sqrt(3)),(-math.sqrt(5),1,math.sqrt(7)),(math.sqrt(11),-math.sqrt(13),1),(1,math.sqrt(17),-math.sqrt(19)),(-math.sqrt(23),math.sqrt(29),1)]:
            vote=self._ray(point,tri,direction)
            if vote is not None:votes.append(vote)
            if len(votes)>=2:
                if len(set(votes))!=1:raise ValueError('Closed footrest containment rays disagree; refuse contact verdict')
                return votes[0]
        raise ValueError('Footrest edge/vertex ray ambiguity; refuse contact verdict')

    def contains(self,point):
        np=self.np;p=np.asarray(point,float)
        for node,tri,lo,hi in self.parts:
            if np.all(p>=lo)and np.all(p<=hi)and self.contains_part(p,node):return True
        return False

    def signed_distance(self,point,unsigned_distance):
        if unsigned_distance<0 or not math.isfinite(unsigned_distance):raise ValueError('Actual finite nonnegative nearest distance required')
        if unsigned_distance==0:return 0.
        return -unsigned_distance if self.contains(point)else unsigned_distance
