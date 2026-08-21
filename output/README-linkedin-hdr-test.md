# Cotera HDR logo — LinkedIn test kit

SDR + HDR/PQ variants of the Cotera icon, built so that **only the white arrow**
emits above SDR white on an HDR-capable display, while the purple gradient stays
at or below the BT.2408 reference white of 203 nits.

**Upload this one first: `cotera-linkedin-hdr-icon-800nits.jpg`.**
**Look at `cotera-hdr-probe.html` before you upload anything.**

---

## Read this before you post

This is **not a supported LinkedIn feature.** It exploits the fact that LinkedIn
strips gain maps but appears to preserve some embedded ICC profiles. Three things
follow, and the third is the one people miss.

1. It may simply not work, and may stop working without notice.
2. **If LinkedIn strips the profile, the failure is ugly.** The PQ code values get
   read as sRGB and the image renders as a washed-out grey-lilac square — not as
   the normal logo.
3. **Even when it works, SDR viewers pay for it.** A browser that honours the PQ
   tagging does not ignore it on an ordinary screen — it tone-maps the content
   down to headroom that isn't there. Measured in Chromium, every HDR variant
   renders its background **23 % darker** than the sRGB control (99,102,243 →
   76,78,188), and Chrome maps the 203-nit reference white to 191 rather than 255.
   Most of your audience is on an SDR screen. They get a duller mark so that
   HDR-display viewers get the glow.

So: **test on your personal profile first, never on the Cotera company page.**
Post it, look at it, delete it if it renders wrong.

## Test order

| # | File | What you are checking |
|---|------|----------------------|
| 0 | `cotera-hdr-probe.html` | Open locally. Does your own screen show the effect at all, before LinkedIn is involved? |
| 1 | `cotera-linkedin-sdr-icon.jpg` | Baseline. Plain sRGB. What "normal" looks like in your feed on this device. |
| 2 | `cotera-linkedin-hdr-icon-800nits.jpg` | **The primary file.** Arrow at 800 nits ≈ 3.9× SDR white. |
| 3 | `cotera-linkedin-hdr-icon-1200nits.jpg` | Push harder if 800 is too subtle. |

Post each as a normal image post, one at a time — not a carousel, not a document
post; those go through different processing.

### Diagnostic files (do not post these)

| File | Purpose |
|---|---|
| `cotera-linkedin-hdr-icon-800nits-cicp.png` | Same pixels, PNG `cICP` chunk instead of an ICC profile. PNG `cICP` is the *documented* no-gain-map HDR-still path. If this glows and the JPEG doesn't, the JPEG's ICC route is what failed — not your display. |
| `cotera-linkedin-hdr-icon-800nits-fullrange.jpg` | Same pixels, conventional 10000-nit PQ curve and the canonical profile description. Matches the curve shape colour stacks may recognise by identity — but renders near-black (119/255 off) in any viewer that applies the curve without HDR handling. Ship only if proven. |
| `cotera-linkedin-sdr-arrow.jpg` / `-hdr-arrow-800nits.jpg` | Arrow alone on near-black. Highest contrast, so the most sensitive test of whether the effect survives. |

## Where this actually works

| Environment | Result | Why |
|---|---|---|
| Chrome / Edge ≥ 108, desktop, HDR display | **works** | Chromium reads the ICC v4.4 `cicp` tag and prefers it over the profile's curves. Our tuple (9, 16, 0, 1) is the accepted case, and Skia's PQ reference white is 203 nits — the same anchor we encoded to. |
| Chrome on Android 14+, HDR panel | likely | Same Blink path, untested. |
| Safari 26+ on macOS 26+ | **unproven** | WebKit delegates to ColorSync, and nothing in Apple's stack is documented to read the ICC `cicp` tag. Safari's announced no-gain-map HDR stills all signal PQ at the container level (PNG `cICP`, AVIF/HEIF/JXL CICP). JPEG is the one format on that list carrying a gain-map caveat. |
| iPhone / iPad, any browser | **no** | Every iOS browser is WebKit underneath. |
| Firefox, any OS | **no** | No HDR still-image support. |
| Screenshots, thumbnails, previews | **no** | Cannot carry HDR. Judge with your eyes on a live page. |

Before blaming the file: GPU acceleration must be on, macOS EDR headroom collapses
at high panel brightness (test around 50–75 % in a dim room), and Low Power Mode
disables EDR outright.

## Reading the result

