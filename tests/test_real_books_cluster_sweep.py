import math
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_real_shelf_books as books


def legacy(parts,overlap=.5):
    boxes=[books._aabb(p['points']) for p in parts];parent=list(range(len(parts)))
    def find(i):
        while parent[i]!=i:i=parent[i]
        return i
    for i in range(len(parts)):
        for j in range(i+1,len(parts)):
            lo=tuple(max(boxes[i][0][k],boxes[j][0][k]) for k in range(3));hi=tuple(min(boxes[i][1][k],boxes[j][1][k]) for k in range(3))
            small=min(books._volume(*boxes[i]),books._volume(*boxes[j])) or 1e-12
            if books._volume(lo,hi)>=overlap*small:parent[find(j)]=find(i)
    groups={}
    for i in range(len(parts)):groups.setdefault(find(i),[]).append(i)
    return [groups[k] for k in sorted(groups)]


def part(low,high):return {'points':[low,high]}


class ClusterSweepTests(unittest.TestCase):
    def test_random_exact_result_and_order_parity(self):
        generator=random.Random(98311)
        for scene in range(150):
            parts=[]
            for _ in range(generator.randrange(45)):
                low=tuple(generator.uniform(-2,2) for _ in range(3))
                high=tuple(value+generator.choice((0,.001,.05,.4,2)) for value in low)
                parts.append(part(low,high))
            for overlap in (.01,.5,1,1.5,0,-.1,float('nan'),float('inf')):
                self.assertEqual(books.cluster_parts(parts,overlap),legacy(parts,overlap),(scene,overlap))

    def test_root_order_preserved_across_transitive_overlaps_and_touching(self):
        parts=[part((0,0,0),(1,1,1)),part((.9,0,0),(1.9,1,1)),part((.5,0,0),(1.5,1,1)),part((5,0,0),(6,1,1)),part((6,0,0),(7,1,1))]
        self.assertEqual(books.cluster_parts(parts,.4),legacy(parts,.4))
        self.assertNotEqual(books.cluster_parts(parts,.4)[-1],[3,4])
        tiny=[part((0,0,0),(0,1,1)),part((2,0,0),(2,1,1))]
        self.assertEqual(books.cluster_parts(tiny,1e-320),legacy(tiny,1e-320))

    def test_sparse_and_zero_volume_islands_avoid_quadratic_narrow_phase(self):
        parts=[part((i*2,0,0),(i*2+1,1,1)) for i in range(2500)]
        parts.extend(part((0,0,i),(1,1,i)) for i in range(2500))
        with patch.object(books,'_volume',wraps=books._volume) as volume:
            groups=books.cluster_parts(parts)
        self.assertEqual(groups,[[i] for i in range(len(parts))])
        self.assertEqual(volume.call_count,len(parts))


if __name__=='__main__':unittest.main()
