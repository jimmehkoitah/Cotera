// Database layer. Every state change that matters runs in one transaction that first locks the single
// `settings` row, so claims, kit awards, and board resets are strictly one-at-a-time and race-free.
import pg from 'pg';
import {
  SIZE, squareName, lineLabel, newlyCompletedLines, lineProgress, completedLines, decideKit,
  cooldownRemaining, nextSetIndex, shuffle, redemptionCode, newToken, RATINGS,
} from './game.js';

const SCHEMA = `
CREATE TABLE IF NOT EXISTS settings (
  id int PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  cooldown_min int NOT NULL DEFAULT 10,
  line_cap int NOT NULL DEFAULT 3,
  first_five int NOT NULL DEFAULT 5,
  paused boolean NOT NULL DEFAULT false,
  ended boolean NOT NULL DEFAULT false,
  current_board_id int,
  version bigint NOT NULL DEFAULT 0
);
INSERT INTO settings (id) VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS players (
  id serial PRIMARY KEY,
  token text NOT NULL UNIQUE,
  name text NOT NULL,
  company text NOT NULL,
  contact_type text NOT NULL,
  contact_value text NOT NULL,
  contact_norm text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (contact_type, contact_norm)
);
CREATE TABLE IF NOT EXISTS boards (
  id serial PRIMARY KEY,
  board_no int NOT NULL,
  set_index int NOT NULL,
  line_kits int NOT NULL DEFAULT 0,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  skipped boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS squares (
  board_id int NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
  idx int NOT NULL CHECK (idx BETWEEN 0 AND 24),
  pain_id text NOT NULL,
  short text NOT NULL,
  full_text text NOT NULL,
  wedge text NOT NULL,
  persona text NOT NULL,
  claim_id int,
  PRIMARY KEY (board_id, idx)
);
CREATE TABLE IF NOT EXISTS claims (
  id serial PRIMARY KEY,
  board_id int NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
  idx int NOT NULL,
  player_id int NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  lines text[] NOT NULL DEFAULT '{}',
  outcome text NOT NULL,
  rating text,
  created_at timestamptz NOT NULL DEFAULT now(),
  undone_at timestamptz
);
CREATE INDEX IF NOT EXISTS claims_player_live ON claims (player_id, created_at) WHERE undone_at IS NULL;
CREATE TABLE IF NOT EXISTS kits (
  id serial PRIMARY KEY,
  player_id int NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  claim_id int NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  reason text NOT NULL,
  code text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  handed_over_at timestamptz,
  voided_at timestamptz
);
`;

export class GameError extends Error {
  constructor(code, message, extra = {}) {
    super(message);
    this.code = code;
    Object.assign(this, extra);
  }
}