| What you see | What it means |
|---|---|
| Only the arrow pops, brighter than page white | **Success.** |
| Nothing pops; looks like the SDR control | Profile stripped or ignored. Fetch the processed image and re-inspect. |
| The whole square glows, purple included | Mask too broad. Re-run with `--mask-mode geometric`. |
| Washed-out, grey, low contrast | Profile stripped. Not a mask problem. Pull the post. |
| Everything looks slightly dark and dull | Expected on an SDR screen — see point 3 above. |

### If it does not glow, check what LinkedIn served

```bash
curl -sL "<posted image url>" -o processed.jpg
exiftool processed.jpg | grep -i -E "profile|color|progressive"
```

`Profile Description : Cotera Rec.2100 PQ …` present → profile survived, problem
is display-side. No ICC profile, or `sRGB IEC61966-2.1` → LinkedIn stripped it,
the trick is dead for that path, pull the post.

## Honest limits of the three tiers

600, 800 and 1200 nits are PQ 8-bit codes **178, 186 and 197** — 19 code values
apart in total. They encode cleanly (the flat arrow interior comes back
byte-exact at quality 98), but browsers tone-map to whatever headroom the display
currently has, so **do not expect to reliably tell the three apart**. Chrome also
assumes a 1000-nit ceiling for a JPEG carrying no mastering-luminance box, so the
1200-nit file is already past what it will render.

The arrow occupies **18 % of the frame**. OLED panels run an automatic brightness
limiter that dims the whole screen when too much of the frame is bright; 5–15 % is
the comfortable range, so on a phone the effect may hold less well than on a
laptop. Reducing the arrow's share of the canvas would trade size for punch.

## Regenerating

```bash
pip install -r cotera-hdr/requirements.txt
python3 cotera-hdr/make_hdr_logo.py       # all assets in output/
python3 cotera-hdr/verify_assets.py       # metadata + colour round-trip checks
python3 cotera-hdr/measure_sdr_cost.py    # what SDR viewers actually see
python3 cotera-hdr/make_preview.py        # SDR ratio simulation
python3 cotera-hdr/build_probe_page.py    # the self-contained probe page
```

Knobs: `--nits 500 700 1000`, `--mask-mode geometric`, `--sdr-white 100`,
`--quality 100`, `--source path/to/logo-long-solid.svg`.

## What is in these files

- **Colour space:** BT.2020 primaries, SMPTE ST.2084 (PQ) transfer.
- **ICC profile:** `Rec2100-PQ.icc`, generated by `cotera-hdr/icc_pq.py` — ICC v4.4
  matrix/shaper with Bradford-adapted BT.2020 colorants, 4096-entry PQ tone
  curves, and a `cicp` tag (primaries 9, transfer 16, matrix 0, full range).
- **TRC normalisation:** anchored at 203 nits rather than the conventional 10000,
  so a colour-managed non-HDR viewer reproduces the artwork correctly and clips
  the arrow to white (1.43/255 from the control) instead of rendering it
  near-black. This is a deliberate departure from the canonical profile; the
  `-fullrange` variant is the canonical alternative.
- **Compositing:** all blending happens in linear light. Compositing a 4×
  brightness step in gamma space leaves a dark fringe on the glyph — measured at
  up to 24/255 on the antialiased edge before this was corrected.
- **JPEG:** progressive, optimized, quality 98, 4:4:4, no alpha, 800 × 800.
- SDR controls carry a real sRGB profile; only HDR variants carry the PQ profile.

### Measured, decoded back out of the saved JPEGs

| File | Arrow median | Background peak | Mask coverage |
|---|---|---|---|
| `hdr-icon-600nits` | 610 nits | 168 nits | 17.98 % |
| `hdr-icon-800nits` | 814 nits | 174 nits | 17.98 % |
| `hdr-icon-1200nits` | 1209 nits | 168 nits | 17.98 % |

Background stays well below SDR white — the purple gradient is untouched. Full
report in `metadata-verification.txt`; SDR-viewer measurements in
`sdr-cost-report.json`.

## If the ICC route fails

The alternative is a **gain-map JPEG** (ISO 21496-1 / Ultra HDR): an SDR base
image plus a per-pixel gain map. Its worst case is clean — when the gain map is
stripped you get the authored SDR image, about 0.6/255 from intended, instead of
a washed-out or darkened one. The catch is exactly why we did not use it here:
gain maps do not survive re-encoding, and LinkedIn re-encodes. PQ + ICC was
chosen because ICC profiles *do* survive re-encoding. That is the whole bet.

## Note on the long lockup

`cotera-logo-long-solid.svg` was **not** generated: no `logo-long-solid.svg` was
present, so there was no wordmark path data to clean up. Drop the real file at the
repo root and re-run — the script parses the gradient, corner radius, arrow paths
and wordmark out of it and emits the cleaned lockup automatically.
