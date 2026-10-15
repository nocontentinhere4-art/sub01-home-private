"""Narrow source installer for actual cabinet settings on the private bridge.

No service actions. Missing/stale/private/malformed state never becomes a
fabricated closed-door state. Existing door/light validation stays authoritative.
"""
KEYS = ('cabinets', 'lowerCabinets')


def four_booleans(value):
    return isinstance(value, list) and len(value) == 4 and all(type(v) is bool for v in value)


def kitchen_state(home, status, privacy):
    settings = home.get('settings')
    if status != 'live' or privacy is not False or not isinstance(settings, dict):
        return None
    if not all(four_booleans(settings.get(k)) for k in KEYS):
        return None
    return {k: list(settings[k]) for k in KEYS}


def validate_controls_patch(data, base_validator):
    if not isinstance(data, dict) or not data or set(data) - {'doors', 'lights', *KEYS}:
        raise ValueError('Only actual door, light and four-boolean cabinet settings are accepted')
    patch = {}
    base = {k: v for k, v in data.items() if k not in KEYS}
    if base:
        patch.update(base_validator(base))
    for key in KEYS:
        if key in data:
            if not four_booleans(data[key]):
                raise ValueError('Expected exactly four cabinet booleans: ' + key)
            patch[key] = list(data[key])
    return patch


def install(source):
    """Return patched bridge text, refusing changed/duplicate insertion points."""
    markers = ('def validate_controls(data):', '        if privacy:\n', '\nSESSION = web.AppKey(')
    if 'kitchen_state' in source or any(source.count(m) != 1 for m in markers):
        raise ValueError('Missing/duplicate actual private bridge hooks')
    source = source.replace(markers[0], 'def _validate_base_controls(data):', 1)
    source = source.replace(markers[1],
        '        doc["kitchen"] = kitchen_state(home, status, privacy)\n' + markers[1], 1)
    source = source.replace(markers[2],
        '\nfrom unreal_kitchen_state_bridge import kitchen_state, validate_controls_patch\n'
        '\ndef validate_controls(data):\n'
        '    return validate_controls_patch(data, _validate_base_controls)\n\n' + markers[2], 1)
    return source
