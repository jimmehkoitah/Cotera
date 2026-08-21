---
name: hdr-logo-glow
description: Build HDR logo and brand assets that render brighter than white on HDR-capable displays, so the mark physically emits more light than surrounding feed content. Covers PQ/ST 2084 encoding, CICP tagging (AVIF nclx, PNG cICP), gain-map JPEG construction (Ultra HDR / ISO 21496-1), Rec.2100 PQ ICC profile generation, linear-light compositing, and byte-level verification. Use this skill whenever someone wants a logo, icon, or graphic to glow, look brighter, pop, or stand out in a social feed; mentions HDR images, HDR ads, the "glowing logo" or LinkedIn brightness trick, gain maps, Ultra HDR, PQ, ST 2084, BT.2100, BT.2020, cICP, nits, or SDR white; asks whether an image is "really HDR"; or wants to make brand artwork brighter than an ordinary white pixel. Also use it to diagnose why an HDR image looks washed out, grey, or too dark.
---

# HDR logo glow

Make a brand mark emit more light than the white pixels beside it.

## The mechanism, in one paragraph

An ordinary image is *relative*: `#ffffff` means "as bright as this display shows
white", and nothing in the file can ask for more. HDR encodings break that
ceiling. The reference point that makes any of it meaningful is **203 nits** —
SDR/diffuse white per ITU-R BT.2408, i.e. what a white pixel in a normal image
is understood to mean. Authoring a mark at 900 nits asks the display for ~4.4×
the light of the white pixels around it. The result is not that the logo looks
*whiter*; it is that everything else on screen looks *dim*. That ratio, not the
absolute number, is what the eye reads as glow.

## Do this first: pick the format from the failure mode, not the spec sheet

There are three ways to signal HDR, and choosing between them is the single
decision that determines whether the work survives contact with a platform.

| | Mechanism | Survives re-encode | Fallback when the signal is lost |
|---|---|---|---|
| **Gain map JPEG** | SDR base + per-pixel gain map (ISO 21496-1 / Ultra HDR / Adaptive HDR) | No | **Clean.** You get the authored SDR image, ~0.6/255 from intended |
| **CICP** (AVIF `nclx`, PNG `cICP`) | Code points declaring BT.2020 + PQ | No | **Breaks.** PQ values read as sRGB: ~30/255 off, washed out |
| **PQ + ICC profile** (JPEG) | 8-bit PQ pixels + a BT.2100 PQ ICC profile | **Yes** | **Breaks badly.** Colour-managed by a non-HDR viewer → mean luma ~18/255, near-black |

Those numbers are measured, not estimated — see `references/measurements.md` for
how to reproduce them.

**Default to the gain-map JPEG.** Not because it is the most faithful (CICP AVIF
is), but because it is the only one whose worst case is "a correct, normal image".
Every other option's worst case is a visibly broken logo in front of an audience.

Reach for the others deliberately:
- **CICP AVIF/PNG** when you control delivery (your own site, a local test) and
  want the cleanest HDR and tiny files.
- **PQ + ICC JPEG** only as an experiment on a pipeline you suspect transcodes.
  ICC does survive re-encoding, which is a real advantage, but ICC is a *colour
  management* mechanism — it carries no "this is absolute luminance" signal — so
  nothing guarantees a viewer grants it headroom. Never present it as guaranteed
  HDR.

If someone asks for HDR JPEG with an ICC profile specifically, build it, but show
them the fallback measurement before they publish it.

**On the ICC-survives-LinkedIn claim.** It is widely repeated as confirmed by
several independent tools. It is not: every published source traces back to a
single 2026 write-up, and no byte-level diff of an upload against the served
rendition has ever been published. The "verify with exiftool" step those tools
recommend inspects their own pre-upload output, which never had a gain map — it
tests nothing about the platform. Treat the ICC route as a plausible untested
hypothesis, and run the download-and-diff yourself rather than citing anyone.

## Workflow

```bash
S=<this skill>/scripts

# 1. Generate. Point it at a mark (SVG or PNG with alpha).
python3 $S/build.py --mark logo.svg --out out/ \
    --layout bleed --gradient "#322f82,#6366f2" --glow-hex "#6366f2" \
    --size 1200x1200 --preset default

# 2. Verify the bytes, never the encoder's word for it.
python3 $S/validate.py out/*.jpg out/*.png out/*.avif

# 3. Show the effect on an SDR screen honestly.
python3 $S/simulate.py --mark logo.svg --out out/headroom.png
```

`build.py --help` lists the layouts, presets and brand inputs. Read
`references/pipeline.md` before changing the compositing itself.

## The four rules that produce most of the bugs

These are worth understanding rather than copying, because each one shows up as a
distinct visual artefact that is easy to misdiagnose as "HDR looks bad".

