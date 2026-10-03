(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  const local = {
    get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
    set(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (_) { /* private mode */ } },
  };

  let token = local.get('bb_token');
  let mine = new Set(JSON.parse(local.get('bb_mine') || '[]'));
  let state = null;
  let me = null;
  let cooldownEnd = 0;
  let sheetMode = null;
  let sheetIdx = null;
  let claimingIdx = null;
  let socket = null;
  let contactType = 'linkedin';

  const CONTACT = {
    linkedin: { type: 'url', inputmode: 'url', autocomplete: 'url', placeholder: 'linkedin.com/in/yourname', hint: 'Paste your profile link, or just your handle.' },
    phone: { type: 'tel', inputmode: 'tel', autocomplete: 'tel', placeholder: '(415) 555-0134', hint: 'Only used to follow up about what you claim.' },
    email: { type: 'email', inputmode: 'email', autocomplete: 'email', placeholder: 'you@company.com', hint: 'Your work email works best.' },
  };

  // ---------- helpers ----------
  async function api(path, body) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 12000);
    let res;
    try {
      res = await fetch(path, {
        method: body ? 'POST' : 'GET',
        headers: Object.assign({ 'Content-Type': 'application/json' }, token ? { 'X-Player-Token': token } : {}),
        body: body ? JSON.stringify(body) : undefined,
        credentials: 'same-origin',
        signal: ctrl.signal,
      });
    } catch (_) {
      const e = new Error('Couldn’t reach the board. Check your signal and try again.');
      e.network = true;
      throw e;
    } finally {
      clearTimeout(timer);
    }
    let data = {};
    try { data = await res.json(); } catch (_) { /* empty */ }
    if (!res.ok) {
      const e = new Error(data.message || 'Something went wrong. Try again.');
      e.code = data.error;
      e.status = res.status;
      e.data = data;
      throw e;
    }
    return data;
  }

  let toastTimer = null;
  function toast(msg) {
    const t = $('toast');
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 2800);
  }

  function show(id) {
    for (const s of ['screen-loading', 'screen-register', 'screen-board']) $(s).hidden = s !== id;
  }

  function fmtClock(secs) {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return m + ':' + String(s).padStart(2, '0');
  }
  function cooldownLeft() {
    return Math.max(0, Math.ceil((cooldownEnd - Date.now()) / 1000));
  }
  function setCooldown(secs) {
    cooldownEnd = secs > 0 ? Date.now() + secs * 1000 : 0;
  }
  function joinLines(lines) {
    if (!lines || !lines.length) return 'a line';
    if (lines.length === 1) return lines[0];
    return lines.slice(0, -1).join(', ') + ' and ' + lines[lines.length - 1];
  }
  function saveMine() { local.set('bb_mine', JSON.stringify([...mine])); }

  // ---------- live connection ----------
  function setLive(on) {
    const live = $('live');
    live.classList.toggle('on', on);
    live.classList.toggle('off', !on);
    $('liveText').textContent = on ? 'Live' : 'Reconnecting';
  }

  function connect() {
    if (socket) {
      socket.auth = { token: token };
      socket.disconnect().connect();
      return;
    }
    socket = io({ auth: { token: token } });
    socket.on('connect', () => setLive(true));
    socket.on('disconnect', () => setLive(false));
    socket.io.on('reconnect_attempt', () => setLive(false));
    socket.on('state', onState);
    socket.on('me', (m) => {
      if (!token && !me) return;
      me = m;
      setCooldown(m.cooldownSeconds);
      renderMe();
      if (sheetMode === 'kits') showKits();
    });
    socket.on('reset', () => signOut(true));
  }

  function onState(s) {
    if (!s || (state && s.version < state.version)) return;
    const prev = state;
    state = s;
    const boardChanged = prev && s.boardNo !== prev.boardNo;
    if (boardChanged) {
      toast('Board complete! Fresh board, fresh pains.');
      if (sheetMode === 'square' && claimingIdx === null) closeSheet();
    } else if (sheetMode === 'square' && sheetIdx !== null && s.squares[sheetIdx].claimed && claimingIdx !== sheetIdx) {
      closeSheet();
      toast('Just taken. Pick another square!');
    }
    renderBoard(prev);
    if (sheetMode === 'square' && sheetIdx !== null) renderSquareSheet(sheetIdx);
  }

  // ---------- board ----------
  function renderBoard(prev) {
    if (!state) return;
    const grid = $('grid');
    if (grid.children.length !== 25) {
      grid.textContent = '';
      for (let i = 0; i < 25; i++) {
        const b = el('button', 'sq');
        b.type = 'button';
        b.dataset.idx = String(i);
        b.setAttribute('role', 'gridcell');
        grid.appendChild(b);
      }
    }
    const sameBoard = prev && prev.boardNo === state.boardNo;
    state.squares.forEach((q, i) => {
      const b = grid.children[i];
      b.textContent = q.short;
      const isMine = q.claimed && mine.has(state.boardNo + ':' + i);
      b.classList.toggle('claimed', q.claimed && !isMine);
      b.classList.toggle('mine', isMine);
      if (sameBoard && q.claimed && !prev.squares[i].claimed) {
        b.classList.remove('just');
        void b.offsetWidth;
        b.classList.add('just');
      }
      b.setAttribute('aria-label', q.name + ': ' + q.short + (q.claimed ? ' (claimed)' : ''));
    });
    $('boardInfo').textContent = 'Board ' + state.boardNo + ' · ' + state.claimedCount + '/25 claimed';

    const hot = state.lines.filter((l) => l.count >= 3 && l.count < 5).slice(0, 2);
    const hotEl = $('hot');
    hotEl.textContent = '';
    if (hot.length) {
      hotEl.append('Closest to bingo: ');
      hot.forEach((l, i) => {
        if (i) hotEl.append(' · ');
        hotEl.append(el('b', null, l.label + ' ' + l.count + '/5'));
      });
    }
    renderBanner();
  }

  function renderBanner() {
    const b = $('banner');
    if (!state) return;
    const left = cooldownLeft();
    b.className = 'banner';
    b.textContent = '';
    if (state.ended) {
      b.classList.add('stop');
      b.textContent = 'That’s a wrap! Thanks for playing.';
    } else if (state.paused) {
      b.classList.add('stop');
      b.textContent = 'Paused for a moment. Hang tight.';
    } else if (left > 0) {
      b.classList.add('wait');
      b.append('Your next claim unlocks in ', el('span', 'clock', fmtClock(left)));
    } else {
      b.textContent = 'Pick the pain that’s most real for you';
    }
  }

  function renderMe() {
    if (!me) return;
    $('hello').textContent = 'Hi ' + me.name.split(' ')[0];
    const pending = me.kits.filter((k) => !k.handedOver);
    $('myKitBtn').hidden = pending.length === 0;
    renderBanner();
  }

  // ---------- sheet ----------
  function openSheet(mode) {
    sheetMode = mode;
    $('backdrop').hidden = false;
    $('sheet').hidden = false;
    $('sheet').textContent = '';
    $('sheet').append(el('div', 'grab'));
    return $('sheet');
  }
  function closeSheet() {
    sheetMode = null;
    sheetIdx = null;
    $('backdrop').hidden = true;
    $('sheet').hidden = true;
  }

  function renderSquareSheet(idx) {
    const q = state.squares[idx];
    const s = openSheet('square');
    sheetIdx = idx;
    s.append(el('span', 'tag', q.name));
    s.append(el('h2', null, q.full));
    const stack = el('div', 'stack');
    const claim = el('button', 'btn primary', 'Claim this square');
    claim.type = 'button';
    const left = cooldownLeft();
    if (state.ended) { claim.disabled = true; claim.textContent = 'The game has ended'; }
    else if (state.paused) { claim.disabled = true; claim.textContent = 'Paused for a moment'; }
    else if (left > 0) { claim.disabled = true; claim.textContent = 'Next claim in ' + fmtClock(left); claim.dataset.cooldown = '1'; }
    if (claimingIdx === idx) { claim.disabled = true; claim.textContent = 'Claiming…'; }
    claim.addEventListener('click', () => doClaim(idx, claim));
    const cancel = el('button', 'btn ghost', 'Not this one');
    cancel.type = 'button';
    cancel.addEventListener('click', closeSheet);
    stack.append(claim, cancel);
    s.append(stack);
  }

  function showNetError(idx, msg) {
    const s = openSheet('square');
    sheetIdx = idx;
    s.append(el('span', 'tag', state.squares[idx].name));
    s.append(el('h2', null, msg));
    const stack = el('div', 'stack');
    const retry = el('button', 'btn primary', 'Try again');
    retry.type = 'button';
    retry.addEventListener('click', () => doClaim(idx, retry));
    const cancel = el('button', 'btn ghost', 'Cancel');
    cancel.type = 'button';
    cancel.addEventListener('click', closeSheet);
    stack.append(retry, cancel);
    s.append(stack);
  }

  async function doClaim(idx, btn) {
    if (claimingIdx !== null) return;
    claimingIdx = idx;
    btn.disabled = true;
    btn.textContent = 'Claiming…';
    const claimsBefore = me ? me.claims : 0;
    const kitsBefore = new Set((me ? me.kits : []).map((k) => k.id));
    try {
      const data = await api('/api/claim', { idx: idx });
      me = data.me;
      setCooldown(me.cooldownSeconds);
      mine.add(data.result.boardNo + ':' + idx);
      saveMine();
      claimingIdx = null;
      renderMe();
      renderBoard();
      showResult(data.result);
    } catch (e) {
      claimingIdx = null;
      if ((e.code === 'taken' || e.code === 'cooldown') && await recover(claimsBefore, kitsBefore, idx)) return;
      if (e.code === 'taken') { closeSheet(); toast('Just taken. Pick another square!'); }
      else if (e.code === 'cooldown') { setCooldown(e.data.cooldownSeconds || 0); renderSquareSheet(idx); renderBanner(); }
      else if (e.code === 'unknown_player') { signOut(); toast('Please sign in again.'); }
      else if (e.code === 'paused' || e.code === 'ended') { closeSheet(); toast(e.message); }
      else if (e.network) showNetError(idx, e.message);
      else { toast(e.message); renderSquareSheet(idx); }
    }
  }

  // If a claim's response got lost on a bad connection, check whether it actually went through.
  async function recover(claimsBefore, kitsBefore, idx) {
    try {
      const m = await api('/api/me');
      if (!m.signedIn || m.claims <= claimsBefore) return false;
      me = m;
      setCooldown(m.cooldownSeconds);
      mine.add(state.boardNo + ':' + idx);
      saveMine();
      renderMe();
      renderBoard();
      const kit = m.kits.find((k) => !kitsBefore.has(k.id));
      showResult({
        claimId: null,
        square: state.squares[idx].name,
        full: state.squares[idx].full,
        lines: kit ? kit.lines : [],
        outcome: kit ? (kit.reason === 'first_five' ? 'first_five_kit' : 'line_kit') : 'none',
        kit: kit ? { code: kit.code, reason: kit.reason, claimNo: null } : null,
      });
      return true;
    } catch (_) {
      return false;
    }
  }

  function codeBox(code) {
    const box = el('div', 'code-box');
    box.append(el('div', 'label', 'Kit code'), el('div', 'code', code));
    return box;
  }

  function showResult(r) {
    const s = openSheet('result');
    const wrap = el('div', r.kit ? 'winner' : '');
    if (r.kit) {
      wrap.append(el('div', 'mug', '☕'));
      if (r.kit.reason === 'first_five') {
        wrap.append(el('div', 'result-title', r.kit.claimNo ? 'You’re claim #' + r.kit.claimNo + ' today!' : 'You won a Coco kit!'));
        wrap.append(el('p', 'result-sub', 'That earns you a Coco by Cotera hot chocolate kit.'));
      } else {
        wrap.append(el('div', 'result-title', 'You completed ' + joinLines(r.lines) + '!'));
        wrap.append(el('p', 'result-sub', 'That’s a Coco by Cotera hot chocolate kit for you.'));
      }
      wrap.append(codeBox(r.kit.code));
      wrap.append(el('p', 'show-jim', 'Show this screen to Jim at the Cotera table.'));
      if (window.confetti) window.confetti(2600, 1);
    } else if (r.outcome === 'line_no_kit') {
      wrap.append(el('div', 'result-title', 'You completed ' + joinLines(r.lines) + '! 🎉'));
      wrap.append(el('p', 'result-sub', 'Nice timing. Now go tell Jim the story behind it.'));
      if (window.confetti) window.confetti(1800, 0.5);
    } else {
      wrap.append(el('div', 'result-title', r.square + ' is yours'));
      wrap.append(el('p', 'result-sub', 'Now find Jim at the Cotera table and tell him about it.'));
    }
    wrap.append(el('p', 'quote', r.full));
    s.append(wrap);

    if (r.claimId) {
      s.append(el('h3', null, 'Is this real for you?'));
      const row = el('div', 'ratings');
      const thanks = el('p', 'note', '');
      [['big', 'Big one'], ['somewhat', 'Somewhat'], ['playing', 'Just playing']].forEach(([value, label]) => {
        const b = el('button', null, label);
        b.type = 'button';
        b.setAttribute('aria-pressed', 'false');
        b.addEventListener('click', async () => {
          for (const x of row.children) x.setAttribute('aria-pressed', String(x === b));
          try {
            await api('/api/rate', { claimId: r.claimId, rating: value });
            thanks.textContent = 'Thanks! That helps Jim follow up on the right thing.';
          } catch (e) {
            thanks.textContent = e.message;
          }
        });
        row.append(b);
      });
      s.append(row, thanks);
    }
    const back = el('button', 'btn dark', 'Back to the board');
    back.type = 'button';
    back.addEventListener('click', closeSheet);
    const stack = el('div', 'stack spaced');
    stack.append(back);
    s.append(stack);
  }

  function showKits() {
    if (!me) return;
    const s = openSheet('kits');
    const wrap = el('div', 'winner');
    const pending = me.kits.filter((k) => !k.handedOver);
    wrap.append(el('div', 'mug', '☕'));
    if (!pending.length) {
      wrap.append(el('div', 'result-title', 'Enjoy your cocoa!'));
      wrap.append(el('p', 'kit-done', 'Jim has marked your kit as handed over.'));
    } else {
      wrap.append(el('div', 'result-title', 'Your Coco by Cotera kit'));
      for (const k of pending) {
        wrap.append(el('p', 'result-sub', k.reason === 'first_five' ? 'One of the first five players' : 'Completed ' + joinLines(k.lines)));
        wrap.append(codeBox(k.code));
      }
      wrap.append(el('p', 'show-jim', 'Show this screen to Jim at the Cotera table.'));
    }
    s.append(wrap);
    const close = el('button', 'btn dark', 'Back to the board');
    close.type = 'button';
    close.addEventListener('click', closeSheet);
    const stack = el('div', 'stack spaced');
    stack.append(close);
    s.append(stack);
  }

  // ---------- sign in ----------
  function setContactType(type) {
    contactType = type;
    for (const b of $('contactTabs').children) b.setAttribute('aria-selected', String(b.dataset.type === type));
    const c = CONTACT[type];
    const input = $('contactValue');
    input.type = c.type;
    input.setAttribute('inputmode', c.inputmode);
    input.setAttribute('autocomplete', c.autocomplete);
    input.placeholder = c.placeholder;
    input.setAttribute('aria-label', type === 'linkedin' ? 'LinkedIn profile' : type === 'phone' ? 'Phone number' : 'Work email');
    $('contactHint').textContent = c.hint;
  }

  async function onRegister(ev) {
    ev.preventDefault();
    const f = ev.target;
    const err = $('regError');
    err.hidden = true;
    const body = {
      name: f.name.value,
      company: f.company.value,
      contactType: contactType,
      contactValue: f.contactValue.value,
    };
    if (!body.name.trim() || !body.company.trim() || !body.contactValue.trim()) {
      err.textContent = 'Add your name, company, and one way to reach you.';
      err.hidden = false;
      return;
    }
    const btn = $('regBtn');
    btn.disabled = true;
    btn.textContent = 'Joining…';
    try {
      const data = await api('/api/register', body);
      token = data.token;
      local.set('bb_token', token);
      me = data.me;
      setCooldown(me.cooldownSeconds);
      connect();
      showBoard();
    } catch (e) {
      err.textContent = e.message;
      err.hidden = false;
    } finally {
      btn.disabled = false;
      btn.textContent = 'Let’s play';
    }
  }

  function signOut(fromReset) {
    token = null;
    me = null;
    mine = new Set();
    local.set('bb_token', null);
    local.set('bb_mine', null);
    closeSheet();
    if (socket) connect();
    show('screen-register');
    if (fromReset) toast('The game was reset. Sign in to play again.');
  }

  function showBoard() {
    show('screen-board');
    renderMe();
    renderBoard();
  }

  // ---------- wire up ----------
  $('regForm').addEventListener('submit', onRegister);
  $('contactTabs').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-type]');
    if (b) { setContactType(b.dataset.type); $('contactValue').focus(); }
  });
  $('grid').addEventListener('click', (e) => {
    const b = e.target.closest('.sq');
    if (!b || !state) return;
    const idx = Number(b.dataset.idx);
    if (state.squares[idx].claimed) { toast('Already claimed. Pick an open square.'); return; }
    renderSquareSheet(idx);
  });
  $('backdrop').addEventListener('click', () => { if (claimingIdx === null) closeSheet(); });
  $('myKitBtn').addEventListener('click', showKits);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && claimingIdx === null) closeSheet(); });

  let wasCooling = false;
  setInterval(() => {
    const left = cooldownLeft();
    if (wasCooling && left === 0 && state && !state.paused && !state.ended && me) {
      toast('You can claim another square!');
      if (navigator.vibrate) navigator.vibrate(60);
    }
    wasCooling = left > 0;
    renderBanner();
    if (sheetMode === 'square' && sheetIdx !== null && claimingIdx === null) {
      const btn = $('sheet').querySelector('.btn.primary');
      if (btn && btn.dataset.cooldown) {
        if (left > 0) btn.textContent = 'Next claim in ' + fmtClock(left);
        else renderSquareSheet(sheetIdx);
      }
    }
  }, 1000);

  document.addEventListener('visibilitychange', async () => {
    if (document.visibilityState !== 'visible') return;
    api('/api/state').then(onState).catch(() => {});
    if (me) {
      try {
        const m = await api('/api/me');
        if (m.signedIn) { me = m; setCooldown(m.cooldownSeconds); renderMe(); }
        else signOut(true);
      } catch (_) { /* offline; the socket will catch up */ }
    }
  });

  async function boot() {
    setContactType('linkedin');
    connect();
    api('/api/state').then(onState).catch(() => {});
    try {
      const m = await api('/api/me');
      if (m.signedIn) {
        me = m;
        setCooldown(me.cooldownSeconds);
        showBoard();
      } else {
        if (token) { token = null; local.set('bb_token', null); }
        show('screen-register');
      }
    } catch (e) {
      if (token) showBoard(); // signed in but offline: the board fills in when the connection returns
      else show('screen-register');
    }
  }
  boot();
})();
