import json
from pathlib import Path
import subprocess
import sys


def test_fixture_uses_valid_life_place_and_separate_ports(tmp_path):
    source=tmp_path/'main';mc=source/'minecraft';mc.mkdir(parents=True)
    (mc/'server.jar').write_bytes(b'fixture only; not executable')
    (mc/'downloads.json').write_text(json.dumps({'java':'fixture','port':25569}))
    (mc/'eula.txt').write_text('eula=true\n')
    (mc/'server.properties').write_text('server-ip=127.0.0.1\nserver-port=25569\n')
    target=tmp_path/'daytime'
    script=Path(__file__).parents[1]/'scripts/prepare_home_daytime_check.py'
    subprocess.run([sys.executable,str(script),str(target),'--main-data',str(source)],check=True,capture_output=True)
    life=json.loads((target/'life.json').read_text())
    assert life['activity']=='play_console' and life['place']=='window'
    assert json.loads((target/'body.json').read_text())['body']['ghrelin']==.1
    assert json.loads((target/'home.json').read_text())['console_game']=='minecraft'
    assert 'server-port=25570' in (target/'minecraft/server.properties').read_text()
    assert 'server-port=25569' in (mc/'server.properties').read_text()
    rerun=subprocess.run([sys.executable,str(script),str(target),'--main-data',str(source)],capture_output=True)
    assert rerun.returncode!=0  # preserve an already-running fixture's state
