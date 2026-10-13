// Preserve real PS/2 key order and a measurable press interval. Privacy cancels
// queued input and releases held keys before stopping the guest.
function guestKeyboard(send, delay = ms => new Promise(resolve => setTimeout(resolve, ms))) {
 let chain = Promise.resolve(), epoch = 0;
 const held = new Map();
 let extended = false;
 return {
  enqueue(codes) {
   const captured = epoch;
   const task = chain.then(async () => {
    for(const code of codes) {
     if(captured !== epoch) return false;
     send([code]);
     if(code === 0xe0) extended = true;
     else {
      const key = (extended ? 'extended:' : '') + (code & 127);
      if(code < 128) held.set(key, extended ? [0xe0, code | 128] : [code | 128]);
      else held.delete(key);
      extended = false;
     }
     await delay(20);
    }
    return true;
   });
   chain = task.catch(() => {});
   return task;
  },
  cancel() {
   epoch++;
   for(const release of held.values()) send(release);
   held.clear(); extended = false;
  }
 };
}
module.exports = { guestKeyboard };
