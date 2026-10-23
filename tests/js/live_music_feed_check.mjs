import assert from 'node:assert/strict';
import {readFileSync}from 'node:fs';
import{createLiveMusicFeed,musicTracks}from '../../web/house/live_music_feed.mjs';
const song=(id,title=id)=>({id,title,artist:'Artist',url:`https://open.spotify.com/track/${id}`});
assert.deepEqual(musicTracks({now:song('A'),today:[song('A'),song('B'),song('B')]}).map(s=>[s.id,s.isNow]),[['A',true],['B',false]]);
assert.equal(musicTracks({now:null,today:[song('B')]}).length,1);
assert.equal(musicTracks({now:song('A'),today:[{title:'A',artist:'Artist',url:song('A').url}]}).length,1,'URL alias deduplicates history even when id is absent');
assert.equal(musicTracks({now:null,today:null}).length,0);
assert.equal(musicTracks({today:[{},null,{title:'A',artist:'B'},{title:'A',artist:'B'}]}).length,1);
assert.equal(musicTracks({today:Array.from({length:12},(_,i)=>song(String(i)))}).length,8);
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
let time=0,id=0;const timers=new Map(),requests=[],writes=[],errors=[];
let activeOwner=null;
const feed=createLiveMusicFeed({
 now:()=>time,setTimer:(fn,delay)=>{const token=++id;timers.set(token,{fn,at:time+delay});return token;},clearTimer:token=>timers.delete(token),
 isActive:o=>o===activeOwner,
 fetchMusic:signal=>new Promise((resolve,reject)=>requests.push({signal,resolve,reject,at:time})),
 onTracks:(owner,tracks)=>writes.push({owner,tracks}),onError:(owner,error)=>errors.push([owner,error]),
});
async function advance(ms){time+=ms;for(let i=0;i<20;i++){
 const due=[...timers].filter(([,t])=>t.at<=time);if(!due.length)break;
 for(const[token,t]of due)if(timers.delete(token))t.fn();await flush();
}}
const ownerA={name:'music-a'};activeOwner=ownerA;feed.setOwner(ownerA);
assert.equal(requests.length,1);for(let i=0;i<20;i++){feed.setOwner(ownerA);feed.refresh();}assert.equal(requests.length,1,'no overlapping requests from repeated render ticks');
requests[0].resolve({now:song('A'),today:[song('A'),song('B')]});await flush();assert.equal(writes.length,1);assert.equal(writes[0].tracks.length,2);
await advance(4999);assert.equal(requests.length,1);await advance(1);assert.equal(requests.length,2);
requests[1].resolve({now:song('A'),today:[song('A'),song('B')]});await flush();assert.equal(writes.length,1,'unchanged current/history list causes no DOM rewrite');
await advance(5000);requests[2].resolve({now:song('C'),today:[song('C'),song('B')]});await flush();assert.equal(writes.length,2);assert.equal(writes.at(-1).tracks[0].id,'C','new live track updates same owned app');
await advance(5000);const old=requests[3];
const ownerB={name:'music-b'};activeOwner=ownerB;feed.setOwner(ownerB);assert.ok(old.signal.aborted);assert.equal(requests.length,5);
old.resolve({now:song('OLD')});await flush();assert.equal(writes.length,2,'ignored abort cannot write or clear the new owner');
requests[4].resolve({now:song('NEW')});await flush();assert.equal(writes.at(-1).owner,ownerB);assert.equal(writes.at(-1).tracks[0].id,'NEW');
await advance(5000);const closing=requests.at(-1);feed.stop();assert.ok(closing.signal.aborted);closing.resolve({now:song('LATE')});await flush();assert.equal(writes.length,3);assert.equal(timers.size,0,'close aborts request and all timers');
activeOwner=ownerA;feed.setOwner(ownerA);const privacy=requests.at(-1);activeOwner=null;feed.refresh();assert.ok(privacy.signal.aborted);privacy.resolve({now:song('PRIVATE')});await flush();assert.equal(writes.length,3,'bathroom/app change cannot accept late data');assert.equal(timers.size,0);
activeOwner=ownerA;feed.setOwner(ownerA);requests.at(-1).reject(new Error('offline'));await flush();assert.equal(errors.length,1);await advance(5000);assert.equal(requests.at(-1).at,time,'failed request retries at bounded interval');
const timed=requests.at(-1);await advance(10000);assert.ok(timed.signal.aborted,'hung HTTP request has deadline');timed.reject(new Error('abort'));await flush();assert.equal(errors.length,1,'expected abort does not surface as error');feed.stop();assert.equal(timers.size,0);
// #68: a track name (it may come from a viewer's wish) is set on the pages as text, never parsed as markup
const page=file=>readFileSync(new URL(`../../web/${file}`,import.meta.url),'utf8');
for(const file of ['house/home.js','life.html','room.html','index.html']){
 const markup=page(file).split('\n').filter(line=>/innerHTML/.test(line)&&/mu-t|mu-a|mu-why|sc-music|scr-music|song\.|music\.|track/.test(line));
 assert.deepEqual(markup,[],`${file}: a music title is set as markup`);
}
assert.match(page('house/home.js'),/textEl\('div', song\.title \+ ' · ' \+ song\.artist/,'phone music rows are text');
console.log('PASS: music text on the pages is set as text, never as markup');
console.log('PASS: now/today dedupe; active same-owner live updates;5s throttle/no overlap; unchanged-list suppression; close/app/privacy abort; ignored-abort stale isolation; timeout/retry; no audio/backend writes');