**1. Composite and downsample in linear light.** Averaging gamma-encoded pixels
across a 4× brightness step darkens the average, so the mark gets a dark fringe.
If a glowing logo has a mysterious outline, this is why.

**2. Author the SDR rendition; do not tone-map into it.** Build both renditions
from the same geometry at different luminances — mark at 900 nits for HDR, mark
at exactly 203 nits for SDR. If the two differ in *shape*, the gain map between
them encodes shape as well as light, which is the exact artefact gain maps exist
to prevent. Keep geometry and luminance separate in the code and this is free.

**3. Render brand artwork at its true values, never normalised to its own
brightest pixel.** Scale so `#ffffff` *in the artwork* lands on your chosen nit
level and let every other colour fall where the designer put it. Normalising by
the artwork's brightest pixel stretches the brand colour toward white — a deep
indigo comes out lavender, and the client will notice immediately.

**4. Glow goes on top of the panel, and gets clipped to it.** Underneath, the
panel simply hides the halo — the opposite of light spilling out of the mark. And
if the halo runs past a panel edge onto a darker ground, it lights that ground at
the boundary and draws a bright rim around the whole logo, which reads as an
unwanted border. Clip the glow to the panel alpha.

## Luminance targets

Only the mark and its spill should exceed SDR white. A brand panel belongs *at*
203 nits — it should look like the ordinary logo, not glow on its own.

| Preset | Mark | vs SDR white | Reads as |
|---|---|---|---|
| `subtle` | 450 nits | 2.2× | noticeable, deniable |
| `default` | 900 nits | 4.4× | clearly emitting |
| `strong` | 1400 nits | 6.9× | aggressive |
| `obnoxious` | 2400 nits | 11.8× | named as a warning |

Watch the reported **average picture level**. OLEDs dim the entire panel when too
much of the frame is bright (auto-brightness limiter), so a bright mark on a dark
or mid frame holds its peak far better than a bright mark on a bright frame. Keep
the fraction of the frame above SDR white in the 5–15% range; a mostly-hot frame
gets clamped and looks worse than a restrained one.

## Verification

Structural validity and "renders as HDR" are different claims. Keep them apart,
and never report the second when you have only established the first.

`validate.py` parses produced bytes: CRCs, chunk order, CICP code points, the MPF
index, and — the check that actually matters for gain-map files — whether the
recorded offset of the second image lands exactly on a JPEG `SOI` marker. It
classifies files from their content, so an SDR control is reported as
intentionally untagged rather than as a broken HDR file.

Cross-check with a second implementation rather than trusting one tool:

```bash
exiftool -a -G1 out/asset.jpg | grep -iE "profile|mpf|color|encoding"
avifdec --info out/asset.avif
python3 -c "from PIL import ImageCms; print(ImageCms.getProfileDescription(ImageCms.getOpenProfile('p.icc')))"
```

Confirming the glow itself needs a real HDR display. `simulate.py` produces an
honest contact sheet for an SDR screen — it holds the panel peak fixed and lets a
reference `#ffffff` swatch fall to grey as headroom grows, which is what the eye
actually experiences. A plain screenshot of an HDR image is always a lie; say so
rather than presenting one as evidence.

## Never fake it

If asked for a specific profile or tagging you cannot legitimately produce, stop
and name the missing dependency. Do not ship a file labelled HDR that is not, and
do not copy a vendor's ICC profile into someone's brand assets — that embeds
their copyright string in your client's files. `scripts/icc_pq.py` generates a
BT.2100 PQ profile from scratch instead, so every byte is accounted for.

Be similarly careful with profiles of unknown provenance. A profile claiming
Apple authorship on a Linux box did not come from Apple.

## Reference files

- `references/pipeline.md` — the compositing model, gain-map maths, layouts, and how to add a format
- `references/containers.md` — exact byte layouts: PNG `cICP`/`mDCV`/`cLLI`, MPF index, ICC structure, CICP code points
- `references/measurements.md` — the survival and fallback numbers, and how to re-measure them
- `references/platforms.md` — what each platform does, and how to test an upload end to end
- `../../../hdr-logo/RESEARCH-BRIEF.md` (this repo only) — a full verified research brief with byte layouts, code points, refuted claims, and the LinkedIn sourcing analysis

## Requirements

`python3` with `numpy`, `scipy`, `Pillow`. `rsvg-convert` (librsvg) to rasterise
SVG. `avifenc` (libavif) for AVIF. `exiftool` for cross-checking. The PNG writer,
gain-map builder and ICC generator have no dependencies beyond Pillow — Pillow
cannot write 16-bit RGB PNGs and other encoders stamp colour chunks that compete
with `cICP`, so those containers are emitted byte by byte.
