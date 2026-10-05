import {activePersonas, isActivePersona, getPersona, personaPains, sharedAIIds} from './personas.mjs';
import {normalize, fail} from './game.mjs';
export const ROUND_MS=300000, CALL_MS=12000, TARGET=3;
const uid=()=>crypto.randomUUID();
const shuffle=a=>{a=[...a];for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]];}return a;};
const publicPain=p=>({id:p.id,short:p.short,full:p.full});
export function initialRoom(){return {schema:1,version:0,players:[],round:null,history:[],matches:[],experiences:[],wins:[],kits:[],notes:[],settings:{paused:false,pausedAt:null,ended:false,kitLimit:null,nextRoundAt:null,announcement:''}};}
export function makeRound(no,now){
 const cards={},chosen={};
 for(const role of activePersonas){const pool=personaPains(role.id);cards[role.id]=shuffle([...shuffle(pool.filter(p=>!sharedAIIds.includes(p.id))).slice(0,5),shuffle(pool.filter(p=>sharedAIIds.includes(p.id)))[0]]);chosen[role.id]=shuffle(cards[role.id]).slice(0,3);}
 const calls=[];for(let pass=0;pass<3;pass++)for(const role of shuffle(activePersonas))calls.push({role:role.id,pain:chosen[role.id][pass]});
 return {id:uid(),no,startedAt:now,cards,calls};
}
export function advanceRoom(s,now=Date.now()){if(s.round){s.history.push(s.round);if(s.history.length>65)s.history.shift();}s.round=makeRound((s.round?.no||0)+1,now);s.settings.paused=false;s.settings.pausedAt=null;s.settings.ended=false;s.settings.nextRoundAt=null;s.settings.announcement='';}
export function roomDue(s,now=Date.now()){return !s.settings.ended&&((s.settings.nextRoundAt&&now>=s.settings.nextRoundAt)||(!s.settings.paused&&s.round&&now>=s.round.startedAt+ROUND_MS));}
export function tickRoom(s,now=Date.now()){
 if(s.settings.ended)return;
 if(s.settings.nextRoundAt&&now>=s.settings.nextRoundAt){advanceRoom(s,now);return;}
 if(!s.settings.paused&&s.round&&now>=s.round.startedAt+ROUND_MS)advanceRoom(s,now);
}
const player=(s,token)=>{const p=s.players.find(p=>p.token===token);if(!p)fail('Please join the room first.',401);return p;};
function requestId(id){if(typeof id!=='string'||id.length<8||id.length>80)fail('Please retry this action.');}
function open(s){if(s.settings.ended)fail('The event has ended. Your saved prize is still available.');}
function available(s){return s.settings.kitLimit==null||s.kits.filter(k=>!k.revoked).length<s.settings.kitLimit;}
function reward(s,p,reason,source,now){
 const existing=s.kits.find(k=>k.player===p.id&&!k.revoked);if(existing)return {status:'already-earned',code:existing.code};
 if(!available(s))return {status:'out-of-stock',code:null};
 let code;do{code=Array.from(crypto.getRandomValues(new Uint8Array(5)),v=>'23456789ABCDEFGHJKLMNPQRSTUVWXYZ'[v%31]).join('');}while(s.kits.some(k=>k.code===code));
 s.kits.push({id:uid(),player:p.id,reason,source,code,at:now,handed:null,revoked:null});return {status:'earned',code};
}
export function joinRoom(s,input,token,now=Date.now()){
 open(s);if(!['bingo','direct'].includes(input.path))fail('Choose Play Bingo or Share three problems.');
 for(const key of ['name','company'])if(typeof input[key]!=='string'||!input[key].trim()||input[key].trim().length>80)fail('Enter your name and company (up to 80 characters each).');
 if(String(input.contact||'').length>200)fail('Contact details are too long.');
 const norm=normalize(input.type,input.contact);if(input.consent!==true)fail('Please accept the contact consent.');
 const existing=s.players.find(p=>p.norm===norm);if(existing){if(existing.token!==token)fail('This contact has already joined. Open the original browser, or ask Jim for help.',409);return existing;}
 const p={id:uid(),token:uid(),name:input.name.trim(),company:input.company.trim(),type:input.type,contact:input.contact.trim(),norm,path:input.path,role:null,joined:now,consentAt:new Date(now).toISOString(),directComplete:null};s.players.push(p);return p;
}
export function selectRoomRole(s,token,role,now=Date.now()) {open(s);const p=player(s,token);if(!isActivePersona(role))fail('Choose one of the listed roles.');p.role=role;if(p.path==='bingo'&&!s.round&&!s.settings.paused)advanceRoom(s,now+10000);return p;}
export function selectRoomPath(s,token,path,now=Date.now()){open(s);const p=player(s,token);if(!['bingo','direct'].includes(path))fail('Choose a way to play.');p.path=path;if(path==='bingo'&&p.role&&!s.round&&!s.settings.paused)advanceRoom(s,now+10000);}
export function calledFor(s,now=Date.now()){
 if(!s.round)return [];
 const time=s.settings.paused?s.settings.pausedAt:now;
 return s.round.calls.slice(0,Math.max(0,Math.min(s.round.calls.length,Math.floor((time-s.round.startedAt)/CALL_MS)+1)));
}
export function matchCall(s,token,input,now=Date.now()){
 const p=player(s,token);requestId(input.request);const prior=s.matches.find(m=>m.player===p.id&&m.request===input.request);if(prior)return prior;
 open(s);if(s.settings.paused)fail('Bingo is paused. Your progress is saved.');if(p.path!=='bingo'||!p.role)fail('Choose your role and Play Bingo first.');
 if(input.round!==s.round?.id)fail('A fresh round has started. Your new card is ready.',409);
 const sq=(s.round.cards[p.role]||[]).find(x=>x.id===input.pain);if(!sq)fail('Choose a problem on your card.');
 if(!calledFor(s,now).some(c=>c.role===p.role&&c.pain.id===sq.id))fail('This problem has not been called yet.');
 if(s.matches.some(m=>m.player===p.id&&m.round===s.round.id&&m.pain.id===sq.id))fail('You already matched this problem.',409);
 const m={id:uid(),request:input.request,player:p.id,round:s.round.id,roundNo:s.round.no,role:p.role,pain:{...sq},at:now};s.matches.push(m);
 const matched=s.matches.filter(x=>x.player===p.id&&x.round===s.round.id&&x.role===p.role);
 if(matched.length>=TARGET&&!s.wins.some(w=>w.player===p.id&&w.round===s.round.id)) {const win={id:uid(),player:p.id,round:s.round.id,roundNo:s.round.no,role:p.role,at:now};win.reward=reward(s,p,'bingo',win.id,now);s.wins.push(win);}
 return m;
}
export function submitProblems(s,token,input,now=Date.now()){
 const p=player(s,token);requestId(input.request);const prior=s.experiences.find(x=>x.player===p.id&&x.request===input.request);if(prior)return prior;
 open(s);if(!p.role)fail('Choose your role first.');
 if(!Array.isArray(input.pains)||input.pains.length!==3||new Set(input.pains).size!==3)fail('Choose exactly three different problems.');
 const allowed=personaPains(p.role);const pains=input.pains.map(id=>allowed.find(p=>p.id===id));if(pains.some(p=>!p))fail('Choose problems from your role.');
 if(p.directComplete)return s.experiences.find(e=>e.id===p.directComplete);
 const entry={id:uid(),request:input.request,player:p.id,role:p.role,pains:pains.map(p=>({...p})),at:now};
 entry.reward=reward(s,p,'three-problems',entry.id,now);s.experiences.push(entry);p.directComplete=entry.id;return entry;
}
export function roomNote(s,token,input,now=Date.now()){const p=player(s,token);open(s);requestId(input.request);const prior=s.notes.find(n=>n.player===p.id&&n.request===input.request);if(prior)return prior;const text=String(input.text||'').trim().replace(/\s+/g,' ');if(text.length<8||text.length>180)fail('Use 8 to 180 characters.');if(s.notes.filter(n=>n.player===p.id).length>=3)fail('You have shared three notes. Thank you.');const n={id:uid(),request:input.request,player:p.id,text,status:'pending',at:now};s.notes.push(n);return n;}
export function roomSnapshot(s,token,now=Date.now()){
 const p=s.players.find(p=>p.token===token),calls=calledFor(s,now),last=calls.at(-1),round=s.round,completed=p&&s.experiences.find(e=>e.id===p.directComplete),kit=p&&s.kits.find(k=>k.player===p.id&&!k.revoked);
 const matches=p?s.matches.filter(m=>m.player===p.id&&m.round===round?.id&&m.role===p.role):[];
 const wins=p?s.wins.filter(w=>w.player===p.id):[];
 return {version:s.version,serverTime:now,settings:s.settings,stockAvailable:available(s),community:{players:s.players.length,wins:s.wins.length,experiences:s.experiences.length},
  round:round?{id:round.id,no:round.no,startedAt:round.startedAt,endsAt:round.startedAt+ROUND_MS,nextCallAt:round.startedAt+calls.length*CALL_MS,totalCalls:round.calls.length,calledCount:calls.length,current:last?{role:last.role,roleLabel:getPersona(last.role).label,pain:publicPain(last.pain)}:null,recent:calls.slice(-6).reverse().map(c=>({role:c.role,roleLabel:getPersona(c.role).label,pain:publicPain(c.pain)}))}:null,
  recentWins:s.wins.slice(-5).reverse().map(w=>({id:w.id,role:getPersona(w.role).label,roundNo:w.roundNo,at:w.at})),callouts:s.notes.filter(n=>n.status==='approved').slice(-6).map(n=>({id:n.id,text:n.text})),
  me:p?{name:p.name,role:isActivePersona(p.role)?p.role:null,path:p.path,card:round&&p.role&&round.cards[p.role]?round.cards[p.role].map(sq=>({...publicPain(sq),called:calls.some(c=>c.role===p.role&&c.pain.id===sq.id),matched:matches.some(m=>m.pain.id===sq.id)})):[],matches:matches.length,wins:wins.map(w=>({id:w.id,roundNo:w.roundNo,round:w.round,at:w.at,reward:w.reward})),kit:kit?{code:kit.code,handed:kit.handed,reason:kit.reason}:null,completed:completed?{pains:completed.pains.map(publicPain),reward:completed.reward}:null,notes:s.notes.filter(n=>n.player===p.id).map(({id,text,status})=>({id,text,status}))}:null};
}
export function roomAdmin(s,now=Date.now()){
 return {...roomSnapshot(s,undefined,now),attendees:s.players.map(p=>({id:p.id,name:p.name,company:p.company,role:getPersona(p.role)?.label||'Choosing a role',path:p.path,contact:p.contact,type:p.type,joined:p.joined,matches:s.matches.filter(m=>m.player===p.id).length,reported:s.experiences.filter(e=>e.player===p.id).flatMap(e=>e.pains.map(publicPain))})),kits:s.kits.filter(k=>!k.revoked).map(k=>({...k,name:s.players.find(p=>p.id===k.player)?.name,company:s.players.find(p=>p.id===k.player)?.company})),notes:s.notes.map(n=>({...n,name:s.players.find(p=>p.id===n.player)?.name,company:s.players.find(p=>p.id===n.player)?.company}))};
}
export function roomAdminAction(s,input,now=Date.now()){
 const q=s.settings;
 switch(input.action){
  case 'start':case 'skip':advanceRoom(s,now);return;
  case 'pause': if(q.ended)fail('Resume the event first.');if(!q.paused){q.paused=true;q.pausedAt=now;}else{if(s.round)s.round.startedAt+=now-q.pausedAt;q.paused=false;q.pausedAt=null;q.nextRoundAt=null;q.announcement='';}return;
  case 'end':q.ended=true;q.paused=true;q.pausedAt=now;q.nextRoundAt=null;return;
  case 'resume':advanceRoom(s,now);return;
  case 'announce':if(!Number.isFinite(input.startAt)||input.startAt<now+1000||input.startAt>now+7*86400000)fail('Choose a future start time within seven days.');if(String(input.message||'').length>120)fail('Keep the announcement under 120 characters.');if(!q.paused)q.pausedAt=now;q.paused=true;q.ended=false;q.nextRoundAt=input.startAt;q.announcement=String(input.message||'Next round after the panel.').trim();return;
  case 'cancel_announcement':q.nextRoundAt=null;q.announcement='';return;
  case 'settings':if(input.kitLimit!==null&&(!Number.isInteger(input.kitLimit)||input.kitLimit<0||input.kitLimit>5000))fail('Enter a kit count from 0 to 5000, or leave blank.');q.kitLimit=input.kitLimit;return;
  case 'hand':{const k=s.kits.find(k=>k.code===input.code&&!k.revoked);if(!k)fail('Prize code not found.');k.handed ||= now;return;}
  case 'moderate':{const n=s.notes.find(n=>n.id===input.id);if(!n||!['approved','hidden'].includes(input.status))fail('Choose an existing note and display status.');n.status=input.status;return;}
  case 'next_call':if(q.paused||q.ended||!s.round)fail('Start or resume Bingo first.');s.round.startedAt-=CALL_MS;tickRoom(s,now);return;
  default:fail('Unknown action.');
 }
}
export function roomCsv(s){
 const rows=[['Entry type','Timestamp (UTC)','Name','Company','Contact type','Contact','Selected role','Round','Problem','Full problem','Prize code','Kit handed over','Consent timestamp']];
 const row=(p,type,time,role,round='',pain=null)=>{const k=s.kits.find(k=>k.player===p.id&&!k.revoked);return [type,new Date(time).toISOString(),p.name,p.company,p.type,p.contact,getPersona(role)?.label||'',round,pain?.short||'',pain?.full||'',k?.code||'',k?.handed?'Y':'N',p.consentAt];};
 for(const p of s.players)rows.push(row(p,'registration',p.joined,p.role));
 for(const m of s.matches)rows.push(row(s.players.find(p=>p.id===m.player),'bingo match — not a reported problem',m.at,m.role,m.roundNo,m.pain));
 for(const e of s.experiences)for(const pain of e.pains)rows.push(row(s.players.find(p=>p.id===e.player),'reported problem',e.at,e.role,'',pain));
 for(const n of s.notes)rows.push(row(s.players.find(p=>p.id===n.player),'written note: '+n.status,n.at,s.players.find(p=>p.id===n.player).role,'',{full:n.text}));
 return '\uFEFF'+rows.map(row=>row.map(v=>'"'+String(v).replace(/^[=+@\-\t\r]/,"'$&").replaceAll('"','""')+'"').join(',')).join('\r\n');
}
