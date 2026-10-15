"""Physical support failures and atomic three-actor rollback, without UE/Blender."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_monitor_support_fix as M


def slab(x0=190, x1=210, y0=-340, y1=-320, z=84.5):
    return [[[x0,y0,z],[x1,y0,z],[x1,y1,z]],[[x0,y0,z],[x1,y1,z],[x0,y1,z]]]


class PhysicalSupport(unittest.TestCase):
    def test_real_scale_foot_area_and_measured_lift(self):
        proof=M.support(slab(194.5,205.5,-334,-326,82),slab())
        self.assertAlmostEqual(proof['supported_foot_area_cm2'],88)
        self.assertAlmostEqual(proof['delta_z_cm'],2.5)
    def test_hole_or_partial_support_refused(self):
        foot=slab(194.5,205.5,-334,-326,82)
        for top in (slab(190,200),slab()[:1],slab()+slab(),slab(z=85)):
            with self.assertRaises(ValueError):M.support(foot,top)
    def test_intermediate_hole_between_corner_samples_refused(self):
        # Outer sample corners could be supported while a central gap remains.
        foot=slab(194.5,205.5,-334,-326,82)
        top=slab(190,199)+slab(201,210)
        with self.assertRaises(ValueError):M.support(foot,top)
    def test_no_repeated_lift_and_nonfinite_refused(self):
        for foot in (slab(z=84.5),slab(z=float('nan'))):
            with self.assertRaises(ValueError):M.support(foot,slab())


class AtomicMove(unittest.TestCase):
    def exercise(self,fail_save=False):
        class Actor:
            def __init__(self,n):self.n=n;self.z=0.;self.moves=0
            def get_path_name(self):return str(self.n)
            def get_actor_location(self):return SimpleNamespace(x=0.,y=0.,z=self.z)
            def get_actor_transform(self):return self.z
            def set_actor_location(self,p,*_):self.z=p.z;self.moves+=1;return True
            def set_actor_transform(self,t,*_):self.z=t
        class Component:
            def __init__(self,a):self.a=a;self.mesh=SimpleNamespace(get_path_name=lambda:'original')
            def get_editor_property(self,n):return self.mesh
            def set_static_mesh(self,m):self.mesh=m
            def get_world_transform(self):return self.a.z
            def get_materials(self):return ['original']
            def set_world_transform(self,t,*_):self.a.z=t
            def set_material(self,*_):pass
        actors=[Actor(i) for i in (73,74,75,999)]
        rows=[(a.n,a,Component(a),slab(z=82)) for a in actors[:3]]
        def snapshot(u,aa):
            return {a.get_path_name():{'transform':{'translation':[0.,0.,a.z]},'components':[{'transform':{'translation':[0.,0.,a.z]},'mesh':next((r[2].mesh.get_path_name() for r in rows if r[1] is a),'original'),'materials':['original']}]} for a in aa}
        def triangles(u,c):return slab(z=82+c.a.z)
        saves=[]
        def save():saves.append(1);return not(fail_save and len(saves)==1)
        u=SimpleNamespace(Vector=lambda x,y,z:SimpleNamespace(x=x,y=y,z=z),LevelEditorSubsystem=object,EditorActorSubsystem=object,
                          get_editor_subsystem=lambda _:SimpleNamespace(save_current_level=save))
        with tempfile.TemporaryDirectory() as tmp:
            project=Path(tmp);(project/'Content/Sub01Home').mkdir(parents=True)
            (project/'Content/Sub01Home/ActualHome.umap').write_bytes(b'original')
            proof={'delta_z_cm':2.5,'native_desk_top_cm':84.5}
            with patch.object(M,'preflight',return_value=(actors,rows,proof,project)),patch.object(M,'snapshot',side_effect=snapshot),patch.object(M,'native_triangles',side_effect=triangles),patch.object(M.source_geometry,'stage',return_value={'replacements':{73:SimpleNamespace(get_path_name=lambda:'owned73'),74:SimpleNamespace(get_path_name=lambda:'owned74')},'proof':[], 'screen75_copied':False}):
                if fail_save:
                    with self.assertRaisesRegex(RuntimeError,'level save failed'):M.run(tmp,False,u)
                    self.assertEqual([a.z for a in actors],[0,0,0,0]);self.assertEqual(len(saves),2)
                    self.assertEqual([r[2].mesh.get_path_name() for r in rows],['original']*3)
                    self.assertFalse((project/'monitor-support-native.json').exists())
                else:
                    result=M.run(tmp,False,u)
                    self.assertEqual([a.z for a in actors],[2.5,2.5,2.5,0]);self.assertEqual(len(saves),1)
                    self.assertFalse(result['native_pc_input_verified'])
                    self.assertEqual([r[2].mesh.get_path_name() for r in rows],['owned73','owned74','original'])
                    self.assertTrue((project/'monitor-support-native.json').exists())
                self.assertEqual([a.moves for a in actors],[1,1,1,0])
    def test_three_moves_once_and_protected_actor_untouched(self):self.exercise()
    def test_save_failure_restores_all_three_and_resaves(self):self.exercise(True)


if __name__=='__main__':unittest.main()
