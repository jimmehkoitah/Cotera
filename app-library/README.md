# Cotera App Library (prototype)

A mobile-first library people open by scanning a QR code. They pick a problem their team has, see the ready-made Cotera agent for it, and open it in their own Cotera workspace. Private pages hold agents designed for a specific person or company.

The whole app is one static page, `dist/index.html`, so it can be hosted anywhere (Render static site, Netlify, Cloudflare Pages) with no server.

## What's in it

- **Library:** browse the 6 GTM teams or search. 52 agents covering 129 problem statements, from `../cotera-bingo/agent-library/cotera-agent-library.json`. Agents that only cover the retired Support and Risk roles are left out.
- **Agent page:** the visitor's problem, how the agent helps, how it works step by step, how to start small, what data it needs, who uses it, and how to measure it.
- **Open in Cotera / Get this agent:** agents with a Cotera link show "Open in Cotera". The rest show "Get this agent", a request form.
- **My agents:** agents the visitor saved, plus any private page they opened. Remembered on their device; no sign-in.

## Adding Cotera links

Edit `data/links.json` and map agent IDs to the agent's link in your Cotera instance:

```json
{ "A01": "https://...", "A05": "https://..." }
```

Agent IDs are on the Agents tab of the library workbook. Then rebuild.

## Private pages for a person or company

Add an entry to `data/custom.json` under a hard-to-guess code (for example `acme-7k2p9`), with a note, your custom agents and any library agents you recommend. `example-acme` shows the format. Send them `https://<your-site>/#/for/<code>`; opening it adds the page to their My agents. Anyone with the link can see that page, so keep sensitive details out of it.

## Build

```bash
python3 build.py        # writes dist/index.html
```

## Prototype limits

- The request form shows a confirmation but does not send anywhere yet. Next step: store requests and notify you.
- My agents lives in the visitor's browser, so it does not follow them to another device.
