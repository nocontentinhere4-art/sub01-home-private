"""Bounded actual Editor Surface Cache display review, restoring the exact CVar."""
import json
import os
import time
from pathlib import Path

_handle=None
_state=None


def complete_png(path,after):
    if not path.exists() or path.stat().st_mtime<after:return False
    data=path.read_bytes()
    return len(data)>100 and data[:8]==b'\x89PNG\r\n\x1a\n' and data[-12:]==b'\0\0\0\0IEND\xaeB`\x82'


def run():
    global _handle,_state
    import unreal as u
    from unreal_editor_task_queue import guard_valid
    if _handle is not None:raise RuntimeError('One Surface Cache review at a time')
    if not guard_valid():raise RuntimeError('Trusted private window required')
    project=Path(u.Paths.project_dir()).resolve()
    if project!=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab'):
        raise RuntimeError('Exact private project required')
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.',1)[0]!='/Game/Sub01Home/ActualHome':
        raise RuntimeError('Already-loaded ActualHome required')
    prior=u.SystemLibrary.get_console_variable_int_value('r.Lumen.Visualize')
    if type(prior)is not int:raise RuntimeError('Actual r.Lumen.Visualize integer required')
    stamp=time.time_ns();root=project/'evidence/scene-review'/('lumen-surface-'+str(stamp));root.mkdir()
    receipt={'schema':'sub01.actual-editor-lumen-surface-review.v1','editor_pid':os.getpid(),
      'requested_epoch':time.time(),'phase':'baseline_requested','prior_visualize':prior,
      'diagnostic_visualize':5,'world':world.get_path_name(),'scene_mutations':0,
      'native_game_coverage_verified':False,'actual_coverage_reviewed':False,
      'fixed_camera_cm':[200,-195,165],'fixed_rotation_deg':[-18,-90,0],
      'viewport_fov_verified':False,'restored_prior_verified':False,'images':{},'error':None}
    output=root/'receipt.json'
    def persist():output.write_text(json.dumps(receipt,indent=2)+'\n')
    def capture(name):
        path=root/(name+'.png');requested=time.time()
        task=u.AutomationLibrary.take_high_res_screenshot(1280,720,str(path),delay=2.0)
        if task is None:raise RuntimeError('Actual screenshot request refused')
        receipt['images'][name]={'path':str(path),'requested_epoch':requested,'fresh_complete_png_verified':False}
    def restore():
        u.SystemLibrary.execute_console_command(world,'r.Lumen.Visualize '+str(prior))
        value=u.SystemLibrary.get_console_variable_int_value('r.Lumen.Visualize')
        receipt['restored_visualize_readback']=value
        receipt['restored_prior_verified']=value==prior
        if value!=prior:raise RuntimeError('Exact prior visualization restoration readback differs')
    def finish(error=None):
        global _handle
        try:restore()
        except Exception as exc:error=(str(error)+'; 'if error else'')+str(exc)
        receipt['error']=error;receipt['finished_epoch']=time.time();receipt['phase']='failed'if error else'complete'
        persist()
        if _handle is not None:u.unregister_slate_post_tick_callback(_handle);_handle=None
    started=time.monotonic()
    def tick(_delta):
        try:
            if time.monotonic()-started>60:raise RuntimeError('Bounded screenshot review timed out')
            if not guard_valid():raise RuntimeError('Trusted private window expired')
            phase=receipt['phase'];name={'baseline_requested':'baseline','surface_requested':'surface-cache-coverage','restored_requested':'restored-baseline'}[phase]
            image=receipt['images'][name]
            if not complete_png(Path(image['path']),image['requested_epoch']):return
            image['fresh_complete_png_verified']=True
            if phase=='baseline_requested':
                u.SystemLibrary.execute_console_command(world,'r.Lumen.Visualize 5')
                if u.SystemLibrary.get_console_variable_int_value('r.Lumen.Visualize')!=5:raise RuntimeError('Surface Cache display readback differs')
                capture('surface-cache-coverage');receipt['phase']='surface_requested';persist()
            elif phase=='surface_requested':
                restore();capture('restored-baseline');receipt['phase']='restored_requested';persist()
            else:finish()
        except Exception as exc:finish(type(exc).__name__+': '+str(exc))
    try:
        u.EditorLevelLibrary.set_level_viewport_camera_info(u.Vector(200,-195,165),u.Rotator(pitch=-18,yaw=-90,roll=0))
        if hasattr(u.EditorLevelLibrary,'editor_set_game_view'):u.EditorLevelLibrary.editor_set_game_view(True)
        capture('baseline');persist();_state=receipt
        _handle=u.register_slate_post_tick_callback(tick)
    except Exception as exc:
        finish(type(exc).__name__+': '+str(exc));raise
    return {'capture_requested':True,'receipt':str(output),'prior_visualize':prior,
            'image_written_verified':False,'must_wait_for_restoration_receipt':True}
