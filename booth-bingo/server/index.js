import http from 'node:http';
import crypto from 'node:crypto';
import path from 'node:path';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import express from 'express';
import cookieParser from 'cookie-parser';
import { Server } from 'socket.io';
import QRCode from 'qrcode';
import { createDb, GameError } from './db.js';
import { validateRegistration } from './game.js';
import { toCsv } from './export.js';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const PORT = Number(process.env.PORT || 3000);
const ON_RENDER = !!process.env.RENDER;
const ADMIN_PIN = process.env.ADMIN_PIN || (ON_RENDER ? '' : '1234');
const COOKIE_SECRET = process.env.COOKIE_SECRET || crypto.randomBytes(32).toString('hex');
const PUBLIC_URL = (process.env.PUBLIC_URL || process.env.RENDER_EXTERNAL_URL || '').replace(/\/+$/, '');
// Multiplies every rate limit. Raise it if a venue network funnels everyone through one IP harder than expected.
const RATE_LIMIT_SCALE = Math.max(1, Number(process.env.RATE_LIMIT_SCALE || 1));

if (!ADMIN_PIN) console.error('ADMIN_PIN is not set: admin page is disabled until it is.');
else if (!process.env.ADMIN_PIN) console.warn('Using the default dev admin PIN 1234.');

const painPoints = JSON.parse(readFileSync(path.join(ROOT, 'pain-points.json'), 'utf8'));
const db = createDb({
  connectionString: process.env.DATABASE_URL || 'postgres://postgres@localhost:5433/bingo',
  ssl: process.env.PGSSL === 'true' ? { rejectUnauthorized: false } : false,
  painPoints,
});

const app = express();
app.set('trust proxy', 1);
app.disable('x-powered-by');
app.use(express.json({ limit: '10kb' }));
app.use(cookieParser(COOKIE_SECRET));
app.use((req, res, next) => {
  res.set({
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'same-origin',
    'X-Frame-Options': 'DENY',
    'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self' ws: wss:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
  });
  next();
});

// ---------- tiny in-memory rate limiter (generous: venue Wi-Fi puts many people behind one IP) ----------
const buckets = new Map();
function limit(key, max, windowMs) {
  const now = Date.now();
  const b = buckets.get(key);
  if (!b || now > b.reset) { buckets.set(key, { n: 1, reset: now + windowMs }); return true; }
  b.n += 1;
  return b.n <= max * RATE_LIMIT_SCALE;
}
setInterval(() => { const now = Date.now(); for (const [k, b] of buckets) if (now > b.reset) buckets.delete(k); }, 60_000).unref();
const rateLimit = (name, max, windowMs = 60_000) => (req, res, next) =>
  limit(`${name}:${req.ip}`, max, windowMs) ? next() : res.status(429).json({ error: 'slow_down', message: 'Too many tries. Give it a few seconds.' });

// ---------- auth helpers ----------
const playerToken = (req) => req.get('x-player-token') || req.signedCookies?.bb_player || null;

function sign(value) {
  return crypto.createHmac('sha256', COOKIE_SECRET).update(value).digest('base64url');
}
function adminCookieValue() {
  const exp = String(Date.now() + 14 * 3600_000);
  return `${exp}.${sign(`admin.${exp}`)}`;
}
function isAdminCookie(v) {
  if (!v || typeof v !== 'string') return false;
  const [exp, mac] = v.split('.');
  if (!exp || !mac || Number(exp) < Date.now()) return false;
  const expected = sign(`admin.${exp}`);
  return mac.length === expected.length && crypto.timingSafeEqual(Buffer.from(mac), Buffer.from(expected));
}
function pinMatches(pin) {
  if (!ADMIN_PIN || typeof pin !== 'string') return false;
  const a = crypto.createHash('sha256').update(pin).digest();
  const b = crypto.createHash('sha256').update(ADMIN_PIN).digest();
  return crypto.timingSafeEqual(a, b);
}
const requireAdmin = (req, res, next) => (isAdminCookie(req.cookies?.bb_admin) ? next() : res.status(401).json({ error: 'admin_only', message: 'Enter the admin PIN.' }));

