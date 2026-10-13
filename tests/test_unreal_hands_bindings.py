import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_hands_bindings import validate_bindings,native_config
from stage_unreal_home_runtime import stage

class BindingTests(unittest.TestCase):
    def source(self):
        return {'binding_requirements':{'animation_sources':{'Walk':'Walking.fbx','DeskTyping':'Typing.glb','Phone':'Texting.fbx','DeskMouse':None}}}

    def imported(self):
        mesh={'class':'SkeletalMesh','object_path':'/Game/Owner/Body.Body','skeleton_path':'/Game/Owner/Skeleton.Skeleton','bind_pose_verified':True}
        clips={role:{'class':'AnimSequence','source_file':path,'object_path':f'/Game/Hands/{role}.{role}','skeleton_path':mesh['skeleton_path'],'retarget_verified':True,'pov_placement_verified':True,'in_place_root_motion_verified':True,'physical_contact_verified':True}for role,path in self.source()['binding_requirements']['animation_sources'].items()if path}
        return {'skeletal_mesh':mesh,'clips':clips}

    def test_actual_source_inventory_is_not_runtime_ready(self):
        path=Path(__file__).resolve().parents[1]/'out/first-person-assets/source-manifest.json'
        if path.exists():
            source=json.loads(path.read_text())
            self.assertFalse(source['binding_requirements']['runtime_ready'])
            self.assertIsNone(source['binding_requirements']['animation_sources']['DeskMouse'])
            with self.assertRaisesRegex(ValueError,'not bound'):validate_bindings(source,{})

    def test_missing_mouse_and_unverified_rest_pose_cannot_be_masked(self):
        report=self.imported();report['clips']['Walk']['retarget_verified']=False
        report['clips']['DeskMouse']=copy.deepcopy(report['clips']['DeskTyping'])
        result=validate_bindings(self.source(),report)
        self.assertNotIn('Walk',result['validated_postures'])
        self.assertNotIn('DeskMouse',result['validated_postures'])
        self.assertNotIn('MouseClipPath',native_config(result))

    def test_skeleton_root_motion_and_real_contact_are_independent_gates(self):
        for role,field,value in [('Phone','skeleton_path','/Game/OtherSkeleton'),('Walk','in_place_root_motion_verified',False),('DeskTyping','physical_contact_verified',False),('Phone','pov_placement_verified',False)]:
            with self.subTest(role=role,field=field):
                report=self.imported();report['clips'][role][field]=value
                self.assertNotIn(role,validate_bindings(self.source(),report)['validated_postures'])
        result=validate_bindings(self.source(),self.imported())
        self.assertEqual(set(result['validated_postures']),{'Walk','DeskTyping','Phone'})

    def test_generated_native_component_is_real_but_defaults_unbound(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);(root/'Config').mkdir();(root/'Sub01HomeLab.uproject').write_text('{}')
            stage(root)
            header=(root/'Source/Sub01HomeLab/Sub01HomeLab.h').read_text()
            cpp=(root/'Source/Sub01HomeLab/Sub01HomeLab.cpp').read_text()
            blend=(root/'Source/Sub01HomeLab/Sub01HomeHands.cpp').read_text()
            self.assertIn('USkeletalMeshComponent',header)
            self.assertIn('Clip->GetSkeleton()!=Mesh->GetSkeleton()',cpp)
            self.assertIn('!ValidatedHandsPostures.Contains(Role)',cpp)
            self.assertIn('if(Moving)WalkPhase+=',cpp)
            self.assertIn('PreviewHandsPose',cpp)
            self.assertIn('backend/device activity unchanged',cpp)
            self.assertIn('FAnimNode_TwoWayBlend',blend)
            self.assertIn('Blend.A.SetLinkNode(&Previous)',blend)
            self.assertIn('Blend.B.SetLinkNode(&Current)',blend)
            self.assertNotIn('.LinkNode(',blend)
            pawn=cpp
            self.assertLess(pawn.index('UpdateNativeCapture();',pawn.index('::Tick(')),pawn.index('if(!HandsFailure.IsEmpty())return;',pawn.index('::Tick(')))
            self.assertIn('NativeCapture->SetWorldTransform(ViewCamera->GetComponentTransform())',pawn)
            self.assertIn('ESceneCaptureSource::SCS_FinalColorLDR',pawn)
            self.assertIn('CaptureWarmFrames<32',pawn)
            self.assertIn('if(CaptureViewport){',pawn)
            self.assertIn('FScreenshotRequest::RequestScreenshot(CapturePath,false,false)',pawn)
            self.assertIn('FParse::Param(FCommandLine::Get(),TEXT("Sub01CaptureViewport"))',pawn)
            self.assertIn('NativeCapture->DestroyComponent()',pawn)
            self.assertIn('NativeCaptureTarget->ReleaseResource()',pawn)
            self.assertIn('IFileManager::Get().FileSize(*CapturePath)>0',pawn)
            self.assertIn('GetCapsuleComponent()->GetScaledCapsuleHalfHeight()',pawn)
            self.assertIn('Previous.SetPlayRate(0)',blend)
            self.assertIn('UpdateAnimationNode(const FAnimationUpdateContext& Context) override',blend)
            self.assertNotIn('FAnimationUpdateContext Context(this',blend)
            self.assertNotIn('SetBoneTransform',cpp+blend)
            self.assertIn('SetVisibility(false)',cpp)
            self.assertFalse((root/'Config/DefaultGame.ini').exists(),'no imaginary asset path is pre-bound')

if __name__=='__main__':unittest.main()
