# Bake-off Scorecard

Run the same tests on both builds. Mark each one pass or fail. Fewest fails wins; if tied, pick the one that
looks and feels better on a phone and on the TV.

## What you need
- Two phones (ideally one iPhone, one Android), the TV or a laptop on the display page, and the admin page open
  on a third screen or tab.
- A few "extra players": open the game in a **private/incognito window**. Each private window counts as a new
  person.

## Before you start (both builds)
1. Admin: **Start fresh** (wipes old test data).
2. Admin: set the **cooldown to 0** so you can tap quickly. Set it back to 10 at the end and check it sticks.

## Tests

| # | Do this | Pass if | Claude | Astra |
|---|---|---|---|---|
| 1 | Scan the QR (or open the link) on each phone and sign up | Takes under 30 seconds; LinkedIn is the first contact option; there's a privacy line | | |
| 2 | Claim a square on phone A | It fills on phone B and the TV within about a second | | |
| 3 | On both phones, open the same square and hit Claim at the same moment | Exactly one gets it; the other sees "just taken" | | |
| 4 | Tap any open square | It shows the full text first and only claims when you press Claim | | |
| 5 | After a claim (cooldown back at 10 for this one) | "Is this real for you?" appears, then a cooldown countdown | | |
| 6 | Have 5 different people (phones + private windows) each claim | All 5 see "grab a Coco kit" with a code; the 6th person does not | | |
| 7 | Complete lines with different people | First 3 line-completers on a board get a kit screen with a code; the 4th sees "You completed a line!" with no prize | | |
| 8 | Have someone who already won a line kit complete another line | Celebration, no second kit | | |
| 9 | Look at the TV the whole time | Shows count, line progress ("B column 4/5"), celebrations, and a QR code; **never** a name, company, or anything about kits | | |
| 10 | Fill all 25 squares | A new board appears on its own with different pain points | | |
| 11 | Refresh a phone, then sign up again on a new private window using the **same** contact info | Phone remembers you after refresh; same contact counts as the same person (cooldown still applies) | | |
| 12 | Admin: undo a claim, mark a kit handed over, change cooldown and cap, pause | Each works immediately; paused game blocks claims | | |
| 13 | Admin: download the CSV and open it in Google Sheets | Opens cleanly; one row per claim with name, company, contact, pain point, wedge, persona, "real?" answer, kit info | | |
| 14 | Turn a phone's Wi-Fi off for 30 seconds, then back on; reload the TV page | Both catch up to the current board without help | | |

## After the bake-off
- Admin: **Start fresh** on the winner so the event starts with an empty board and a clean first-five count.
- Set the cooldown back to **10** and the line-kit cap to **3**.
- Only the winner stays live. The QR points at it.