const wrap = (fn) => async (req, res) => {
  try {
    await fn(req, res);
  } catch (err) {
    if (err instanceof GameError) {
      res.status(err.code === 'unknown_player' ? 401 : 409).json({ error: err.code, message: err.message, cooldownSeconds: err.cooldownSeconds });
    } else {
      console.error(err);
      res.status(500).json({ error: 'server', message: 'Something went wrong. Try again.' });
    }
  }
};

// ---------- live updates ----------
const server = http.createServer(app);
const io = new Server(server, { serveClient: true, pingInterval: 10_000, pingTimeout: 8_000 });

let broadcastQueued = false;
function broadcast() {
  if (broadcastQueued) return;
  broadcastQueued = true;
  setImmediate(async () => {
    broadcastQueued = false;
    try {
      io.to('public').emit('state', await db.publicState());
      io.to('admin').emit('admin:changed');
    } catch (err) { console.error('broadcast failed', err); }
  });
}
async function pushPlayer(playerId) {
  const token = await db.tokenByPlayerId(playerId);
  if (token) io.to(`player:${playerId}`).emit('me', await db.playerState(token));
}

io.on('connection', async (socket) => {
  try {
    socket.join('public');
    socket.emit('state', await db.publicState());
    const cookies = parseCookieHeader(socket.handshake.headers.cookie);
    if (socket.handshake.auth?.role === 'admin' && isAdminCookie(cookies.bb_admin)) socket.join('admin');
    const token = socket.handshake.auth?.token || cookieParser.signedCookie(cookies.bb_player || '', COOKIE_SECRET) || null;
    if (token) {
      const id = await db.playerIdByToken(token);
      if (id) {
        socket.join(`player:${id}`);
        socket.emit('me', await db.playerState(token));
      }
    }
  } catch (err) { console.error('socket connect failed', err); }
});

