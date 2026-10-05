// Serves the built Worker on Render with Miniflare: the same workerd runtime and local D1
// (SQLite on the persistent disk) that `wrangler dev` uses, without wrangler's DevTools proxy,
// which keeps every inspector message in memory and exhausts RAM under event traffic.
// Env: PORT, STATE_DIR, PUBLIC_HOSTNAME (or PUBLIC_ORIGIN for local checks), ADMIN_PIN, ADMIN_SECRET.
// Run after `npm run build`.
import {readFileSync, readdirSync, statSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Log, LogLevel, Miniflare} from 'miniflare';

for (const key of ['STATE_DIR', 'ADMIN_PIN', 'ADMIN_SECRET']) {
  if (!process.env[key]) throw new Error(`${key} must be set`);
}
const origin = process.env.PUBLIC_ORIGIN || (process.env.PUBLIC_HOSTNAME && `https://${process.env.PUBLIC_HOSTNAME}`);
if (!origin) throw new Error('PUBLIC_HOSTNAME must be set');

const root = fileURLToPath(new URL('../dist/server/', import.meta.url));
const config = JSON.parse(readFileSync(join(root, 'wrangler.json'), 'utf8'));
const main = join(root, config.main);
const modules = [];
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (name === '.wrangler' || name === '.vite') continue;
    if (statSync(path).isDirectory()) walk(path);
    else if (/\.m?js$/.test(name)) modules.push({type: 'ESModule', path});
  }
})(root);
modules.sort((a, b) => Number(b.path === main) - Number(a.path === main));

const mf = new Miniflare({
  host: '0.0.0.0',
  port: Number(process.env.PORT || 10000),
  log: new Log(LogLevel.WARN),
  modules,
  modulesRoot: root,
  compatibilityDate: config.compatibility_date,
  compatibilityFlags: config.compatibility_flags,
  bindings: {ADMIN_PIN: process.env.ADMIN_PIN, ADMIN_SECRET: process.env.ADMIN_SECRET},
  d1Databases: {DB: config.d1_databases[0].database_id},
  d1Persist: join(process.env.STATE_DIR, 'v3/d1'),
  assets: {directory: join(root, config.assets.directory), routerConfig: {has_user_worker: true}},
  // The API compares the browser Origin with the request URL, so requests must carry the public HTTPS origin.
  upstream: origin,
});

const url = await mf.ready;
console.log(`Cotera Bingo ready on ${url.href} for ${origin}`);
for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, async () => {
    await mf.dispose();
    process.exit(0);
  });
}
