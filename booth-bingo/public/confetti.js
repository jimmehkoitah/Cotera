// Tiny canvas confetti in cocoa colors. confetti(durationMs, density)
(function () {
  const COLORS = ['#d2632a', '#c8873e', '#fbf6ef', '#7a4a2e', '#f1e4d3', '#ffffff'];
  window.confetti = function (duration = 2500, density = 1) {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const canvas = document.createElement('canvas');
    canvas.className = 'confetti';
    document.body.appendChild(canvas);
    const ctx = canvas.getContext('2d');
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => { canvas.width = innerWidth * dpr; canvas.height = innerHeight * dpr; };
    resize();
    const count = Math.round(Math.min(260, (innerWidth * innerHeight) / 9000) * density);
    const parts = Array.from({ length: count }, () => ({
      x: Math.random() * canvas.width,
      y: -Math.random() * canvas.height * 0.6,
      w: (6 + Math.random() * 8) * dpr,
      h: (8 + Math.random() * 10) * dpr,
      vy: (2 + Math.random() * 4) * dpr,
      vx: (Math.random() - 0.5) * 2.5 * dpr,
      r: Math.random() * Math.PI,
      vr: (Math.random() - 0.5) * 0.25,
      c: COLORS[Math.floor(Math.random() * COLORS.length)],
    }));
    const start = performance.now();
    function frame(t) {
      const elapsed = t - start;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.globalAlpha = elapsed > duration - 600 ? Math.max(0, (duration - elapsed) / 600) : 1;
      for (const p of parts) {
        p.x += p.vx; p.y += p.vy; p.r += p.vr;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.r);
        ctx.fillStyle = p.c;
        ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        ctx.restore();
      }
      if (elapsed < duration) requestAnimationFrame(frame);
      else canvas.remove();
    }
    requestAnimationFrame(frame);
  };
})();
