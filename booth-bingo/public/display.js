(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  // Which cells belong to each line, by label (matches server/game.js).
  const COLS = ['B', 'I', 'N', 'G', 'O'];
  const LINE_CELLS = {};
  for (let r = 0; r < 5; r++) LINE_CELLS['Row ' + (r + 1)] = [0, 1, 2, 3, 4].map((c) => r * 5 + c);
  for (let c = 0; c < 5; c++) LINE_CELLS[COLS[c] + ' column'] = [0, 1, 2, 3, 4].map((r) => r * 5 + c);
  LINE_CELLS['Diagonal ↘'] = [0, 6, 12, 18, 24];
  LINE_CELLS['Diagonal ↗'] = [20, 16, 12, 8, 4];

  let state = null;
  const queue = [];
  let celebrating = false;

  function render(prev) {
    const grid = $('grid');
    if (grid.children.length !== 25) {
      grid.textContent = '';
      for (let i = 0; i < 25; i++) grid.appendChild(el('div', 'sq'));
    }
    const sameBoard = prev && prev.boardNo === state.boardNo;
    state.squares.forEach((q, i) => {
      const d = grid.children[i];
      d.textContent = q.short;
      d.classList.toggle('claimed', q.claimed);
      if (sameBoard && q.claimed && !prev.squares[i].claimed) {
        d.classList.remove('just');
        void d.offsetWidth;
        d.classList.add('just');
      }
    });
    $('claimed').textContent = String(state.claimedCount);
    $('fill').style.width = (state.claimedCount / 25) * 100 + '%';
    $('boardNo').textContent = 'Board ' + state.boardNo;

    const list = $('lines');
    list.textContent = '';
    const open = state.lines.filter((l) => l.count < 5 && l.count > 0).slice(0, 4);
    if (!open.length) {
      list.append(el('li', 'none', 'Fresh board. Be the first to claim a square!'));
    }
    for (const l of open) {
      const li = el('li', l.count >= 4 ? 'hot' : '');
      li.append(el('span', null, l.label));
      const pips = el('span', 'pips');
      for (let i = 0; i < 5; i++) pips.append(el('span', i < l.count ? 'pip on' : 'pip'));
      li.append(pips);
      list.append(li);
    }

    const banner = $('stateBanner');
    if (state.ended) { banner.textContent = 'That’s a wrap! Thanks for playing.'; banner.hidden = false; }
    else if (state.paused) { banner.textContent = 'Paused for a moment'; banner.hidden = false; }
    else banner.hidden = true;
  }

  function celebrateNext() {
    if (celebrating || !queue.length) return;
    celebrating = true;
    const c = queue.shift();
    $('celebrateText').textContent = c.text;
    $('celebrateSub').textContent = c.sub;
    $('celebrate').hidden = false;
    const lit = [];
    if (c.cells) {
      for (const i of c.cells) { const d = $('grid').children[i]; if (d) { d.classList.add('lit'); lit.push(d); } }
    }
    if (window.confetti) window.confetti(3200, 1.2);
    setTimeout(() => {
      $('celebrate').hidden = true;
      setTimeout(() => {
        lit.forEach((d) => d.classList.remove('lit'));
        celebrating = false;
        celebrateNext();
      }, 1200);
    }, 3400);
  }

  function onState(s) {
    if (!s || (state && s.version < state.version)) return;
    const prev = state;
    state = s;
    if (prev && s.boardNo !== prev.boardNo) {
      queue.push({ text: 'Board complete!', sub: 'Fresh board, fresh pains. Scan to play.' });
    } else if (prev) {
      const before = new Set(prev.completedLines);
      const fresh = s.completedLines.filter((l) => !before.has(l));
      if (fresh.length) {
        const text = fresh.length === 1 ? fresh[0] + ' complete!' : fresh.join(' + ') + ' complete!';
        const cells = [...new Set(fresh.flatMap((l) => LINE_CELLS[l] || []))];
        queue.push({ text: text, sub: 'Bingo! Who’s next?', cells: cells });
      }
    }
    render(prev);
    celebrateNext();
  }

  // Keep the TV awake.
  let wakeLock = null;
  async function keepAwake() {
    try {
      if ('wakeLock' in navigator && document.visibilityState === 'visible') wakeLock = await navigator.wakeLock.request('screen');
    } catch (_) { /* not supported or denied */ }
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    keepAwake();
    fetch('/api/state').then((r) => r.json()).then(onState).catch(() => {});
  });
  keepAwake();
  // One click or tap anywhere: go fullscreen (browsers require a gesture for that).
  document.addEventListener('click', () => {
    keepAwake();
    if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  });

  fetch('/api/config').then((r) => r.json()).then((c) => { $('url').textContent = c.shortUrl; }).catch(() => {});

  const socket = io();
  socket.on('connect', () => { $('conn').hidden = true; });
  socket.on('disconnect', () => { $('conn').hidden = false; });
  socket.on('state', onState);

  // Belt and braces: if the socket is quiet for a long time, refresh state over HTTP.
  setInterval(() => {
    fetch('/api/state').then((r) => r.json()).then(onState).catch(() => {});
  }, 30000);
})();
