"""Rollback releases every new mesh before destroying actors; originals survive."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_owned_import_cleanup as C

class Cleanup(unittest.TestCase):
    def test_all_new_meshes_detach_before_any_destroy_and_original_is_untouched(self):
        events=[]
        class Component:
            def __init__(self,name):self.name=name;self.mesh=object()
            def set_static_mesh(self,mesh):self.mesh=mesh;events.append(('detach',self.name))
            def get_path_name(self):return self.name
        class Actor:
            def __init__(self,name):self.name=name;self.components=[Component(name+'/Mesh')]
            def get_path_name(self):return self.name
            def get_components_by_class(self,cls):return self.components
        actors=[Actor('original'),Actor('new1'),Actor('new2')]
        original_mesh=actors[0].components[0].mesh
        def destroy(a):
            self.assertTrue(all(c.mesh is None for a in actors[1:] for c in a.components))
            events.append(('destroy',a.name));return True
        eas=NS(get_all_level_actors=lambda:actors,destroy_actor=destroy)
        result=C.detach_added(NS(StaticMeshComponent=object),eas,{'original':{}})
        self.assertIs(actors[0].components[0].mesh,original_mesh)
        self.assertEqual(events,[('detach','new1/Mesh'),('detach','new2/Mesh'),('destroy','new2'),('destroy','new1')])
        self.assertFalse(result['asset_directories_deleted'])
    def test_detach_failure_does_not_destroy_referenced_actor(self):
        destroyed=[]
        def fail(mesh):raise RuntimeError('detach refused')
        actor=NS(get_path_name=lambda:'new',get_components_by_class=lambda cls:[NS(set_static_mesh=fail)])
        eas=NS(get_all_level_actors=lambda:[actor],destroy_actor=lambda a:destroyed.append(a))
        with self.assertRaisesRegex(RuntimeError,'detach refused'):C.detach_added(NS(StaticMeshComponent=object),eas,{})
        self.assertEqual(destroyed,[])
if __name__=='__main__':unittest.main()
