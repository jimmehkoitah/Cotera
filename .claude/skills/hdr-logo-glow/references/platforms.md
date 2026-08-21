# Platforms and testing

## What decides whether the effect appears

Three things must all hold. Diagnose in this order — it saves a lot of confusion.

1. **The display has headroom available.** Phone OLEDs and mini-LED laptops do;
   most desktop monitors do not. Headroom also shrinks as screen brightness
   approaches maximum, so *lower* brightness in a dim room often shows the effect
   better than max brightness.
2. **The viewer honours the signal.** CICP in AVIF/PNG and gain maps in JPEG are
   the mechanisms with real support. An ICC PQ profile is colour management, not
   an HDR signal, and may simply be converted to SDR.
3. **The platform did not strip it.** This is where most attempts die. See
   `measurements.md`.

If a CICP AVIF opened locally does not glow on the device, nothing served over a
platform will either. Establish that baseline before testing uploads — it
separates "my file is wrong" from "the platform stripped it".

## Testing an upload end to end

```bash
# 1. Post the file. Then fetch back what the platform actually serves.
curl -sL -o processed.jpg "<CDN url from the published post>"

# 2. Compare against your source.
ls -l source.jpg processed.jpg            # identical size hints at byte passthrough
exiftool processed.jpg | grep -iE "profile|color space|encoding|components"
exiftool -MPF:all processed.jpg           # gain map alive => "Number Of Images : 2"
python3 scripts/validate.py processed.jpg
```

Reading the result:

- **Same bytes / same size** — best case, the platform served your file untouched.
- **ICC profile intact, gain map gone** — the pipeline transcodes but preserves
  colour management. The ICC route is viable here; the gain-map route is not.
- **No profile, no MPF** — everything was stripped. No source-side change fixes
  this.
- **`Profile Description: sRGB`** — worse than stripping. The pixels were
  reinterpreted, so PQ values are now being read as sRGB and the image is wrong.

Always upload an SDR control alongside and compare them in the same scroll. The
eye adapts within seconds, so judging glow from memory does not work.

**A screenshot cannot capture this.** Screenshots are SDR; the HDR and SDR
versions will look identical in one even when the difference is obvious in person.
If someone offers a screenshot as proof the effect works, it proves nothing —
and never present one as evidence yourself.

## Platform notes

Verify current behaviour rather than trusting any table, including this one —
these pipelines change without announcement, and several platforms have moved to
clamp HDR in feeds after users complained about brightness abuse.

- **Feed images vs avatars** — avatars are aggressively resized to small squares
  and are the least likely surface to preserve anything. Feed images are the
  better bet on any platform.
- **Native app vs web** — often different rendering paths. Check both.
- **Instagram/Meta, Apple, Chrome/Android** have all shipped HDR-limiting
  controls or tone-mapping at some point. Expect clamping to increase over time,
  and treat any working recipe as perishable.

## Accessibility and restraint

This makes a phone emit more light at someone without their consent. That is
worth taking seriously and not only as a compliance matter:

- Bright flashes are a genuine problem for people with photosensitivity, migraine
  and light sensitivity.
- Sustained high luminance draws battery and heats the panel.
- It is a commons: the technique works because it is rare. If everyone does it,
  nobody stands out and platforms clamp it for all.

Practical restraint: keep the frame's bright fraction low so only the mark is
hot, avoid full-frame maximum luminance, never animate or flash it, and prefer
`subtle`/`default` over `strong`. A mark at 4× SDR white on a calm frame reads as
premium. A whole frame at 12× reads as an advert someone will mute you for.
