"""Release owned temporary actor references; retain compiling assets for diagnosis."""


def release_temporary(eas, actor, component):
    if component is not None:
        component.set_static_mesh(None)
    if actor is not None and not eas.destroy_actor(actor):
        raise RuntimeError('Owned temporary actor cleanup failed; retain quarantined assets')


def detach_added(u, eas, before):
    """Detach every new component before destroying any newly created actor.

    Original identities are an immutable allowlist. No assets are loaded or
    deleted: pending compilation and Python references may still own them.
    """
    added = [a for a in eas.get_all_level_actors() if a.get_path_name() not in before]
    detached, destroyed = [], []
    for actor in added:
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            component.set_static_mesh(None)
            detached.append(component.get_path_name())
    for actor in reversed(added):
        path = actor.get_path_name()
        if not eas.destroy_actor(actor):
            raise RuntimeError('Owned actor rollback cleanup failed: '+path)
        destroyed.append(path)
    return {'detached_components': detached, 'destroyed_added_actors': destroyed,
            'asset_directories_deleted': False}
