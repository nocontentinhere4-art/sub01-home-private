"""Verify actual imported node locations before placing a first-person camera."""
import itertools
import math

def infer_import_transform(pairs, tolerance_cm=1.5):
    if len(pairs) < 3:
        raise ValueError('Need three actual matched source/imported node pivots')
    source = [p[0] for p in pairs]
    # A real 2D floor layout, not three copies of one pivot or one line.
    if not any(abs((b[0]-source[0][0])*(c[2]-source[0][2])-(b[2]-source[0][2])*(c[0]-source[0][0]))>.01 for b,c in itertools.combinations(source[1:],2)):
        raise ValueError('Matched source pivots do not span the actual house floor')
    solutions=[]
    for horizontal in [(0,2),(2,0)]:
        for signs in itertools.product((-1,1),repeat=2):
            axes=(horizontal[0],horizontal[1],1);sign=(signs[0],signs[1],1)
            offset=tuple(pairs[0][1][i]-100*sign[i]*pairs[0][0][axes[i]] for i in range(3))
            error=max(math.dist(tuple(offset[i]+100*sign[i]*src[axes[i]] for i in range(3)),dest) for src,dest in pairs)
            if error<=tolerance_cm:solutions.append({'axes':axes,'signs':sign,'offset_cm':offset,'scale_cm_per_meter':100,'max_error_cm':error,'matched_pivots':len(pairs)})
    if len(solutions)!=1:
        raise ValueError('Actual Unreal import scale/orientation is not uniquely verified at 100cm/m')
    return solutions[0]

def convert_position(source,transform):
    return tuple(transform['offset_cm'][i]+100*transform['signs'][i]*source[transform['axes'][i]] for i in range(3))
