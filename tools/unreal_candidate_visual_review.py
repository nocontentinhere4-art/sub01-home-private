"""Actual saved candidate Editor viewport captures, never live player input."""
import hashlib,json,os,time,struct
from pathlib import Path
_handle=globals().get('_handle')
_active_finish_hook=globals().get('_active_finish_hook')
VIEWS=[('living',(-100,260,165),(-7,-115,0)),('kitchen',(-125,-190,165),(-8,-134,0)),('media',(-170,-35,165),(-9,-171,0)),('desk',(200,-180,155),(-22,-90,0)),('bedroom',(-110,-80,465),(-26,-128,0)),('bathroom',(-230,120,465),(-22,123,0)),('balcony',(-140,455,465),(-12,180,0)),('courtyard',(200,560,165),(-12,90,0))]
def complete(path,after):
 if not path.exists()or path.stat().st_mtime<after:return False
 b=path.read_bytes();return len(b)>100 and b[:8]==b'\x89PNG\r\n\x1a\n'and struct.unpack('>II',b[16:24])==(1280,720)and b[-12:]==b'\0\0\0\0IEND\xaeB`\x82'
def run(views=None,capture_delay=3.,initial_delay=30.,before_view=None,on_finish=None):
 global _handle,_active_finish_hook
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE,SCOPE,trusted_json
 assert active_candidate_guard(u.Paths.project_dir());scope=trusted_json(SCOPE)
 if scope.get('nullrhi')is not False or b'-vulkan'not in Path('/proc/self/cmdline').read_bytes().split(b'\0'):raise RuntimeError('Actual isolated Vulkan Editor required; NullRHI cannot produce review pixels')
 if _handle is not None:raise RuntimeError('One candidate visual review at a time')
 views=VIEWS if views is None else views
 root=CANDIDATE/'evidence/actual-candidate-review'/str(time.time_ns());root.mkdir(parents=True)
 report={'schema':'sub01.actual-candidate-editor-visual-review.v1','editor_pid':os.getpid(),'original_game_pid':159171,'original_game_preserved':True,'original_player_input_changed':False,'world':u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world().get_path_name(),'candidate_map_sha256':hashlib.sha256((CANDIDATE/'Content/Sub01Home/ActualHome.umap').read_bytes()).hexdigest(),'started_epoch':time.time(),'images':[],'mode':'real saved home Editor Vulkan viewport, not gameplay','viewport_fov_verified':False,'visual_acceptance':False,'native_gameplay_accepted':False}
 receipt=root/'receipt.json';state={'index':-1,'ready_after':time.monotonic()+initial_delay,'requested':None,'last':0,'busy':False};report['capture_delay_seconds']=capture_delay
 def persist():receipt.write_text(json.dumps(report,indent=2)+'\n')
 def finish(error=None):
  global _handle,_active_finish_hook
  if on_finish is not None:
   try:report['restored_prior_verified']=bool(on_finish(error))
   except Exception as exc:error=(str(error)+'; 'if error else'')+'Restore: '+str(exc)
  _active_finish_hook=None
  if error is None and(len(report['images'])!=len(views)or not all(i.get('complete_png_verified')for i in report['images'])):error='Not all actual room images were verified complete'
  report.update(finished_epoch=time.time(),all_images_complete=error is None,error=error);persist()
  if _handle is not None:u.unregister_slate_post_tick_callback(_handle);_handle=None
 def tick(_):
  if state['busy']:return
  state['busy']=True
  try:
   if time.monotonic()<state['ready_after']or time.monotonic()-state['last']<2:return
   state['last']=time.monotonic();assert active_candidate_guard(u.Paths.project_dir())
   if state['requested']is not None:
    image=report['images'][-1]
    if not complete(Path(image['path']),image['requested_epoch']):
     if time.time()-image['requested_epoch']>150:raise RuntimeError('Actual candidate viewport image not completed within bounded wait')
     return
    image.update(complete_png_verified=True,sha256=hashlib.sha256(Path(image['path']).read_bytes()).hexdigest());persist();state['requested']=None
   state['index']+=1
   if state['index']>=len(views):finish();return
   name,position,angles=views[state['index']]
   if before_view is not None:before_view(name)
   u.EditorLevelLibrary.set_level_viewport_camera_info(u.Vector(*position),u.Rotator(pitch=angles[0],yaw=angles[1],roll=angles[2]))
   if hasattr(u.EditorLevelLibrary,'editor_set_game_view'):u.EditorLevelLibrary.editor_set_game_view(True)
   path=root/(name+'.png');image={'view':name,'path':str(path),'position_cm':position,'pitch_yaw_roll':angles,'requested_epoch':time.time(),'complete_png_verified':False};report['images'].append(image);persist()
   state['requested']='native screenshot call pending'
   task=u.AutomationLibrary.take_high_res_screenshot(1280,720,str(path),delay=capture_delay)
   if task is None:raise RuntimeError('Actual Editor screenshot API refused')
   state['requested']=task
  except Exception as exc:finish(type(exc).__name__+': '+str(exc))
  finally:state['busy']=False
 persist();_active_finish_hook=on_finish;_handle=u.register_slate_post_tick_callback(tick)
 return {'review_started':True,'receipt':str(receipt),'no_live_game_input_changed':True,'visual_acceptance':False}

def settled_review():
 return run([('bedroom-settled',(-110,-80,465),(-26,-128,0)),('sofa-overview',(-100,260,165),(-7,-115,0))],capture_delay=15.,initial_delay=0.)

def cancel():
 global _handle,_active_finish_hook
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 assert active_candidate_guard(u.Paths.project_dir())
 if _active_finish_hook is not None:_active_finish_hook('Canceled by fixed candidate task');_active_finish_hook=None
 if _handle is not None:u.unregister_slate_post_tick_callback(_handle);_handle=None
 receipt={'schema':'sub01.candidate-editor-visual-cancel.v1','epoch':time.time(),'editor_pid':os.getpid(),'only_owned_slate_callback_removed':True,'prior_images_visually_accepted':False,'native_queued_screenshot_tickers_not_recalled':True,'live_game_input_changed':False}
 (CANDIDATE/'private-audit/candidate-visual-cancel.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt
