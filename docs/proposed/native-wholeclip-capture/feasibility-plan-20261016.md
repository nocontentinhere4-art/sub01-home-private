# Native whole-clip skin capture: feasibility and isolated execution plan

Actual Editor probe124 preserved the complete map/world. Its report SHA is `e5278dc5a940f1be3531de64d1a0c406088d0848ab7367ff1f3cb460c4618d71`.

The loaded module exposes `AnalyzeCapturedSeatSkin` aggregates, `DumpImportedFootWitness` and `DumpImportedHandWitness`; none exports the complete five-region per-vertex series. `DescribeImportedSkinGeometry` provides counts/bounds only. The tested Python SkeletalMesh/Component interfaces do not expose imported sections/raw weights. GeometryScript class names tested were unavailable in this Editor; this is not a claim that every possible GeometryScript interface is absent. A DynamicMesh copy alone would not prove original section/global vertex and influence identity.

The exact installed Engine has UBT, Build.sh, clang20.1.8 and imported-model headers. `FModuleManager::Exec_Dev` supports `Module Load`, but its paths cache can retain the already scanned project manifest. Python exposes neither ModuleManager nor a cache reset. Therefore injecting a new module into the current Editor without an independently established registration path is not an approved shortcut.

## Concrete proposed execution

Build a separate tiny Editor diagnostic project/module (`Sub01WholeClipWitness`) outside both live and candidate projects. It contains a UBlueprintFunctionLibrary with one read-only capture method. Copy only the already imported owner/Skeleton/Grip assets and their required referenced assets into the new project's same `/Game/` paths, recording source/destination hashes. Do not reimport, rename bones, change mesh/clip, or replace any active module. Do not use shared writable hardlinks.

After separate approval of this plan, run one **NullRHI Editor commandlet**, never a second Game, on a bounded CPU set. This is a new isolated diagnostic process, not a restart of Game225250 or Editor203351. It uses an empty transient world, does not load/save ActualHome, and preserves all existing processes/input/camera/device policy. The source asset manifest is rechecked afterward.

The diagnostic allocates a temporary USkeletalMeshComponent for the exact imported mesh and existing GamingGrip UAnimSequence on its exact Skeleton. For each integer n=0..151, request n/30 seconds (inclusive endpoint151/30=5.033333333), non-looping, force native animation tick and RefreshBoneTransforms, then read actual component-space bone transforms and BodyWorld. Check actual clip length/rate before capture; refuse substitutions or truncated samples.

Export static vertex identities once: LOD0, section/local/globalVertex, material, bind position/normal, section BoneMap, every raw influence/bone identity and sum, plus topology. Five independent fixed-bind witness memberships use >=30% weight for Hips, LeftUpLeg, RightUpLeg, LeftFoot/ToeBase, RightFoot/ToeBase. A vertex may belong to multiple memberships; do not silently winner-filter it. These broad witnesses are not anatomical contact patches.

For each actual evaluated frame export world position and normal per selected imported identity, component-space pose, body transform, requested/read-back sequence time, actual evaluation revision if the installed component API supplies it, monotonic native evaluation ordinal and native cycle/time stamp, pose digest and frame ordinal. Store compact float arrays plus a JSON layout/manifest instead of repetitive huge JSON. Record that these are native imported-skin evaluations, not source-GLB FK and not live gameplay contact evidence.

Normals must follow the installed native skinning implementation, with explicit scale assumptions or proper matrix handling; do not silently reuse bind normals. Prefer native CPU-skinned render outputs only if a complete actual imported-to-render vertex/section/weight identity check succeeds. Otherwise compute imported LBS using actual inverse binds and the component's actually evaluated transforms, documenting the exact native formula and validating representative native CPU outputs before accepting the series.

Never set seat, controller, activity or contact readiness. Downstream selection/whole-clip five-region surface fitting remains owned by the seating source chat.

## Schedule and refusal boundaries

No build or extra Editor has been started. A new-project build time is not yet measured. A planning estimate from previous module builds and Editor startup is roughly10–20minutes for build+isolated capture; this is not a completion promise. First milestone is a bounded compile result. Stop on ABI/build failure or unknown vertex identity/normal mapping; do not start repeated processes or modify the live project to make capture succeed. Deadline remains2026-10-16 02:19:35UTC and existing cap100/reserve10.
