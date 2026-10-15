"""Explicit private native map profile; legacy browser geometry stays default.

Enable only alongside the actually imported corridor map and matching native
module. This selects walking/privacy coordinates, never collision acceptance.
"""
import os

CORRIDOR_PROFILE = '5ffac2406e66'
PROFILE_ENV = 'HOME_NATIVE_BATHROOM_CORRIDOR_PROFILE'


def corridor_enabled():
    value = os.environ.get(PROFILE_ENV, '')
    if value not in ('', CORRIDOR_PROFILE):
        raise ValueError('Unknown private bathroom corridor geometry profile')
    return value == CORRIDOR_PROFILE


def apply_walking_nodes(nodes):
    if corridor_enabled():
        nodes.update(bath_aisle=(-.6, 4.65, -.2),
                     bath_door=(-.567, 4.65, 1.35))

