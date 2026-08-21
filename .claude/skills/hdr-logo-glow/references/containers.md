# Container byte layouts and CICP code points

Everything here is what the encoders in `scripts/` actually emit. When a file is
rejected or ignored by a decoder, the cause is almost always one of these details.

## Contents
- [CICP code points](#cicp-code-points)
- [PNG: cICP, mDCV, cLLI](#png-cicp-mdcv-clli)
- [AVIF / HEIF: the nclx colr box](#avif--heif)
- [Gain-map JPEG: XMP + MPF](#gain-map-jpeg)
- [ICC profile structure](#icc-profile-structure)

---

## CICP code points

From ITU-T H.273. Four small integers that say what the pixel values mean.

| Field | Value | Meaning |
|---|---|---|
| `colour_primaries` | 1 | BT.709 / sRGB |
| | 9 | **BT.2020 / BT.2100** |
| | 12 | Display P3 |
| `transfer_characteristics` | 1 | BT.709 |
| | 13 | sRGB |
| | 16 | **SMPTE ST 2084 (PQ)** |
| | 18 | ARIB STD-B67 (HLG) |
| `matrix_coefficients` | 0 | Identity / RGB |
| | 1 | BT.709 |
| | 9 | BT.2020 non-constant luminance |
| `video_full_range_flag` | 1 | full range |

The standard HDR10-style tagging is **9 / 16 / 9 / 1**. In PNG the matrix must be
**0**, because PNG stores RGB rather than YCbCr.

## PNG: cICP, mDCV, cLLI

Standard PNG chunk framing: 4-byte big-endian length, 4-byte type, data, 4-byte
CRC32 over type+data. Insert after `IHDR` and before `IDAT`.

**`cICP`** — 4 bytes, one per CICP field:

```
00 00 00 04   'cICP'   09 10 00 01   <crc32>
              │        │  │  │  └── video_full_range_flag = 1
              │        │  │  └───── matrix_coefficients = 0  (required in PNG)
              │        │  └──────── transfer = 16 = PQ
              │        └─────────── primaries = 9 = BT.2020
```

**`cLLI`** — content light level, 8 bytes: MaxCLL then MaxFALL, each a uint32 in
units of 0.0001 cd/m². 800 nits is `8000000`.

**`mDCV`** — mastering display colour volume, 24 bytes: 8 × uint16 chromaticities
(R,G,B,W as x,y) in units of 0.00002, then max and min luminance as uint32 in
units of 0.0001 cd/m².

Two practical notes. Pillow cannot write 16-bit RGB PNGs at all, so
`scripts/encode.py` emits the file from scratch (IHDR + IDAT + IEND with adaptive
per-row filtering). And strip `iCCP`, `sRGB`, `gAMA` and `cHRM`: the spec says
`cICP` takes precedence, but decoders in the wild are inconsistent, so removing
the competition is safer than relying on precedence.

## AVIF / HEIF

The tagging lives in the `colr` box with type `nclx`. With `avifenc`:

```bash
avifenc --cicp 9/16/9 -r full -d 10 -y 444 -q 90 in.png out.avif
```

`avifenc` does no colour management — it tags and converts RGB→YCbCr with the
given matrix. So hand it RGB that is *already* PQ-encoded. Verify with
`avifdec --info`, and confirm `ICC Profile: Absent`: an embedded ICC profile
out-ranks the `nclx` box in most decoders and silently defeats the tagging.

10-bit is the right default. 8-bit PQ bands badly; 12-bit has weaker support.

## Gain-map JPEG

Layout:

```
SOI
APP0  JFIF
APP1  XMP  -- GContainer directory naming the two images
APP2  MPF  -- CIPA DC-007 index: offsets and sizes
...primary SDR JPEG data... EOI
...gain map JPEG, its own APP1 XMP with hdrgm: metadata... EOI
```

The primary XMP declares a `Container:Directory` with two items, `Item:Semantic`
of `Primary` and `GainMap`, the second carrying `Item:Length`. The gain map's own
XMP carries `hdrgm:GainMapMin`, `GainMapMax`, `Gamma`, `OffsetSDR`, `OffsetHDR`,
`HDRCapacityMin`, `HDRCapacityMax`, `BaseRenditionIsHDR`.

**MPF** (APP2, payload starts `MPF\0`) is a TIFF-style structure: byte order
`MM`, magic 42, offset to the MP Index IFD. Three entries — `0xB000` MPFVersion
(`"0100"`), `0xB001` NumberOfImages (2), `0xB002` MPEntry pointing at 2 × 16
bytes. Each MP entry is: 4-byte attribute (primary is `0x00030000`, secondary
`0x00000000`), 4-byte size, 4-byte offset, then two 2-byte dependency fields.

Two things trip people up:

1. **The primary image's offset field must be 0**, per spec. Only subsequent
   images carry real offsets, and those are measured from the start of the MP
   Endian field (the `MM`), *not* from the start of the file.
2. Offsets depend on the segment's own length, so build the segment with
   placeholder values, measure the assembled primary, then patch the entries in
   place. The length never changes, so one pass is enough.

The decisive validation is whether the recorded secondary offset lands exactly on
a `\xff\xd8` SOI marker. `validate.py` checks this; `exiftool -MPF:all` should
report `Number Of Images : 2`.

### Gain map maths

Encode, per pixel, with luminances normalised against SDR white:

```
ratio    = (Yhdr + offsetHDR) / (Ysdr + offsetSDR)
encoded  = ((log2(ratio) - MIN) / (MAX - MIN)) ^ (1/gamma)
```

Decode on a display with `H` stops of headroom:

```
w    = clamp((H - CapacityMin) / (CapacityMax - CapacityMin), 0, 1)
Yhdr = (Ysdr + offsetSDR) * 2^((encoded^gamma * (MAX-MIN) + MIN) * w) - offsetHDR
```

`offsetSDR = offsetHDR = 1/64` and `gamma = 1.0` are the usual defaults. A
correct implementation round-trips exactly: at zero headroom you get the SDR
rendition back, at `CapacityMax` you get the authored HDR peak, and above that it
clamps rather than overshooting. Test those three points — it catches most errors.

Use full resolution for a gain map covering a hard-edged mark. Downsampled gain
maps blur the boundary of the boost region and halo the edges.

## ICC profile structure

128-byte header, then a tag table (4-byte count, then 12 bytes per tag: signature,
offset, size), then 4-byte-aligned tag data.

For an RGB matrix-shaper display profile: `desc`, `cprt` (both `mluc` in v4),
`wtpt`, `chad`, `rXYZ`/`gXYZ`/`bXYZ`, `rTRC`/`gTRC`/`bTRC`.

PQ cannot be expressed as an ICC `parametricCurveType` — those only cover simple
gamma forms — so the TRC must be a sampled `curveType` LUT. 4096 entries is
ample. Identical TRCs can be stored once and referenced by all three tags.

The primaries go in as BT.2020 RGB→XYZ adapted from D65 to the D50 PCS via
Bradford, with the adaptation matrix itself in `chad`. Sanity check: `rXYZ` should
come out ≈ `0.67345, 0.27902, -0.00194`.

**The catch worth understanding.** PQ is absolute (0–10000 cd/m²) but the ICC PCS
is relative. Normalising the TRC to 10000 nits is spec-correct and puts SDR white
(203 nits) at 0.0203 relative — so a viewer that colour-manages the file without
knowing it is PQ renders it drastically too dark. That is not a bug in the
profile; it is why PQ needs a decoder that knows the signal is absolute, and why
CICP exists. See `measurements.md`.
