"""Guard only the explicitly authorized replacement private home runtime."""
import json, os, time, urllib.request
from pathlib import Path
DEADLINE=1791957106
NAME='sub01-home-private-recovery'
AUTHORIZED_PODS={
 '5ldnm4vax9kelh':'sub01-home-private-migration-20261014',
}
def verify_authorized_pod(pod,state):
 if pod not in AUTHORIZED_PODS or state['id']!=pod or state['name']!=AUTHORIZED_PODS[pod]:
  raise RuntimeError('Unauthorized private home migration identity')
def main():
 pod=os.environ['RUNPOD_POD_ID'];key=os.environ['SUB01_HOME_CONTROL_API_KEY']
 root=Path('/workspace/sub01-home-private');root.mkdir(parents=True,exist_ok=True);secure=Path('/root/.sub01-home-private');secure.mkdir(parents=True,exist_ok=True);secure.chmod(0o700);(root/'logs').mkdir(exist_ok=True)
 c=secure/'control.json';c.write_text(json.dumps({'api_key':key,'pod_id':pod,'budget_usd':100,'max_hours':10}));c.chmod(0o600)
 (root/'logs/budget-20261013-deadline').write_text(str(DEADLINE)+'\n')
 def api(query):
  r=urllib.request.Request('https://api.runpod.io/graphql?api_key='+key,data=json.dumps({'query':query}).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(r,timeout=15) as response:d=json.load(response)
  if d.get('errors'):raise RuntimeError('Private home guard API rejected')
  return d['data']
 state=api('query { pod(input:{podId:'+json.dumps(pod)+'}) { id name } }')['pod']
 verify_authorized_pod(pod,state)
 print('AUTHENTICATED_PRIVATE_HOME',pod,'deadline',DEADLINE,'total_cap',100,flush=True)
 while time.time()<DEADLINE:
  try:
   price=api('query { pod(input:{podId:'+json.dumps(pod)+'}) { id name adjustedCostPerHr } }')['pod']
   verify_authorized_pod(pod,price)
   if price['adjustedCostPerHr']>.65:break
  except Exception as e:
   print('PRICE_CHECK_RETRY',type(e).__name__,flush=True)
  time.sleep(min(60,max(0,DEADLINE-time.time())))
 while True:
  try:
   d=api('mutation { podStop(input:{podId:'+json.dumps(pod)+'}) { id desiredStatus } }')['podStop']
   if d['id']==pod and d['desiredStatus'] in ('EXITED','STOPPED'):print('STOP_CONFIRMED_PRIVATE_HOME',pod,flush=True);return
  except Exception as e:print('STOP_RETRY',type(e).__name__,flush=True)
  time.sleep(5)
if __name__=='__main__':main()
