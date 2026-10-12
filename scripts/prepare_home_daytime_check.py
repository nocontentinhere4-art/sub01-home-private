"""Prepare an isolated, declared daytime integration fixture; never edit main state."""
import argparse
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from home_world import HomeWorld
from life import PLACES, ACTIVITIES

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination',type=Path)
parser.add_argument('--main-data',type=Path,default=ROOT/'data')
args=parser.parse_args()
target=args.destination.resolve(); source=args.main_data.resolve()
if target==source or target.exists(): parser.error('Use a new separate fixture directory')
for name in ['server.jar','downloads.json','eula.txt','server.properties']:
    if not (source/'minecraft'/name).is_file(): parser.error('Prepare the main approved Minecraft runtime first')
target.mkdir(parents=True)
(target/'spiking').mkdir()
for name in ['growth.npz','live_weights.npz']:
    if (source/'spiking'/name).exists(): shutil.copy2(source/'spiking'/name,target/'spiking'/name)
mc=target/'minecraft';mc.mkdir()
(mc/'server.jar').symlink_to(source/'minecraft'/'server.jar')
for name in ['downloads.json','eula.txt']: shutil.copy2(source/'minecraft'/name,mc/name)
properties=(source/'minecraft'/'server.properties').read_text().replace('server-port=25569','server-port=25570')
(mc/'server.properties').write_text(properties)
config=json.loads((mc/'downloads.json').read_text());config['port']=25570
(mc/'downloads.json').write_text(json.dumps(config,indent=2))
start=datetime.now(ZoneInfo('Asia/Tokyo')).replace(hour=13,minute=0,second=0,microsecond=0).timestamp()
(target/'home.json').write_text(json.dumps(HomeWorld({'node':'bed','console_game':'minecraft'}).to_dict()))
place=ACTIVITIES['play_console'][0]
x,z=PLACES[place]
(target/'life.json').write_text(json.dumps({'activity':'play_console','place':place,'x':x,'z':z,'path':[],
    'until':start+900,'dur':None,'bread':2,'boredom':.5,'viewer_nudge':['play_console',start]}))
(target/'body.json').write_text(json.dumps({'body':{'ghrelin':.1},'neuro':{}}))
(target/'test-fixture.json').write_text(json.dumps({'purpose':'Daytime device integration test',
    'scenario':'Operator-initialized console activity with a fed starting body',
    'brain':'Copied learned weights and growth state; base neurons remain 500000',
    'start_tokyo':'13:00','time_scale':1.01,'server_port':25570,'viewer_port':8805,
    'source':str(source)},indent=2))
print('Prepared isolated daytime fixture:',target)
