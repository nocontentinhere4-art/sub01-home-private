"""Execute real mesh-swap branches with native-like unserializable materials."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def native_component():
    return SimpleNamespace(get_path_name=lambda: 'native_component',
                           get_materials=lambda: [object()],
                           set_static_mesh=lambda mesh: None,
                           set_material=lambda slot, material: None)


def execute(statements, namespace):
    tree = ast.fix_missing_locations(ast.Module(body=statements, type_ignores=[]))
    exec(compile(tree, '<actual-furniture-activation>', 'exec'), namespace)


def has_mesh_swap(node):
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == 'set_static_mesh' for n in ast.walk(node))


def test_both_actual_office_swap_branches_preserve_material_proof_catalog():
    tree = ast.parse((ROOT/'tools/unreal_import_real_office_bundle.py').read_text())
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    swaps = [n for n in ast.walk(run) if isinstance(n, ast.If)
             and isinstance(n.test, ast.Name) and n.test.id == 'replacement' and has_mesh_swap(n)]
    assert len(swaps) == 2  # Genuine plant and complete books both take this path.
    for branch in swaps:
        catalog = [{'material': '/Game/ActualShelf', 'texture_verified': True}]
        namespace = {'materials': catalog, 'replacement': object(), 'c': native_component()}
        execute([branch], namespace)
        assert json.loads(json.dumps(namespace['materials'])) == catalog


def test_actual_retained_sink_activation_preserves_kitchen_material_proof_catalog():
    tree = ast.parse((ROOT/'tools/unreal_import_real_kitchen.py').read_text())
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    swaps = [n for n in ast.walk(run) if isinstance(n, ast.For)
             and isinstance(n.iter, ast.Subscript) and isinstance(n.iter.value, ast.Name)
             and n.iter.value.id == 'retained_restore' and has_mesh_swap(n)]
    assert len(swaps) == 1
    catalog = [{'material': '/Game/ActualKitchen', 'normal_verified': True}]
    namespace = {'materials': catalog, 'retained_restore': {
        'replacements': [(None, native_component(), object(), [object()])]}}
    execute(swaps, namespace)
    assert json.loads(json.dumps(namespace['materials'])) == catalog
