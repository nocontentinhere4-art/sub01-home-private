"""Preserve explicit component collision config; never copy a live FBodyInstance."""


def capture(u,component):
    cast=getattr(u.CollisionChannel,'cast',None)
    if not callable(cast):raise RuntimeError('Complete collision-channel enum casting unavailable')
    channels=[cast(index)for index in range(32)]
    body=component.get_editor_property('body_instance')
    profile=component.get_collision_profile_name()
    if str(body.get_editor_property('collision_profile_name'))!=str(profile):
        raise RuntimeError('Component/body collision profile mismatch before capture')
    return {'profile':profile,'enabled':component.get_collision_enabled(),
            'object_type':component.get_collision_object_type(),
            'responses':[(channel,component.get_collision_response_to_channel(channel))for channel in channels],
            'generate_overlap_events':bool(component.get_editor_property('generate_overlap_events'))}


def restore(u,component,state):
    """Restore semantics first, then exact reflected profile metadata, and verify.

    Loading a named profile called Custom can reload BlockAll defaults. The
    original object type and ALL32 channel responses must therefore survive
    independently of that profile name. Only its exposed Name member is written;
    no FBodyInstance/physics handles are copied or assigned.
    """
    if component.get_collision_object_type()!=state['object_type']:
        component.set_collision_object_type(state['object_type'])
    for channel,response in state['responses']:
        if component.get_collision_response_to_channel(channel)!=response:
            component.set_collision_response_to_channel(channel,response)
    if component.get_collision_enabled()!=state['enabled']:
        component.set_collision_enabled(state['enabled'])
    if bool(component.get_editor_property('generate_overlap_events'))!=state['generate_overlap_events']:
        component.set_editor_property('generate_overlap_events',state['generate_overlap_events'])
    if str(component.get_collision_profile_name())!=str(state['profile']):
        body=component.get_editor_property('body_instance')
        body.set_editor_property('collision_profile_name',state['profile'])
    if capture(u,component)!=state:
        raise RuntimeError('Exact component collision configuration restore failed')
