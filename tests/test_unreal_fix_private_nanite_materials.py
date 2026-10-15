import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_fix_private_nanite_materials as fix


class Material:
    def __init__(self,name):self.name=name;self.props={'used_with_nanite':False};self.parameters={'roughness':.38,'albedo':'original-texture'}
    def get_path_name(self):return self.name
    def get_name(self):return self.name.split('.')[-1]
    def get_editor_property(self,key):return self.props[key]
    def set_editor_property(self,key,value):self.props[key]=value


class Instance(Material):
    def __init__(self,name,parent):super().__init__(name);self.props={'parent':parent}


class FixTests(unittest.TestCase):
    def setup_world(self,folder,fail_after_parent=False):
        names=json.loads(fix.MANIFEST.read_text())['material_paths']
        base=Material('/InterchangeAssets/gltf/Materials/M_Default.M_Default')
        external=Instance('/InterchangeAssets/gltf/MI_Default_Opaque.MI_Default_Opaque',base)
        assets={names[0]:Material(names[0])}
        for name in names[1:]:assets[name]=Instance(name,external)
        originals=dict(assets);changes=[]
        for n in fix.FIXTURE_FIELDS:
            name='/Game/Sub01Home/ImportedScene/full-home/Materials/Material_'+n+'.Material_'+n
            assets.setdefault(name,Instance(name,external))
        config=folder/'Config/DefaultGame.ini';config.parent.mkdir();config.write_text('[/Script/Sub01HomeLab.Sub01HomeCharacter]\nNativeFixtureEmissionParentPath='+external.name+'\nOtherValue=keep\n')
        for name in names:
            f=folder/'Content'/(name.split('.')[0][6:]+'.uasset');f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(name.encode())
        def duplicate(name,dest):
            source={base.name:base,external.name:external}[name]
            obj=copy.copy(source);obj.props=dict(source.props);obj.parameters=dict(source.parameters)
            obj.name=dest+'.'+dest.split('/')[-1];assets[obj.name]=obj;return obj
        def reparent(child,parent):changes.append(child.name);child.props['parent']=parent
        mel=SimpleNamespace(set_material_instance_parent=reparent,
                            set_material_usage=lambda m,_:m.props.update(used_with_nanite=True),
                            recompile_material=lambda m:None,update_material_instance=lambda m:None)
        eal=SimpleNamespace(load_asset=assets.get,duplicate_asset=duplicate,save_loaded_asset=lambda *a,**k:True)
        u=SimpleNamespace(Material=Material,MaterialInstanceConstant=Instance,MaterialEditingLibrary=mel,
                          EditorAssetLibrary=eal,MaterialUsage=SimpleNamespace(MATUSAGE_NANITE=1))
        calls=[0]
        def effective(_,material):
            calls[0]+=1
            state=dict(material.parameters)
            if fail_after_parent and calls[0]>70 and calls[0]<=140:state['roughness']=.9
            return state
        return u,originals,base,external,changes,effective

    def test_config_update_is_receipt_derived_and_preserves_unrelated_settings(self):
        old={n:'/InterchangeAssets/glTF/MI_Original' for n in fix.FIXTURE_FIELDS}
        new=dict(old,**{'13':'/Game/Sub01Home/NaniteMaterials/Owned'})
        text='; keep comment\n[/Script/Sub01HomeLab.Sub01HomeCharacter]\nNativeFixtureEmissionParentPath='+old['13']+'\nOtherValue=keep\n[Other]\nvalue=unchanged\n'
        result=fix.fixture_config_text(text,old,new)
        self.assertIn('OtherValue=keep\n',result)
        self.assertTrue(result.endswith('[Other]\nvalue=unchanged\n'))
        self.assertIn('NativeFixtureEmissionParentMaterial13='+new['13'],result)
        self.assertIn('NativeFixtureEmissionParentMaterial63='+old['63'],result)
        with self.assertRaisesRegex(RuntimeError,'Existing reviewed'):
            fix.fixture_config_text(text,dict(old,**{'63':'unexpected'}),dict(new,**{'63':'unexpected-new'}))

    def test_ue_repeated_class_sections_merge_without_touching_posture_block(self):
        old={n:'/InterchangeAssets/glTF/MI_Original' for n in fix.FIXTURE_FIELDS}
        new={n:'/Game/Sub01Home/NaniteMaterials/Owned'+n for n in fix.FIXTURE_FIELDS}
        first='[/Script/Sub01HomeLab.Sub01HomeCharacter]\n'+''.join(f'{key}={old[n]}\n'for n,key in fix.FIXTURE_FIELDS.items())
        posture='[/Script/Sub01HomeLab.Sub01HomeCharacter]\nWalkClip=/Game/Owner/Walk\nNativePhoneClipVerified=False\n'
        result=fix.fixture_config_text(first+'[Other]\nvalue=keep\n'+posture,old,new)
        self.assertEqual(result.count('[/Script/Sub01HomeLab.Sub01HomeCharacter]'),2)
        self.assertTrue(result.endswith(posture))
        self.assertIn('[Other]\nvalue=keep\n',result)
        for n,key in fix.FIXTURE_FIELDS.items():self.assertEqual(result.count(key+'='+new[n]),1)
        # Repeated headers are valid; duplicated identity keys are still refused.
        with self.assertRaisesRegex(RuntimeError,'Duplicate fixture parent config'):
            fix.fixture_config_text(first+posture+'NativeFixtureEmissionParentMaterial13='+old['13']+'\n',old,new)

    def test_owned_ancestor_clone_preserves_plugin_and_exact_original_bindings(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);u,originals,base,external,changes,eff=self.setup_world(root)
            with patch.object(fix,'PROJECT',root),patch.object(fix,'effective',eff),patch.object(fix,'binding_inventory',return_value={'component':['same']}):
                report=fix.run(False,u)
            self.assertFalse(base.props['used_with_nanite'])
            self.assertIs(external.props['parent'],base)
            self.assertEqual(len(report['owned_ancestors']),2)
            for obj in originals.values():
                self.assertTrue(fix.chain(u,obj)[-1].props['used_with_nanite'])
                if isinstance(obj,Instance):self.assertIsNot(obj.props['parent'],external)
            self.assertTrue(report['pbr_parameters_unchanged'])
            self.assertEqual(len(report['asset_backups']),70)

    def test_changed_effective_parameter_refuses_and_restores_every_original_parent(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);u,originals,base,external,changes,eff=self.setup_world(root,True)
            with patch.object(fix,'PROJECT',root),patch.object(fix,'effective',eff),patch.object(fix,'binding_inventory',return_value={}):
                with self.assertRaisesRegex(RuntimeError,'Effective PBR'):fix.run(False,u)
            for obj in originals.values():
                if isinstance(obj,Instance):self.assertIs(obj.props['parent'],external)
                else:self.assertFalse(obj.props['used_with_nanite'])
            self.assertFalse(base.props['used_with_nanite'])
            report=json.loads(next(root.glob('Saved/PrivateMaterialBackups/*/failure.json')).read_text())
            self.assertTrue(report['rollback_pbr_and_bindings_equal'])


if __name__=='__main__':unittest.main()
