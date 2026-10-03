// Pure game rules. No I/O here, so everything is unit-testable.
import crypto from 'node:crypto';

export const COLS = ['B', 'I', 'N', 'G', 'O'];
export const SIZE = 25;

export function squareName(idx) {
  return COLS[idx % 5] + (Math.floor(idx / 5) + 1);
}

function buildLines() {
  const lines = [];
  for (let r = 0; r < 5; r++) {
    lines.push({ key: `row-${r + 1}`, label: `Row ${r + 1}`, cells: [0, 1, 2, 3, 4].map((c) => r * 5 + c) });
  }
  for (let c = 0; c < 5; c++) {
    lines.push({ key: `col-${COLS[c]}`, label: `${COLS[c]} column`, cells: [0, 1, 2, 3, 4].map((r) => r * 5 + c) });
  }
  lines.push({ key: 'diag-down', label: 'Diagonal ↘', cells: [0, 6, 12, 18, 24] });
  lines.push({ key: 'diag-up', label: 'Diagonal ↗', cells: [20, 16, 12, 8, 4] });
  return lines;
}

export const LINES = buildLines();
const LINE_BY_KEY = Object.fromEntries(LINES.map((l) => [l.key, l]));

export function lineLabel(key) {
  return LINE_BY_KEY[key]?.label ?? key;
}

/** Lines that become complete when `idx` is added to the already-claimed set. */
export function newlyCompletedLines(claimedBefore, idx) {
  const has = (i) => i === idx || claimedBefore.has(i);
  if (claimedBefore.has(idx)) return [];
  return LINES.filter((l) => l.cells.includes(idx) && l.cells.every(has)).map((l) => l.key);
}

/** Per-line claim counts, hottest (most claimed, not yet complete) first; complete lines last. */
export function lineProgress(claimed) {
  return LINES.map((l) => ({ key: l.key, label: l.label, count: l.cells.filter((i) => claimed.has(i)).length }))
    .sort((a, b) => {
      const ac = a.count === 5, bc = b.count === 5;
      if (ac !== bc) return ac ? 1 : -1;
      return b.count - a.count;
    });
}

export function completedLines(claimed) {
  return LINES.filter((l) => l.cells.every((i) => claimed.has(i))).map((l) => l.key);
}

/**
 * Decide what a claim earns. At most one kit per claim.
 * First five takes precedence; a first-five claim that also completes a line does not use the board's cap.
 */
export function decideKit({ isPlayersFirstClaim, firstFiveAwarded, firstFiveLimit, newLines, boardLineKits, lineCap, playerHasLineKit }) {
  if (isPlayersFirstClaim && firstFiveAwarded < firstFiveLimit) {
    return { kit: 'first_five', outcome: 'first_five_kit' };
  }
  if (newLines.length > 0) {
    if (boardLineKits < lineCap && !playerHasLineKit) return { kit: 'line_win', outcome: 'line_kit' };
    return { kit: null, outcome: 'line_no_kit' };
  }
  return { kit: null, outcome: 'none' };
}

/** Seconds a player must still wait, given their last claim time. */
export function cooldownRemaining(lastClaimAt, now, cooldownMinutes) {
  if (!lastClaimAt || cooldownMinutes <= 0) return 0;
  const ms = new Date(lastClaimAt).getTime() + cooldownMinutes * 60_000 - new Date(now).getTime();
  return ms > 0 ? Math.ceil(ms / 1000) : 0;
}

/** Next set after the one that just finished; never the same set unless there is only one. */
export function nextSetIndex(current, numSets) {
  if (numSets <= 1) return 0;
  return (current + 1) % numSets;
}

export function shuffle(items) {
  const a = items.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = crypto.randomInt(i + 1);
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// No look-alikes: drops 0/O, 1/I/L, 2/Z, 5/S, 8/B.
const CODE_ALPHABET = 'ACDEFGHJKMNPQRTUVWXY34679';
export function redemptionCode() {
  let s = '';
  for (let i = 0; i < 4; i++) s += CODE_ALPHABET[crypto.randomInt(CODE_ALPHABET.length)];
  return s;
}

export function newToken() {
  return crypto.randomBytes(24).toString('base64url');
}

function cleanText(v, max) {
  if (typeof v !== 'string') return '';
  // Strip control characters, collapse whitespace.
  return v.replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, max);
}

/** Normalize a contact so the same person can't register twice. */
export function normalizeContact(type, raw) {
  const value = cleanText(raw, 200);
  if (!value) return { ok: false, error: 'Add a way to reach you.' };
  if (type === 'email') {
    const norm = value.toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(norm)) return { ok: false, error: 'That email doesn’t look right.' };
    return { ok: true, norm, display: norm };
  }
  if (type === 'phone') {
    let digits = value.replace(/\D/g, '');
    if (!value.trim().startsWith('+') && digits.length === 10) digits = '1' + digits;
    if (digits.length < 7 || digits.length > 15) return { ok: false, error: 'That phone number doesn’t look right.' };
    return { ok: true, norm: digits, display: value };
  }
  if (type === 'linkedin') {
    let handle = null;
    const m = value.match(/linkedin\.com\/in\/([^/?#\s]+)/i);
    if (m) handle = m[1];
    else if (/^@?[A-Za-z0-9\-_.%]{3,100}$/.test(value) && !value.includes('linkedin')) handle = value.replace(/^@/, '');
    if (!handle) return { ok: false, error: 'Paste your LinkedIn profile link (linkedin.com/in/…).' };
    try { handle = decodeURIComponent(handle); } catch { /* keep raw */ }
    handle = handle.replace(/\/+$/, '');
    if (handle.length < 3) return { ok: false, error: 'Paste your LinkedIn profile link (linkedin.com/in/…).' };
    return { ok: true, norm: handle.toLowerCase(), display: `linkedin.com/in/${handle}` };
  }
  return { ok: false, error: 'Pick LinkedIn, phone, or email.' };
}

export function validateRegistration(body) {
  const name = cleanText(body?.name, 60);
  const company = cleanText(body?.company, 80);
  if (!name) return { ok: false, error: 'Add your name.' };
  if (!company) return { ok: false, error: 'Add your company.' };
  const contact = normalizeContact(body?.contactType, body?.contactValue);
  if (!contact.ok) return contact;
  return { ok: true, name, company, contactType: body.contactType, contactValue: contact.display, contactNorm: contact.norm };
}

export const RATINGS = { big: 'Big one', somewhat: 'Somewhat', playing: 'Just playing' };
