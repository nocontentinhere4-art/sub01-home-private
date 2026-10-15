"""Exact positive-area source surfaces; zero-area padding is never support."""
import math


def area_squared(triangle):
    if len(triangle)!=3 or any(len(p)!=3 or not all(math.isfinite(v)for v in p)for p in triangle):
        raise ValueError('Finite complete physical source triangle required')
    a,b=[[triangle[n][k]-triangle[0][k]for k in range(3)]for n in(1,2)]
    return sum(v*v for v in(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]))/4


def partition(triangles):
    positive=[];zero=[]
    for i,t in enumerate(triangles):
        if area_squared(t)==0:zero.append(i)
        else:positive.append(t)
    return positive,zero
