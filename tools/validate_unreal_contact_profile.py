"""Reject incomplete measured contact profiles before private native pose review."""
import math
ARMS={'LeftArm','LeftForeArm','LeftHand','RightArm','RightForeArm','RightHand'}
# docs/qa/contact.md, seated "type": both hands' fingertips touch the keycaps, 0 to +2 mm,
# through the whole clip; a gap is a failure of the same weight as a penetration.
KEY_GAP_MAX_CM=.2
def finite_metric(value):
 if not isinstance(value,(int,float)) or not math.isfinite(value):
  raise ValueError('Nonfinite measured contact metric')
 return value

def measured_hands(hands):
 if len(hands)!=2 or {h.get('side') for h in hands}!={'left','right'}:
  raise ValueError('Expected measured left and right hands')
 for hand in hands:
  for field in ['selectedVertices','overKeyVertices','penetrationCm']:
   finite_metric(hand[field])
  if hand['selectedVertices']<=0 or hand['overKeyVertices']<=0:
   raise ValueError('Empty skin selection or no true key overlap')
  if not 0<=hand['overKeyVertices']<=hand['selectedVertices'] or hand['penetrationCm']<0:
   raise ValueError('Impossible measured hand contact')

def validate(data):
 rows=data.get('samples',[])
 # The native loader binds exactly 301 rows; 30 Hz profiles missed midpoint penetration (HOME_COORDINATION).
 if len(rows)!=301:raise ValueError('Expected complete 60Hz 3–8second samples (301)')
 rate=(len(rows)-1)/5
 for i,row in enumerate(rows):
  if abs(finite_metric(row['time'])-(3+i/rate))>1e-6:raise ValueError('Incomplete/nonmonotonic time samples')
  if row['invalidInfluences']!=0:raise ValueError('Invalid imported skin influences')
  if not 0<=finite_metric(row['finger_local_max_error_degrees'])<=.1:raise ValueError('Captured finger rotation changed')
  if not 0<=finite_metric(row['bone_length_max_error_cm'])<=.01:raise ValueError('Bone stretch detected')
  if set(row['corrected_local_arms'])!=ARMS:raise ValueError('Correction must affect six arm bones only')
  measured_hands(row['hands'])
  measured_hands(row['corrected']['hands'])
  if row['corrected']['invalidInfluences']!=0:raise ValueError('Invalid corrected skin influences')
  top=finite_metric(row['corrected']['keyTopCm'])
  for h in row['corrected']['hands']:
   if h['penetrationCm']>.1:raise ValueError('Surface contact unresolved')
   if finite_metric(h['overMinCm'])-top>KEY_GAP_MAX_CM+1e-9:raise ValueError('Fingertips hover above the keycaps (gap over 2 mm)')
  for t in row['corrected_local_arms'].values():
   if [len(t[k]) for k in ['translation','rotation','scale']]!=[3,4,3]:
    raise ValueError('Malformed arm transform')
   values=t['translation']+t['rotation']+t['scale']
   if not all(math.isfinite(v)for v in values):raise ValueError('Nonfinite pose')
   if any(v<=0 for v in t['scale']):raise ValueError('Invalid arm scale')
   if abs(sum(v*v for v in t['rotation'])-1)>.001:raise ValueError('Nonunit quaternion')
 for side in [0,1]:
  if min(row['hands'][side]['overKeyVertices'] for row in rows)<=0:raise ValueError('No true key overlap at one or more samples')
 gaps={side:max(r['corrected']['hands'][side]['overMinCm']-r['corrected']['keyTopCm'] for r in rows) for side in (0,1)}
 return {'samples':len(rows),'sample_rate_hz':rate,'max_corrected_top_penetration_cm':max(h['penetrationCm']for r in rows for h in r['corrected']['hands']),
  'max_corrected_key_gap_cm':{'left':gaps[0],'right':gaps[1]},'acceptance':f'distal skin against extracted keytop triangles at{rate:g}Hz only; palm/bevel/midpoint/POV not certified'}
