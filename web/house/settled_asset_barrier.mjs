// Track actual initial asset/parse promises, not LoadingManager network idleness.
// Register a spawned asset before its parent task settles. Future unrelated
// dynamic work is outside a completed initial barrier and can use a later drain.
export function createSettledAssetBarrier({onRejected,maxFailures=32}={}){
 if(!Number.isInteger(maxFailures)||maxFailures<0)throw new TypeError('maxFailures must be a nonnegative integer');
 const seen=new WeakSet(),pending=new Set(),failures=[];
 let registered=0,fulfilled=0,rejected=0,droppedFailures=0,drain=null;
 const report=()=>({registered,fulfilled,rejected,pending:pending.size,failures:[...failures],droppedFailures});
 function add(promise){
  if(!promise||!['object','function'].includes(typeof promise)||typeof promise.then!=='function')throw new TypeError('Asset barrier requires a promise');
  if(seen.has(promise))return promise;
  seen.add(promise);registered++;
  const ticket={done:null};pending.add(ticket);
  // Both paths resolve the observer. Callers retain their original rejection
  // behavior, while the barrier can finish with visible failure fallbacks.
  ticket.done=Promise.resolve(promise).then(()=>{fulfilled++;},error=>{
   rejected++;
   if(failures.length<maxFailures)failures.push(error);else droppedFailures++;
   try{onRejected?.(error);}catch{/* Reporting cannot strand asset readiness. */}
  }).then(()=>{pending.delete(ticket);});
  return promise;
 }
 function settled(){
  if(drain)return drain;
  const run=async()=>{
   // Even an empty first wave yields once, allowing same-turn registration.
   do{await Promise.all([...pending].map(ticket=>ticket.done));}while(pending.size);
   return report();
  };
  drain=run().then(result=>{drain=null;return result;},error=>{drain=null;throw error;});
  return drain;
 }
 return{add,settled};
}
