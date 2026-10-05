import assert from 'node:assert/strict';
import {personas,matchesPersona} from '../lib/personas.mjs';
const origin='http://127.0.0.1:5173';
async function call(payload,cookie=''){
 const res=await fetch(origin+'/api/game?mode=personal',{method:payload?'POST':'GET',headers:{Origin:origin,'Content-Type':'application/json',Cookie:cookie},...(payload?{body:JSON.stringify(payload)}:{})});
 return {status:res.status,data:await res.json(),cookie:res.headers.get('set-cookie')?.split(';')[0]||cookie};
}
let players=[];
for(const role of personas){
 const r=await call({action:'register',name:'Persona QA',company:'Local test',type:'email',contact:'persona-'+crypto.randomUUID()+'@example.com',consent:true,role:role.id});
 assert.equal(r.status,200,JSON.stringify(r.data));assert.equal(r.data.me.role,role.id);
 assert.equal(r.data.board.squares.length,25);assert.ok(r.data.board.squares.every(p=>matchesPersona(role.id,p.id)));
 players.push(r);
 const reload=await call(null,r.cookie);assert.equal(reload.data.board.id,r.data.board.id);assert.equal(reload.data.me.role,role.id);
}
const a=players[0],b=players[1];
for(let i=0;i<5;i++){
 const r=await call({action:'claim',board:a.data.board.id,index:i,request:crypto.randomUUID()},a.cookie);
 assert.equal(r.status,200,JSON.stringify(r.data));a.data=r.data;
}
assert.equal(a.data.me.wins.length,1);assert.equal(a.data.me.kits.length,1);
assert.equal((await call(null,b.cookie)).data.board.count,0);
const change=await call({action:'role',role:'customers'},a.cookie);
assert.equal(change.status,200);assert.equal(change.data.me.rolePending,true);assert.equal(change.data.board.count,5);assert.equal(change.data.me.kits[0].code,a.data.me.kits[0].code);
const newRole=await call({action:'role',role:'support'},b.cookie);
assert.equal(newRole.status,200);assert.ok(newRole.data.board.squares.every(p=>matchesPersona('support',p.id)));
assert.equal((await call({action:'role',role:'invented'},b.cookie)).status,400);
assert.equal((await call({action:'role',role:'sales'})).status,401);
const publicData=await fetch(origin+'/api/game?mode=personal&public=1',{headers:{Cookie:a.cookie}}).then(r=>r.json());
assert.equal(publicData.me,null);assert.ok(!JSON.stringify(publicData).includes(a.data.me.kits[0].code));
assert.equal(new Set(players.map(p=>p.data.board.id)).size,personas.length);
console.log('HTTP checks passed: role cards, persistence, isolation, bingo, retained prizes, role changes, validation and public privacy.');
