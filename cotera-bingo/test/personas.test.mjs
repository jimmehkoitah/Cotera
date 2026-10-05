import {test} from 'node:test';
import assert from 'node:assert/strict';
import {personas,personaPains,matchesPersona,painCatalog,sharedAIIds} from '../lib/personas.mjs';
import {initial,register,chooseRole,claim,personal,snapshot,advanceRound,csv,upgrade} from '../lib/game.mjs';
const join=(s,role)=>register(s,{name:'Role test',company:'Example',type:'email',contact:crypto.randomUUID()+'@example.com',consent:true,role});
const tap=(s,p,index)=>claim(s,p.token,{board:s.personalBoards[p.id].id,index,request:crypto.randomUUID()});

test('all 34 reference profiles map to a role, with complete unique problem pools',()=>{
 assert.deepEqual([...new Set(personas.flatMap(p=>p.profiles))].sort((a,b)=>a-b),Array.from({length:34},(_,i)=>i+1));
 assert.equal(new Set(painCatalog.map(p=>p.id)).size,painCatalog.length);
 for(const role of personas){
  const pains=personaPains(role.id);
  assert.ok(pains.length>=25,role.id);
  assert.ok(role.painIds.every(id=>painCatalog.some(p=>p.id===id)),role.id+' has unresolved IDs');
  assert.equal(new Set(role.painIds).size,role.painIds.length);
  assert.ok(pains.every(p=>p.short&&p.full&&p.topic));
 }
});

test('personal role cards contain 25 unique relevant problems, retain their role and stay isolated',()=>{
 const s=initial('personal');
 for(const role of personas){
  const p=join(s,role.id),b=s.personalBoards[p.id];
  assert.equal(b.squares.length,25);
  assert.equal(new Set(b.squares.map(p=>p.id)).size,25);
  assert.ok(b.squares.every(p=>matchesPersona(role.id,p.id)));assert.equal(b.squares.filter(p=>sharedAIIds.includes(p.id)).length,3);
  tap(s,p,0);
  const roundTrip=upgrade(JSON.parse(JSON.stringify(s)));
  assert.equal(personal(roundTrip,p.token).role,role.id);
  assert.equal(snapshot(roundTrip,p.token).board.count,1);
 }
 assert.equal(new Set(Object.values(s.personalBoards).map(b=>b.id)).size,personas.length);
 assert.equal(snapshot(s).board.count,0);
});

test('changing a role never erases marks or wins and takes effect in the next round',()=>{
 const s=initial('personal'),p=join(s,'sales');
 const old=s.personalBoards[p.id].id;
 chooseRole(s,p.token,'customers');
 assert.notEqual(s.personalBoards[p.id].id,old);
 assert.equal(s.personalBoards[p.id].role,'customers');
 for(let i=0;i<5;i++)tap(s,p,i);
 const card=s.personalBoards[p.id].id,code=personal(s,p.token).kits[0].code;
 chooseRole(s,p.token,'technology');
 assert.equal(s.personalBoards[p.id].id,card);
 assert.equal(snapshot(s,p.token).board.count,5);
 assert.equal(personal(s,p.token).rolePending,true);
 assert.equal(personal(s,p.token).cardRole,'customers');
 advanceRound(s);
 assert.equal(personal(s,p.token).rolePending,false);
 assert.equal(s.personalBoards[p.id].role,'technology');
 assert.ok(s.personalBoards[p.id].squares.every(p=>matchesPersona('technology',p.id)));
 assert.equal(personal(s,p.token).kits[0].code,code);
 for(let i=0;i<5;i++)tap(s,p,i);
 assert.equal(personal(s,p.token).kits.length,1);
 assert.ok(csv(s).includes('Customer success & accounts'));
 assert.ok(csv(s).includes('Role card'));
});

test('completing a personal card keeps the role and historical claims',()=>{
 const s=initial('personal'),p=join(s,'risk'),before=s.personalBoards[p.id].id;
 for(let i=0;i<25;i++)tap(s,p,i);
 assert.notEqual(s.personalBoards[p.id].id,before);
 assert.equal(s.personalBoards[p.id].no,2);
 assert.ok(s.personalBoards[p.id].squares.every(p=>matchesPersona('risk',p.id)));
 assert.equal(s.claims.length,25);
 assert.equal(personal(s,p.token).kits.length,1);
});

test('shared role changes do not alter the room board or reveal player roles',()=>{
 const s=initial(),p=join(s,'revops'),before=structuredClone(s.board);
 chooseRole(s,p.token,'support');
 assert.deepEqual(s.board,before);
 assert.equal(personal(s,p.token).role,'support');
 const publicData=snapshot(s);
 assert.equal(publicData.me,undefined);
 assert.ok(!JSON.stringify(publicData).includes('"role"'));
 assert.throws(()=>chooseRole(s,'bad-token','sales'),/Join the game/);
 assert.throws(()=>chooseRole(s,p.token,'invented'),/listed roles/);
 assert.throws(()=>join(s,'invented'),/listed roles/);
});

test('kit stock is shared across personal cards, and exhausted stock never produces another code',()=>{
 const s=initial('personal');s.settings.kitLimit=1;
 const a=join(s,'customers'),b=join(s,'support');
 for(let i=0;i<5;i++)tap(s,a,i);
 for(let i=0;i<5;i++)tap(s,b,i);
 assert.equal(personal(s,a.token).kits.length,1);
 assert.equal(personal(s,b.token).kits.length,0);
 assert.equal(personal(s,b.token).wins.length,1);
 assert.equal(s.kits.length,1);
 advanceRound(s);
 for(let i=0;i<5;i++)tap(s,b,i);
 assert.equal(s.kits.length,1);
});
