fetch('/api/config').then((r) => r.json()).then((c) => { document.getElementById('url').textContent = c.shortUrl; }).catch(() => {});
document.getElementById('printBtn').addEventListener('click', () => window.print());
