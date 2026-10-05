# Cotera Booth Bingo

A hosted, three-minute Bingo game and a direct three-problem conversation path. Both collect attendee details before role selection. Cotera branding, square choices, durable sessions, a main screen, prize collection and a private attendee export are included.

## Routes and data

- Practice: `/?mode=personal`, `/display?mode=personal`, `/admin?mode=personal`, `/print?mode=personal`.
- Event: the same routes with `?mode=event`. The root defaults to event.
- Older `mode=practice` links now alias personal practice; `mode=live` aliases event.
- Practice and event use separate D1 records (`hosted:personal`, `hosted:event`) and HttpOnly cookies. Old line-based game records are preserved, not migrated into the new game.
- `/review.html` remains the persona copy review, not the live game.

## The attendee journey

Welcome → Play Bingo or Share three problems → name, company, one contact method and consent → role → chosen path. Details are saved before role selection so an unfinished registration is still in the private export. Returning in the same browser restores the session. No password or background notifications.

**Bingo:** Each round lasts five minutes. The event offers six GTM roles (Support and Risk are retired from the picker and caller but remain readable in old records). Every role gets six square tiles (five role problems and one shared AI problem). The caller draws three of those six per role, shuffled across the six roles in three passes. Calls arrive every 12 seconds, with the final call at 3:24 and about 1.5 minutes left for matching, so attendees can walk around and check back. Every card has exactly three callable matches by the end. A person must tap all three before the round ends; no row, column or diagonal is required. Earlier calls remain available. A new card arrives with the next round; earned codes stay saved. First entry starts a ten-second lead-in if the room is not paused. Phones show the caller, so a TV is optional.

**Direct path:** Choose exactly three distinct role-relevant problems from paginated square tiles and submit them. This records actual reported problems and can award a kit immediately, without Bingo. It remains available during a Bingo pause. Attendees can switch paths and Bingo winners can subsequently report real problems.

**Prizes:** One code per registered attendee across both paths and all rounds. Kit stock is one atomic pool. Blank stock means unlimited; set the physical stock before the event. Exhausted stock still records Bingo or reported problems, without issuing a code. Reducing stock never revokes existing awards. Booth staff mark codes collected; attendees see that state on their phones.

**Tracking:** Bingo matches are explicitly labelled participation, not pain endorsement. Registrations, game matches, reported problems, notes and prize status are exportable in an admin-only CSV. The main screen shows anonymous role-level wins, calls and approved notes. It never exposes contact details or prize codes.

## Booth operation

Open `/admin?mode=event` with the existing booth PIN. Set kit count, open the main screen, and use the event QR. Pause/resume freezes and restores Bingo time. A scheduled panel announcement pauses the caller and starts a fresh round on the first request at or after the scheduled time. New players cannot override the panel pause. End event blocks new registrations and gameplay but keeps earned codes available for collection. Practice has a Preview next call button for rehearsals; the server rejects this action in event mode.

Attendees may save up to three written notes. Notes appear anonymously on the main screen only after booth approval. Notes do not earn extra kits.

## Implementation

React/Vinext on a Sites Cloudflare Worker, with D1 storage. `lib/hosted-game.mjs` holds the new rules. API writes use compare-and-swap updates and retry complete business operations after a version conflict. Matching, reported problems and notes have idempotency keys; prize assignment shares their atomic commit. One-second polling while visible and five-second polling in a background page keep phones and the caller aligned. Timing comes from the server, with client clock-offset correction. Rounds advance on demand without an external timer job.

Contact normalization rejects duplicate registration from another browser; knowing a contact address does not grant access to its session. Player sessions use random HttpOnly SameSite cookies. Admin uses a server-signed, twelve-hour session, rate-limited PIN login and same-origin writes. CSV formula cells are escaped. This is an event-sized design, not a general multi-tenant platform.

The old `lib/game.mjs`, `app/legacy-ui.tsx` and old tests retain the former rules for reference. The old HTTP integration scripts do not target the new API; use `test/hosted-integration.mjs` for this release.

## Local development and verification

Node 22+. Dependencies and the local D1 migration are already initialized in this checkout. Set ADMIN_PIN and ADMIN_SECRET in ignored `.dev.vars`, then run `npm run dev`. Do not reset `.wrangler/state` to restart the preview.

- `npm test`: 32 checks, including 13 hosted-game checks and preserved legacy checks. The fairness test simulates 320 cards across all eight roles.
- `npx tsc --noEmit`: type check.
- `npm run build`: Worker/client production build.
- `node test/hosted-integration.mjs`: local practice only; requires local network permission and the existing local PIN file at `../../work/admin-local.json`. Creates 24 practice attendees, advances the practice caller, checks eight wins, twelve duplicate taps, isolation, both paths, a sixteen-person last-kit race, CSV, privacy and access controls. It preserves the stock setting. Do not run during a human rehearsal.

Browser rehearsals completed both onboarding paths, three-match Bingo, post-win reported problems without another code, direct-path prize award, returning sessions, and booth redemption. At a 390px viewport, the six problem tiles measured 173×173px with no horizontal overflow.

## Publishing and final event rehearsal

This revision is local only. The existing public URL still serves an older version because the Sites source-publication workflow was rejected by automatic approval review while terminal approvals are disabled. Local QR codes point to this computer and must not be distributed.

After publication, use the checklist in ACCEPTANCE.md on actual iPhone and Android devices and venue connectivity. Expected attendance, event timing and physical kit stock still need to be supplied. Keep real event data separate from practice and export it at event close.
