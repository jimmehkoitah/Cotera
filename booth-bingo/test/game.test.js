import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  LINES, squareName, newlyCompletedLines, lineProgress, completedLines, decideKit,
  cooldownRemaining, nextSetIndex, shuffle, redemptionCode, normalizeContact, validateRegistration,
} from '../server/game.js';

test('square names map B1 top-left to O5 bottom-right', () => {
  assert.equal(squareName(0), 'B1');
  assert.equal(squareName(4), 'O1');
  assert.equal(squareName(12), 'N3');
  assert.equal(squareName(20), 'B5');
  assert.equal(squareName(24), 'O5');
});

test('there are exactly 12 distinct lines of 5 cells', () => {
  assert.equal(LINES.length, 12);
  const keys = new Set(LINES.map((l) => l.cells.slice().sort((a, b) => a - b).join(',')));
  assert.equal(keys.size, 12);
  for (const l of LINES) assert.equal(new Set(l.cells).size, 5);
});

test('completing a row reports only that row', () => {
  const before = new Set([0, 1, 2, 3]);
  assert.deepEqual(newlyCompletedLines(before, 4), ['row-1']);
});

test('the center square can complete four lines at once', () => {
  const everythingButCenter = new Set([...Array(25).keys()].filter((i) => i !== 12));
  assert.deepEqual(newlyCompletedLines(everythingButCenter, 12).sort(), ['col-N', 'diag-down', 'diag-up', 'row-3'].sort());
});

test('a claim that completes nothing reports nothing; an already-claimed square reports nothing', () => {
  assert.deepEqual(newlyCompletedLines(new Set([0, 1]), 2), []);
  assert.deepEqual(newlyCompletedLines(new Set([0, 1, 2, 3, 4]), 4), []);
});

test('line progress puts the hottest open lines first and complete lines last', () => {
  const claimed = new Set([0, 1, 2, 3, 4, 5, 10, 15]); // row 1 complete, B column 4/5
  const p = lineProgress(claimed);
  assert.equal(p[0].key, 'col-B');
  assert.equal(p[0].count, 4);
  assert.equal(p[p.length - 1].count, 5);
  assert.deepEqual(completedLines(claimed), ['row-1']);
});

test('first five beats a line win and does not use the board cap', () => {
  const r = decideKit({ isPlayersFirstClaim: true, firstFiveAwarded: 4, firstFiveLimit: 5, newLines: ['row-1'], boardLineKits: 0, lineCap: 3, playerHasLineKit: false });
  assert.deepEqual(r, { kit: 'first_five', outcome: 'first_five_kit' });
});

test('the sixth first-time player gets no first-five kit', () => {
  const r = decideKit({ isPlayersFirstClaim: true, firstFiveAwarded: 5, firstFiveLimit: 5, newLines: [], boardLineKits: 0, lineCap: 3, playerHasLineKit: false });
  assert.deepEqual(r, { kit: null, outcome: 'none' });
});

test('a returning player is not a first-five winner even if slots remain', () => {
  const r = decideKit({ isPlayersFirstClaim: false, firstFiveAwarded: 2, firstFiveLimit: 5, newLines: [], boardLineKits: 0, lineCap: 3, playerHasLineKit: false });
  assert.equal(r.kit, null);
});

test('line wins stop at the board cap', () => {
  const base = { isPlayersFirstClaim: false, firstFiveAwarded: 5, firstFiveLimit: 5, newLines: ['row-2'], lineCap: 3, playerHasLineKit: false };
  assert.equal(decideKit({ ...base, boardLineKits: 2 }).kit, 'line_win');
  assert.deepEqual(decideKit({ ...base, boardLineKits: 3 }), { kit: null, outcome: 'line_no_kit' });
});

test('one line kit per person', () => {
  const r = decideKit({ isPlayersFirstClaim: false, firstFiveAwarded: 5, firstFiveLimit: 5, newLines: ['row-2', 'col-B'], boardLineKits: 0, lineCap: 3, playerHasLineKit: true });
  assert.deepEqual(r, { kit: null, outcome: 'line_no_kit' });
});

test('cooldown counts down and zero minutes means no wait', () => {
  const t0 = new Date('2026-10-05T23:00:00Z');
  assert.equal(cooldownRemaining(t0, new Date('2026-10-05T23:05:00Z'), 10), 300);
  assert.equal(cooldownRemaining(t0, new Date('2026-10-05T23:10:00Z'), 10), 0);
  assert.equal(cooldownRemaining(t0, new Date('2026-10-05T23:00:01Z'), 0), 0);
  assert.equal(cooldownRemaining(null, new Date(), 10), 0);
});

test('next set cycles 1,2,3,4,1 and never repeats the finished set', () => {
  assert.deepEqual([0, 1, 2, 3].map((i) => nextSetIndex(i, 4)), [1, 2, 3, 0]);
  for (let i = 0; i < 4; i++) assert.notEqual(nextSetIndex(i, 4), i);
  assert.equal(nextSetIndex(0, 1), 0);
});

test('shuffle keeps every item', () => {
  const items = [...Array(25).keys()];
  assert.deepEqual(shuffle(items).sort((a, b) => a - b), items);
});

test('redemption codes are 4 unambiguous characters', () => {
  for (let i = 0; i < 500; i++) assert.match(redemptionCode(), /^[ACDEFGHJKMNPQRTUVWXY34679]{4}$/);
});

test('contacts normalize so the same person matches', () => {
  assert.equal(normalizeContact('email', '  Jane@Acme.COM ').norm, 'jane@acme.com');
  assert.equal(normalizeContact('phone', '(415) 555-0134').norm, '14155550134');
  assert.equal(normalizeContact('phone', '+1 415 555 0134').norm, '14155550134');
  assert.equal(normalizeContact('phone', '+44 20 7946 0958').norm, '442079460958');
  assert.equal(normalizeContact('linkedin', 'https://www.linkedin.com/in/Jane-Doe-123/').norm, 'jane-doe-123');
  assert.equal(normalizeContact('linkedin', 'linkedin.com/in/jane-doe-123?utm=x').norm, 'jane-doe-123');
  assert.equal(normalizeContact('linkedin', '@jane-doe-123').norm, 'jane-doe-123');
  assert.equal(normalizeContact('linkedin', 'https://www.linkedin.com/in/Jane-Doe-123/').display, 'linkedin.com/in/Jane-Doe-123');
});

test('bad contacts are rejected with a friendly message', () => {
  assert.equal(normalizeContact('email', 'jane@acme').ok, false);
  assert.equal(normalizeContact('phone', '123').ok, false);
  assert.equal(normalizeContact('linkedin', 'https://linkedin.com/company/acme').ok, false);
  assert.equal(normalizeContact('fax', '555').ok, false);
  assert.equal(normalizeContact('email', '').ok, false);
});

test('registration requires name, company, and a contact, and cleans text', () => {
  assert.equal(validateRegistration({ name: '', company: 'Acme', contactType: 'email', contactValue: 'a@b.co' }).ok, false);
  assert.equal(validateRegistration({ name: 'Jane', company: ' ', contactType: 'email', contactValue: 'a@b.co' }).ok, false);
  const r = validateRegistration({ name: '  Jane\n  Doe ', company: 'Acme\u0000 Inc', contactType: 'email', contactValue: 'A@B.co' });
  assert.equal(r.ok, true);
  assert.equal(r.name, 'Jane Doe');
  assert.equal(r.company, 'Acme Inc');
  assert.equal(r.contactNorm, 'a@b.co');
});
