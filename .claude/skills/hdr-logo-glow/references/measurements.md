# Measured behaviour

Numbers a decision should rest on, and how to re-derive them. Re-measure rather
than trusting these — platform pipelines change.

## What survives processing

Same source file through each operation, then re-classified from its bytes:

| Operation | Gain map | CICP tagging | ICC profile |
|---|---|---|---|
| Pillow re-save | destroyed | destroyed | dropped unless explicitly passed |
| Pillow resize | destroyed | destroyed | dropped unless explicitly passed |
| ImageMagick re-save / resize | destroyed | destroyed | **preserved by default** |
| `exiftool -all=` | destroyed | destroyed | destroyed |
| AVIF decode → re-encode | n/a | destroyed | n/a |

The asymmetry is the useful part: colour management is something image pipelines
deliberately preserve, because getting photo colour wrong is a visible bug. Gain
maps and CICP live in structures a transcoder has no reason to carry.

So an HDR signal only survives where a platform hands back the original bytes —
with ICC as a partial exception worth testing, since a pipeline that transcodes
may still carry the profile.

## How each format fails

Measured against the authored SDR rendition, mean absolute difference per channel:

| File, signal removed | Difference | Looks like |
|---|---|---|
| Gain-map JPEG, gain map stripped | **0.58 / 255** | indistinguishable from intended |
| PQ PNG, `cICP` stripped | **30.2 / 255** | washed out; background `#242263` → `#3d395e` |
| PQ + ICC JPEG, colour-managed to sRGB by a non-HDR viewer | mean luma **18 / 255** | near-black; panel `#080924` |
| PQ + ICC JPEG, profile ignored | mean luma **110 / 255** vs 130 target | washed grey; white mark reads `#b9b9b9` |

This is the whole argument for gain maps. A gain-map file's worst case is a
correct image. Every other format's worst case is a visibly broken one, and the
ICC-PQ case is the worst of all — the fallback is not merely wrong, it is dark
enough to look like a loading error.

## Reproducing it

```bash
# survival
convert asset.jpg -resize 600x600 -quality 90 out.jpg
python3 scripts/validate.py out.jpg
exiftool out.jpg | grep -iE "profile|number of images"

# fallback appearance of an ICC-PQ file
python3 - <<'PY'
from PIL import Image, ImageCms
import numpy as np, io
im = Image.open('asset-icc-pq.jpg')
managed = ImageCms.profileToProfile(
    im, ImageCms.getOpenProfile(io.BytesIO(im.info['icc_profile'])),
    ImageCms.createProfile('sRGB'), outputMode='RGB')
print('colour-managed mean luma', np.asarray(managed, float).mean())
print('profile ignored  mean luma', np.asarray(im.convert('RGB'), float).mean())
PY
```

## Frame statistics worth watching

`compose.scene_stats()` reports these; they predict how a panel will behave.

- **`sdr_white_multiple`** — peak ÷ 203. The perceptual strength of the effect.
- **`frac_above_sdr_white`** — keep in the 5–15% band. A frame that is mostly
  above SDR white reads as a bright rectangle, not a glowing mark, and invites
  clamping.
- **`apl_vs_sdr_white`** — average picture level against a full-screen SDR white
  frame. OLED auto-brightness limiters reduce peak output as this rises, so a
  restrained frame can end up *brighter* on the mark than an aggressive one.

## Verifying the PQ implementation

The ST 2084 constants have several equivalent published forms; reduced fractions
like `2523/32` and `2413/128` are correct and equal to `2523/4096*128` and
`2413/4096*32`. Check against known code values instead of eyeballing constants:

| Luminance | PQ code | 10-bit | 8-bit |
|---|---|---|---|
| 100 nits | 0.508078 | 520 | 130 |
| 203 nits (SDR white) | 0.580689 | 594 | 148 |
| 600 nits | 0.696294 | 712 | 178 |
| 800 nits | 0.727525 | 744 | 186 |
| 1000 nits | 0.751827 | 769 | 192 |
| 10000 nits | 1.000000 | 1023 | 255 |

Note how little 8-bit code space separates 600 from 1200 nits (178 vs 197). PQ in
8 bits is coarse; dither when quantising or the panel gradient will band.
