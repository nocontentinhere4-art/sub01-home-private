"""Exact authored house light recipe in SI units, converted for Unreal placement.

Three point/spot intensity is candela and directional intensity lux; Unreal
supports those same units directly. The Cycles 683 conversion MUST NOT be
applied here: it corrected the Blender glTF importer, not authored radiometry.
The hour is an explicit static authoring preview, not the brain's live clock.
"""
import math

def srgb_hex_linear(value):
    values=[int(value[i:i+2],16)/255 for i in (1,3,5)]
    return [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]

def authored_lights(hour=11,lamps_on=False):
    angle=(hour-6)/12*math.pi;sun=max(0,math.sin(angle))
    rows=[dict(name='SUN',kind='directional',position=[-14*math.cos(angle),3+15*sun,12*sun],target=[0,1,0],color='#ffba7b' if sun<.35 else '#ffead0',intensity=3.2*sun,unit='lux')]
    for name,kind,position,color,intensity,distance in [
        ('DeskLamp','point',[1.1,1.35,-3.15],'#ffd49a',12,5),
        ('BedLamp','point',[-3.55,3.768,-3.1],'#ffc88a',3.5,4),
        ('KitchenWork','point',[-2.7,1.55,-3.45],'#ffe2b9',2.4,1.8),
        ('LowerPendant','spot',[-2,2.43,.5],'#ffddb0',10,6),
        ('UpperPendant','point',[2,4.98,-.2],'#ffddb0',10,5),
    ]:
        row=dict(name=name,kind=kind,position=position,color=color,intensity=intensity if lamps_on else 0,unit='candela',distance=distance)
        if kind=='spot':row.update(target=[-2,0,.5],outer_angle_degrees=180*.37,inner_angle_degrees=180*.37*.65)
        rows.append(row)
    return rows

def place_authored_lights(u,actors,pos,hour=11,lamps_on=False):
    # Idempotent setup: replace only our own tagged lights, never imported assets.
    for actor in actors.get_all_level_actors():
        if actor.get_actor_label().startswith('SUB01_AuthoredLight_'):actors.destroy_actor(actor)
    report=[]
    for row in authored_lights(hour,lamps_on):
        cls={'directional':u.DirectionalLight,'point':u.PointLight,'spot':u.SpotLight}[row['kind']]
        rotation=u.MathLibrary.find_look_at_rotation(pos(row['position']),pos(row['target'])) if 'target'in row else u.Rotator(0,0,0)
        actor=actors.spawn_actor_from_class(cls,pos(row['position']),rotation);actor.set_actor_label('SUB01_AuthoredLight_'+row['name'])
        light=actor.get_component_by_class(u.LightComponent)
        light.set_mobility(u.ComponentMobility.MOVABLE)
        light.set_light_color(u.LinearColor(*srgb_hex_linear(row['color']),1),False)
        if row['kind']!='directional':
            light.set_editor_property('intensity_units',u.LightUnits.CANDELAS)
            light.set_editor_property('use_inverse_squared_falloff',True)
            light.set_editor_property('attenuation_radius',row['distance']*100)
        if row['kind']=='spot':
            light.set_editor_property('inner_cone_angle',row['inner_angle_degrees'])
            light.set_editor_property('outer_cone_angle',row['outer_angle_degrees'])
        light.set_intensity(row['intensity']);light.set_editor_property('cast_shadows',True)
        report.append(dict(row,actor=actor.get_path_name(),position_ue_cm=list(pos(row['position']).to_tuple()) if hasattr(pos(row['position']),'to_tuple') else [pos(row['position']).x,pos(row['position']).y,pos(row['position']).z]))
    return report
