"""Match browser-only material grades in editable Blender scenes and light bakes."""
import bpy

def apply_browser_material_grades():
    graded = 0
    for material in bpy.data.materials:
        if material.get('homeOakGradeApplied'):
            continue
        if not material.get('lightOak') or not material.use_nodes:
            continue
        bsdf = next((node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
        if not bsdf:
            continue
        color = bsdf.inputs['Base Color']
        gamma = material.node_tree.nodes.new('ShaderNodeGamma')
        gamma.inputs['Gamma'].default_value = .45
        if color.is_linked:
            material.node_tree.links.new(color.links[0].from_socket, gamma.inputs['Color'])
        else:
            gamma.inputs['Color'].default_value = color.default_value
        tint = material.node_tree.nodes.new('ShaderNodeVectorMath')
        tint.operation = 'MULTIPLY'
        tint.inputs[1].default_value = (.95,.90,.80)
        material.node_tree.links.new(gamma.outputs['Color'], tint.inputs[0])
        material.node_tree.links.new(tint.outputs['Vector'], color)
        material['homeOakGradeApplied'] = True
        graded += 1
    return graded
