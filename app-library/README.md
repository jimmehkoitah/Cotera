# Cotera App Library (prototype)

A mobile-first library people open by scanning a QR code. They pick a problem their team has, see the ready-made Cotera agent for it, and open it in their own Cotera workspace.

The app is a static site, `dist/`, so it can be hosted anywhere (Render static site, Netlify, Cloudflare Pages) with no server.

## What's in it

- **Library:** browse the 6 GTM teams, or see all agents. 52 agents covering 129 problem statements, from `../cotera-bingo/agent-library/cotera-agent-library.json`. Agents that only cover the retired Support and Risk roles are left out.
- **Search on every page:** the bar at the top (and the Search tab) searches problems, agents and teams. Product names such as Salesforce, HubSpot, Gong or Zendesk find what the product is (CRM, call transcripts, tickets), because the agents are written for any tool. Results have their own link, so Back returns to them.
- **Back links on every page:** each page except the home page starts and, on long pages, ends with a Back link to where the visitor came from, or to the page above it when they opened a link directly. Back returns to the same scroll position.
- **Agent page:** the visitor's problem, how the agent helps, how it works step by step, how to start small, what data it needs, who uses it, and how to measure it.
- **Open in Cotera / Get this agent:** agents with a Cotera link show "Open in Cotera". The rest show "Get this agent", a request form.
- **My agents:** agents the visitor saved with the heart. Remembered on their device; no sign-in.

## Adding Cotera links

Edit `data/links.json` and map agent IDs to the agent's link in your Cotera instance:

```json
{ "A01": "https://...", "A05": "https://..." }
```

Agent IDs are on the Agents tab of the library workbook. Then rebuild.

## Private pages (not in use)

The app can still show a private page of custom agents for one person or company, but none are published: custom agents are handed out directly instead. To publish one, add an entry to `data/custom.json` under a hard-to-guess code (letters, digits, `-` and `_`), then rebuild and send `https://<your-site>/#/for/<code>`:

```json
{ "acme-7k2p9": { "for": "Acme Robotics", "title": "Agents we sketched after our chat", "note": "...",
    "agents": [{ "id": "C1", "name": "...", "what": "...", "how": ["step one", "step two"], "link": "https://app.cotera.co/share/..." }],
    "library": ["A05", "A06"] } }
```

Each page is published as its own file, `dist/for/<code>.json`, not inside the main page. Anyone with the link can see it, so keep sensitive details out.

## Build

```bash
python3 build.py        # writes dist/index.html and dist/for/*.json
```

The build also copies the brand fonts from `assets/fonts` (Inter, Newsreader and DM Mono as small Latin WOFF2 files, SIL Open Font License) to `dist/fonts`, writes `dist/favicon.svg` from the Cotera logo mark, and copies `assets/apple-touch-icon.png`. The site makes no third-party requests.

## Prototype limits

- The request form shows a confirmation but does not send anywhere yet. Next step: store requests and notify you.
- My agents lives in the visitor's browser, so it does not follow them to another device.
