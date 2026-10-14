"""Signed arm correction from measured skin over actual keycap triangles."""

CPP = r'''
// Outside-key fingertips are not contact witnesses for the keycaps. Using their
// minimum height lifted both arms needlessly; a real over-key gap also needs a
// downward correction. The caller still audits the complete resulting skin.
static bool Sub01KeyboardContactCorrection(double KeyTop,double OverKeyMinimum,int OverKeyVertices,double& Shift){
 Shift=0.;
 if(OverKeyVertices<4||!std::isfinite(KeyTop)||!std::isfinite(OverKeyMinimum))return false;
 const double Delta=KeyTop+.08-OverKeyMinimum;
 if(!std::isfinite(Delta)||std::fabs(Delta)>12.)return false;
 Shift=Delta;
 return std::fabs(Delta)>.001;
}
'''
