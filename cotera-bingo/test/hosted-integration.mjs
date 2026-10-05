import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {personas,personaPains} from '../lib/personas.mjs';
const origin='http://127.0.0.1:5173',mode='personal',run=crypto.randomUUID();
const endpoint=origin+'/api/game?mode='+mode;
async function call(payload=null,cookie='',suffix=''){const res=await fetch(endpoint+suffix,{method:payload?'POST':'GET',headers:{Origin:origin,'Content-Type':'application/json',Cookie:cookie},...(payload?{body:JSON.stringify(payload)}:{})});return {status:res.status,data:await res.json(),cookie:res.headers.get('set-cookie')?.split(';')[0]||cookie};}
function ok(r){assert.equal(r.status,200,r.data?.error||'Request failed');return r;}
const {pin}=JSON.parse(await readFile(new URL('../../../work/admin-local.json',import.meta.url),'utf8'));
const admin=ok(await call({action:'login',pin})).cookie;
const original=ok(await call(null,admin,'&admin=1')).data;
const players=[];
for(let n=0;n<24;n+=6){const group=await Promise.all(Array.from({length:6},async(_,j)=>{const i=n+j,role=personas[i%8].id;const p=ok(await call({action:'register',name:'Simulation '+i,company:'Practice only',type:'email',contact:`sim-${run}-${i}@example.com`,consent:true,path:'bingo'}));assert.equal(p.data.me.role,null);const r=ok(await call({action:'role',role},p.cookie));assert.equal(r.data.me.card.length,6);return {...r,role};}));players.push(...group);}
assert.equal((await call(null,'','&admin=1')).status,401);
assert.equal((await fetch(endpoint,{method:'POST',headers:{Origin:'https://wrong.example','Content-Type':'application/json'},body:JSON.stringify({action:'match'})})).status,403);
ok(await call({action:'skip'},admin));
for(let i=0;i<23;i++)ok(await call({action:'next_call'},admin));
let fresh=ok(await call(null,players[0].cookie));assert.equal(fresh.data.round.calledCount,24);
const matchPayload={action:'match',round:fresh.data.round.id,pain:fresh.data.me.card.find(c=>c.called).id,request:crypto.randomUUID()};
const duplicates=await Promise.all(Array.from({length:12},()=>call(matchPayload,players[0].cookie)));duplicates.forEach(ok);assert.equal(ok(await call(null,players[0].cookie)).data.me.matches,1);assert.equal(ok(await call(null,players[8].cookie)).data.me.matches,0);
for(const p of players.slice(0,8)){const before=ok(await call(null,p.cookie)).data;for(const sq of before.me.card.filter(c=>c.called&&!c.matched))ok(await call({action:'match',round:before.round.id,pain:sq.id,request:crypto.randomUUID()},p.cookie));const after=ok(await call(null,p.cookie)).data;assert.ok(after.me.kit);assert.equal(after.me.matches,3);assert.equal(after.me.wins.length,1);}
const code=ok(await call(null,players[0].cookie)).data.me.kit.code;
ok(await call({action:'path',path:'direct'},players[0].cookie));ok(await call({action:'problems',pains:personaPains(players[0].role).slice(0,3).map(p=>p.id),request:crypto.randomUUID()},players[0].cookie));assert.equal(ok(await call(null,players[0].cookie)).data.me.kit.code,code);
const publicState=ok(await call(null,players[0].cookie,'&public=1')).data;assert.equal(publicState.me,null);assert.ok(!JSON.stringify(publicState).includes(code));
const current=ok(await call(null,admin,'&admin=1')).data;
ok(await call({action:'settings',kitLimit:current.kits.length+1},admin));
const stockRace=await Promise.all(players.slice(8).map(p=>call({action:'problems',pains:personaPains(p.role).slice(0,3).map(p=>p.id),request:crypto.randomUUID()},p.cookie)));stockRace.forEach(ok);
const afterRace=ok(await call(null,admin,'&admin=1')).data;assert.equal(afterRace.kits.length,current.kits.length+1);
ok(await call({action:'settings',kitLimit:original.settings.kitLimit},admin));
ok(await call({action:'pause'},admin));const paused=ok(await call(null,players[0].cookie)).data;assert.equal(paused.settings.paused,true);ok(await call({action:'pause'},admin));
const exportResponse=await fetch(endpoint+'&export=1',{headers:{Cookie:admin}});assert.equal(exportResponse.status,200);const csv=await exportResponse.text();assert.ok(csv.includes('bingo match — not a reported problem'));assert.ok(csv.includes('reported problem'));assert.ok(csv.includes('registration'));
const illegal=await fetch(origin+'/api/game?mode=event',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json',Cookie:admin},body:JSON.stringify({action:'next_call'})});assert.equal(illegal.status,403);
console.log('HTTP simulations passed: 24 attendees, eight roles, simultaneous joins, 12 duplicate taps, eight Bingos, isolated marks, both paths, 16-person last-kit race, reload persistence, pause/resume, CSV, public privacy and access controls.');
