// Load simulation: N bot players claim as fast as the rules allow while M live connections watch.
// Usage: BASE=http://localhost:3100 PIN=1234 PLAYERS=60 CLAIMS=120 node test/simulate.js
// WARNING: wipes all game data on the target server, then restores cooldown 10 / cap 3.
import { io } from 'socket.io-client';

const BASE = process.env.BASE || 'http://localhost:3100';
const PIN = process.env.PIN || '1234';
const PLAYERS = Number(process.env.PLAYERS || 60);
const CLAIMS = Number(process.env.CLAIMS || 120);

async function api(path, body, headers = {}) {
  const res = await fetch(BASE + path, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: res.status, data: await res.json().catch(() => ({})), headers: res.headers };
}
const pct = (arr, p) => arr.slice().sort((a, b) => a - b)[Math.min(arr.length - 1, Math.floor(arr.length * p))];

const login = await api('/api/admin/login', { pin: PIN });
const cookie = (login.headers.get('set-cookie') || '').split(';')[0];
const admin = (p, b) => api(p, b, { Cookie: cookie });
await admin('/api/admin/wipe', { confirm: 'RESET' });
await admin('/api/admin/settings', { cooldownMin: 0, lineCap: 3, paused: false, ended: false });

// Register bots and open one live connection per bot (like phones), plus a "TV".
const tokens = [];
for (let i = 0; i < PLAYERS; i++) {
  const r = await api('/api/register', { name: `Sim ${i}`, company: `SimCo ${i % 7}`, contactType: 'email', contactValue: `sim${i}@simco.com` });
  tokens.push(r.data.token);
}
const sockets = [];
let latest = null;
const lastVersion = new Map();
const connectOne = (auth) => new Promise((resolve) => {
  const s = io(BASE, { auth, transports: ['websocket', 'polling'] });
  s.on('state', (st) => {
    if (!latest || st.version > latest.version) latest = st;
    lastVersion.set(s, Math.max(lastVersion.get(s) || 0, st.version));
  });
  s.on('connect', () => resolve(s));
  sockets.push(s);
});
await Promise.all([...tokens.map((token) => connectOne({ token })), connectOne({})]);
console.log(`${PLAYERS} players registered, ${sockets.length} live connections open`);
if (!latest) latest = (await api('/api/state')).data;

let claimed = 0;
let taken = 0;
let errors = 0;
let throttled = 0;
const latencies = [];
const outcomes = {};
async function bot(token) {
  while (claimed < CLAIMS) {
    const st = latest;
    const open = st.squares.filter((q) => !q.claimed).map((q) => q.idx);
    if (!open.length) { await new Promise((r) => setTimeout(r, 20)); continue; }
    const idx = open[Math.floor(Math.random() * open.length)];
    const t = performance.now();
    const r = await api('/api/claim', { idx }, { 'X-Player-Token': token });
    latencies.push(performance.now() - t);
    if (r.status === 200) {
      claimed++;
      outcomes[r.data.result.outcome] = (outcomes[r.data.result.outcome] || 0) + 1;
    } else if (r.data.error === 'taken') taken++;
    else if (r.status === 429) { throttled++; await new Promise((res) => setTimeout(res, 1000)); }
    else { errors++; if (errors < 5) console.log('error', r.status, r.data); }
    await new Promise((res) => setTimeout(res, Math.random() * 40));
  }
}
const t0 = performance.now();
await Promise.all(tokens.map(bot));
const secs = (performance.now() - t0) / 1000;

await new Promise((r) => setTimeout(r, 1500));
const final = (await api('/api/state')).data;
const stale = sockets.filter((s) => lastVersion.get(s) !== final.version).length;
const a = (await admin('/api/admin/state')).data;
const csv = await (await fetch(BASE + '/api/admin/export.csv', { headers: { Cookie: cookie } })).text();
const rows = csv.trim().split(/\r\n/).slice(1);
const lineKitsByBoard = {};
for (const f of a.feed) if (f.kit && f.kit.reason === 'line_win') lineKitsByBoard[f.boardNo] = (lineKitsByBoard[f.boardNo] || 0) + 1;

console.log(`claims: ${claimed} in ${secs.toFixed(1)}s, just-taken: ${taken}, throttled: ${throttled}, errors: ${errors}`);
console.log(`claim latency ms: p50 ${pct(latencies, 0.5).toFixed(0)}, p95 ${pct(latencies, 0.95).toFixed(0)}, max ${latencies.reduce((m, x) => Math.max(m, x), 0).toFixed(0)}`);
console.log('outcomes:', JSON.stringify(outcomes));
console.log(`board now #${final.boardNo} (set ${final.setNo}) with ${final.claimedCount} claimed; line kits per board:`, JSON.stringify(lineKitsByBoard));
console.log(`connections not on the final state: ${stale} of ${sockets.length}`);

const problems = [];
if (errors) problems.push(`${errors} unexpected errors`);
if (stale) problems.push(`${stale} connections missed the final state`);
if (a.stats.first_five !== 5) problems.push(`first-five kits = ${a.stats.first_five}`);
if (Object.values(lineKitsByBoard).some((n) => n > 3)) problems.push('a board exceeded 3 line kits');
if (rows.length < CLAIMS) problems.push(`CSV rows ${rows.length} < claims ${CLAIMS}`);
const expectBoard = Math.floor(a.stats.claims / 25) + 1;
if (final.boardNo !== expectBoard) problems.push(`board #${final.boardNo}, expected #${expectBoard}`);
if (final.claimedCount !== a.stats.claims % 25) problems.push('claimed count does not match total claims');

await admin('/api/admin/settings', { cooldownMin: 10, lineCap: 3 });
for (const s of sockets) s.close();
console.log(problems.length ? 'PROBLEMS:\n- ' + problems.join('\n- ') : 'SIMULATION CLEAN');
process.exit(problems.length ? 1 : 0);
