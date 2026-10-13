"""Validation shared by the separate world-direct recipe and linear combiner."""
MATCHED=('source_sha256','atlas_sha256','samples','threads','seed','adaptive_sampling','denoising','receivers','width','height')
PHYSICAL_MATCHED=('source_recipe_sha256','preparation_recipe_sha256','material_grades_sha256','geometry_proof_sha256','device','gpu_names')
def require_physical(record):
    import math
    preparation=record.get('preparation',{})
    if record.get('recipe')!='home-physical-source-v1' or preparation.get('recipe')!='home-physical-source-v1':
        raise ValueError('Missing physical preparation receipt')
    if record.get('diagnostic_only') is not False:
        raise ValueError('Physical installation requires a full bake')
    if record.get('mode') not in ('day','night') or preparation.get('mode')!=record['mode']:
        raise ValueError('Physical component mode mismatch')
    if record.get('device') not in ('CPU','METAL') or not isinstance(record.get('gpu_names'),list):
        raise ValueError('Missing physical compute device receipt')
    if (record['device']=='METAL')!=bool(record['gpu_names']):
        raise ValueError('Physical GPU selection receipt mismatch')
    written=record.get('written_receiver_ids',[])
    if len(written)!=record.get('receivers') or len(set(written))!=len(written):
        raise ValueError('Physical receiver coverage is incomplete')
    for key in PHYSICAL_MATCHED[:4]:
        value=record.get(key)
        if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Missing physical provenance hash: '+key)
    if preparation.get('hdr_strength')!=(0 if record.get('mode')=='night' else .4225) or preparation.get('hemisphere_intensity')!=.22:
        raise ValueError('Physical world energy mismatch')
    if preparation.get('runtime_hdr_rotation_y')!=-math.pi/2 or preparation.get('cycles_hdr_lookup_rotation_z')!=math.pi/2:
        raise ValueError('Physical environment orientation mismatch')
    if preparation.get('source_runtime_photometric_intensities_changed') is not False or preparation.get('import_energy_factor')!=683:
        raise ValueError('Physical photometric import mismatch')
    if not isinstance(preparation.get('hdr_sha256'),str) or len(preparation['hdr_sha256'])!=64:
        raise ValueError('Missing physical HDR hash')
    if preparation.get('fixture_emission_policy')!='positive finite lampEmission metadata only, night only':
        raise ValueError('Physical emission policy mismatch')
    if record.get('mode')!='night' and preparation.get('enabled_fixtures')!=[]:
        raise ValueError('Day physical recipe contains fixture emission')
    return preparation

def require_indirect(record):
    if record.get('finished') is not True:raise ValueError('Reference indirect bake is unfinished')
    if record.get('diagnostic_only') is True:raise ValueError('Diagnostic subset cannot be installed as a full bake')
    if record.get('direct') is not False or record.get('indirect') is not True or record.get('surface_albedo') is not False:
        raise ValueError('Reference must be indirect-only, albedo-free')
    for key in MATCHED:
        if key not in record:raise ValueError('Missing reference field: '+key)
    if record['adaptive_sampling'] or record['denoising']:raise ValueError('Controlled recipe requires no adaptive sampling or denoising')
    return record

def validate_recipe(reference,source_sha,atlas_sha,samples,threads,seed):
    require_indirect(reference)
    for key,value in [('source_sha256',source_sha),('atlas_sha256',atlas_sha),('samples',samples),('threads',threads),('seed',seed)]:
        if reference[key]!=value:raise ValueError('Recipe mismatch: '+key)

def validate_sky_pair(indirect,sky):
    require_indirect(indirect)
    if sky.get('finished') is not True:raise ValueError('Sky bake is unfinished')
    if sky.get('direct') is not True or sky.get('indirect') is not False or sky.get('surface_albedo') is not False:
        raise ValueError('Sky must be direct-only and albedo-free; indirect would be duplicated')
    if sky.get('world_only') is not True or sky.get('emissive_materials_disabled') is not True:
        raise ValueError('Sky recipe must disable all practical lights and emissive shaders')
    if indirect.get('recipe')=='home-physical-source-v1' or sky.get('recipe')=='home-physical-source-v1':
        a,b=require_physical(indirect),require_physical(sky)
        if indirect.get('mode')!='day' or sky.get('mode')!='day':raise ValueError('Physical sky pair must be daylight')
        if b.get('world_only') is not True or b.get('lights')!=[] or b.get('enabled_fixtures')!=[]:
            raise ValueError('Physical sky includes a practical emitter')
        for key in PHYSICAL_MATCHED:
            if indirect.get(key)!=sky.get(key):raise ValueError('Physical component mismatch: '+key)
        if a['hdr_sha256']!=b['hdr_sha256']:raise ValueError('Physical HDR source mismatch')
        if set(indirect['written_receiver_ids'])!=set(sky['written_receiver_ids']):raise ValueError('Physical receiver IDs mismatch')
    elif sky.get('world_rgb')!=[.76,.84,1.0] or sky.get('world_strength')!=.12:
        raise ValueError('Sky radiance differs from current GI recipe')
    for key in MATCHED:
        if sky.get(key)!=indirect[key]:raise ValueError('Component mismatch: '+key)
    return {key:indirect[key] for key in MATCHED}

def validate_night(indirect,night):
    require_indirect(night)
    if night.get('mode')!='night':raise ValueError('Night source is not a night bake')
    for key in MATCHED:
        if night[key]!=indirect[key]:raise ValueError('Night mismatch: '+key)
    if indirect.get('recipe')=='home-physical-source-v1' or night.get('recipe')=='home-physical-source-v1':
        a,b=require_physical(indirect),require_physical(night)
        for key in PHYSICAL_MATCHED:
            if indirect.get(key)!=night.get(key):raise ValueError('Physical night mismatch: '+key)
        if a['hdr_sha256']!=b['hdr_sha256'] or set(indirect['written_receiver_ids'])!=set(night['written_receiver_ids']):
            raise ValueError('Physical night source/coverage mismatch')

def validate_radiance_bounds(minimum,maximum,finite):
    import math
    if finite is not True or not math.isfinite(minimum) or not math.isfinite(maximum) or minimum<0:
        raise ValueError('Nonfinite or negative radiance')
