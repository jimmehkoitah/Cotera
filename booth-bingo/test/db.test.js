// Integration tests against a real Postgres. Set TEST_DATABASE_URL (defaults to the local test cluster).
import { test, before, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createDb } from '../server/db.js';
import { LINES } from '../server/game.js';

const painPoints = JSON.parse(readFileSync(new URL('../pain-points.json', import.meta.url)));
const db = createDb({
  connectionString: process.env.TEST_DATABASE_URL || 'postgres://postgres@localhost:5433/bingo_test',
  painPoints,
});

let n = 0;
async function player(name = `P${++n}`) {
  return db.register({ name, company: `${name} Co`, contactType: 'email', contactValue: `${name}@x.co`, contactNorm: `${name.toLowerCase()}@x.co` });
}
async function claimErr(token, idx) {
  try { await db.claim(token, idx); return null; } catch (e) { return e.code; }
}

before(async () => { await db.init(); });
after(async () => { await db.close(); });
beforeEach(async () => {
  await db.wipeAll();
  await db.updateSettings({ cooldownMin: 0, lineCap: 3, paused: false, ended: false });
});

test('a fresh game has board 1 with set 1 and 25 open squares', async () => {
  const s = await db.publicState();
  assert.equal(s.boardNo, 1);
  assert.equal(s.setNo, 1);
  assert.equal(s.squares.length, 25);
  assert.equal(s.claimedCount, 0);
  const ids = new Set(painPoints.sets[0].items.map((i) => i.short));
  for (const q of s.squares) assert.ok(ids.has(q.short));
});

test('registering twice with the same contact returns the same player', async () => {
  const a = await db.register({ name: 'Jane', company: 'Acme', contactType: 'email', contactValue: 'jane@acme.com', contactNorm: 'jane@acme.com' });
  const b = await db.register({ name: 'Jane D', company: 'Acme Inc', contactType: 'email', contactValue: 'JANE@acme.com', contactNorm: 'jane@acme.com' });
  assert.equal(a.token, b.token);
  assert.equal(b.name, 'Jane D');
});

test('20 people claiming the same square at the same instant: exactly one wins', async () => {
  const players = await Promise.all([...Array(20)].map(() => player()));
  const results = await Promise.allSettled(players.map((p) => db.claim(p.token, 7)));
  const ok = results.filter((r) => r.status === 'fulfilled');
  const taken = results.filter((r) => r.status === 'rejected' && r.reason.code === 'taken');
  assert.equal(ok.length, 1);
  assert.equal(taken.length, 19);
  assert.equal((await db.publicState()).claimedCount, 1);
});

test('cooldown blocks a second claim until it passes', async () => {
  await db.updateSettings({ cooldownMin: 10 });
  const p = await player();
  await db.claim(p.token, 0);
  try { await db.claim(p.token, 1); assert.fail('should be blocked'); } catch (e) {
    assert.equal(e.code, 'cooldown');
    assert.ok(e.cooldownSeconds > 590 && e.cooldownSeconds <= 600);
  }
  assert.ok((await db.playerState(p.token)).cooldownSeconds > 590);
  await db.updateSettings({ cooldownMin: 0 });
  await db.claim(p.token, 1);
});

test('the first five distinct players get a kit; the sixth does not; repeat claims do not count', async () => {
  const ps = await Promise.all([...Array(6)].map(() => player()));
  const first = await db.claim(ps[0].token, 0);
  assert.equal(first.kit.reason, 'first_five');
  assert.equal(first.kit.claimNo, 1);
  const again = await db.claim(ps[0].token, 1); // same player again, not a new first-five
  assert.equal(again.kit, null);
  const rest = [];
  for (let i = 1; i < 6; i++) rest.push(await db.claim(ps[i].token, 10 + i));
  assert.deepEqual(rest.map((r) => r.kit?.claimNo ?? null), [2, 3, 4, 5, null]);
});

// Fill 5 first-five claims on cells that never complete a line, so later tests start "clean".
async function burnFirstFive() {
  const cells = [1, 7, 13, 19, 21]; // no two together complete anything with few claims
  for (const c of cells) await db.claim((await player()).token, c);
}

test('a completed line wins a kit; only 3 line kits per board; 4th line celebrates without a kit', async () => {
  await burnFirstFive();
  const outcomes = [];
  // Complete rows 1..4 using a new player for the final square each time.
  for (const row of [0, 1, 2, 3]) {
    const cells = [0, 1, 2, 3, 4].map((c) => row * 5 + c);
    const s = await db.publicState();
    const open = cells.filter((i) => !s.squares[i].claimed);
    for (const i of open.slice(0, -1)) await db.claim((await player()).token, i);
    const finisher = await player();
    const r = await db.claim(finisher.token, open[open.length - 1]);
    outcomes.push(r.outcome);
    assert.ok(r.lines.includes(`Row ${row + 1}`));
  }
  assert.deepEqual(outcomes, ['line_kit', 'line_kit', 'line_kit', 'line_no_kit']);
  const admin = await db.adminState();
  assert.equal(admin.board.lineKits, 3);
});

test('one line kit per person, even across lines', async () => {
  await db.updateSettings({ lineCap: 12 }); // cap out of the way so only the per-person rule applies
  await burnFirstFive(); // claims 1, 7, 13, 19, 21
  const lucky = await player('Lucky');
  for (const i of [0, 5, 10, 15]) await db.claim((await player()).token, i);
  const r1 = await db.claim(lucky.token, 20); // finishes B column (0, 5, 10, 15, 20)
  assert.deepEqual(r1.lines, ['B column']);
  assert.equal(r1.outcome, 'line_kit');
  for (const i of [22, 23]) await db.claim((await player()).token, i);
  const r2 = await db.claim(lucky.token, 24); // finishes Row 5 (20, 21, 22, 23, 24)
  assert.deepEqual(r2.lines, ['Row 5']);
  assert.equal(r2.outcome, 'line_no_kit');
});

