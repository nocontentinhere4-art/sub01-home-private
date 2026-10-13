"""Source-only Linux Game packaging proposal. Never builds, cooks or edits a project.

Official UE5.8.3 evidence read from the private engine:
UnrealGame.target = Linux/Development/Game; all current module dependencies live
under Engine/Source/Runtime. BuildCookRun.Automation.cs66-69 parses cookdir;
ProjectParams.cs1187-1206 parses MapsToCook; CookCommandlet.cpp369-375 accepts
filesystem COOKDIR entries. Execution remains gated on native baseline acceptance.
"""
import argparse,json,re
from pathlib import Path

RUNTIME_MODULES=frozenset(('Core','CoreUObject','Engine','InputCore','AnimGraphRuntime',
 'AnimationCore','RenderCore','RHI','HTTP','Json','JsonUtilities','Slate','SlateCore',
 'ApplicationCore','ImageCore'))
DYNAMIC_CONTENT=('Sub01Hands/FBX','Sub01Home/Devices')

def make_plan(engine,baseline,proposal,archive,build_source,target_source):
    engine,baseline,proposal,archive=map(Path,(engine,baseline,proposal,archive))
    if baseline.suffix!='.uproject':raise ValueError('Baseline must be an actual .uproject path')
    accepted=baseline.parent.resolve()
    if proposal.resolve()==baseline.resolve() or proposal.resolve()==accepted or accepted in proposal.resolve().parents:
        raise ValueError('Proposal must be outside accepted baseline')
    if archive.resolve()==accepted or accepted in archive.resolve().parents:
        raise ValueError('Archive must be outside accepted baseline')
    dependencies=set(re.findall(r'"([A-Za-z][A-Za-z0-9]+)"',build_source))
    if dependencies!=RUNTIME_MODULES:
        raise ValueError('Unverified runtime module dependencies: '+str(sorted(dependencies^RUNTIME_MODULES)))
    if 'TargetType.Game' not in target_source or 'UnrealEd' in build_source:
        raise ValueError('A runtime-only Game target is required')
    name=baseline.stem
    project=proposal/(name+'.uproject')
    cook_dirs='+'.join(str(proposal/'Content'/p)for p in DYNAMIC_CONTENT)
    command=['bash',str(engine/'Engine/Build/BatchFiles/RunUAT.sh'),'BuildCookRun',
        '-project='+str(project),'-nop4','-platform=Linux','-clientconfig=Development',
        '-build','-cook','-stage','-pak','-archive','-unattended','-SkipCookingEditorContent',
        '-MapsToCook=/Game/Sub01Home/ActualHome','-cookdir='+cook_dirs,
        '-archivedirectory='+str(archive)]
    return {'kind':'proposed-not-executed-linux-game-cook','baseline_project':str(baseline),
        'proposed_project':str(project),'required_verified_gates':[
            'actual-live-descending-solid-floor-arrival','native-bathroom-opaque-privacy',
            'actual-minecraft-pixels-on-native-TV'],
        'prepare_separate_copy_only_after_gates':{
            'copy_from':str(baseline.parent),'copy_to':str(proposal),
            'entries':['Content','Config','Source',baseline.name,'unreal-skinned-contact-audit.json'],
            'exclude':['Saved','Intermediate','Binaries','.env','operator-token','backend-state']},
        'runtime_modules_verified':sorted(dependencies),'dynamic_load_directories':list(DYNAMIC_CONTENT),
        'cook_argv':command,'execution_environment':'runtime-driver/cache allowlist; no operator/provider/Jupyter credentials needed for cook',
        'native_runtime_after_success':{
            'receipt_required':'actual staged Linux Game receipt and executable; do not assume archive layout',
            'reuse':'actual protected operator environment, HomeState/PC loopback origins and measured contact JSON',
            'capture':'same authenticated X11 real-window pipeline, not editor/movie camera'},
        'acceptance_pending':['Game target compilation','cook completion','dynamic skin/clip/device material loading',
                              'startup time improvement','actual native window and three baseline gates']}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--proposal',type=Path,required=True);p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--module-build-source',type=Path,required=True);p.add_argument('--game-target-source',type=Path,required=True)
    a=p.parse_args()
    plan=make_plan(a.engine,a.baseline,a.proposal,a.archive,a.module_build_source.read_text(),a.game_target_source.read_text())
    print(json.dumps(plan,indent=2))

if __name__=='__main__':main()
