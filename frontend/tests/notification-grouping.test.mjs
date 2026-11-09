import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
function worker({badges=false,quota=false}={}) {
 const listeners={},stores=new Map(),notifications=[],badgeCounts=[];let clock=Date.parse('2026-11-09T12:00Z');
 const caches={open:async name=>{
  if(quota)throw Error('quota');
  if(!stores.has(name))stores.set(name,new Map());const map=stores.get(name),key=r=>typeof r==='string'?r:r.url;
  return {match:async r=>map.get(key(r))?.clone(),put:async(r,v)=>map.set(key(r),v.clone()),keys:async()=>Array.from(map.keys()).map(x=>new Request(new URL(x,'https://club.test'))),delete:async r=>map.delete(key(r))};
 }};
 const self={location:{origin:'https://club.test'},navigator:{setAppBadge:async n=>badgeCounts.push(n)},registration:{showNotification:async(title,options)=>notifications.push({title,...options})},addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn)};
 const context=vm.createContext({self,caches,Request,Response,URL,Headers,Promise,Date:class extends Date{static now(){return clock;}}});
 vm.runInContext(readFileSync(new URL('../sw.js',import.meta.url),'utf8'),context);
 if(badges)vm.runInContext(readFileSync(new URL('../../pwa/sw-pwa.js',import.meta.url),'utf8'),context);
 return {notifications,badgeCounts,advance:ms=>clock+=ms,push:async data=>{const jobs=[];for(const fn of listeners.push)fn({data:{json:()=>data},waitUntil:p=>jobs.push(p)});await Promise.all(jobs);}};
}
test('persistent groups serialize concurrent pushes and stable tag deduplicates',async()=>{
 const w=worker({badges:true}),a={kind:'cancelled',club_id:1,tag:'a',title:'A',body:'room1'};
 await Promise.all([w.push(a),w.push({...a,tag:'b',title:'B'})]);
 await w.push(a);
 assert.equal(w.notifications.length,3);assert.equal(w.notifications[2].title,'KipClub · изменения: 2');
 assert.equal(w.notifications[0].tag,w.notifications[1].tag);assert.equal(w.notifications[1].renotify,false);
 assert.deepEqual(w.badgeCounts,[1,2]);
});
test('groups separate club/kind and reset on next Moscow day',async()=>{
 const w=worker(),a={kind:'reminder',club_id:1,tag:'a',title:'A'};
 await w.push(a);await w.push({...a,club_id:2,tag:'b'});await w.push({...a,kind:'digest',tag:'d'});
 assert.equal(new Set(w.notifications.map(x=>x.tag)).size,3);
 w.advance(86400000);await w.push({...a,tag:'next',title:'Next'});assert.equal(w.notifications.at(-1).title,'Next');
});
test('quota/private cache still fulfills userVisibleOnly push contract',async()=>{
 const w=worker({quota:true});await w.push({title:'Update',body:'Text',url:'/?release=1.9.019'});
 assert.equal(w.notifications.length,1);assert.equal(w.notifications[0].data.url,'/?release=1.9.019');
});
