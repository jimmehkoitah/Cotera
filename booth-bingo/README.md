# Cotera Booth Bingo

Live GTM pain-point bingo for Cotera's booth at **Architecting AI-Native GTM** (Mon Oct 5, 2026, 4 to 7 PM PT,
Eragon HQ, 575 Market St Suite 2450). Rules: [`SPEC.md`](SPEC.md). Bake-off scorecard: [`ACCEPTANCE.md`](ACCEPTANCE.md).
Pain points: [`pain-points.json`](pain-points.json) (4 sets of 25, edit freely, then redeploy).

## The four pages

| Page | Who | Address |
|---|---|---|
| Play | Attendees (the QR code points here) | `/` |
| Live board | The booth TV | `/display` |
| Admin | Jim, PIN protected | `/admin` |
| QR card | Printing | `/print` |

## Event-day checklist (Monday)

**3:30 PM, setting up**
1. TV: open `/display` in Chrome, click once anywhere to go fullscreen. Turn off the laptop's sleep.
2. Your phone: open `/admin`, enter the PIN.
3. Admin: **Start fresh** (type RESET). This clears all test data so the first-five count starts at zero.
4. Admin: check **Cooldown = 10** and **Line kits per board = 3**.
5. Do not claim a square yourself after this point: your claim would use up one of the first-five kits.

**4:00 to 7:00 PM, during the event**
- Winners show you a code on their phone. Find it under **Kits to hand over** and tap **Handed over**.
- Someone claimed by accident? Find them in the **Live feed** and tap **Undo**.
- Running low on kits? Set **Line kits per board** to 0. First-five kits are already finished after the first five people.
- Need a breather? **Pause** stops new claims; **Resume** starts them again.
- TV looks frozen? Reload the page and click once for fullscreen.
- An attendee's phone won't load? Ask them to switch between cell data and Wi-Fi.

**7:00 PM, wrapping up**
1. Admin: **End game**.
2. Admin: **Download CSV**. One row per claim, with name, company, contact, pain point, wedge, persona, and their
   "Is this real for you?" answer. Opens directly in Google Sheets.
3. Leave the app up for an hour so winners can still show their codes, then shut the Render services down.

## Running it locally (developers)

Needs Node 22 and Postgres.

```bash
npm install
DATABASE_URL=postgres://user@localhost:5432/bingo ADMIN_PIN=1234 npm start   # http://localhost:3000
npm test                                     # rules + database tests (TEST_DATABASE_URL for the db tests)
BASE=http://localhost:3000 node test/simulate.js                        # 60-player load simulation (wipes data)
NODE_PATH=$(npm root -g) BASE=http://localhost:3000 node test/e2e.cjs   # browser checks + screenshots (wipes data)
```

Environment variables: `DATABASE_URL` (required), `ADMIN_PIN` (required on Render), `PUBLIC_URL` (defaults to
Render's URL; used for the QR code), `COOKIE_SECRET` (keeps admin logged in across restarts), `PGSSL=true` for
external database URLs, `RATE_LIMIT_SCALE` (raise if one venue network sends unusually heavy traffic).
