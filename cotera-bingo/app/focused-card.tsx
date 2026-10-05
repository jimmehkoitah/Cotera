'use client';
import {useEffect, useState} from 'react';
import {getPersona, matchesPersona} from '../lib/personas.mjs';

type Square = {id:string;short:string;claimed:boolean};
type Props = {board:{id:string;no:number;squares:Square[];count:number};role:string;solo:boolean;ownSquares:number[];busy:boolean;onSelect:(index:number)=>void;onChangeRole:()=>void};
const coordinate=(i:number)=>'BINGO'[i%5]+(Math.floor(i/5)+1);
// Reading order crosses rows and columns so a page is not itself a winning line.
const readingOrder=[0,14,7,22,3,10,17,4,12,24,16,1,20,8,6,23,18,11,2,15,13,5,21,19,9];
export default function FocusedCard({board,role,solo,ownSquares,busy,onSelect,onChangeRole}:Props){
 const [page,setPage]=useState(0),[all,setAll]=useState(false);
 useEffect(()=>{setPage(0);setAll(false);},[board.id,role]);
 const indices=readingOrder.filter(i=>solo||all||matchesPersona(role,board.squares[i].id));
 const pages=Math.max(1,Math.ceil(indices.length/6));
 const current=Math.min(page,pages-1),visible=indices.slice(current*6,current*6+6);
 return <section className="focused-card" aria-label="Your role's problems">
  <div className="role-strip"><span>{getPersona(role)?.label||'Your work'}</span><button onClick={onChangeRole} disabled={busy}>Change role</button></div>
  <div className="focus-heading"><span className="eyebrow">ROUND {board.no} · {solo?'YOUR OWN CARD':'SHARED BOARD'}</span><h2>Sound like your week?</h2><p>Tap a problem to read more and mark it.</p></div>
  {!solo&&<div className="reading-controls"><button aria-pressed={!all} onClick={()=>{setAll(false);setPage(0);}}>For your role</button><button aria-pressed={all} onClick={()=>{setAll(true);setPage(0);}}>All problems</button></div>}
  <div className="focus-problems">{visible.map(i=>{const sq=board.squares[i],own=ownSquares.includes(i);return <button key={board.id+'-'+i} className={'focus-problem'+(sq.claimed?' marked':'')} disabled={busy} onClick={()=>onSelect(i)} aria-label={`${coordinate(i)}: ${sq.short}${sq.claimed?(own?' — marked by you':' — taken'):''}`}><span className="focus-coordinate">{coordinate(i)}</span><span className="focus-copy">{sq.short}</span><span className="focus-state" aria-hidden="true">{sq.claimed?(own?'✓':'Taken'):'+'}</span></button>;})}</div>
  {!indices.length&&<p className="empty-role">This shared round has no problems for your role. Browse all problems or add your own below.</p>}
  <nav className="focus-pagination" aria-label="Problem pages"><button disabled={current===0} onClick={()=>setPage(current-1)}>Previous</button><span aria-live="polite">{indices.length?current*6+1:0}–{Math.min((current+1)*6,indices.length)} of {indices.length}</span><button disabled={current===pages-1} onClick={()=>setPage(current+1)}>Next six</button></nav>
  <details className="card-progress"><summary><span>{solo?'Your bingo card':'The shared bingo board'}</span><span>{board.count}/25 marked</span></summary><p>Five in a row, column or diagonal makes bingo. Tap a space to read its problem.</p><div className="mini-letters" aria-hidden="true">{'BINGO'.split('').map(l=><span key={l}>{l}</span>)}</div><div className="mini-board">{board.squares.map((sq,i)=><button key={i} disabled={busy} className={sq.claimed?'marked':''} onClick={()=>onSelect(i)} aria-label={`${coordinate(i)}: ${sq.short}${sq.claimed?' — marked':''}`}><span>{coordinate(i)}</span>{sq.claimed&&<span aria-hidden="true">✓</span>}</button>)}</div></details>
 </section>;
}
