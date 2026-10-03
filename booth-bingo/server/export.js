// CSV export: one row per live claim. UTF-8 with BOM so Excel and Google Sheets open it cleanly.

const COLUMNS = [
  'timestamp_pt', 'board_no', 'set_no', 'square', 'pain_point_short', 'pain_point_full', 'wedge', 'wedge_name',
  'persona', 'player_name', 'company', 'contact_type', 'contact_value', 'real_pain_rating', 'outcome',
  'lines_completed', 'kit_code', 'kit_handed_over', 'kit_handed_over_at_pt',
];

const RATING_LABELS = { big: 'Big one', somewhat: 'Somewhat', playing: 'Just playing' };

export function formatPT(d) {
  if (!d) return '';
  // sv-SE gives an ISO-like "2026-10-05 16:12:03".
  return new Date(d).toLocaleString('sv-SE', { timeZone: 'America/Los_Angeles' });
}

function cell(v) {
  let s = v === null || v === undefined ? '' : String(v);
  // Attendees typed some of these fields; stop spreadsheet formula injection.
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(rows) {
  const lines = [COLUMNS.join(',')];
  for (const r of rows) {
    lines.push([
      formatPT(r.created_at),
      r.board_no,
      r.set_no,
      r.square,
      r.short,
      r.full_text,
      r.wedge,
      r.wedge_name,
      r.persona,
      r.name,
      r.company,
      r.contact_type,
      r.contact_value,
      RATING_LABELS[r.rating] ?? '',
      r.outcome,
      r.lines_completed,
      r.kit_live ? r.kit_code : '',
      r.kit_live ? (r.handed_over_at ? 'Y' : 'N') : '',
      r.kit_live ? formatPT(r.handed_over_at) : '',
    ].map(cell).join(','));
  }
  return '﻿' + lines.join('\r\n') + '\r\n';
}
