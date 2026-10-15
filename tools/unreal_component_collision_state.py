"""Preserve effective collision config without copying live FBodyInstance handles.

CollisionResponse is data-only. Native struct copying retains its UPROPERTY
container/array without assuming this engine's hidden channel count. Exposed
standard channels and owner profile/object/enabled state are verified directly;
unavailable hidden-container reflection is reported, never called verified.
"""


def _hidden_export(response):
    try:
        container=response.get_editor_property('response_to_channels')
        text=container.export_text()
        return text if text and text!='()' else None
    except Exception:
        return None


def capture(u,component):
    body=component.get_editor_property('body_instance')
    response=body.get_editor_property('collision_responses')
    copied=response.copy()  # Data-only FCollisionResponse, NEVER FBodyInstance.
    hidden=_hidden_export(response)
    if hidden is not None and _hidden_export(copied)!=hidden:
        raise RuntimeError('Plain collision-response copy changed reflected container')
    channels=[getattr(u.CollisionChannel,name)for name in sorted(dir(u.CollisionChannel))
              if name.startswith('ECC_')and name not in('ECC_MAX','ECC_OVERLAP_ALL_DEPRECATED')]
    if not channels:raise RuntimeError('No actual standard collision channels exposed')
    return {'profile':component.get_collision_profile_name(),'enabled':component.get_collision_enabled(),
            'object_type':component.get_collision_object_type(),'responses':copied,
            'visible_responses':[(channel,component.get_collision_response_to_channel(channel))for channel in channels],
            'use_default_collision':bool(component.get_editor_property('use_default_collision')),
            'generate_overlap_events':bool(component.get_editor_property('generate_overlap_events')),
            'hidden_container_export':hidden}


def signature(state):
    return {k:v for k,v in state.items()if k!='responses'}


def restore(u,component,state,force_response_copy=False):
    """Apply only data/config fields and actual component APIs, then read owner.

    Never call SetCollisionProfileName for an unchanged Custom profile: the
    engine clears its external profile even when the effective name is equal.
    """
    if not force_response_copy and signature(capture(u,component))==signature(state):return
    if bool(component.get_editor_property('use_default_collision'))!=state['use_default_collision']:
        component.set_editor_property('use_default_collision',state['use_default_collision'])
    if component.get_collision_object_type()!=state['object_type']:
        component.set_collision_object_type(state['object_type'])
    if component.get_collision_enabled()!=state['enabled']:
        component.set_collision_enabled(state['enabled'])
    if bool(component.get_editor_property('generate_overlap_events'))!=state['generate_overlap_events']:
        component.set_editor_property('generate_overlap_events',state['generate_overlap_events'])
    # Only this data-only member is assigned, never the surrounding physics body.
    body=component.get_editor_property('body_instance')
    body.set_editor_property('collision_responses',state['responses'].copy())
    for channel,response in state['visible_responses']:
        if component.get_collision_response_to_channel(channel)!=response:
            component.set_collision_response_to_channel(channel,response)
    if str(component.get_collision_profile_name())!=str(state['profile']):
        body.set_editor_property('collision_profile_name',state['profile'])
    if signature(capture(u,component))!=signature(state):
        raise RuntimeError('Exact effective component collision configuration restore failed')