export function createDb({ connectionString, ssl = false, painPoints }) {
  const pool = new pg.Pool({
    connectionString, ssl, max: 10,
    connectionTimeoutMillis: 5000,
    statement_timeout: 5000,
    idle_in_transaction_session_timeout: 10000,
  });
  // A dropped idle connection must not crash the process.
  pool.on('error', (err) => console.error('Postgres pool error:', err.message));
  const sets = painPoints.sets.map((s) => s.items);
  const wedgeNames = painPoints.wedges;

  async function tx(fn) {
    const client = await pool.connect();
    try {
      await client.query('BEGIN');
      const settings = (await client.query('SELECT * FROM settings WHERE id = 1 FOR UPDATE')).rows[0];
      const now = (await client.query('SELECT now() AS now')).rows[0].now;
      const result = await fn(client, settings, now);
      await client.query('COMMIT');
      return result;
    } catch (err) {
      await client.query('ROLLBACK').catch(() => {});
      throw err;
    } finally {
      client.release();
    }
  }

  async function bumpVersion(client) {
    await client.query('UPDATE settings SET version = version + 1 WHERE id = 1');
  }

  async function openBoard(client, setIndex) {
    const no = (await client.query('SELECT COALESCE(MAX(board_no), 0) + 1 AS n FROM boards')).rows[0].n;
    const board = (await client.query(
      'INSERT INTO boards (board_no, set_index) VALUES ($1, $2) RETURNING *', [no, setIndex])).rows[0];
    const items = shuffle(sets[setIndex]);
    const values = [];
    const params = [];
    items.forEach((it, idx) => {
      const b = params.length;
      values.push(`($${b + 1}, $${b + 2}, $${b + 3}, $${b + 4}, $${b + 5}, $${b + 6}, $${b + 7})`);
      params.push(board.id, idx, it.id, it.short, it.full, it.wedge, it.persona);
    });
    await client.query(
      `INSERT INTO squares (board_id, idx, pain_id, short, full_text, wedge, persona) VALUES ${values.join(',')}`, params);
    await client.query('UPDATE settings SET current_board_id = $1 WHERE id = 1', [board.id]);
    return board;
  }

  async function init() {
    await pool.query(SCHEMA);
    await tx(async (client, settings) => {
      if (!settings.current_board_id) {
        await openBoard(client, 0);
        await bumpVersion(client);
      }
    });
  }

  async function register(reg) {
    const { rows } = await pool.query(
      `INSERT INTO players (token, name, company, contact_type, contact_value, contact_norm)
       VALUES ($1, $2, $3, $4, $5, $6)
       ON CONFLICT (contact_type, contact_norm)
       DO UPDATE SET name = EXCLUDED.name, company = EXCLUDED.company, contact_value = EXCLUDED.contact_value, updated_at = now()
       RETURNING id, token, name, company`,
      [newToken(), reg.name, reg.company, reg.contactType, reg.contactValue, reg.contactNorm]);
    return rows[0];
  }

  async function playerByToken(token) {
    if (!token || typeof token !== 'string') return null;
    const { rows } = await pool.query('SELECT id, token, name, company FROM players WHERE token = $1', [token]);
    return rows[0] ?? null;
  }

  async function claim(token, idx) {
    if (!Number.isInteger(idx) || idx < 0 || idx >= SIZE) throw new GameError('bad_square', 'That square doesn’t exist.');
    return tx(async (client, settings, now) => {
      if (settings.ended) throw new GameError('ended', 'The game has ended. Thanks for playing!');
      if (settings.paused) throw new GameError('paused', 'The game is paused for a moment. Try again shortly.');
      const player = (await client.query('SELECT id, name FROM players WHERE token = $1', [token])).rows[0];
      if (!player) throw new GameError('unknown_player', 'Please sign in again.');

      const last = (await client.query(
        'SELECT created_at FROM claims WHERE player_id = $1 AND undone_at IS NULL ORDER BY created_at DESC LIMIT 1',
        [player.id])).rows[0];
      const wait = cooldownRemaining(last?.created_at, now, settings.cooldown_min);
      if (wait > 0) throw new GameError('cooldown', 'You can claim another square soon.', { cooldownSeconds: wait });

      const boardId = settings.current_board_id;
      const board = (await client.query('SELECT * FROM boards WHERE id = $1', [boardId])).rows[0];
      const squares = (await client.query(
        'SELECT idx, pain_id, short, full_text, wedge, persona, claim_id FROM squares WHERE board_id = $1 ORDER BY idx', [boardId])).rows;
      const sq = squares[idx];
      if (sq.claim_id) throw new GameError('taken', 'Just taken. Pick another square!');

      const claimedBefore = new Set(squares.filter((s) => s.claim_id).map((s) => s.idx));
      const newLines = newlyCompletedLines(claimedBefore, idx);
      const firstFiveAwarded = Number((await client.query(
        "SELECT count(*) AS n FROM kits WHERE reason = 'first_five' AND voided_at IS NULL")).rows[0].n);
      const playerHasLineKit = (await client.query(
        "SELECT 1 FROM kits WHERE player_id = $1 AND reason = 'line_win' AND voided_at IS NULL LIMIT 1", [player.id])).rowCount > 0;
      const decision = decideKit({
        isPlayersFirstClaim: !last,
        firstFiveAwarded,
        firstFiveLimit: settings.first_five,
        newLines,
        boardLineKits: board.line_kits,
        lineCap: settings.line_cap,
        playerHasLineKit,
      });

      const c = (await client.query(
        'INSERT INTO claims (board_id, idx, player_id, lines, outcome) VALUES ($1, $2, $3, $4, $5) RETURNING id, created_at',
        [boardId, idx, player.id, newLines, decision.outcome])).rows[0];
      await client.query('UPDATE squares SET claim_id = $1 WHERE board_id = $2 AND idx = $3', [c.id, boardId, idx]);

      let kit = null;
      if (decision.kit) {
        let code = redemptionCode();
        for (let i = 0; i < 10 && (await client.query('SELECT 1 FROM kits WHERE code = $1', [code])).rowCount; i++) code = redemptionCode();
        await client.query('INSERT INTO kits (player_id, claim_id, reason, code) VALUES ($1, $2, $3, $4)',
          [player.id, c.id, decision.kit, code]);
        if (decision.kit === 'line_win') {
          await client.query('UPDATE boards SET line_kits = line_kits + 1 WHERE id = $1', [boardId]);
        }
        kit = { code, reason: decision.kit, claimNo: decision.kit === 'first_five' ? firstFiveAwarded + 1 : null };
      }

      let boardCompleted = false;
      if (claimedBefore.size + 1 === SIZE) {
        await client.query('UPDATE boards SET completed_at = now() WHERE id = $1', [boardId]);
        await openBoard(client, nextSetIndex(board.set_index, sets.length));
        boardCompleted = true;
      }
      await bumpVersion(client);

      return {
        claimId: c.id,
        idx,
        square: squareName(idx),
        short: sq.short,
        full: sq.full_text,
        lines: newLines.map(lineLabel),
        lineKeys: newLines,
        outcome: decision.outcome,
        kit,
        boardNo: board.board_no,
        boardCompleted,
        cooldownSeconds: settings.cooldown_min * 60,
      };
    });
  }

  async function rate(token, claimId, rating) {
    if (!RATINGS[rating]) throw new GameError('bad_rating', 'Pick one of the options.');
    const { rowCount } = await pool.query(
      `UPDATE claims SET rating = $1 FROM players
       WHERE claims.id = $2 AND claims.player_id = players.id AND players.token = $3 AND claims.undone_at IS NULL`,
      [rating, claimId, token]);
    if (!rowCount) throw new GameError('not_found', 'That claim wasn’t found.');
  }

  async function undoClaim(claimId) {
    return tx(async (client, settings) => {
      const c = (await client.query('SELECT * FROM claims WHERE id = $1 AND undone_at IS NULL', [claimId])).rows[0];
      if (!c) throw new GameError('not_found', 'Claim not found or already undone.');
      if (c.board_id !== settings.current_board_id) {
        throw new GameError('old_board', 'Only claims on the current board can be undone.');
      }
      await client.query('UPDATE claims SET undone_at = now() WHERE id = $1', [c.id]);
      await client.query('UPDATE squares SET claim_id = NULL WHERE board_id = $1 AND idx = $2 AND claim_id = $3',
        [c.board_id, c.idx, c.id]);
      const kit = (await client.query('SELECT * FROM kits WHERE claim_id = $1 AND voided_at IS NULL', [c.id])).rows[0];
      let kitVoided = false;
      if (kit && !kit.handed_over_at) {
        await client.query('UPDATE kits SET voided_at = now() WHERE id = $1', [kit.id]);
        if (kit.reason === 'line_win') {
          await client.query('UPDATE boards SET line_kits = GREATEST(line_kits - 1, 0) WHERE id = $1', [c.board_id]);
        }
        kitVoided = true;
      }
      await bumpVersion(client);
      return { playerId: c.player_id, kitVoided };
    });
  }

  async function setHandedOver(kitId, handed) {
    const { rows } = await pool.query(
      `UPDATE kits SET handed_over_at = CASE WHEN $2 THEN now() ELSE NULL END
       WHERE id = $1 AND voided_at IS NULL RETURNING player_id`, [kitId, !!handed]);
    if (!rows[0]) throw new GameError('not_found', 'Kit not found.');
    return { playerId: rows[0].player_id };
  }

  async function updateSettings(patch) {
    return tx(async (client) => {
      const fields = [];
      const params = [];
      const add = (col, v) => { params.push(v); fields.push(`${col} = $${params.length}`); };
      if (patch.cooldownMin !== undefined) {
        const v = Number(patch.cooldownMin);
        if (!Number.isInteger(v) || v < 0 || v > 120) throw new GameError('bad_value', 'Cooldown must be 0 to 120 minutes.');
        add('cooldown_min', v);
      }
      if (patch.lineCap !== undefined) {
        const v = Number(patch.lineCap);
        if (!Number.isInteger(v) || v < 0 || v > 12) throw new GameError('bad_value', 'Cap must be 0 to 12.');
        add('line_cap', v);
      }
      if (patch.paused !== undefined) add('paused', !!patch.paused);
      if (patch.ended !== undefined) add('ended', !!patch.ended);
      if (fields.length) await client.query(`UPDATE settings SET ${fields.join(', ')} WHERE id = 1`, params);
      await bumpVersion(client);
    });
  }

  async function skipToNextSet() {
    return tx(async (client, settings) => {
      const board = (await client.query('SELECT * FROM boards WHERE id = $1', [settings.current_board_id])).rows[0];
      await client.query('UPDATE boards SET completed_at = now(), skipped = true WHERE id = $1', [board.id]);
      await openBoard(client, nextSetIndex(board.set_index, sets.length));
      await bumpVersion(client);
    });
  }

  async function wipeAll() {
    return tx(async (client) => {
      await client.query('TRUNCATE kits, claims, squares, boards, players RESTART IDENTITY CASCADE');
      await client.query('UPDATE settings SET current_board_id = NULL, paused = false, ended = false WHERE id = 1');
      await openBoard(client, 0);
      await bumpVersion(client);
    });
  }

  async function publicState() {
    const s = (await pool.query('SELECT * FROM settings WHERE id = 1')).rows[0];
    const board = (await pool.query('SELECT * FROM boards WHERE id = $1', [s.current_board_id])).rows[0];
    const squares = (await pool.query(
      'SELECT idx, short, full_text, claim_id FROM squares WHERE board_id = $1 ORDER BY idx', [board.id])).rows;
    const claimed = new Set(squares.filter((q) => q.claim_id).map((q) => q.idx));
    return {
      version: Number(s.version),
      boardNo: board.board_no,
      setNo: board.set_index + 1,
      claimedCount: claimed.size,
      squares: squares.map((q) => ({ idx: q.idx, name: squareName(q.idx), short: q.short, full: q.full_text, claimed: !!q.claim_id })),
      lines: lineProgress(claimed),
      completedLines: completedLines(claimed).map(lineLabel),
      paused: s.paused,
      ended: s.ended,
      cooldownMin: s.cooldown_min,
    };
  }

  async function playerState(token) {
    const p = await playerByToken(token);
    if (!p) return null;
    const s = (await pool.query('SELECT cooldown_min FROM settings WHERE id = 1')).rows[0];
    const { rows: [{ now }] } = await pool.query('SELECT now() AS now');
    const last = (await pool.query(
      'SELECT created_at FROM claims WHERE player_id = $1 AND undone_at IS NULL ORDER BY created_at DESC LIMIT 1', [p.id])).rows[0];
    const kits = (await pool.query(
      `SELECT k.id, k.code, k.reason, k.handed_over_at, b.board_no, c.idx, c.lines FROM kits k
       JOIN claims c ON c.id = k.claim_id JOIN boards b ON b.id = c.board_id
       WHERE k.player_id = $1 AND k.voided_at IS NULL ORDER BY k.created_at`, [p.id])).rows;
    const claims = Number((await pool.query(
      'SELECT count(*) AS n FROM claims WHERE player_id = $1 AND undone_at IS NULL', [p.id])).rows[0].n);
    return {
      name: p.name,
      company: p.company,
      claims,
      cooldownSeconds: cooldownRemaining(last?.created_at, now, s.cooldown_min),
      kits: kits.map((k) => ({
        id: k.id, code: k.code, reason: k.reason, handedOver: !!k.handed_over_at,
        square: squareName(k.idx), lines: k.lines.map(lineLabel), boardNo: k.board_no,
      })),
    };
  }

  const CLAIM_ROWS_SQL = `
    SELECT c.id, c.created_at, c.idx, c.lines, c.outcome, c.rating, c.undone_at, c.board_id,
           b.board_no, b.set_index, s.short, s.full_text, s.wedge, s.persona,
           p.id AS player_id, p.name, p.company, p.contact_type, p.contact_value,
           k.id AS kit_id, k.code AS kit_code, k.reason AS kit_reason, k.handed_over_at, k.voided_at
    FROM claims c
    JOIN boards b ON b.id = c.board_id
    JOIN squares s ON s.board_id = c.board_id AND s.idx = c.idx
    JOIN players p ON p.id = c.player_id
    LEFT JOIN kits k ON k.claim_id = c.id`;

  async function adminState() {
    const s = (await pool.query('SELECT * FROM settings WHERE id = 1')).rows[0];
    const feed = (await pool.query(`${CLAIM_ROWS_SQL} ORDER BY c.created_at DESC LIMIT 300`)).rows;
    const board = (await pool.query('SELECT * FROM boards WHERE id = $1', [s.current_board_id])).rows[0];
    const stats = (await pool.query(`
      SELECT (SELECT count(*) FROM players) AS players,
             (SELECT count(*) FROM claims WHERE undone_at IS NULL) AS claims,
             (SELECT count(*) FROM kits WHERE voided_at IS NULL) AS kits,
             (SELECT count(*) FROM kits WHERE voided_at IS NULL AND handed_over_at IS NOT NULL) AS handed,
             (SELECT count(*) FROM kits WHERE voided_at IS NULL AND reason = 'first_five') AS first_five,
             (SELECT count(*) FROM boards) AS boards`)).rows[0];
    return {
      settings: {
        cooldownMin: s.cooldown_min, lineCap: s.line_cap, firstFive: s.first_five, paused: s.paused, ended: s.ended,
      },
      board: { id: board.id, boardNo: board.board_no, setNo: board.set_index + 1, lineKits: board.line_kits },
      stats: Object.fromEntries(Object.entries(stats).map(([k, v]) => [k, Number(v)])),
      feed: feed.map((r) => ({
        id: r.id,
        at: r.created_at,
        square: squareName(r.idx),
        boardNo: r.board_no,
        currentBoard: r.board_id === s.current_board_id,
        short: r.short,
        full: r.full_text,
        wedge: r.wedge,
        wedgeName: wedgeNames[r.wedge] ?? r.wedge,
        persona: r.persona,
        name: r.name,
        company: r.company,
        contactType: r.contact_type,
        contactValue: r.contact_value,
        rating: r.rating,
        outcome: r.outcome,
        lines: r.lines.map(lineLabel),
        undone: !!r.undone_at,
        kit: r.kit_id && !r.voided_at ? { id: r.kit_id, code: r.kit_code, reason: r.kit_reason, handedOver: !!r.handed_over_at } : null,
      })),
    };
  }

  async function exportRows() {
    const rows = (await pool.query(`${CLAIM_ROWS_SQL} WHERE c.undone_at IS NULL ORDER BY c.created_at`)).rows;
    return rows.map((r) => ({
      ...r,
      square: squareName(r.idx),
      set_no: r.set_index + 1,
      wedge_name: wedgeNames[r.wedge] ?? r.wedge,
      lines_completed: r.lines.map(lineLabel).join('; '),
      kit_live: !!r.kit_id && !r.voided_at,
    }));
  }

  async function playerIdByToken(token) {
    const p = await playerByToken(token);
    return p?.id ?? null;
  }

  async function tokenByPlayerId(id) {
    const { rows } = await pool.query('SELECT token FROM players WHERE id = $1', [id]);
    return rows[0]?.token ?? null;
  }

  return {
    pool, init, register, playerByToken, playerIdByToken, tokenByPlayerId, claim, rate, undoClaim, setHandedOver,
    updateSettings, skipToNextSet, wipeAll, publicState, playerState, adminState, exportRows,
    close: () => pool.end(),
  };
}
