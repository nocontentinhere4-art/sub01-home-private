"""Match native runtime to the actual owned corridor import, never old maps.

An absent receipt preserves legacy generation byte for byte. A present invalid
receipt refuses staging. Renderer alone imports the map and owns the receipt.
"""
import json
from pathlib import Path

SOURCE_SHA = '9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
EXPORT_SHA = '5ffac2406e668a327427e60bc75e3ee3ecf13a89381d0312b821277386cb9c91'
CONTRACT_SHA = 'dbe28857c96054836813f5d6c35f14097bd7d118df39e02480a04348cbf44e79'
NODES = [117, 118, 151, 152, 153, 154, 155, 156, 158]
RECEIPT = 'private-audit/bathroom-corridor-native-import.json'
TAG = 'SUB01BathroomCorridor:' + EXPORT_SHA + ':SourceNode118'
PREFIX = '/Game/Sub01Home/BathroomCorridor/V_5ffac2406e66/Attempt_'


def receipt_profile(project):
    path = Path(project) / RECEIPT
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > 2_000_000:
        raise ValueError('Bounded actual corridor import receipt required')
    row = json.loads(path.read_text())
    if (row.get('schema') != 'sub01.bathroom-corridor-native-import.v1'
            or row.get('source_sha256') != SOURCE_SHA
            or row.get('export_sha256') != EXPORT_SHA
            or row.get('source_contract_sha256') != CONTRACT_SHA
            or row.get('source_nodes') != NODES
            or row.get('saved') is not True
            or row.get('originals_preserved') is not True):
        raise ValueError('Exact saved owned corridor import receipt required')
    return row


def install(header, cpp, project):
    if receipt_profile(project) is None:
        return header, cpp
    # All adapters are already installed. Update each physical camera gate,
    # including device input, viewer handoff/resume and read-only skin capture.
    if 'Eye.X<-85' not in cpp or 'x<-85&&x>-378' not in cpp:
        raise ValueError('Actual legacy bathroom privacy hooks missing')
    cpp = cpp.replace('Eye.X<-85', 'Eye.X<-100')
    cpp = cpp.replace('x<-85&&x>-378', 'x<-100&&x>-378')
    old = 'if(FVector::Dist(B.Origin,FVector(-85,135,405))<.2&&FVector::Dist(B.BoxExtent,FVector(3.25,44.5,100))<.2){Panel=C;++Matches;}'
    new = ('if(C->ComponentHasTag(TEXT("' + TAG + '"))&&'
           'C->GetStaticMesh()->GetPathName().StartsWith(TEXT("' + PREFIX + '"))&&'
           'C->IsVisible()&&C->GetCollisionEnabled()!=ECollisionEnabled::NoCollision&&'
           'FVector::Dist(B.Origin,FVector(-100,135,405))<.2&&'
           'FVector::Dist(B.BoxExtent,FVector(3.25,44.5,100))<.2){Panel=C;++Matches;}')
    replacements = {
        old: new,
        'FVector(-73.8f,135+(From+To)*.5f,405)': 'FVector(-88.8f,135+(From+To)*.5f,405)',
        'if(P.X>-50||LiveHome)BathDoorEgressRequested=false;':
            'if(P.X>-56.7||LiveHome)BathDoorEgressRequested=false;',
        'source9556495f node118/Mesh101 absoluteDelta=11.2,0,0':
            'source5ffac2406e66 ownedSourceNode118 absoluteDelta=11.2,0,0',
    }
    for name, x, y in (('bath_aisle', -60., -20.), ('bath_door', -56.7, 135.)):
        old_graph = f' LiveHomeNodes.Add(TEXT("{name}"),FVector(-50.000000,{y:.6f},300.000000));'
        new_graph = f' LiveHomeNodes.Add(TEXT("{name}"),FVector({x:.6f},{y:.6f},300.000000));'
        if cpp.count(new_graph) != 1:
            replacements[old_graph] = new_graph
    schema_hook = ' const TSharedPtr<FJsonObject>* Source=nullptr;FString Status;'
    apply_start = cpp.index('void ASub01HomeCharacter::ApplyLiveHome(')
    hook_at = cpp.index(schema_hook, apply_start)
    cpp = (cpp[:hook_at] + ' FString GeometryProfile;if(!Doc->TryGetStringField(TEXT("native_geometry_profile"),GeometryProfile)||GeometryProfile!=TEXT("5ffac2406e66")){LiveHomeFresh=false;return;}\n'
           + cpp[hook_at:])
    for before, after in replacements.items():
        if cpp.count(before) != 1:
            raise ValueError('Ambiguous/missing actual corridor runtime hook: ' + before[:90])
        cpp = cpp.replace(before, after, 1)
    return header, cpp
