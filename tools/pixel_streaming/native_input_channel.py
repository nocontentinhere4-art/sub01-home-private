"""Bounded physical input over the existing authenticated viewer socket.

Same permission/privacy/rate checks as HTTP. No renderer commands, arbitrary
host keys, backend movement, new listener or authentication mechanism.
"""
import time


def packet(value, previous_id=0):
    if (not isinstance(value,dict) or set(value)!={'id','event'}
            or type(value['id']) is not int or not previous_id<value['id']<2**53):
        raise ValueError('Bounded increasing physical input identifier required')
    return value['id'],value['event']


def dispatch(state,event,validate,physical_factory,egress_allowed,clock=time.monotonic,
             *,pace=False,sleeper=time.sleep,cancelled=lambda:False):
    event=validate(event)
    with state.input_lock:
        def permitted():
            return not cancelled() and (state.enabled('native-viewer-input-enabled') or (state.can_private_egress() and egress_allowed(event)))
        if not permitted():
            return 409,{'error':'Private movement only; devices and settings remain locked'}
        now=clock()
        rate_limited=event['action']!='release' and event.get('down',True)
        remaining=.005-(now-state.last_input)
        if rate_limited and remaining>0:
            if not pace:return 429,{'error':'Input rate exceeded'}
            # The socket reader owns at most one waiting event, never an unbounded
            # server queue. Keep the original 200 Hz limit and recheck the live
            # native identity/privacy/deadline after this bounded pause.
            sleeper(min(remaining,.005))
            if not permitted():return 409,{'error':'Native input permission changed'}
            if clock()-state.last_input<.005-1e-9:
                return 429,{'error':'Input rate exceeded'}
        if event['action']=='gamepad':
            try:state.gamepad.deliver(event)
            except PermissionError:
                return 200,{'acceptedInputs':state.accepted,'gamepadAccepted':False,'delivery':'none','session':state.session}
            state.last_input=clock();state.last_lease=state.last_input;state.accepted+=1
            return 200,{'acceptedInputs':state.accepted,'gamepadAccepted':True,'delivery':'nativeTVGamepadIntent','session':state.session}
        if event['action']=='release' and hasattr(state,'gamepad'):state.gamepad.release()
        if state.input is None:state.input=physical_factory()
        state.input.send(event);state.last_input=clock();state.last_lease=state.last_input;state.accepted+=1
        return 200,{'acceptedInputs':state.accepted,'physicalDelivery':'XTest','session':state.session}


INPUT_SOCKET_JS = r'''
let nativeInputId=0;
const nativePendingInputs=new Map();
function sendNativeSocketInput(event){
 const socket=window.nativeViewerSocket;
 if(!socket||socket.readyState!==1)return null;
 if(nativePendingInputs.size>=64||socket.bufferedAmount>16384)return Promise.reject(Error('Control connection overloaded'));
 const id=++nativeInputId;
 return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{nativePendingInputs.delete(id);reject(Error('Control acknowledgement timed out'));},2500);
  nativePendingInputs.set(id,{socket,resolve,reject,timer});
  try{socket.send(JSON.stringify({id,event}));}
  catch(error){clearTimeout(timer);nativePendingInputs.delete(id);reject(error);}
 });
}
function acknowledgeNativeSocketInput(socket,text){
 let value;try{value=JSON.parse(text);}catch(error){return;}
 if(!value||value.type!=='input-ack'||!Number.isSafeInteger(value.id))return;
 const pending=nativePendingInputs.get(value.id);
 if(!pending||pending.socket!==socket)return;
 nativePendingInputs.delete(value.id);clearTimeout(pending.timer);
 if(value.status===200&&Number.isSafeInteger(value.acceptedInputs)&&value.acceptedInputs>=0){
  accepted=Math.max(accepted,value.acceptedInputs);window.nativeViewerAcceptedInputs=accepted;pending.resolve(value);
 }else pending.reject(Error(value.error||'Native input refused'));
}
function closeNativeSocketInputs(socket){
 for(const[id,pending]of nativePendingInputs)if(pending.socket===socket){
  clearTimeout(pending.timer);nativePendingInputs.delete(id);pending.reject(Error('Control socket closed'));
 }
}
'''