test('claiming all 25 opens a fresh board with the next set, then cycles 1,2,3,4,1', async () => {
  const seen = [];
  for (let b = 0; b < 5; b++) {
    const s = await db.publicState();
    seen.push(s.setNo);
    let last;
    for (let i = 0; i < 25; i++) last = await db.claim((await player()).token, i);
    assert.equal(last.boardCompleted, true);
  }
  assert.deepEqual(seen, [1, 2, 3, 4, 1]);
  const s = await db.publicState();
  assert.equal(s.boardNo, 6);
  assert.equal(s.claimedCount, 0);
});

test('undo reopens the square, voids an unclaimed kit, frees the cap slot, and clears cooldown', async () => {
  await db.updateSettings({ cooldownMin: 10 });
  const p = await player();
  const r = await db.claim(p.token, 0);
  assert.equal(r.kit.reason, 'first_five');
  assert.ok((await db.playerState(p.token)).cooldownSeconds > 0);
  const u = await db.undoClaim(r.claimId);
  assert.equal(u.kitVoided, true);
  const s = await db.publicState();
  assert.equal(s.squares[0].claimed, false);
  const ps = await db.playerState(p.token);
  assert.equal(ps.cooldownSeconds, 0);
  assert.equal(ps.kits.length, 0);
  // The freed first-five slot goes to the next first claim.
  const again = await db.claim(p.token, 3);
  assert.equal(again.kit.reason, 'first_five');
  assert.equal(again.kit.claimNo, 1);
});

test('a handed-over kit survives an undo', async () => {
  const p = await player();
  const r = await db.claim(p.token, 0);
  const st = await db.playerState(p.token);
  await db.setHandedOver(st.kits[0].id, true);
  const u = await db.undoClaim(r.claimId);
  assert.equal(u.kitVoided, false);
  assert.equal((await db.playerState(p.token)).kits[0].handedOver, true);
});

test('paused and ended games reject claims', async () => {
  const p = await player();
  await db.updateSettings({ paused: true });
  assert.equal(await claimErr(p.token, 0), 'paused');
  await db.updateSettings({ paused: false, ended: true });
  assert.equal(await claimErr(p.token, 0), 'ended');
});

test('ratings are stored only on the player’s own claim', async () => {
  const a = await player();
  const b = await player();
  const r = await db.claim(a.token, 0);
  await db.rate(a.token, r.claimId, 'big');
  await assert.rejects(db.rate(b.token, r.claimId, 'somewhat'), { code: 'not_found' });
  await assert.rejects(db.rate(a.token, r.claimId, 'nope'), { code: 'bad_rating' });
  const rows = await db.exportRows();
  assert.equal(rows[0].rating, 'big');
});

test('public state never contains names, companies, contacts, or tags', async () => {
  const p = await db.register({ name: 'Zelda Quux', company: 'Hyrule Systems', contactType: 'phone', contactValue: '+1 415 555 0199', contactNorm: '14155550199' });
  await db.claim(p.token, 12);
  const state = await db.publicState();
  const json = JSON.stringify(state);
  for (const leak of ['Zelda', 'Hyrule', '555', '0199']) assert.ok(!json.includes(leak), `public state leaked "${leak}"`);
  assert.deepEqual(Object.keys(state).sort(),
    ['boardNo', 'claimedCount', 'completedLines', 'cooldownMin', 'ended', 'lines', 'paused', 'setNo', 'squares', 'version']);
  for (const q of state.squares) assert.deepEqual(Object.keys(q).sort(), ['claimed', 'full', 'idx', 'name', 'short']);
});

test('long random game: invariants hold across many boards', async () => {
  await db.updateSettings({ cooldownMin: 0, lineCap: 3 });
  const ps = await Promise.all([...Array(60)].map(() => player()));
  const lineKitsByPlayer = new Map();
  let firstFive = 0;
  const perBoard = new Map();
  for (let step = 0; step < 25 * 4 + 7; step++) {
    const s = await db.publicState();
    const open = s.squares.filter((q) => !q.claimed).map((q) => q.idx);
    const idx = open[Math.floor(Math.random() * open.length)];
    const p = ps[Math.floor(Math.random() * ps.length)];
    const r = await db.claim(p.token, idx);
    if (r.kit?.reason === 'first_five') firstFive++;
    if (r.kit?.reason === 'line_win') {
      lineKitsByPlayer.set(p.token, (lineKitsByPlayer.get(p.token) || 0) + 1);
      perBoard.set(r.boardNo, (perBoard.get(r.boardNo) || 0) + 1);
    }
    // Sanity: a claim reports a line only if that line is really complete now (or the board just reset).
    if (!r.boardCompleted && r.lineKeys.length) {
      const after = await db.publicState();
      for (const key of r.lineKeys) {
        const line = LINES.find((l) => l.key === key);
        assert.ok(line.cells.every((i) => after.squares[i].claimed));
      }
    }
  }
  assert.equal(firstFive, 5);
  for (const [, v] of perBoard) assert.ok(v <= 3);
  for (const [, v] of lineKitsByPlayer) assert.equal(v, 1);
  const s = await db.publicState();
  assert.equal(s.boardNo, 5);
  assert.equal(s.claimedCount, 7);
  const rows = await db.exportRows();
  assert.equal(rows.length, 107);
});
