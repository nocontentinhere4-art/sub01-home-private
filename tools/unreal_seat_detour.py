"""Walk around the desk chair to the seat approach instead of through it.

The approach stands between the cushion and the desk (cushion + SitHipBackCm along the
facing yaw), but UpdateSeatTransition pushed the pawn there in a straight line from the
graph's desk node, i.e. through the chair: the pawn stopped against the backrest. When
that line is obstructed, this picks a route behind and beside the chair whose every leg
is clear for the pawn capsule (lifted 5 cm so floor and rug edges never count), once per
live command. Movement stays CharacterMovement input; no teleport, no seating claim.
"""
from pathlib import Path

HEADER_ANCHOR = ' FVector2D SeatApproach=FVector2D::ZeroVector;\n'
HEADER_ADD = ' TArray<FVector2D> SeatDetour; uint64 SeatDetourCommand=0;\n'

HELPERS = r'''
static bool Sub01SeatLegClear(UWorld* World,const ACharacter* Self,const FVector2D& From,const FVector2D& To,float Z){
 const auto* Capsule=Self->GetCapsuleComponent();FHitResult Hit;FCollisionQueryParams Params(SCENE_QUERY_STAT(Sub01SeatDetour),false,Self);
 const FCollisionShape Shape=FCollisionShape::MakeCapsule(Capsule->GetScaledCapsuleRadius(),Capsule->GetScaledCapsuleHalfHeight()-5.f);
 return !World->SweepSingleByChannel(Hit,FVector(From.X,From.Y,Z+5.f),FVector(To.X,To.Y,Z+5.f),FQuat::Identity,ECC_Pawn,Shape,Params);
}
// Behind the chair, then beside it, then the approach: the first route whose legs are all clear.
static bool Sub01SeatDetourRoute(UWorld* World,const ACharacter* Self,const FVector& Here,const FVector2D& Approach,float YawDeg,TArray<FVector2D>& Out){
 Out.Reset();const FVector2D Start(Here.X,Here.Y);
 if(Sub01SeatLegClear(World,Self,Start,Approach,Here.Z))return false;
 const float R=FMath::DegreesToRadians(YawDeg);const FVector2D Facing(FMath::Cos(R),FMath::Sin(R)),Side(-Facing.Y,Facing.X);
 // The approach itself grazes the cushion front: end 8 cm toward the desk, inside the 12 cm arrival radius.
 const FVector2D Target=Approach+Facing*8.f;
 for(const float Offset:{60.f,80.f,100.f})for(const float Sign:{1.f,-1.f}){
  const FVector2D Beside=Approach+Side*Offset*Sign,Behind=Beside-Facing*120.f;
  if(Sub01SeatLegClear(World,Self,Start,Beside,Here.Z)&&Sub01SeatLegClear(World,Self,Beside,Target,Here.Z)){Out={Beside,Target};return true;}
  if(Sub01SeatLegClear(World,Self,Start,Behind,Here.Z)&&Sub01SeatLegClear(World,Self,Behind,Beside,Here.Z)&&Sub01SeatLegClear(World,Self,Beside,Target,Here.Z)){Out={Behind,Beside,Target};return true;}
 }
 return false;
}
'''

FUNCTION_ANCHOR = 'void ASub01HomeCharacter::UpdateSeatTransition(float Dt){\n'

MOVE_OLD = ''' else if(In.WantSeat&&In.Fresh&&!In.Private&&!In.Blocked&&SeatOut.Phase==ESub01SeatPhase::Standing&&!In.AtApproach&&Controller){
  const float Distance=ToApproach.Size();if(Distance>1)AddMovementInput(FVector(ToApproach.X/Distance,ToApproach.Y/Distance,0),FMath::Clamp(Distance/45.f,.15f,1.f));
 }
'''
MOVE_NEW = ''' else if(In.WantSeat&&In.Fresh&&!In.Private&&!In.Blocked&&SeatOut.Phase==ESub01SeatPhase::Standing&&!In.AtApproach&&Controller){
  if(SeatDetourCommand!=In.Command){
   SeatDetourCommand=In.Command;
   if(Sub01SeatDetourRoute(GetWorld(),this,Here,SeatApproach,SeatYaw,SeatDetour)){UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_DETOUR legs=%d first=(%.1f,%.1f) approach=(%.1f,%.1f)"),SeatDetour.Num(),SeatDetour[0].X,SeatDetour[0].Y,SeatApproach.X,SeatApproach.Y);}
   else{UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_DETOUR none: direct leg clear or no clear route; approach=(%.1f,%.1f)"),SeatApproach.X,SeatApproach.Y);}
  }
  if(SeatDetour.Num()&&(SeatDetour[0]-FVector2D(Here.X,Here.Y)).Size()<12)SeatDetour.RemoveAt(0);
  const FVector2D ToGoal=(SeatDetour.Num()?SeatDetour[0]:SeatApproach)-FVector2D(Here.X,Here.Y);
  const float Distance=ToGoal.Size();if(Distance>1)AddMovementInput(FVector(ToGoal.X/Distance,ToGoal.Y/Distance,0),FMath::Clamp(ToApproach.Size()/45.f,.15f,1.f));
 }
'''


def install(module_dir):
    module = Path(module_dir)
    header, cpp = module / 'Sub01HomeLab.h', module / 'Sub01HomeLab.cpp'
    h, c = header.read_text(), cpp.read_text()
    if 'SUB01_SEAT_DETOUR' in c:
        return False
    if h.count(HEADER_ANCHOR) != 1 or c.count(FUNCTION_ANCHOR) != 1 or c.count(MOVE_OLD) != 1:
        raise RuntimeError('Seat source differs from the reviewed r22 module; not patched')
    header.write_text(h.replace(HEADER_ANCHOR, HEADER_ANCHOR + HEADER_ADD))
    cpp.write_text(c.replace(FUNCTION_ANCHOR, HELPERS.lstrip('\n') + FUNCTION_ANCHOR).replace(MOVE_OLD, MOVE_NEW))
    return True


if __name__ == '__main__':
    import sys
    print('PATCHED' if install(sys.argv[1]) else 'ALREADY_PATCHED')
