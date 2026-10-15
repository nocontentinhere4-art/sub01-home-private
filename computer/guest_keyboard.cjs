// Preserve real PS/2 key order and a measurable press interval. Privacy cancels
// queued input and releases held keys before stopping the guest.
function guestKeyboard(send, delay = ms => new Promise(resolve => setTimeout(resolve, ms))) {
 let chain = Promise.resolve(), epoch = 0;
 const held = new Map();
 let extended = false, extendedOwner=null;
 return {
  enqueue(codes, valid=()=>true, waitFor=async p=>{await p;return true;}) {
   const captured = epoch, owner=Symbol();
   async function releaseOwned(){
    if(extendedOwner===owner){extended=false;extendedOwner=null;}
    for(const [key,entry]of held)if(entry.owner===owner){
     try{await waitFor(send(entry.release));}catch(_){}finally{held.delete(key);}
    }
   }
   const task = chain.then(async () => {
    try {
     for(const code of codes) {
      if(captured !== epoch||!valid()){await releaseOwned();return false;}
      // Record the synchronous invocation before awaiting its Promise, so a
      // concurrent privacy pause still sees and releases this request's keys.
      const sending=send([code]);
      if(code === 0xe0){extended = true;extendedOwner=owner;}
      else {
       const key = (extended ? 'extended:' : '') + (code & 127);
       if(code < 128) {
        if(!held.has(key))held.set(key,{release:extended ? [0xe0,code|128]:[code|128],owner});
       }else held.delete(key);
       extended = false;extendedOwner=null;
      }
      if(!await waitFor(sending)){await releaseOwned();return false;}
      await delay(20);
     }
     if(captured!==epoch||!valid()){await releaseOwned();return false;}
     return true;
    }catch(error){await releaseOwned();throw error;}
   });
   chain = task.catch(() => {});
   return task;
  },
  cancel() {
   epoch++;
   for(const entry of held.values()) {
    try{Promise.resolve(send(entry.release)).catch(()=>{});}catch(_){}
   }
   held.clear(); extended = false;extendedOwner=null;
  }
 };
}
module.exports = { guestKeyboard };
