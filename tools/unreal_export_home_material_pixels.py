"""Read-only PNG export of actual loaded bed albedo textures, for source parity.

No texture/settings/mesh changes. Run only in the existing private editor gap.
"""
import hashlib
import json
from pathlib import Path


def run(output):
    import unreal as u
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for suffix in ('teal', 'cream', 'linen', 'blue_fabric'):
        material_path = '/Game/Sub01Home/ImportedScene/full-home/Materials/Original_' + suffix + '_upholstery_001'
        material = u.load_asset(material_path)
        if material is None:
            raise RuntimeError('Actual bed source material absent: ' + material_path)
        texture = u.MaterialEditingLibrary.get_material_instance_texture_parameter_value(material, 'BaseColorTexture')
        if texture is None or not isinstance(texture, u.Texture2D):
            raise RuntimeError('Actual bed albedo texture absent: ' + material_path)
        target = root / ('actual-bed-' + suffix + '-albedo.png')
        task = u.AssetExportTask()
        task.set_editor_property('object', texture)
        task.set_editor_property('exporter', u.TextureExporterPNG())
        task.set_editor_property('filename', str(target))
        task.set_editor_property('automated', True)
        task.set_editor_property('prompt', False)
        task.set_editor_property('replace_identical', True)
        if not u.Exporter.run_asset_export_task(task) or not target.is_file():
            raise RuntimeError('Actual texture pixel export failed: ' + texture.get_path_name())
        rows.append({'material': material_path, 'texture': texture.get_path_name(),
                     'png': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                     'srgb': texture.get_editor_property('srgb')})
    report = {'schema': 'sub01-actual-native-bed-pixels-v1', 'read_only': True, 'exports': rows}
    (root / 'actual-bed-texture-pixels.json').write_text(json.dumps(report, indent=2) + '\n')
    u.log('SUB01_ACTUAL_BED_TEXTURE_PIXELS ' + json.dumps(report))
    return report
