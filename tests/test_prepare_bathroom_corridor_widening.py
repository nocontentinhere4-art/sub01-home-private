import copy
import pytest
from prepare_bathroom_corridor_widening import architecture_positions, shorten_x, WALL_BOXES


def fixture():
    faces=(0,1,3,0,3,2,4,6,7,4,7,5,0,4,5,0,5,1,
           2,3,7,2,7,6,0,2,6,0,6,4,1,5,7,1,7,3)
    points=[];ids=[]
    for box in range(41):
        lo,hi=WALL_BOXES.get(box*12,((10+box,0,0),(10.5+box,1,1)))
        offset=len(points)
        points += [(x,y,z) for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])]
        ids += [offset+i for i in faces]
    return points,ids


def test_five_boxes_change_without_touching_global_roof_or_other_rooms():
    points,ids=fixture();before=copy.deepcopy(points)
    changed,triangles=architecture_positions(points,ids)
    assert points==before
    assert len(triangles)==60
    protected={v for t in range(492) if t not in triangles for v in ids[t*3:t*3+3]}
    assert all(changed[v]==before[v] for v in protected)
    assert changed[35*8][0]==pytest.approx(before[35*8][0])
    assert max(p[0] for p in changed[35*8:36*8])==pytest.approx(-.925)
    assert max(p[0] for p in changed[37*8:38*8])==pytest.approx(-.95)


def test_selection_refuses_different_wall_or_shared_protected_vertex():
    points,ids=fixture();points[35*8]=(42,0,0)
    with pytest.raises(ValueError,match='wall box differs'):architecture_positions(points,ids)
    points,ids=fixture();ids[0]=35*8
    with pytest.raises(ValueError,match='shares vertices'):architecture_positions(points,ids)


def test_shrink_keeps_west_endpoint_and_refuses_outside_points():
    assert shorten_x((-3.85,3.05,.5),-3.85,-.8)==(-3.85,3.05,.5)
    assert shorten_x((-.8,3.05,.5),-3.85,-.8)[0]==pytest.approx(-.95)
    with pytest.raises(ValueError):shorten_x((0,3.05,.5),-3.85,-.8)


def test_proposed_waypoints_clear_true_skirting_rail_and_fitted_closed_door():
    rail=-27.853170037269592
    old_wall=-77.50000357627869
    assert rail-old_wall<50
    new_skirting=-77.25000260397792-15
    assert rail-new_skirting>64
    # Door retains its measured existing +11.2cm source-relative track fit.
    fitted_door_outer=-100+11.2+3.25
    assert rail-fitted_door_outer>57
    assert -60-25>new_skirting and -60+25<rail
    assert -56.7-25>fitted_door_outer and -56.7+25<rail
