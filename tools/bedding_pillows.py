"""Align a CC0 scanned cushion by its actual thickness, not its display pose."""
import bpy
import numpy as np


def sleeping_pillows(scene, source_path):
    bpy.ops.import_scene.gltf(filepath=str(source_path))
    source = next(o for o in scene.objects if o.type == 'MESH' and o.name.startswith('throw_pillows_01_pillow02'))
    vertices = np.array([tuple(v.co) for v in source.data.vertices])
    values, axes = np.linalg.eigh(np.cov(vertices.T))
    basis = axes[:, [2, 1, 0]]  # longest, second length, thickness
    if np.linalg.det(basis) < 0:
        basis[:, 2] *= -1
    # Avoid BLAS flags leaking from Blender's numerical runtime.
    aligned = np.einsum('ij,jk->ik', vertices - vertices.mean(axis=0), basis)
    aligned -= (aligned.max(axis=0) + aligned.min(axis=0)) / 2
    aligned *= np.array([.65, .43, .15]) / np.ptp(aligned, axis=0)
    objects = []
    for index, x in enumerate((-.38, .38)):
        obj = source.copy()
        obj.data = source.data.copy()
        scene.collection.objects.link(obj)
        obj.name = f'Pillow {index + 1}'
        obj.parent = None
        obj.rotation_mode = 'XYZ'
        obj.location = (x, .76, .08)
        obj.rotation_euler = (0, 0, .065 if index == 0 else -.065)
        obj.scale = (1, 1, 1)
        obj.data.vertices.foreach_set('co', aligned.reshape(-1))
        obj.data.update()
        # Imported split normals describe the old mesh orientation. Recompute
        # them after alignment/scaling rather than lighting the cushion sideways.
        if obj.data.has_custom_normals:
            bpy.context.view_layer.objects.active = obj
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
        obj.data.materials.clear()
        objects.append(obj)
    return objects
