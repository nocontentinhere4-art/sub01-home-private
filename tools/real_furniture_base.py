"""Scoped verified native-base helpers; no scene, lighting or furniture mutations."""
import hashlib
import json
import struct
from pathlib import Path
NATIVE_BASE_SCHEMA = "sub01.native-dressing-base.v1"

class BaseRefusedError(RuntimeError):
    """The opened .blend is not an accepted dressing base."""

def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(part)
    return digest.hexdigest()

def verify_base(scene_props, blend_path, allow_unassembled, mesh_stats, source_sha256=None,
                base_sha256=None, base_bytes=None):
    """Accept only (a) the assembled home (homeVersion 114), or (b) with
    allow_unassembled, the native dressing base written by
    prepare_native_dressing_base.py whose recorded source GLB SHA-256 matches the
    expected one. mesh_stats = (mesh_object_count, total_original_vertices)."""
    get = scene_props.get
    recorded = get('sub01NativeSourceSha256')
    if get('homeVersion') == 114 and not recorded:
        return {'basis': 'assembled-home114'}
    if not allow_unassembled:
        raise BaseRefusedError('base is not the assembled home (homeVersion 114); '
                               'pass --allow-unassembled to accept the verified native dressing base')
    if not recorded:
        raise BaseRefusedError('base has no sub01NativeSourceSha256: not written by prepare_native_dressing_base.py')
    evidence = {'basis': 'native-dressing-base', 'recorded_source_sha256': recorded,
                'authoring_basis': get('sub01AuthoringBasis'), 'private_only': bool(get('privateOnly'))}
    sidecar_path = Path(blend_path).with_suffix('.json') if blend_path else None
    sidecar = None
    if sidecar_path and sidecar_path.is_file():
        sidecar = json.loads(sidecar_path.read_text())
        if sidecar.get('schema') != NATIVE_BASE_SCHEMA:
            raise BaseRefusedError(f'{sidecar_path.name} schema is {sidecar.get("schema")!r}')
        if sidecar.get('source_sha256') != recorded:
            raise BaseRefusedError('sidecar source_sha256 differs from the scene record')
        if [sidecar.get('mesh_objects'), sidecar.get('vertices')] != list(mesh_stats):
            raise BaseRefusedError(f'mesh objects/vertices {list(mesh_stats)} differ from the sidecar '
                                   f'{[sidecar.get("mesh_objects"), sidecar.get("vertices")]}')
        evidence['sidecar'] = str(sidecar_path)
    expected = source_sha256 or (sidecar or {}).get('source_sha256')
    if not expected:
        raise BaseRefusedError('no expected source SHA-256: pass --source-sha256 (or keep the base sidecar)')
    if expected != recorded:
        raise BaseRefusedError(f'source SHA-256 mismatch: expected {expected}, base records {recorded}')
    evidence['source_sha256'] = recorded
    evidence['mesh_objects'], evidence['vertices'] = mesh_stats
    if base_sha256 or base_bytes is not None:
        if not blend_path or not Path(blend_path).is_file():
            raise BaseRefusedError('base file path unavailable for --base-sha256/--base-bytes')
        if base_bytes is not None and Path(blend_path).stat().st_size != base_bytes:
            raise BaseRefusedError(f'base size {Path(blend_path).stat().st_size} != {base_bytes}')
        if base_sha256 and sha256_file(blend_path) != base_sha256:
            raise BaseRefusedError('base .blend SHA-256 mismatch')
        evidence['base_sha256_verified'] = bool(base_sha256)
        evidence['base_bytes_verified'] = base_bytes is not None
    return evidence

def glb_json(path):
    import struct
    data = Path(path).read_bytes()
    if data[:4] != b'glTF':
        raise ValueError(f'{path} is not a GLB')
    length = struct.unpack_from('<I', data, 12)[0]
    return json.loads(data[20:20 + length])
