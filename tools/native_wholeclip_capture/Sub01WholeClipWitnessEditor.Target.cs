using UnrealBuildTool;
public class Sub01WholeClipWitnessEditorTarget : TargetRules {
 public Sub01WholeClipWitnessEditorTarget(TargetInfo Target) : base(Target) {
  Type=TargetType.Editor;DefaultBuildSettings=BuildSettingsVersion.Latest;
  ExtraModuleNames.Add("Sub01WholeClipWitness");
 }
}
