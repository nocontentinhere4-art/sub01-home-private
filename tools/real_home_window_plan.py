"""Measured original window construction plan; source only, no native mutation.

References establish real construction principles. This is original modeled
joinery sized to the exact955 home, not licensed manufacturer CAD/certification.
"""
import json
from pathlib import Path
SOURCE_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
UNITS=[
 {'id':'WestSouth','facade':'west','rough_u':[-3.84,-1.41],'lights':3,'operable_light':0,'old_nodes':[5,6,7,8,9]},
 {'id':'WestMiddleTV','facade':'west','rough_u':[-1.29,1.29],'lights':3,'operable_light':None,'old_nodes':[11,12,13,14,15]},
 {'id':'WestNorth','facade':'west','rough_u':[1.41,3.84],'lights':3,'operable_light':2,'old_nodes':[17,18,19,20,21]},
 {'id':'FrontWest','facade':'front','rough_u':[-3.91,-.15],'lights':4,'operable_light':0,'old_nodes':[23,24,25,26,27]},
 {'id':'FrontMiddle','facade':'front','rough_u':[.20,1.10],'lights':1,'operable_light':0,'old_nodes':[29,30,31,32,33]},
 {'id':'FrontEast','facade':'front','rough_u':[2.80,3.70],'lights':1,'operable_light':0,'old_nodes':[35,36,37,38,39]},
]
PIERS=[[-.15,.20],[1.10,1.45],[2.55,2.80],[3.70,3.91]]
DIMENSIONS={'rough_v':[.70,2.575],'installation_gap_m':.020,'wall_depth_m':.180,'overall_profile_depth_m':.149,'mainframe_reference_depth_m':.114,'mainframe_sightline_m':.035,'sash_sightline_m':.035,'glass_pane_thickness_m':.004,'glass_cavity_m':.012,'glass_layers':3,'sill_thickness_m':.020,'interior_sill_projection_from_wall_m':.060}
REFERENCES=[
 {'url':'https://velfac.co.uk/windows/velfac-products/velfac-200/','observed_via':'playwright-isolated','used_for':'Composite timber/aluminium frames; distinguish actual fixed and outward-operating units; three-layer glazing and consistent sightlines. Not a copied product model.'},
 {'url':'https://products-domestic.velfac.co.uk/downloads/31467/33604/33607/#p-28240','observed_via':'playwright-isolated','used_for':'Sill/head/jamb interfaces, weather seal, packers, air barrier and supported sill rather than a floating four-bar box.'},
 {'url':'https://cdn.velfac.com/files/18522/V200E.W1.02.A.C.002.A%20-%20Clipped%20cill.pdf/Preview?mimetype=image/jpg','observed_via':'playwright-isolated actual drawing viewed','drawing':'V200E.W1.02.A.C.002.A','used_for':'Drawing labels149mm overall/114mm mainframe option, nominal20mm opening allowance, clipped exterior cill/drip. Our wall remains180mm; surrounding masonry/insulation layers are not copied.'},
 {'url':'https://www.andersenwindows.com/windows-and-doors/windows/casement-windows/400-series-casement-window','observed_via':'playwright-isolated','used_for':'Independent residential reference for wood interiors, stepped profiles and real operating hardware. No claim this model matches400Series dimensions or licensed CAD.'},
]


def unit_plan(row):
 result=dict(row);lo,hi=row['rough_u'];v0,v1=DIMENSIONS['rough_v'];gap=DIMENSIONS['installation_gap_m'];result.update(rough_v=[v0,v1],unit_u=[lo+gap,hi-gap],unit_v=[v0+gap,v1-gap]);result['unit_width_m']=hi-lo-2*gap;result['unit_height_m']=v1-v0-2*gap
 if result['unit_width_m']<=0 or result['unit_height_m']<=0:raise ValueError('Positive measured opening required')
 return result


def plan():
 units=[unit_plan(row)for row in UNITS]
 return {'schema':'sub01.original-real-home-window-plan.v1','original_source_sha256':SOURCE_SHA,'construction_dimensions':DIMENSIONS,'units':units,'new_front_wall_infill_piers_u_m':PIERS,'entry_boundary_renderer_owned':{'rough_u':[1.45,2.55],'authentic_frame_u':[1.48,2.51],'renderer_owned_packer_gaps':[[1.45,1.48],[2.51,2.55]],'renderer_owned_transom_v':[2.145,2.575]},'upper_fenestration_renderer_owned':{'retire_nodes':list(range(41,49)),'rough_floor_m':3.025,'rough_header_m':5.45},'protected_tv_backer':{'source_node':158,'u_m':[-1.125,1.025],'interior_normal_m':[.09,.23],'v_m':[0,2.8],'policy':'Middle west glazing fixed behind actual backer; no new trim/sill may enter that protected volume'},'exact_old_lower_frame_nodes':sorted(n for u in units for n in u['old_nodes']),'references':REFERENCES,'manufacturer_cad_reused':False,'all_new_profile_geometry_original':True,'source_ready':False,'native_ready':False,'windows_activity_ready':False}

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();Path(a.output).write_text(json.dumps(plan(),indent=2)+'\n')
