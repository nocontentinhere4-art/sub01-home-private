using UnrealBuildTool;
public class Sub01WholeClipWitness : ModuleRules {
 public Sub01WholeClipWitness(ReadOnlyTargetRules Target):base(Target) {
  PCHUsage=PCHUsageMode.UseExplicitOrSharedPCHs;
  PublicDependencyModuleNames.AddRange(new string[]{"Core","CoreUObject","Engine","Json"});
  PrivateDependencyModuleNames.AddRange(new string[]{"UnrealEd","RenderCore","RHI","AnimationCore"});
 }
}
