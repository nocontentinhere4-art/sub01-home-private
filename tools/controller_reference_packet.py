"""Frozen source-only controller packet checks; cannot grant runtime acceptance."""
import math

def validate_packet(source,proof,held_sha,display_sha):
 if source.get('schema')!='sub01.reference-controller-r11-source.v1'or proof.get('schema')!='sub01.reference-controller-r11-exported-proof.v1':raise ValueError('Exact reviewed controller source generation required')
 for record in(source,proof):
  if any(record.get(k)is not False for k in('native_imported','hand_contact_accepted','activity_ready')):raise ValueError('Source-only packet cannot activate native or hand/contact readiness')
  if record.get('old_contact_proofs_invalidated')is not True or record.get('new_grip_recheck_required')is not True:raise ValueError('New shell must invalidate all older grip/contact receipts')
 held,display=proof.get('held',{}),proof.get('display',{})
 if held.get('sha256')!=held_sha or display.get('sha256')!=display_sha or source.get('held_glb_sha256')!=held_sha or source.get('display_glb_sha256')!=display_sha:raise ValueError('Actual complete exported geometry hashes required')
 if any(not isinstance(x,(int,float))or not math.isfinite(x)for x in(held.get('width_m'),display.get('width_m'))):raise ValueError('Finite actual controller widths required')
 if abs(held['width_m']-.15380217134952545)>1e-7 or abs(display['width_m']-.16)>1e-7:raise ValueError('15.380217cm held width and separate16cm display width required')
 if held.get('triangles')!=display.get('triangles')or held.get('triangles',0)<=0 or source.get('triangles')!=held['triangles']:raise ValueError('Uniform display derivative must preserve full held geometry')
 for row in(held,display):
  if row.get('material_primitives')!=6 or not row.get('texture_dimensions')or any(max(size)>256 for size in row['texture_dimensions']):raise ValueError('Actual six-primitives opaque PBR and small embedded texture proof required')
 shells=proof.get('source_shell_topology',[])
 if len(shells)!=2 or any(s.get('boundary_edges')!=0 or s.get('nonmanifold_edges')!=0 for s in shells):raise ValueError('Closed independently modeled core and covers required')
 if proof.get('ok')is not True:raise ValueError('Actual independent export proof failed')
 return True
