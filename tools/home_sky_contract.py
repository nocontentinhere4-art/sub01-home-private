"""Validation shared by the separate world-direct recipe and linear combiner."""
MATCHED=('source_sha256','atlas_sha256','samples','threads','seed','adaptive_sampling','denoising','receivers','width','height')
def require_indirect(record):
    if record.get('finished') is not True:raise ValueError('Reference indirect bake is unfinished')
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
    if sky.get('world_rgb')!=[.76,.84,1.0] or sky.get('world_strength')!=.12:raise ValueError('Sky radiance differs from current GI recipe')
    for key in MATCHED:
        if sky.get(key)!=indirect[key]:raise ValueError('Component mismatch: '+key)
    return {key:indirect[key] for key in MATCHED}

def validate_night(indirect,night):
    require_indirect(night)
    if night.get('mode')!='night':raise ValueError('Night source is not a night bake')
    for key in MATCHED:
        if night[key]!=indirect[key]:raise ValueError('Night mismatch: '+key)

def validate_radiance_bounds(minimum,maximum,finite):
    import math
    if finite is not True or not math.isfinite(minimum) or not math.isfinite(maximum) or minimum<0:
        raise ValueError('Nonfinite or negative radiance')
