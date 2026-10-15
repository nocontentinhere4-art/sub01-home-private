"""Prove dense-mesh acceleration retains full triangle/permutation semantics."""
import ast,math,itertools,random
from pathlib import Path
import pytest
p=Path(__file__).parents[1]/'tools/unreal_remove_frame_backings.py'
f=next(n for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='same_triangles')
module=ast.Module(body=[f],type_ignores=[]);env={'math':math,'itertools':itertools};exec(compile(module,str(p),'exec'),env);same=env['same_triangles']
def brute(expected,actual,tolerance):
 if len(expected)!=len(actual):return False
 left=list(actual)
 for triangle in expected:
  choices=[(min(max(math.dist(a,b)for a,b in zip(triangle,order))for order in itertools.permutations(t)),i)for i,t in enumerate(left)]
  if not choices:return False
  error,i=min(choices)
  if error>tolerance:return False
  left.pop(i)
 return True

def test_random_dense_multiset_and_exact_thresholds_match_full_search():
 r=random.Random(442);tol=.0001
 for _ in range(40):
  expected=[[[r.uniform(-.01,.01)for _ in range(3)]for _ in range(3)]for _ in range(25)]
  actual=[list(reversed([[v+r.uniform(-tol*.2,tol*.2)for v in point]for point in t]))for t in expected];r.shuffle(actual)
  assert same(expected,actual,tol)==brute(expected,actual,tol)
  actual[0][0][2]+=.001
  assert same(expected,actual,tol)==brute(expected,actual,tol)
 for center in[-1000,-.0002,0,.000199999999999,1000]:
  t=[[center,0,0],[center,.001,0],[center,0,.001]]
  for delta in[tol*.999,tol*1.001]:
   shifted=[[p[0]+delta,p[1],p[2]]for p in t]
   assert same([t],[shifted],tol)==brute([t],[shifted],tol)

def test_duplicate_missing_positive_surface_or_deformed_corner_still_refuses():
 t=[[0,0,0],[1,0,0],[0,1,0]];other=[[0,0,1],[1,0,1],[0,1,1]]
 assert same([t,t,other],[other,t,t],.0001)
 assert not same([t,t,other],[other,t,other],.0001)
 assert not same([t,t],[t],.0001)
 bad=[[0,0,0],[1.001,0,0],[0,1,0]]
 assert not same([t],[bad],.0001)
@pytest.mark.parametrize('tol',[0,-1,float('nan'),float('inf')])
def test_bad_tolerance_refuses(tol):
 with pytest.raises(ValueError):same([],[],tol)
