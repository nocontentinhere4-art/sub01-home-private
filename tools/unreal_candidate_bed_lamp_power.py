"""Retain existing switch while honoring reviewed finite bedside source power."""
OLD='{TEXT("BedLamp"),3.5f}'
NEW='{TEXT("BedLamp"),FMath::IsFinite(BedsideLampIntensityCandela)?FMath::Clamp(BedsideLampIntensityCandela,0.f,10.f):3.5f}'
FIELD=' UPROPERTY(EditAnywhere,Config,Category="SUB01|Lighting") float BedsideLampIntensityCandela=3.5f;'
def install(header,cpp):
 if FIELD in header:
  if OLD in cpp or cpp.count(NEW)!=2:raise RuntimeError('Incomplete candidate bedside power patch')
  return header,cpp
 anchor=' void InitializePrivateViewSettings();'
 if header.count(anchor)!=1 or cpp.count(OLD)!=2:raise RuntimeError('Exact current authored switch source required')
 return header.replace(anchor,FIELD+'\n'+anchor,1),cpp.replace(OLD,NEW)
