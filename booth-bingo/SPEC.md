# Cotera Booth Bingo: Product Spec

The rules every build is judged against. Stack-agnostic. If anything here conflicts with `ACCEPTANCE.md`, this
file wins on rules and `ACCEPTANCE.md` wins on how a rule is tested.

## 1. Purpose and setting

A live, shared bingo board of GTM pain points that attendees play on their phones at Cotera's booth.

- **Event:** "Architecting AI-Native GTM" (Amdahl, #SFTechWeek), Monday Oct 5, 2026, 4:00 to 7:00 PM PT,
  Eragon HQ, 575 Market St Suite 2450, San Francisco. Panels run 4:40 to 6:00, so most booth traffic is
  4:00 to 4:40 and 6:00 to 7:00.
- **Goal 1:** every claimed square becomes a conversation between the attendee and Jim (Cotera's only rep on site).
- **Goal 2:** every claim becomes a lead row for follow-up: who, which company, how to reach them, which pain
  they claimed, and whether it is real for them.
- **Prize:** "Coco by Cotera" hot chocolate kits, handed out by hand. Software only tells Jim when someone has
  earned one.
- Jim is running the booth solo and also giving demos, so the game must run itself.

## 2. Three surfaces

| Surface | Who | Where |
|---|---|---|
| Phone | Attendees, after scanning the QR code | `/` |
| Display | The booth TV (landscape, 1920x1080) | `/display` |
| Admin | Jim (PIN protected) | `/admin` |

A printable QR card (`/print`) is a nice-to-have.

## 3. The board

- 5 columns headed **B I N G O**, 5 rows numbered 1 to 5. Squares are named column letter + row number
  (`B1` top-left, `O5` bottom-right). Index `i = row * 5 + col`, zero-based, row-major.
- Each square holds one pain point from the current set. The grid shows `short`; tapping shows `full`.
- There is no free center square.
- **12 lines:** 5 rows, 5 columns, 2 diagonals (`B1 I2 N3 G4 O5` and `O1 G2 N3 I4 B5`).
- Everyone (all phones and the display) sees the same board, updated live (target: under 1 second).

## 4. Pain points (`pain-points.json`)

- 4 sets of 25. Each item: `id`, `short` (max 24 chars), `full` (max 90 chars), `wedge`, `persona`.
- `wedge` is one of `W1` Account Targeting, `W2` Buyer Readiness, `W3` Customer Risk & Growth, `W4` Market
  Intelligence, `W5` Operational Intelligence, `PLATFORM` Agent Platform (build vs. buy).
- `wedge` and `persona` are **never shown to players or on the display**. They appear only in admin and the CSV.
- A board uses one whole set, with positions shuffled.
- The first board of the event uses set 1. When a board fills up, the next board uses the next set in order
  (1, 2, 3, 4, then back to 1). The next board never reuses the set that just finished.
- The content is data. Changing the JSON (and restarting) changes the squares; no code changes.

## 5. Players and sign-in

- Quick form, one screen, no passwords, no OAuth, no text codes:
  - **Name** (required)
  - **Company** (required)
  - **One way to reach you** (required), picked with tabs in this order: **LinkedIn** (profile URL or handle),
    **Phone**, **Work email**. Light validation only: LinkedIn must contain a handle, phone must have 7 to 15
    digits, email must look like an email.
  - Consent line under the button: "By playing, you agree Cotera may follow up about what you claim."
    with a link to https://cotera.co/legal/privacy.
- The phone remembers the player (token stored on the device). Refreshing or re-scanning does not ask again.
- **One person, one player.** Contact values are normalized (email lowercased; phone digits only, 10-digit US
  numbers get a leading 1; LinkedIn reduced to the `/in/handle` part, lowercased). Registering again with the
  same contact (new phone, cleared browser) returns the same player, keeps their cooldown and kit history, and
  updates name/company to the latest.

## 6. Claiming a square

1. Tap an open square: a sheet opens with the full pain point and a **Claim this square** button.
   (No claim on the first tap, to prevent accidental claims on a small grid.)
2. Tap **Claim**. The server decides. Exactly one person can get a square, even if two tap at the same instant.
3. If someone else got it first: "Just taken, pick another." The board updates.
4. On success: the square fills on every screen, then the phone asks **"Is this real for you?"** with three
   buttons: **Big one / Somewhat / Just playing**. Optional, one tap, can be skipped. Stored on the claim.
5. **Cooldown:** after a claim, that player waits **10 minutes** (admin-adjustable, 0 allowed) before their next
   claim. The phone shows a live countdown. The board stays visible during the cooldown.

## 7. Kits (prizes)

A claim earns at most **one** kit. Rules, checked in this order:

1. **First five:** the first 5 distinct players to make a claim in the event each earn a kit on their first claim
   ("You're claim #3 today, grab a Coco kit from Jim!"). Per event, not per board.
2. **Line win:** a claim that completes one or more lines earns a kit if **both**:
   - fewer than **3** line kits have been awarded on this board (cap is admin-adjustable live), and
   - this player has never earned a line kit before (max one line kit per person per event).
   Completing several lines at once still earns one kit and uses one slot of the cap.
3. Otherwise no kit. A line can still complete (the display celebrates it); the player just sees
   "You completed a line!" with no prize promise.

If a first-five claim also completes a line, the player gets the first-five kit and the line does **not** use a
slot of the board's cap.

**Winner screen:** full screen on the claimant's phone: what they won, "Show this screen to Jim", and a short
redemption code (4 characters, no look-alike characters such as 0/O, 1/I). It stays available from a button on
the phone until Jim marks it handed over.

## 8. Board reset

- When the 25th square is claimed, that claim is processed normally (it can complete lines and win), then the
  board closes and a fresh board with the next set opens immediately.
- The display shows a short "Board complete! New board" moment.
- There is no limit on resets.

## 9. The display (booth TV)

Landscape, readable from 3 meters:
- The big B-I-N-G-O board with claimed squares visibly filled.
- "17 / 25 claimed" and the board number.
- Line progress, with the hottest lines first (e.g. "B column 4/5", "Row 3 4/5", "Diagonal 3/5").
- A celebration when a line completes ("Row 3 complete!") and when a board fills.
- A large QR code and short URL so people walking by can join from the screen.
- Stays awake (Screen Wake Lock where supported) and reconnects by itself.

**Never shown on the display, anywhere:** player names, companies, contact info, or anything a player typed;
who won; whether any kit was earned or handed out; wedge/persona tags. The display shows board progress only.

## 10. Admin (Jim)

PIN protected (PIN set by environment variable). Must work on a phone.
- **Live feed:** every claim, newest first: time, square, pain point, wedge, persona, name, company, contact,
  "real?" rating, outcome.
- **Kits:** earned-but-not-handed-over kits with name, code, reason; a **Handed over** button.
- **Undo claim:** for claims on the current board. Reopens the square, voids that claim's kit if not yet handed
  over, and clears that player's cooldown. Other players' kits are not touched.
- **Controls:** pause/resume claiming, end game (no more claims), skip to the next set, cooldown minutes, line-kit
  cap per board.
- **Start fresh:** wipes all players, claims, kits, and boards (for clearing test data before doors open).
  Requires typing a confirmation word.
- **Download CSV** (see below).

## 11. CSV export

One row per claim (undone claims excluded), UTF-8 with BOM, opens cleanly in Google Sheets and Excel.
Columns: `timestamp_pt`, `board_no`, `set_no`, `square`, `pain_point_short`, `pain_point_full`, `wedge`,
`wedge_name`, `persona`, `player_name`, `company`, `contact_type`, `contact_value`, `real_pain_rating`, `outcome`
(`first_five_kit`, `line_kit`, `line_no_kit`, `none`), `lines_completed` (e.g. `Row 3; B column`), `kit_code`,
`kit_handed_over` (`Y`/`N`), `kit_handed_over_at_pt`.

## 12. Reliability

- Phone page must load fast on weak cell signal (keep it small; no heavy frameworks).
- Phones and the display recover on their own after a network drop and resync to the latest board.
- If a claim cannot reach the server, the phone says so and offers a retry. It never shows a claim as
  successful unless the server confirmed it.
- Many attendees on venue Wi-Fi share one IP address, so any rate limiting must allow that.
- Everything user-typed is shown as plain text (never as HTML), with length limits.

## 13. Non-goals

LinkedIn/OAuth sign-in, text-message codes, live Google Sheet sync, claiming on someone's behalf, any public
leaderboard of people or prizes, a native app.