function parseCookieHeader(header = '') {
  const out = {};
  for (const part of header.split(';')) {
    const i = part.indexOf('=');
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

// ---------- pages ----------
const page = (file) => (req, res) => res.set('Cache-Control', 'no-cache').sendFile(path.join(ROOT, 'public', file));
app.get('/', page('play.html'));
app.get('/display', page('display.html'));
app.get('/admin', page('admin.html'));
app.get('/print', page('print.html'));
app.use(express.static(path.join(ROOT, 'public'), { index: false, setHeaders: (res) => res.set('Cache-Control', 'no-cache') }));

app.get('/healthz', wrap(async (req, res) => {
  await db.pool.query('SELECT 1');
  res.json({ ok: true });
}));

function publicUrl(req) {
  return PUBLIC_URL || `${req.protocol}://${req.get('host')}`;
}
app.get('/api/config', (req, res) => {
  const url = publicUrl(req);
  res.json({ url, shortUrl: url.replace(/^https?:\/\//, '') });
});
app.get('/qr.svg', wrap(async (req, res) => {
  const svg = await QRCode.toString(publicUrl(req), { type: 'svg', margin: 1, errorCorrectionLevel: 'M', color: { dark: '#2b1a12', light: '#ffffff' } });
  res.set({ 'Content-Type': 'image/svg+xml', 'Cache-Control': 'no-cache' }).send(svg);
}));

// ---------- player API ----------
app.get('/api/state', wrap(async (req, res) => res.json(await db.publicState())));

app.post('/api/register', rateLimit('register', 120), wrap(async (req, res) => {
  const v = validateRegistration(req.body);
  if (!v.ok) return res.status(400).json({ error: 'invalid', message: v.error });
  const p = await db.register(v);
  res.cookie('bb_player', p.token, { signed: true, httpOnly: true, sameSite: 'lax', secure: req.secure, maxAge: 30 * 86400_000 });
  res.json({ token: p.token, me: await db.playerState(p.token) });
  io.to('admin').emit('admin:changed');
}));

app.get('/api/me', wrap(async (req, res) => {
  const me = await db.playerState(playerToken(req));
  res.json(me ? { signedIn: true, ...me } : { signedIn: false });
}));

app.post('/api/claim', rateLimit('claim', 300), wrap(async (req, res) => {
  const token = playerToken(req);
  if (!token || !limit(`claim-token:${token}`, 20, 60_000)) return res.status(429).json({ error: 'slow_down', message: 'Easy there! Give it a second.' });
  const result = await db.claim(token, Number(req.body?.idx));
  res.json({ result, me: await db.playerState(token) });
  broadcast();
}));

app.post('/api/rate', rateLimit('rate', 300), wrap(async (req, res) => {
  await db.rate(playerToken(req), Number(req.body?.claimId), req.body?.rating);
  res.json({ ok: true });
  io.to('admin').emit('admin:changed');
}));

// ---------- admin API ----------
app.post('/api/admin/login', rateLimit('admin-login', 10), (req, res) => {
  if (!pinMatches(req.body?.pin)) return res.status(401).json({ error: 'bad_pin', message: 'Wrong PIN.' });
  res.cookie('bb_admin', adminCookieValue(), { httpOnly: true, sameSite: 'strict', secure: req.secure, maxAge: 14 * 3600_000 });
  res.json({ ok: true });
});
app.get('/api/admin/session', (req, res) => res.json({ admin: isAdminCookie(req.cookies?.bb_admin) }));
app.post('/api/admin/logout', (req, res) => { res.clearCookie('bb_admin'); res.json({ ok: true }); });
app.get('/api/admin/state', requireAdmin, wrap(async (req, res) => res.json(await db.adminState())));

app.post('/api/admin/undo', requireAdmin, wrap(async (req, res) => {
  const r = await db.undoClaim(Number(req.body?.claimId));
  res.json({ ok: true, ...r });
  broadcast();
  pushPlayer(r.playerId).catch(() => {});
}));
app.post('/api/admin/kit', requireAdmin, wrap(async (req, res) => {
  const r = await db.setHandedOver(Number(req.body?.kitId), !!req.body?.handed);
  res.json({ ok: true });
  io.to('admin').emit('admin:changed');
  pushPlayer(r.playerId).catch(() => {});
}));
app.post('/api/admin/settings', requireAdmin, wrap(async (req, res) => {
  const { cooldownMin, lineCap, paused, ended } = req.body || {};
  await db.updateSettings({ cooldownMin, lineCap, paused, ended });
  res.json({ ok: true });
  broadcast();
}));
app.post('/api/admin/skip', requireAdmin, wrap(async (req, res) => {
  await db.skipToNextSet();
  res.json({ ok: true });
  broadcast();
}));
app.post('/api/admin/wipe', requireAdmin, wrap(async (req, res) => {
  if (req.body?.confirm !== 'RESET') return res.status(400).json({ error: 'confirm', message: 'Type RESET to confirm.' });
  await db.wipeAll();
  res.json({ ok: true });
  // Player ids restart after a wipe, so detach every socket from its old player room first.
  for (const room of [...io.of('/').adapter.rooms.keys()]) if (room.startsWith('player:')) io.socketsLeave(room);
  broadcast();
  io.to('public').emit('reset'); // phones drop their stored player and sign in again
}));
app.get('/api/admin/export.csv', requireAdmin, wrap(async (req, res) => {
  const stamp = new Date().toLocaleString('sv-SE', { timeZone: 'America/Los_Angeles' }).replace(/[: ]/g, '-');
  res.set({
    'Content-Type': 'text/csv; charset=utf-8',
    'Content-Disposition': `attachment; filename="cotera-bingo-leads-${stamp}.csv"`,
    'Cache-Control': 'no-store',
  });
  res.send(toCsv(await db.exportRows()));
}));

app.use((req, res) => res.status(404).json({ error: 'not_found' }));

// ---------- start ----------
for (let attempt = 1; ; attempt++) {
  try {
    await db.init();
    break;
  } catch (err) {
    console.error(`Database not ready (attempt ${attempt}): ${err.message}`);
    await new Promise((r) => setTimeout(r, Math.min(2000 * attempt, 15000)));
  }
}
server.keepAliveTimeout = 120_000;
server.headersTimeout = 125_000;
server.listen(PORT, () => console.log(`Booth bingo listening on :${PORT}`));

function shutdown() {
  console.log('Shutting down');
  io.close();
  server.close(() => db.close().finally(() => process.exit(0)));
  setTimeout(() => process.exit(0), 5000).unref();
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
