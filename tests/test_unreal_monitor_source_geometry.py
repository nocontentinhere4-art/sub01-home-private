"""Full source proof refuses a reduced private copy without touching live screens."""
import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_monitor_source_geometry as G
from test_real_office_plant_owned_geometry import Mesh, Settings, Component

TRI = [[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]]

class SourceProof(unittest.TestCase):
    def exercise(self, bad=False):
        originals=[Mesh(G.PREFIX+f'Mesh_{i}.Mesh_{i}') for i in (56,57,58)]
        components=[Component(m) for m in originals]
        settings=copy.deepcopy([m.settings for m in originals])
        rows=[(n,object(),c,TRI*(2 if n==75 else 300)) for n,c in zip((73,74,75),components)]
        created=[]; destroyed=[]; deleted=[]
        def duplicate(src,dst):
            m=Mesh(dst+'.'+dst.rsplit('/',1)[-1]);created.append(m);return m
        def spawn(*args):
            a=NS(c=Component(None),set_actor_label=lambda x:None,set_actor_hidden_in_game=lambda x:None)
            a.get_component_by_class=lambda x:a.c
            return a
        def destroy(a):
            self.assertIsNone(a.c.mesh);destroyed.append(a);return True
        sub=NS(get_nanite_settings=lambda m:Settings(m.settings),set_nanite_settings=lambda m,s,apply:setattr(m,'settings',copy.deepcopy(s.d)))
        lib=NS(duplicate_asset=duplicate,save_loaded_asset=lambda *a,**kw:True,delete_directory=lambda p:deleted.append(p))
        u=NS(StaticMeshEditorSubsystem=object,get_editor_subsystem=lambda _:sub,EditorAssetLibrary=lib,
             StaticMeshActor=object,StaticMeshComponent=object,Vector=lambda *v:v,CollisionEnabled=NS(NO_COLLISION=0))
        def native(u,c):
            if c.mesh is originals[2]:return TRI*2
            if c.mesh in originals:return TRI*256
            return TRI*(299 if bad else 300)
        if bad:
            with self.assertRaisesRegex(RuntimeError,'complete monitor source triangles differ'):G.stage(u,NS(spawn_actor_from_class=spawn,destroy_actor=destroy),rows,native)
        else:
            result=G.stage(u,NS(spawn_actor_from_class=spawn,destroy_actor=destroy),rows,native)
            self.assertEqual(set(result['replacements']),{73,74})
            self.assertEqual([p['full_source_triangles'] for p in result['proof']],[300,300,2])
            self.assertFalse(result['screen75_copied'])
        self.assertEqual([c.mesh for c in components],originals)
        self.assertEqual([m.settings for m in originals],settings)
        self.assertEqual(len(destroyed),len(created))
        self.assertEqual(deleted,[])
    def test_private_complete_copies_preserve_shared_meshes_and_live_screen(self):self.exercise()
    def test_reduced_copy_fails_before_any_binding_and_keeps_assets_quarantined(self):self.exercise(True)
    def test_screen_cannot_defer_to_private_rebuild(self):
        self.assertFalse(G.can_rebuild(None,75,None))
if __name__=='__main__':unittest.main()
