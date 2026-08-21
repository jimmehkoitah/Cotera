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

Verify current behaviour rather than trusting any table, including this one.
These pipelines change without announcement.

**Sourcing discipline matters more than usual here.** The public knowledge on
this topic is a handful of hobby repos that mostly cite one another. Counting
derivative repos as independent replications is a common-source fallacy, and it
is how "one blog post" becomes "confirmed by five tools". Before repeating any
claim about a platform's pipeline, check whether the sources actually trace to
separate observations — and prefer a test you ran yourself over any of them.

The decisive test nobody publishes is trivial: upload, download the served
rendition, and diff it against the source. Do that rather than citing.

### Established as of August 2026

- **CSS `dynamic-range-limit`** (CSS Color HDR Level 1): `standard` |
  `constrained` | `no-limit`, **initial value `no-limit`**, inherited. Chrome/Edge
  136+; Safari 26.0 partial (`standard` and `no-limit` only). The CSSWG
  *rejected* making `standard` the default (issue #11711, closed Wontfix July
  2025), so the web still defaults to unclamped HDR and a page must opt out.
- **iOS 26** added `UITraitCollection.hdrHeadroomUsageLimit`, which *advises*
  apps to restrict headroom rather than hard-clamping. Per-view limiting has
  existed since iOS 17 (`UIImage.DynamicRange`). The user-facing control is
  Settings → Photos → "View Full HDR", and apps cannot read its state.
- **Android 15** added `Window.setDesiredHdrHeadroom()`; Google's guidance is
  ~2× for mixed SDR/HDR UI. **Android 16 QPR** added a user-facing "Enhanced HDR
  brightness" toggle, on by default — the most consequential consumer-side brake.
- **Accepted upload formats decide the vector.** AVIF, HEIC and WebP are absent
  from LinkedIn's accepted-format lists, which rules out CICP-tagged AVIF as an
  upload there regardless of how good the encoding is. WebP cannot carry HDR at
  all (8-bit, no signalling, no gain map). Build AVIF for your own surfaces and
  for confirming a device can show the effect — not for upload.
- **The tooling trend runs toward preservation, not stripping.** WordPress 7.1
  (2026) detects gain maps on upload and carries them through every generated
  sub-size. Do not assume platforms passively destroy HDR.

### Claims to stop repeating

- **"Instagram clamped HDR in 2025 after abuse."** No announcement, engineering
  post or changelog supports this. Unsupported.
- **"AirDrop converts HDR to SDR."** AirDrop does a HEIC→JPEG *format*
  transcode, not tone mapping, and would not strip an ICC profile from a file
  that is already a JPEG. The sound general rule is the real one: any
  intermediate re-save through an encoder that does not carry `icc_profile`
  through kills it. Pillow drops it by default.
- **Named brands as proof.** Effectiveness claims for this technique carry *no*
  published numbers — no impressions, CTR, or engagement lift, anywhere. If
  someone quotes a lift figure, assume it is invented.

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
