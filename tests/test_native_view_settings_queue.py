"""Execute the served settings queue against delayed native acknowledgements."""
import json
import shutil
import subprocess

import pytest

from tools.pixel_streaming.native_live_viewer import HTML, VIEW_SETTINGS_QUEUE_JS


def run_queue(scenario):
    node = shutil.which("node")
    assert node, "Node is required to execute the production viewer queue"
    script = VIEW_SETTINGS_QUEUE_JS + "\n" + scenario
    result = subprocess.run([node, "--input-type=commonjs", "-"], input=script,
                            text=True, capture_output=True, timeout=5, check=True)
    return json.loads(result.stdout)


def test_rapid_controls_wait_for_each_native_ack():
    result = run_queue(r'''
let health={nativeIdentity:[42,100],privacy:false,viewMode:'manual',inputEnabled:true};
async function readHealth(){return health;}
let release,started=[],active=0,peak=0,state={lamps:false,fov:60};
const first=new Promise(resolve=>release=resolve);
async function submit(value){active++;peak=Math.max(peak,active);started.push(value);
 if(started.length===1)await first;Object.assign(state,value);active--;}
(async()=>{
 const tasks=[queueNativeViewSetting({lamps:true},[42,100],submit),
              queueNativeViewSetting({lamps:false},[42,100],submit),
              queueNativeViewSetting({fov:75},[42,100],submit)];
 await new Promise(resolve=>setImmediate(resolve));
 const before=started.length;release();await Promise.all(tasks);
 console.log(JSON.stringify({before,started,peak,state}));
})().catch(e=>{console.error(e);process.exitCode=1;});
''')
    assert result == {"before": 1, "started": [{"lamps": True}, {"lamps": False}, {"fov": 75}],
                      "peak": 1, "state": {"lamps": False, "fov": 75}}


@pytest.mark.parametrize("changed", [
    "health.privacy=null", "health.nativeIdentity=[43,101]",
    "health.viewMode='live'", "health.inputEnabled=false",
])
def test_queued_changes_do_not_cross_privacy_identity_or_ownership(changed):
    result = run_queue(r'''
let health={nativeIdentity:[42,100],privacy:false,viewMode:'manual',inputEnabled:true};
async function readHealth(){return health;}
let applied=[];
async function submit(value){applied.push(value);CHANGE;}
(async()=>{
 const tasks=[queueNativeViewSetting({fov:75},[42,100],submit),
              queueNativeViewSetting({hour:0},[42,100],submit),
              queueNativeViewSetting({lamps:false},[42,100],submit)];
 const results=await Promise.allSettled(tasks);
 console.log(JSON.stringify({applied,statuses:results.map(x=>x.status)}));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''.replace("CHANGE", changed))
    assert result == {"applied": [{"fov": 75}], "statuses": ["fulfilled", "rejected", "rejected"]}


def test_unacknowledged_change_cancels_the_already_queued_followup():
    result = run_queue(r'''
async function readHealth(){return {nativeIdentity:[42,100],privacy:false,viewMode:'manual',inputEnabled:true};}
let applied=[];
async function submit(value){applied.push(value);throw Error('Native setting was not acknowledged');}
(async()=>{
 const results=await Promise.allSettled([
  queueNativeViewSetting({lamps:false},[42,100],submit),
  queueNativeViewSetting({hour:11},[42,100],submit)]);
 console.log(JSON.stringify({applied,statuses:results.map(x=>x.status)}));
})().catch(e=>{console.error(e);process.exitCode=1;});
''')
    assert result == {"applied": [{"lamps": False}], "statuses": ["rejected", "rejected"]}


def test_browser_serves_the_executed_queue_and_updates_owner_identity():
    assert VIEW_SETTINGS_QUEUE_JS in HTML
    assert "%SETTINGS_QUEUE%" not in HTML
    assert "settingsIdentity=[p.native_pid,p.native_start_ticks]" in HTML
    assert "queueNativeViewSetting(value,settingsIdentity,submit)" in HTML


def test_a_new_explicit_request_can_recover_after_failed_batch():
    result = run_queue(r'''
async function readHealth(){return {nativeIdentity:[42,100],privacy:false,viewMode:'manual',inputEnabled:true};}
let applied=[],owners=[];
async function submit(value,expected){applied.push(value);owners.push(expected);
 if(applied.length===1)throw Error('Not acknowledged');}
(async()=>{
 const results=await Promise.allSettled([
  queueNativeViewSetting({hour:0},[42,100],submit),
  queueNativeViewSetting({hour:11},[42,100],submit)]);
 await queueNativeViewSetting({fov:75},[42,100],submit);
 console.log(JSON.stringify({applied,owners,statuses:results.map(x=>x.status)}));
})().catch(e=>{console.error(e);process.exitCode=1;});
''')
    assert result == {"applied": [{"hour": 0}, {"fov": 75}],
                      "owners": [[42, 100], [42, 100]],
                      "statuses": ["rejected", "rejected"]}


def test_native_ack_must_match_the_queued_owner():
    assert "ack.native_pid!==expected[0]||ack.native_start_ticks!==expected[1]" in HTML
