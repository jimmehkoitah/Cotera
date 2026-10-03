(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  let data = null;
  let socket = null;

  async function api(path, body) {
    const res = await fetch(path, {
      method: body ? 'POST' : 'GET',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
      credentials: 'same-origin',
    });
    let json = {};
    try { json = await res.json(); } catch (_) { /* empty */ }
    if (!res.ok) {
      const e = new Error(json.message || 'Something went wrong.');
      e.status = res.status;
      throw e;
    }
    return json;
  }

  let toastTimer;
  function toast(msg) {
    const t = $('toast');
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
  }

  const timeFmt = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', hour: 'numeric', minute: '2-digit' });
  const OUTCOME = { first_five_kit: 'First-five kit', line_kit: 'Line kit', line_no_kit: 'Line, no kit', none: '' };
  const RATING = { big: 'Big one', somewhat: 'Somewhat', playing: 'Just playing' };

  function render() {
    const s = data.stats;
    const stats = $('stats');
    stats.textContent = '';
    const tiles = [
      [s.players, 'Players'],
      [s.claims, 'Claims'],
      [s.kits, 'Kits earned'],
      [s.handed + ' / ' + s.kits, 'Kits handed over'],
      ['#' + data.board.boardNo, 'Board (set ' + data.board.setNo + ')'],
      [data.board.lineKits + ' / ' + data.settings.lineCap, 'Line kits this board'],
    ];
    for (const [n, k] of tiles) {
      const t = el('div', 'card stat');
      t.append(el('div', 'n', String(n)), el('div', 'k', k));
      stats.append(t);
    }

    // Kits
    const kits = $('kits');
    kits.textContent = '';
    const withKits = data.feed.filter((f) => f.kit && !f.undone);
    const pending = withKits.filter((f) => !f.kit.handedOver);
    const handed = withKits.filter((f) => f.kit.handedOver).slice(0, 5);
    if (!pending.length) kits.append(el('p', 'empty', 'Nobody is waiting on a kit.'));
    for (const f of pending) kits.append(kitRow(f, false));
    if (handed.length) {
      kits.append(el('p', 'empty', 'Recently handed over'));
      for (const f of handed) kits.append(kitRow(f, true));
    }

    // Controls
    if (document.activeElement !== $('cooldown')) $('cooldown').value = data.settings.cooldownMin;
    if (document.activeElement !== $('cap')) $('cap').value = data.settings.lineCap;
    $('pauseLabel').textContent = data.settings.paused ? 'Claiming is PAUSED' : 'Claiming is open';
    $('pause').textContent = data.settings.paused ? 'Resume' : 'Pause';
    $('endLabel').textContent = data.settings.ended ? 'Game has ENDED' : 'Game is running';
    $('end').textContent = data.settings.ended ? 'Reopen game' : 'End game';

    // Feed
    const feed = $('feed');
    feed.textContent = '';
    if (!data.feed.length) feed.append(el('p', 'empty', 'No claims yet.'));
    for (const f of data.feed) {
      const card = el('div', 'card feed-item' + (f.undone ? ' undone' : ''));
      const left = el('div');
      left.append(el('div', 'main', f.square + ' · ' + f.short + (f.undone ? ' (undone)' : '')));
      left.append(el('div', 'meta', f.name + ' · ' + f.company + ' · ' + f.contactValue));
      const badges = el('div', 'meta');
      badges.append(el('span', 'badge wedge', f.wedge + ' ' + f.wedgeName));
      badges.append(el('span', 'badge', f.persona));
      if (f.rating) badges.append(el('span', 'badge' + (f.rating === 'big' ? ' rate-big' : ''), RATING[f.rating]));
      if (OUTCOME[f.outcome]) badges.append(el('span', 'badge win', OUTCOME[f.outcome] + (f.kit ? ' ' + f.kit.code : '')));
      if (f.lines.length) badges.append(el('span', 'badge', f.lines.join(' + ')));
      left.append(badges);
      const right = el('div', 'row-actions');
      right.append(el('span', 'meta', timeFmt.format(new Date(f.at)) + ' · B' + f.boardNo));
      if (!f.undone && f.currentBoard) {
        const undo = el('button', 'btn ghost', 'Undo');
        undo.type = 'button';
        undo.addEventListener('click', async () => {
          if (!confirm('Undo ' + f.name + '’s claim on ' + f.square + '? The square reopens.')) return;
          try { await api('/api/admin/undo', { claimId: f.id }); toast('Claim undone'); refresh(); } catch (e) { toast(e.message); }
        });
        right.append(undo);
      }
      card.append(left, right);
      feed.append(card);
    }
  }

  function kitRow(f, handed) {
    const row = el('div', 'kit-row');
    const left = el('div');
    left.append(el('div', 'code', f.kit.code));
    const why = f.kit.reason === 'first_five' ? 'First five' : 'Completed ' + f.lines.join(' + ');
    left.append(el('div', 'who', f.name + ' · ' + f.company + ' · ' + why));
    const btn = el('button', handed ? 'btn ghost' : 'btn primary', handed ? 'Undo' : 'Handed over');
    btn.type = 'button';
    btn.addEventListener('click', async () => {
      try { await api('/api/admin/kit', { kitId: f.kit.id, handed: !handed }); refresh(); } catch (e) { toast(e.message); }
    });
    row.append(left, btn);
    return row;
  }

  let refreshTimer = null;
  function refresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(async () => {
      try {
        data = await api('/api/admin/state');
        render();
      } catch (e) {
        if (e.status === 401) showLogin();
      }
    }, 150);
  }

  function connect() {
    if (socket) { socket.disconnect().connect(); return; }
    socket = io({ auth: { role: 'admin' } });
    socket.on('connect', () => { $('live').className = 'live on'; $('liveText').textContent = 'Live'; refresh(); });
    socket.on('disconnect', () => { $('live').className = 'live off'; $('liveText').textContent = 'Reconnecting'; });
    socket.on('admin:changed', refresh);
  }

  function showLogin() {
    $('dash').hidden = true;
    $('login').hidden = false;
    $('pin').focus();
  }
  async function showDash() {
    $('login').hidden = true;
    $('dash').hidden = false;
    connect();
    refresh();
  }

  $('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    $('loginError').hidden = true;
    try {
      await api('/api/admin/login', { pin: $('pin').value });
      $('pin').value = '';
      showDash();
    } catch (err) {
      $('loginError').textContent = err.message;
      $('loginError').hidden = false;
    }
  });
  $('logout').addEventListener('click', async () => { await api('/api/admin/logout', {}).catch(() => {}); if (socket) socket.disconnect(); showLogin(); });

  async function save(body, msg) {
    try { await api('/api/admin/settings', body); toast(msg); refresh(); } catch (e) { toast(e.message); }
  }
  $('saveCooldown').addEventListener('click', () => save({ cooldownMin: Number($('cooldown').value) }, 'Cooldown saved'));
  $('saveCap').addEventListener('click', () => save({ lineCap: Number($('cap').value) }, 'Cap saved'));
  $('pause').addEventListener('click', () => save({ paused: !data.settings.paused }, data.settings.paused ? 'Resumed' : 'Paused'));
  $('end').addEventListener('click', () => {
    if (!data.settings.ended && !confirm('End the game? Nobody can claim after this.')) return;
    save({ ended: !data.settings.ended }, data.settings.ended ? 'Game reopened' : 'Game ended');
  });
  $('skip').addEventListener('click', async () => {
    if (!confirm('Skip to a fresh board with the next set of pain points?')) return;
    try { await api('/api/admin/skip', {}); toast('New board'); refresh(); } catch (e) { toast(e.message); }
  });
  $('wipe').addEventListener('click', async () => {
    const word = prompt('This deletes ALL players, claims, and kits. Download the CSV first if you need it.\n\nType RESET to confirm.');
    if (word === null) return;
    try { await api('/api/admin/wipe', { confirm: word.trim() }); toast('Fresh start'); refresh(); } catch (e) { toast(e.message); }
  });

  setInterval(() => { if (!$('dash').hidden) refresh(); }, 15000);

  api('/api/admin/session').then((s) => (s.admin ? showDash() : showLogin())).catch(showLogin);
})();
