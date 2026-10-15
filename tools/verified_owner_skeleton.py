"""Read the unchanged owner hierarchy from its hash-pinned portable source GLB.

This is source provenance only; no Unreal import, pose or contact acceptance.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

OWNER_CHARACTER_SHA256 = '7609eccbe81631c00d123e69c54241597e28861d1dc947999425cd6c3257adbb'
PORTABLE_OWNER_SHA256 = '45e917725f02836dee6d051d9b47dd2785208c78b503fa935ddb322fe69adea8'
PORTABLE_OWNER = 'SourceAssets/owner-with-clips-unreal.glb'


def read_project_owner_parents(project: Path) -> dict[str, str | None]:
    path = Path(project) / PORTABLE_OWNER
    size = path.stat().st_size
    if not 20 <= size <= 64 * 1024 * 1024:
        raise RuntimeError('Portable owner source size is outside the reviewed bound')
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != PORTABLE_OWNER_SHA256:
        raise RuntimeError('Portable owner source differs from the approved unchanged owner')
    with path.open('rb') as handle:
        magic, version, length, json_length, kind = struct.unpack('<4sIIII', handle.read(20))
        if magic != b'glTF' or version != 2 or length != size or kind != 0x4E4F534A or not 0 < json_length <= min(size - 20, 8 * 1024 * 1024):
            raise RuntimeError('Portable owner GLB header or JSON chunk changed')
        doc = json.loads(handle.read(json_length))
    nodes, skins = doc.get('nodes', []), doc.get('skins', [])
    if len(skins) != 1 or len(skins[0].get('joints', [])) != 65:
        raise RuntimeError('Exactly the original 65 owner joints are required')
    joints = skins[0]['joints']
    if len(set(joints)) != 65 or any(type(i) is not int or not 0 <= i < len(nodes) for i in joints):
        raise RuntimeError('Owner joint indices changed')
    names = [nodes[i].get('name') for i in joints]
    if len(set(names)) != 65 or any(not isinstance(n, str) or not n.startswith('mixamorig:') for n in names):
        raise RuntimeError('Original owner joint names are required')
    parent = {}
    for index, node in enumerate(nodes):
        for child in node.get('children', []):
            if type(child) is not int or not 0 <= child < len(nodes) or child in parent:
                raise RuntimeError('Owner hierarchy has an invalid or repeated parent')
            parent[child] = index
    joint_set = set(joints)
    result = {nodes[i]['name']: (nodes[parent[i]]['name'] if parent.get(i) in joint_set else None) for i in joints}
    if [n for n, p in result.items() if p is None] != ['mixamorig:Hips'] or sum(p is not None for p in result.values()) != 64:
        raise RuntimeError('The complete 65-joint / 64-parent owner tree is required')
    for name in result:
        seen = set()
        while name is not None:
            if name in seen or name not in result:
                raise RuntimeError('Owner hierarchy is cyclic or incomplete')
            seen.add(name)
            name = result[name]
    return result
