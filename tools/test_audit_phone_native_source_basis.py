import math,unittest
import audit_phone_native_source_basis as P

class Q:
 @staticmethod
 def qnorm(a):
  n=math.sqrt(sum(x*x for x in a));return tuple(x/n for x in a)
 @staticmethod
 def qinv(a):return (-a[0],-a[1],-a[2],a[3])
 @staticmethod
 def qmul(a,b):
  x,y,z,w=a;X,Y,Z,W=b;return (w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z)
 @staticmethod
 def qrot(q,v):
  p=Q.qmul(Q.qmul(q,(*v,0)),Q.qinv(q));return p[:3]
 @staticmethod
 def qangle_deg(a,b):return math.degrees(2*math.acos(min(1,abs(sum(x*y for x,y in zip(Q.qnorm(a),Q.qnorm(b)))))))

START='SUB01_DERIVED_PHONE_VISUAL_REVIEW play=1 source=81c1d4e1 exact imported557keys'
FRAME='SUB01_PHONE_CAPTURED_BONE_FRAME time=4.000000 wrist=X=110 Y=320 Z=230 wristQ=X=-0.7071067811865476 Y=0 Z=0 W=0.7071067811865476 wristScale=X=1 Y=1 Z=1 headAvailable=1 head=X=10 Y=20 Z=130 headQ=X=-0.7071067811865476 Y=0 Z=0 W=0.7071067811865476 headScale=X=0 Y=0 Z=0 body=10,20,30|0,0,0|1,1,1; read_only=true'

class PhoneBasisTests(unittest.TestCase):
 def test_old_assembly_centres_are_not_bone_orientation(self):
  rows,excluded=P.parse_rows('SUB01_PHONE_REVIEW_GEOMETRY wrist=X=1 Y=2 Z=3 phoneCenter=X=4 Y=5 Z=6\n'*167)
  self.assertEqual(rows,[]);self.assertEqual(excluded,0)
 def test_exact_source_session_and_phone_zero_timebase(self):
  rows,n=P.parse_rows(FRAME);self.assertEqual(rows,[]);self.assertEqual(n,1)
  rows,n=P.parse_rows(START+'\n'+FRAME);self.assertEqual(n,0);self.assertEqual(rows[0]['source_time_s'],4);self.assertNotIn('LeftHand',rows[0]['joints'])
  rows,n=P.parse_rows(START+'\nSUB01_EXPLICIT_VIEW_MODE_SWITCH mode=manual\n'+FRAME);self.assertEqual(rows,[]);self.assertEqual(n,1)
 def test_positive90_basis_is_measured_not_borrowed(self):
  row=P.parse_rows(START+'\n'+FRAME)[0][0];world={0:((1,2,3),(0,0,0,1),1),1:((0,1,0),(0,0,0,1),0)}
  result=P.compare_frame(Q,row,world,{'RightHand':0,'Head':1})
  self.assertAlmostEqual(result['RightHand']['position_error_cm'],0);self.assertAlmostEqual(result['RightHand']['distance_to_positive90X_deg'],0);self.assertEqual(result['Head']['native_logged_scale'],[0,0,0])
  row['joints']['RightHand']['quaternion']=[0,0,0,1];result=P.compare_frame(Q,row,world,{'RightHand':0,'Head':1});self.assertAlmostEqual(result['RightHand']['distance_to_positive90X_deg'],90)
 def test_repeated_single_phase_and_missing_lh_not_constancy(self):
  row=P.parse_rows(START+'\n'+FRAME)[0][0];row['comparison']=P.compare_frame(Q,row,{0:((1,2,3),(0,0,0,1),1),1:((0,1,0),(0,0,0,1),0)},{'RightHand':0,'Head':1});summary=P.summarize(Q,[row,row])
  self.assertFalse(summary['RightHand']['sampled_constancy_evaluable']);self.assertFalse(summary['LeftHand']['basis_observed']);self.assertFalse(summary['RightHand']['full557_key_constancy_proven'])
 def test_missing_pair_and_invalid_body_refuse(self):
  with self.assertRaises(ValueError):P.parse_rows(START+'\n'+FRAME.replace('wristQ=','rotation='))
  with self.assertRaises(ValueError):P.parse_rows(START+'\n'+FRAME.replace('|1,1,1','|1,2,1'))
  with self.assertRaises(ValueError):P.parse_rows(START+'\n'+FRAME.replace('time=4.000000','time=22.000000'))

if __name__=='__main__':unittest.main()
