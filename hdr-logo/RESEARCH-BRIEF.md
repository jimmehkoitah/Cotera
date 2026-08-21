# HDR "Glowing Logo" — Definitive Technical Brief for the Cotera Build

**Audience:** the engineer building Cotera's HDR logo asset.
**Status of the repo you're working in:** `/home/user/Cotera` already contains a working toolchain (`hdr-logo/src/build.py`, `.claude/skills/hdr-logo-glow/scripts/`, and `make-linkedin-hdr-assets.py`) that produced verified-correct PQ+ICC JPEG, gain-map JPEG, 10-bit PQ AVIF and 16-bit PQ PNG outputs. Everything below either confirms, corrects or extends what's there. Commands marked ✅ were executed in this session against those files.

---

## 0. Evidence tiers used throughout

| Tag | Meaning |
|---|---|
| **[SOLID]** | Read from a primary spec, vendor doc, or reference-implementation source; or measured/executed here. |
| **[LIKELY]** | Well-supported and internally consistent, but the primary source was unreachable or the only sources are practitioner reverse-engineering. |
| **[UNVERIFIED]** | Anecdote, vendor self-attribution, or single non-retrievable source. **Never state as fact.** |

Several widely-repeated claims were **refuted** during verification. Corrections are applied inline and the refuted originals are catalogued in §12 so you don't reintroduce them.

---

## 1. The mechanism, in plain language

A normal image is *relative*. `#ffffff` means "whatever this panel calls white." Nothing in an sRGB file can ask for more light than the pixel next to it.

Modern compositors do **not** treat `255,255,255` as the panel's maximum. They treat SDR/diffuse white as a **reference level** and reserve everything above it as **headroom**. Apple calls this EDR: `headroom = display peak nits ÷ current SDR-white nits`, with EDR 1.0 = reference white and values >1.0 rendering brighter than any SDR white on screen. **[SOLID]** — Apple, WWDC21 session 10161, verbatim: *"EDR 0.0 represents black, 1.0 represents SDR max, also known as 'reference white' or 'UI white'"*; and *"there is 3.2x SDR headroom"* on a Pro Display XDR at the 500-nit XDR preset (1600 ÷ 500).

An HDR-tagged image reaches into that reserve. Two independent signalling families do it:

**(a) Absolute transfer function.** You declare the pixels are PQ (SMPTE ST 2084 / BT.2100 PQ), where a code value *is* a luminance in cd/m² on a 0–10,000 scale. `0.7518` isn't "quite bright" — it's **1000 nits**. Signalled by ITU-T H.273 **CICP code points** in a PNG `cICP` chunk, an AVIF/HEIF `colr`/`nclx` box, or (the LinkedIn route) an ICC profile whose TRC *is* the PQ curve.

**(b) Gain map.** The file is an ordinary SDR JPEG plus a hidden per-pixel log₂ gain image and metadata. A viewer with headroom applies a proportionate fraction; a viewer without one just shows the SDR base and is none the wiser. (Ultra HDR / Apple Adaptive HDR / ISO 21496-1.)

**The whole effect is contrast, not emission.** The logo doesn't look *whiter* — everything around it looks *dim*. On an OLED the surround can be literally 0 nits, which is why a small mark on a dark tile is the maximally effective geometry and a full-bleed bright image is self-defeating.

**Why LinkedIn specifically forces family (a):** practitioners consistently report LinkedIn re-encodes uploads, discarding the MPF segments and `XMP-hdrgm` packet that carry gain maps, while **preserving the embedded ICC profile**. So the HDR has to ride inside colour management. **[LIKELY]** — see §5 for the important caveats on that claim.

---

## 2. Reference white, headroom, and the nit ladder

### 2.1 The denominator

**SDR / diffuse / graphics white = 203 cd/m²**, from **ITU-R Report BT.2408** (it is a *Report*, not a Recommendation — cite it correctly). **[SOLID]** Independently corroborated by libplacebo: `#define PL_COLOR_SDR_WHITE 203.0f` with the comment *"See ITU-R Report BT.2408 for more information."*

Cross-check from the W3C PNG spec: *"HDR Reference White has a luminance level of 203 cd/m² … This corresponds to a code value of 58% in PQ and 75% in HLG on a 1000 cd/m² display."* My computed PQ value for 203 nits is **0.5807** — 58%. ✅

Note the collision: Apple's *image-pipeline* reference white is described only qualitatively ("the brightness of a page of a book indoors"); the 100-nit figure in Apple material is **HDR10's** reference white, not a general rule. Do not attribute "~100 nits reference white" to WWDC24. **[SOLID, corrected]**

### 2.2 PQ inverse EOTF (ST 2084 / BT.2100)

```
m1 = 2610/16384      = 0.1593017578125
m2 = (2523/4096)*128 = 78.84375
c1 = 3424/4096       = 0.8359375
c2 = (2413/4096)*32  = 18.8515625
c3 = (2392/4096)*32  = 18.6875          # identity: c1 = c3 - c2 + 1

y  = clamp(nits / 10000, 0, 1)
E' = ((c1 + c2*y**m1) / (1 + c3*y**m1)) ** m2
```

### 2.3 The ladder (computed here ✅)

| nits | PQ E′ | 8-bit | 10-bit | ×203 | stops |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.1499 | 38 | 153 | 0.005× | −7.67 |
| 100 | 0.5081 | 130 | 520 | 0.49× | −1.02 |
| **203** | **0.5807** | **148** | **594** | **1.00×** | **0.00** |
| 400 | 0.6526 | 166 | 668 | 1.97× | +0.98 |
| 600 | 0.6963 | 178 | 712 | 2.96× | +1.56 |
| 812 | 0.7291 | 186 | 746 | 4.00× | +2.00 |
| 1000 | 0.7518 | 192 | 769 | 4.93× | +2.30 |
| 1600 | 0.8031 | 205 | 822 | 7.88× | +2.98 |
| 3000 | 0.8715 | 222 | 892 | 14.78× | +3.89 |
| 4000 | 0.9026 | 230 | 923 | 19.70× | +4.30 |
| 10000 | 1.0000 | 255 | 1023 | 49.26× | +5.62 |

Read the table twice. **A logo painted flat at 8-bit code 205 is a 1600-nit emitter on an HDR path and an 80%-grey on a naive SDR path.** That single fact is both the trick and the failure mode.

### 2.4 What you author is a *request*, not a delivery

Delivered brightness ≈ `min(encoded nits, current headroom × current SDR-white, ABL ceiling at that APL)`. **[LIKELY — composed inference, not measured]**

- Headroom is **inversely** related to the brightness slider: `current headroom ≈ max display brightness ÷ current SDR brightness` (Apple's own "oversimplification", WWDC22 session 10113). Turning the screen up *destroys* the effect. **[SOLID]**
- Apple's stated figures: **iPhone XDR "up to 8× SDR headroom"; conventional backlit Macs/iPads "up to 2×"; iPad Pro Liquid Retina XDR "up to 16×"** (WWDC21 10161). iPad Pro Reference Mode pins SDR at 100 and HDR peak at 1000 = exactly 10×. **[SOLID]**
- **Do NOT compute headroom as `peak-HDR-nits ÷ max-typical-SDR-nits`.** "Max brightness (typical)" is a full-screen SDR ceiling, not the EDR reference white. The often-repeated "iPhone = 1600/1000 = 1.6× headroom" is arithmetically invalid. **[refuted]**
- Measured browser headroom (informal, self-reported, `lilith/browser-hdr-test`): Windows Chrome ≥4.0×, macOS Safari 2–8×, iOS Safari ~2.0×, Android Chrome 2.0× (needs Samsung Super HDR). Range is **2–8×**, not 2–4×. **[LIKELY]**
- OLED: per-pixel emissive, with ABL/ASBL reducing output as average picture level rises, so a small bright element can be driven substantially brighter than a full-field white. **Do not state "~3% APL" as a general rule** — the measurement window is product- and standard-specific (VESA DisplayHDR uses a 10% centre patch; vendors quote 1–10% windows). **[LIKELY, corrected]**
- Mini-LED/FALD: a highlight smaller than a backlight zone forces the whole zone up and leaks into neighbours → blooming, worst for small bright marks on dark grounds. Severity depends on zone count and dimming algorithm — not "cannot", just "will halo to a degree." **[LIKELY, corrected]**
- Low Power Mode, backgrounded windows, and non-XDR external monitors all reclaim headroom to ~1.0. **[LIKELY]**

---

## 3. Exact code points and byte layouts

### 3.1 ITU-T H.273 CICP — ColourPrimaries

`1` BT.709/sRGB/IEC 61966-2-4 · `2` unspecified · `3` **reserved** · `4` BT.470M · `5` BT.470BG · `6` BT.601 · `7` SMPTE 240M · `8` generic film · **`9` BT.2020 = BT.2100** · `10` XYZ (SMPTE ST 428-1) · **`11` DCI-P3 (SMPTE RP 431-2, DCI white)** · **`12` Display P3 / P3-D65 (SMPTE EG 432-1)** · `22` EBU Tech 3213-E / JEDEC P22. **[SOLID]** — verified against libavif `avif.h` and FFmpeg `pixfmt.h`. *Correction: 11 and 12 are frequently swapped in blog posts; 12 is Display P3.*

### 3.2 TransferCharacteristics

`1` BT.709 · `2` unspecified · `4` BT.470M (2.2γ) · `5` BT.470BG (2.8γ) · `6` BT.601 · `7` SMPTE 240M · `8` linear · `9` log100 · `10` log100-√10 · `11` IEC 61966-2-4 · `12` BT.1361 · **`13` sRGB (IEC 61966-2-1)** · `14` BT.2020 10-bit · `15` BT.2020 12-bit · **`16` SMPTE ST 2084 / PQ / BT.2100 PQ** · `17` SMPTE ST 428 · **`18` ARIB STD-B67 / HLG / BT.2100 HLG**. **[SOLID]**

> PQ is **16**. HLG is **18**. Getting this wrong (writing 18 for PQ) is the single most common slip.

### 3.3 MatrixCoefficients + range flag

`0` Identity (GBR/RGB) · `1` BT.709 · `2` unspecified · `3` reserved · `4` FCC · `5` BT.470BG · `6` BT.601 · `7` SMPTE 240M · `8` YCgCo · **`9` BT.2020 NCL** · `10` BT.2020 CL · `11` SMPTE 2085 · `12/13` chroma-derived NCL/CL · `14` ICtCp · **`15` IPT-C2 (SMPTE ST 2128)** · `16` YCgCo-Re · `17` YCgCo-Ro. **[SOLID, corrected — 15 is absent from libavif and is routinely omitted from copied lists; it exists in FFmpeg as `AVCOL_SPC_IPT_C2`.]**

`VideoFullRangeFlag`: `0` = limited/narrow, `1` = full. (Applies to YUV planes only; RGB and alpha are always full range.)

### 3.4 PNG `cICP` chunk — exact bytes

Spec (W3C PNG, Third Edition REC 2025-06-24; text read from the w3c/png source): *"The four-byte chunk type field contains the hexadecimal values `63 49 43 50`"*; *"The cICP chunk consists of four 1-byte unsigned integers"*; *"RGB is currently the only supported color model in PNG, and as such **Matrix Coefficients shall be set to 0**"*; *"The cICP chunk MUST come before the PLTE and IDAT chunks"*; *"This chunk, if understood by the decoder, is the **highest-precedence color chunk**."* **[SOLID]**

Colour-chunk priority (lowest number wins): `cICP` = 1, `iCCP` = 2, `sRGB` = 3, `cHRM`/`gAMA` = 4.

Payload = `[ColourPrimaries][TransferFunction][MatrixCoefficients][FullRangeFlag]`, one byte each.

Complete on-the-wire 16-byte chunks (length ‖ type ‖ data ‖ CRC32 of type+data) — **CRCs computed here ✅**:

| Tagging | Payload | Full chunk hex |
|---|---|---|
| **BT.2100 PQ, full range** | `09 10 00 01` | `00000004 63494350 09100001 4D2323FE` |
| BT.2100 HLG, full range | `09 12 00 01` | `00000004 63494350 09120001 4EA7F790` |
| Display P3, full range | `0C 0D 00 01` | `00000004 63494350 0C0D0001 6E03E3EF` |
| BT.709, narrow range | `01 01 00 00` | *(spec example; matrix 0, range 0)* |

**Cotera's existing PNG output already carries exactly `cICP len=4 data=09100001`.** ✅

### 3.5 PNG `mDCV` (Mastering Display Colour Volume) — 24 bytes

Type field `6D 44 43 56`. Layout: 12 bytes primaries (3 × `uint16 x, uint16 y`, divisor **0.00002**, ordered largest-x first = R,G,B for RGB) + 4 bytes white point (same divisor) + 4 bytes max luminance (`uint32`, divisor **0.0001** cd/m²) + 4 bytes min luminance (same). MUST precede PLTE/IDAT, and *"a cICP chunk must accompany the use of mDCV."* **[SOLID]**

BT.2020 primaries + D65 + 1000 / 0.0001 cd/m², computed ✅:
```
8a48 3908  2134 9baa  1996 08fc   3d13 4042   00989680  00000001
 R x  R y   G x  G y   B x  B y    D65 x,y     1000 nits  0.0001
CRC32 = 9F5C61DE
```
(Spec worked examples: 4000 cd/m² → `02 62 5A 00`; 0.0005 cd/m² → `00 00 00 05`.)

### 3.6 PNG `cLLI` (Content Light Level Information) — 8 bytes

Type field `63 4C 4C 49`. `uint32 MaxCLL` + `uint32 MaxFALL`, **both divisor 0.0001 cd/m² — i.e. stored value = nits × 10000.** Zero means "unknown or not currently calculable." Calculation method per CTA-861.3-A. **[SOLID]**

Examples: 1000 cd/m² → `00 98 96 80`; 250 → `00 26 25 A0`; (4000, 600) → `02625a00 005b8d80`, CRC `FE99749A` ✅.

**Cotera's PNG carries `cLLI 007a1200 000c3006` = MaxCLL 800.0 nits, MaxFALL 79.87 nits.** ✅ Correct and honest.

> The ×10000 divisor is the most common off-by-10000 bug in this whole area.

### 3.7 PNG `hRWL` — Fourth Edition only, do not rely on it

Type `68 52 57 4C`, 4 bytes `uint32`, divisor 0.0001 cd/m². Carries a **non-standard** HDR reference white. *"If the standard value of 203 cd/m² has been used, the hRWL chunk should not be added."* Added to the w3c/png repo 2026-07-01 (PR #573 / issue #390) — **it is NOT in the published Third Edition Recommendation and tooling support is effectively nil.** **[SOLID]**

### 3.8 AVIF/HEIF `colr` / `nclx` box — exact bytes

`'colr'` ‖ `'nclx'` ‖ `uint16 colour_primaries` ‖ `uint16 transfer_characteristics` ‖ `uint16 matrix_coefficients` ‖ 1 byte whose **top bit (0x80) is full_range_flag**.

A PQ BT.2020 full-range file contains the literal signature:
```
63 6f 6c 72  6e 63 6c 78  0009  0010  0009  80
   'colr'       'nclx'      9     16     9   full
```
Scan for the signature; the offset is file-specific, not constant. **[SOLID]** MIAF makes the `colr` box authoritative over the AV1 sequence-header CICP — but libavif 1.4.0 deliberately re-forwards CICP to the OBU too *"for compatibility with libraries that wrongly ignore the colr box."*

`clli` box in HEIF/AVIF is **16-bit** (`uint16 maxCLL; uint16 maxPALL`) in cd/m², unlike PNG's 32-bit ×10000. Spec anchors peak white to 10,000 cd/m² when `transfer_characteristics == 16`. **[SOLID]**

**Cotera's AVIF verifies clean:** `nclx / BT.2020,BT.2100 / SMPTE ST 2084,ITU BT.2100 PQ / BT.2020 non-constant luminance / Video Full Range Flag: 1`, `yuv444p10le(pc)`. ✅

### 3.9 The ICC route (what LinkedIn actually carries)

Historical precedent: before `cICP` existed, W3C's *"Using the ITU BT.2100 PQ EOTF with the PNG Format"* signalled HDR PQ purely through an `iCCP` chunk whose profile name is the reserved string `ITUR_2100_PQ_FULL`. **[SOLID]** The LinkedIn trick is the direct descendant.

Two profile descriptions in the wild:
- `Rec2020 Gamut with PQ Transfer` — Apple ColorSync profile, ~9,196 bytes, **carries a 12-byte ICC `cicp` tag = `09 10 00 01`**. This is what was measured inside the live LinkedIn reference file.
- `Rec. ITU-R BT.2100 PQ` — what **Cotera's `icc_pq.build_profile()` currently emits**: ICC v4.3, 8,776 bytes, 10 tags (`desc cprt wtpt chad rXYZ gXYZ bXYZ rTRC gTRC bTRC`), TRC = sampled `curv` with 4096 entries, midpoint 0.00923 (correct for PQ; a plain gamma would be ~0.2). ✅ Validated by `validate.py`: **ALL CHECKS PASSED**, and lcms2 accepts it.

**⚠️ Actionable gap for Cotera:** the generated profile has **no `cicp` tag**. `validate.py` itself flags this: *"ICC carries no absolute-luminance signal, and a viewer that colour-manages this without HDR awareness renders it near-black."* ICC v4.4 (ICC.1:2022) added `cicpTag`, permitted when the data colour space is RGB/YCbCr/XYZ and the class is Input or Display **[LIKELY]** — that is the standards-correct way to make the profile self-describing, and it is what the Apple profile does. **Adding a 12-byte `cicp` tag (`09 10 00 01`) to `icc_pq.py` is the single highest-value change available, because it makes the file's HDR intent explicit rather than inferred from a sampled curve shape.** No evidence exists that the *description string* matters to any renderer; the tag might.

### 3.10 Gain-map metadata — exact field names

**Google Ultra HDR v1.1** — XMP, namespace `http://ns.adobe.com/hdr-gain-map/1.0/`, prefix `hdrgm`, on the **gain-map** image: **[SOLID]**

| Field | Required | Default | Meaning |
|---|---|---|---|
| `hdrgm:Version` | ✅ | `"1.0"` | |
| `hdrgm:GainMapMax` | ✅ | — | `log2(max_content_boost)` |
| `hdrgm:HDRCapacityMax` | ✅ | — | `log2(max_display_boost)` |
| `hdrgm:GainMapMin` | | `0.0` | `log2(min_content_boost)` |
| `hdrgm:Gamma` | | `1.0` | |
| `hdrgm:OffsetSDR` | | `0.015625` (1/64) | |
| `hdrgm:OffsetHDR` | | `0.015625` (1/64) | |
| `hdrgm:HDRCapacityMin` | | `0.0` | |
| `hdrgm:BaseRenditionIsHDR` | | `False` | must be `False` for SDR-base files |

Location: Google **GContainer** XMP directory on the primary — `http://ns.google.com/photos/1.0/container/` (prefix `Container`) and `http://ns.google.com/photos/1.0/container/item/` (prefix `Item`), with `Item:Semantic` ∈ {`Primary`, `GainMap`}, `Item:Mime`, `Item:Length`, `Item:Padding` — **plus an MPF (CIPA DC-x 007-2009 Multi-Picture Format) APP2 segment**, with the gain-map JPEG appended after the primary. Offset = `PrimaryImageLength + Σ(PreviousItemLengths) + Σ(PreviousPaddings)`.

**Cotera's gain-map JPEG verifies clean:** `XMP-hdrgm Version 1.0`, `XMP-Container DirectoryItemSemantic Primary` + `GainMap`, `DirectoryItemMime image/jpeg`, `DirectoryItemLength 18079`, `MPF0 NumberOfImages 2`, `MPImage1 59442 @ 0` / `MPImage2 18079 @ 59442`. ✅

**Ultra HDR maths** — encode:
```
pixel_gain      = (Yhdr + offset_hdr) / (Ysdr + offset_sdr)
map_min_log2    = log2(min_content_boost);  map_max_log2 = log2(max_content_boost)
log_recovery    = (log2(pixel_gain) - map_min_log2) / (map_max_log2 - map_min_log2)
recovery        = pow(clamp(log_recovery, 0, 1), map_gamma)
encoded         = floor(recovery * 255 + 0.5)
```
apply:
```
log_recovery    = pow(encoded/255, 1/map_gamma)
weight_factor   = clamp((log2(max_display_boost) - hdr_capacity_min)
                        / (hdr_capacity_max - hdr_capacity_min), 0, 1)
log_boost       = gain_map_min*(1-log_recovery) + gain_map_max*log_recovery
HDR             = (SDR + offset_sdr) * exp2(log_boost * weight_factor) - offset_hdr
```
Recommended: single-channel gain map where possible; ¼ linear resolution (1/16 area); gain-map JPEG quality 85–90; `HDRCapacityMax = GainMapMax`, `HDRCapacityMin = max(GainMapMin, 0.0)`; Display-P3 profile on the base. **[SOLID]**

**libultrahdr public struct** (values in **linear**, not log₂):
`uhdr_gainmap_metadata { float max_content_boost[3]; min_content_boost[3]; gamma[3]; offset_sdr[3]; offset_hdr[3]; float hdr_capacity_min; hdr_capacity_max; int use_base_cg; }`. Serialisation struct `uhdr_gainmap_metadata_frac` stores everything as rational N/D pairs plus `bool backwardDirection; bool useBaseColorSpace;`, with bit masks `kIsMultiChannelMask = (1u<<7)`, `kUseBaseColorSpaceMask = (1u<<6)`. **[SOLID]**

**ISO 21496-1:2025** — *"Digital photography — Gain map metadata for image conversion — Part 1: Dynamic range conversion"*, published 2025-07-07, ISO/TC 42, 16 pages. Field names as implemented by libavif: **[SOLID for libavif; the spec's own snake_case spelling is UNVERIFIED — paywalled]**
```
avifGainMap {
  avifSignedFraction   gainMapMin[3], gainMapMax[3];
  avifUnsignedFraction gainMapGamma[3];
  avifSignedFraction   baseOffset[3], alternateOffset[3];
  avifUnsignedFraction baseHdrHeadroom, alternateHdrHeadroom;
  avifBool             useBaseColorSpace;
  avifRWData altICC; avifColorPrimaries altColorPrimaries;
  avifTransferCharacteristics altTransferCharacteristics;
  avifMatrixCoefficients altMatrixCoefficients; avifRange altYUVRange;
  uint32_t altDepth, altPlaneCount; avifContentLightLevelInformationBox altCLLI;
}
```
Maths: `gainMapLog2 = lerp(gainMapMin, gainMapMax, pow(gainMapEncoded, 1/gainMapGamma))`; `f = clamp((H − baseHdrHeadroom)/(alternateHdrHeadroom − baseHdrHeadroom), 0, 1)`; `w = sign(alternateHdrHeadroom − baseHdrHeadroom) * f`; `toneMappedLinear = ((baseImageLinear + baseOffset) * exp2(gainMapLog2 * w)) − alternateOffset`. The gain-map image's own `colorPrimaries` and `transferCharacteristics` **shall be 2** (unspecified).

**Design contract worth internalising:** *"the result of tone mapping for a display with an HDR headroom ≤ baseHdrHeadroom is the base image, and ≥ alternateHdrHeadroom is the alternate image."* Setting `alternateHdrHeadroom ≈ 2 stops` means most phones/laptops get the full intended look; 4+ stops means almost nobody does.

**JPEG carriage of ISO 21496-1:** APP2 (`0xFFE2`) segment whose identifier string is literally **`urn:iso:std:iso:ts:21496:-1`**, written NUL-terminated (28 bytes with the NUL), followed by `uint16 minimum_version` + `uint16 writer_version`. libultrahdr's documented segment order: `SOI → APP0(JFIF) → APP1(XMP) → APP2(ICC) → APP2(ISO) → DQT/SOF/DHT → APP2(MPF) → SOS`, MPF written immediately before SOS per CIPA DC-007. On read, *"if both iso block and xmp block are available, then iso block is preferred."* **[SOLID]**

**Android `Gainmap`** (API 34 / Android 14) uses natural-log form: `W = clamp((log(H) − log(minDisplayRatioForHdrTransition)) / (log(displayRatioForFullHdr) − log(minDisplayRatioForHdrTransition)), 0, 1)`; `L = mix(log(ratioMin), log(ratioMax), pow(G, gamma))`; `D = (B + epsilonSdr) * exp(L * W) − epsilonHdr`. Setters: `setRatioMin/Max`, `setGamma`, `setEpsilonSdr/Hdr`, `setDisplayRatioForFullHdr`, `setMinDisplayRatioForHdrTransition`. *"When rendering to a `COLOR_MODE_HDR` activity, the hardware accelerated Canvas will automatically apply the gainmap when sufficient HDR headroom is available."* **[SOLID]**

**Gain maps in PNG (`gMAP` + `gDAT`) are NOT standardised.** Proposal w3c/png#380 is open, milestoned to the 4th Edition, and the author notes it *"relates to an earlier version of the ISO gain map specification. It is outdated."* Do not plan around it. **[SOLID]**

---

## 4. Design craft — what makes it read as deliberate rather than broken

### 4.1 Lift only near-white pixels

Boosting everything is exactly what "naively tagging a file HDR" does, and it looks wrong. Both independent open-source implementations use a **smoothstep gate on relative luminance**: **[SOLID — read from source]**

```python
Y    = 0.2627*R + 0.6780*G + 0.0593*B      # BT.2020 luma (or BT.709 0.2126/0.7152/0.0722)
t    = clip((Y - 0.55) / (0.90 - 0.55), 0, 1)   # ≈ sRGB codes 196 → 243
t    = t*t*(3 - 2*t)                        # smoothstep → C1 continuity, no seam
gain = 1.0 + (2**stops - 1.0) * t**1.5
```

Smoothstep is *specifically* why there is no visible seam where the lift begins and no halo on antialiased logo edges. Pixels below the threshold keep their true SDR luminance, so the brand colour is untouched.

Cotera's `compose.py` goes further and composites in **linear light in absolute nits** with the panel held at exactly `SDR_WHITE_NITS = 203`, so only the arrow and its spill exceed reference white. That's the right architecture — keep it.

### 4.2 Lit-area fraction is the main taste dial

Measured across shipped variants: **9.5%** (mark only — "reads like a neon sign", the recommended setting), **28.2%** (mark glows, brand colour untouched at ~59 nits), **29.7%** (whole tile lifted to ~202 nits), **69.0%** (the real live reference file), **91.0%** (polarity inverted, field glows — the "flashbang"). **[SOLID — re-measured]**

Cotera's current avatar build reports `frac_above_sdr_white: 0.1359` (13.6%) with `apl_vs_sdr_white: 0.703`. That sits in the gentle/deliberate band. Good default.

Three concrete reasons not to light the whole canvas: (1) glare spills across adjacent feed text, unpleasant at night; (2) it is the version people complain about; (3) for a dark-brand mark, a white-square SDR fallback is a **permanent brand change for the SDR majority**.

### 4.3 The nit target

- **No de-facto industry standard exists.** "4000 is what everyone uses" is one hobby tool's argparse default. An independent tool (Glowkri) deliberately targets 10,000. **[refuted → downgraded]**
- Practitioner ladders in circulation: +2 stops ≈ 812 nits ("subtle-bright"), +3 ≈ 1624 ("the well-known glowing-logo look"), +3.9 ≈ 3030 ("practical maximum"). A *different* tool calls 4000 "strong" and 10000 "clips flat." These two sources contradict each other and neither is sourced. **[LIKELY at best]**
- The one file with real measurements attached sits at **p50 3,977 / p90 4,602 / p99 6,643 / p100 10,000 nits**, 69% above SDR white. So even the "don't use 10,000" reference file hits 10,000 at p100. **[SOLID measurements, UNVERIFIED provenance — see §5.4]**
- Physics ceiling: an XDR panel physically reaches ~1,000–1,600 nits **[LIKELY, single practitioner source; Apple specs unreachable]**, so above ~1,600 you're buying diminishing visible brightness and rising clipping risk.

**Recommendation for Cotera:** the existing 600 / 800 / 1200 test ladder is the right experimental design. Ship at **800 nits (+2.0 stops, 3.94×)** as the default. It is comfortably inside every panel's real capability, survives clamping gracefully, and is the value your build already treats as canonical.

### 4.4 Texture: lit material vs blown slab

A perfectly flat bright field reads as an error; slow low-frequency luminance modulation reads as a lamp. The measured reference file varies **3,977 → 4,602 nits (~600 nits of slow veining)** across its bright field. **[SOLID measurement]**

⚠️ The widely-quoted **"structure beats noise 7:1"** statistic is **invalid as constructed** — it divides a 16-code-value *range* by a 2.2-code-value *standard deviation*, two different statistics. Use the ~600-nit veining figure; drop the ratio. **[refuted]**

Implementation: 3 octaves of low-frequency noise at scales 3/6/12 with halving amplitude, applied **only** to pixels already in the headroom, amplitude ~0.12–0.14. And be honest that it invents surface the logo never had — it's a design decision, not a setting.

### 4.5 Encoding hygiene

- **Gamut-convert BEFORE scaling to absolute luminance.** Skipping the sRGB→Rec.2020 matrix oversaturates every colour (Rec.2020 primaries are far wider). Matrix rows: `(0.62740390, 0.32928304, 0.04331307)`, `(0.06909729, 0.91954040, 0.01136232)`, `(0.01639144, 0.08801331, 0.89559525)`. **[SOLID]**
- **JPEG must be 4:4:4** (`subsampling=0`). The default 4:2:0 smears hard logo edges, extremely visible at high nits. Quality 95–96, `progressive=True`. **[SOLID]** ✅ Cotera's output verifies as `Progressive DCT, Huffman coding` + `YCbCr4:4:4 (1 1)`.
- **8-bit PQ bands on gradients.** Flat-fill marks and wordmarks are safe; long low-amplitude ramps (a big soft bloom halo) are the highest-risk construction on the 8-bit JPEG route specifically. Use 16-bit PNG or 10-bit AVIF if you need a soft ramp. Cotera's multi-sigma bloom (`0.008/0.022/0.055/0.120`) is exactly the kind of ramp that will band at 8 bits — **compare the 8-bit JPEG against the 16-bit PNG side by side before shipping.** **[SOLID principle, untested on your specific art]**
- **No alpha on the social route.** JPEG has no alpha; flatten onto a solid background first. Square input; 400×400 is LinkedIn's recommended company-logo size.
- **Re-master from vector.** A low-res or already-compressed source gets visibly worse at high nits. Cotera has `assets/cotera-arrow.svg` — good.
- **Black surround maximises the effect** because OLED black is literally 0 nits. It is simultaneous contrast, weaponised.

### 4.6 Graceful degradation — measured

| Path | Brand blue `106,145,227` | Logo white |
|---|---|---|
| **Colour-managed SDR conversion** (PQ → nits → ÷203 → 2020→709 → clip → sRGB) | `106,144,226` — lossless to 1 code value | `255,255,255` |
| **Unmanaged** (raw PQ code values read as sRGB) | `109,115,139` — washed grey-blue | `230,230,230` — dull grey |

**[SOLID — measured]** That second row is the entire risk of the PQ route. Any surface that drops or ignores the ICC profile turns your logo into grey soup, and losing the tag does **not** restore the original look — the pixels are still PQ.

Gain maps do not have this failure mode **by construction**: the primary image *is* the SDR rendition, so legacy readers show exactly what you intended. This is the fundamental tension: **the safe format is the one LinkedIn destroys; the format that survives is the fragile one.**

---

## 5. The LinkedIn-specific reality

### 5.1 What is actually established

**[LIKELY]** — LinkedIn re-encodes uploaded images into sized renditions served from `media.licdn.com` (paths like `/dms/image/v2/<id>/company-logo_200_200/…`, `profile-displayphoto-shrink_200_200/…`, with `e=` expiry / `v=beta` / `t=` token params). In that re-encode it discards EXIF, XMP (including `hdrgm`) and MPF segments, but preserves the embedded ICC profile.

**⚠️ Critical sourcing caveat.** This is **not** confirmed by four or five independent tools, as it is usually presented. Superwhite's own credits state: *"The underlying profile-splicing technique was first documented by Tom Nick (tn1ck.com/blog/abuse-hdr-images-for-marketing)."* Every downstream repo traces to that single write-up. Counting derivative repos as independent replications is a common-source fallacy. **No byte-level diff of an upload versus a served rendition has ever been published**, and the "verify with exiftool" step those repos recommend inspects the tool's *own pre-upload output* (which never had a gain map) — it is not a test of LinkedIn's pipeline at all. **[refuted as "confirmed"]**

**LinkedIn has published nothing.** No help-centre page, no ad spec, no engineering post, no policy line mentions HDR, gain maps, PQ, or luminance — searched thoroughly in both directions. The nearest policy hooks are generic: Ads Policy's *"must not deceive, confuse or otherwise degrade the experience of members"*, *"must not contain audio or flash animation that plays automatically"*, and *"must not use tactics intended to circumvent the ad review process"*. None names brightness. **[SOLID negative result]**

### 5.2 Surface-by-surface

| Surface | Status | Notes |
|---|---|---|
| **Company / brand Page logo** | Best-attested **[LIKELY]** | Two low-star repos report it as the most reliable surface. ⚠️ Complication: Superwhite attributes the *company-page* result to a **PNG cICP** variant (credited to Gal Tidhar), and JPEG+ICC to the *feed-post* variant. So "company logo is most reliable" may be true of a **different encoding** than the JPEG+ICC payload. Test both. |
| **Feed post image** | Best-sourced **[LIKELY]** | Survives when uploaded **directly as JPEG with no cropping or editing in LinkedIn's composer** — composer re-processing strips the profile. Three separate files from one vendor agree verbatim. |
| **Personal profile photo** | **UNRESOLVED** | One repo says it fails (facial-recognition cropping + aggressive recompression); one marketing page reportedly says it works. Superwhite — the most-cited source — **does not mention personal profile photos anywhere**. No side-by-side test exists. |
| **Document/carousel (PDF), article cover, banner, Page cover, event, newsletter** | **ZERO DATA** | The PDF rasterisation path would be expected to drop ICC, but this is untested speculation. |
| **Sponsored / ad creative** | **ZERO DATA** | No report of an HDR creative passing or failing ad review. Ad pipelines may transform differently. |
| **DMs** | **UNVERIFIED** | A claim that DMs retain full metadata (which would imply gain maps survive there) comes from SEO metadata-tool blogs only. |

### 5.3 Upload path

Upload from a **desktop browser**; re-copy the file from the source folder, never from a Slack/email preview. **[LIKELY]**

⚠️ The commonly-repeated warning that "AirDrop and the iOS picker convert HDR to SDR" is **mechanically wrong as stated** — AirDrop and `PHPickerViewController` do a *format* transcode (HEIC→JPEG under Automatic vs Keep Originals), not HDR→SDR tone mapping, and neither would strip an ICC profile from a file that is already a JPEG. The sound general rule is: **any intermediate re-save through an encoder that doesn't carry `icc_profile` through kills the effect.** (Pillow, for one, drops it by default.) **[corrected]**

Whether LinkedIn's own CDN size variants preserve the ICC is **untested** — the claim rests on the absence of contrary reports in a corpus of ~four hobby repos that never tested variants. **Verify by downloading the served rendition and running exiftool on it.**

### 5.4 Format specs (third-party aggregation — LinkedIn Help was unreachable) **[LIKELY]**

Page logo 400×400 recommended / 268×268 min, PNG or JPEG, ≤3 MB · Page cover 1128×191, ≤8 MB · Profile photo 400×400, ≤8 MB · Profile banner 1584×396 · Feed image JPG/PNG/non-animated GIF, <5 MB, 1200×627 (1.91:1) or 1080×1350 (4:5) · Document post PDF ≤300 pages / ≤100 MB · Single Image Ad 1200×627, <5 MB, max 7680×4320.

**AVIF, HEIC and WebP are not in any accepted-format list** — which rules out cICP-tagged AVIF as an upload vector on LinkedIn. (WebP is structurally incapable anyway: 8-bit only, no HDR signalling, no gain map.)

### 5.5 Brand precedent — read this before citing anybody

- **Lusha — NO EVIDENCE.** Seven targeted searches; nothing. (Beware the false positive: "Lusha HDR" returns a database entry for the unrelated architecture firm HDR, Inc.) **[refuted]**
- **Brandlight — NO EVIDENCE.** The company exists (Tel Aviv, founded Oct 2024); nothing ties it to HDR creative. **[refuted]**
- **Artisan / Artisan AI ("Aristan") — NO EVIDENCE.** Their documented attention play is physical OOH ("Stop Hiring Humans"), not HDR imagery. The spelling "Aristan" matches no company, so even the identification is speculative. **[refuted]**
- **AlphaSignal (12 Jan 2026, "first sighting") — [UNVERIFIED].** One commentary blog, unfetchable, snippet-only; the same source hedges that it is not proof of first use. Do not present as the origin point.
- **Taupia / Anton Neike (20 Jan 2026) — [UNVERIFIED].** A named individual, quoted, with attributed intent, sourced entirely to that same unfetchable blog plus a LinkedIn post whose text nobody read. The ~1,000-nit figure is suspiciously identical to one tool's default preset. **Do not repeat this in a deck.**
- **Wiz — [UNVERIFIED, partially attributable].** The only brand named by any primary source. Superwhite's own site says *"The glowing Wiz logo in the LinkedIn feed is a regular JPEG with an HDR color profile embedded, **made with Superwhite**"* — vendor self-attribution about another company's asset, with a chronology problem (Superwhite's repo was created 2026-07-10, after the writeups it credits for documenting the effect). **State it as "a vendor claims", never as fact.**
- **Port.io "before Wiz" — [refuted].** Surfaced once, non-reproducible.
- **Origin chain that IS solid:** `dtinth/superwhite` (2023, 1.6k stars — ~1 KB HEVC 10-bit PQ clip authored at 5000-nit peak, base64 data-URL `<video>`) → the April 2025 HDR Slack-emoji wave (`sharpletters.net`, HDRify, `swankjesse/hdr-emojis`, ImageMagick + Rec.2020 ICC at 16-bit) → the 2026 LinkedIn logo craze. **[SOLID]**

**No numbers exist.** Zero impressions, CTR, follower or engagement-lift figures are attached to this technique anywhere. Every effectiveness claim is qualitative. **If anyone quotes you a lift number, assume it is invented.** **[SOLID negative result]**

---

## 6. Production recipe — ordered, exact

### Step 0 — Rasterise from vector (never from a compressed raster)

```bash
cd /home/user/Cotera
rsvg-convert -w 2400 -h 2400 hdr-logo/assets/cotera-arrow.svg -o /tmp/cotera-mark@2400.png
```
✅ `rsvg-convert 2.58.0` is installed. There is no HDR SVG path — every route consumes raster RGB(A). Rasterise at 2–4× the final display size, do the HDR maths on the raster, then downsample.

### Step 1 — Build the full asset set with the repo's own toolchain (preferred)

```bash
cd /home/user/Cotera
python3 make-linkedin-hdr-assets.py --out output
```
Produces, per visual variant, an SDR control plus **both** HDR encodings at 600/800/1200 nits:
- `*-<n>nits.jpg` — 8-bit PQ/BT.2020 JPEG + `Rec. ITU-R BT.2100 PQ` ICC (the ICC bet)
- `*-<n>nits-gainmap.jpg` — SDR base + gain map + `hdrgm` XMP + MPF (the correct-everywhere path)

Shipping both and A/B-uploading them is the **only** way to learn what LinkedIn's pipeline actually does, since nobody has published a byte-level answer.

For the multi-format set (AVIF/PNG/UltraHDR at four aspect ratios):
```bash
python3 hdr-logo/src/build.py --size avatar --style brand-tile      # 400x400 company page
python3 hdr-logo/src/build.py --size square                          # 1200x1200 feed
python3 hdr-logo/src/build.py --size portrait                        # 1080x1350 mobile feed
python3 hdr-logo/src/build.py --size landscape                       # 1200x627 link preview
```

### Step 2 — Generic ffmpeg route (if you're building outside the repo)

**The critical, badly-documented detail:** `npl=` is a no-op on the **linearize** step (`t=linear`) when the input is SDR-tagged — SDR white lands on exactly 100 nits regardless. But `npl=` on the **delinearize** step (`t=smpte2084`) directly sets what linear 1.0 means in nits. **Verified here ✅** (white pixel → 8-bit 148 / 192 / 230 for `npl=203 / 1000 / 4000`, matching the §2.3 table exactly).

```bash
# 16-bit BT.2020/PQ PNG with alpha, ffmpeg writes cICP automatically
ffmpeg -y -i logo.png -vf "\
setparams=color_primaries=bt709:color_trc=iec61966-2-1:colorspace=bt709:range=pc,\
zscale=t=linear:npl=100,format=gbrapf32le,\
zscale=p=bt2020,zscale=t=smpte2084:npl=800:r=full,format=rgba64be" \
  -frames:v 1 -update 1 cotera-hdr-pq.png
```

Notes, all verified: **(a)** the leading `setparams=` is **required** — without input tagging the graph fails; **(b)** use `format=gbrapf32le` (with the `a`) or alpha is lost; **(c)** ffmpeg 6.1 zscale has **no `m=rgb` value** — omit `m=` for RGB output; **(d)** a digit in the output filename triggers image2-sequence mode, so pass `-update 1`; **(e)** ffmpeg writes `cICP 09100001` **plus a `cHRM` fallback, and no `gAMA`** (PQ isn't expressible as a gamma). PNG cICP read+write landed in FFmpeg commit `6f79f09` (Leo Izen, 2023-01-25), i.e. FFmpeg 6.0+. ✅
**Do not use the `exposure=exposure=N` workaround** that circulates widely — it's clamped to ±3 stops per instance, needs chaining, and is strictly worse than `npl` on the delinearize step. **[refuted]**

10-bit PQ AVIF:
```bash
ffmpeg -y -i logo.png -vf "setparams=color_primaries=bt709:color_trc=iec61966-2-1:colorspace=bt709:range=pc,\
zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt2020,\
zscale=t=smpte2084:npl=800:m=bt2020nc:r=full,format=yuv444p10le" \
  -c:v libaom-av1 -still-picture 1 -crf 18 \
  -color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc -color_range pc \
  -frames:v 1 cotera-hdr-pq.avif        # no alpha on this path
```

### Step 3 — avifenc (if you need alpha in AVIF)

```bash
avifenc --cicp 9/16/9 -d 10 -y 444 -r full --clli 800,80 --ignore-icc -q 90 -s 4 \
        cotera-hdr-pq.png cotera-hdr-pq.avif
```
`--nclx` is an alias for `--cicp`; the triplet is `P/T/M`. `9/16/0` (identity matrix) also works but **requires `-y 444`** — with 4:2:0 avifenc prints *"matrixCoefficients may not be set to identity (0) when subsampling. Resetting MC to defaults (6)."*

Three landmines:
1. **avifenc does no transfer-function or gamut conversion — it labels.** It *does* do RGB→YUV matrixing, bit-depth scaling and subsampling, but the PQ maths must already be in the pixels. Tagging a plain sRGB PNG `9/16/9` produces a mislabelled SDR file. ✅
2. **libavif < 1.4.0 ignores an input PNG's `cICP` chunk.** Fed an ffmpeg-produced PNG (cICP + cHRM), avifenc 1.0.4 emits **CP 9 / TC 2 / MC 6** — primaries right, transfer *Unspecified*, which is more dangerous than an obvious failure. ✅ **Always pass `--cicp` explicitly on < 1.4.0.** PNG cICP reading was added in 1.4.0 (2026-03-04).
3. **Avoid libavif exactly 1.3.0** — issue #2850, `--cicp` silently dropped from the AV1 sequence header (colr box still fine, but ffprobe-style tools saw nothing). Fixed by PR #2859 in 1.4.0. Use ≤1.2.1 or ≥1.4.0. There is no 1.3.1.

### Step 4 — Gain-map JPEG via libultrahdr (the "correct everywhere" file)

`ultrahdr_app` is **not installed here**; the repo's `ultrahdr.py` does it in pure Python instead (and it works ✅). If you want the reference encoder:

```bash
git clone https://github.com/google/libultrahdr && cd libultrahdr && mkdir build && cd build
cmake -G Ninja -DUHDR_BUILD_DEPS=1 -DUHDR_BUILD_EXAMPLES=1 \
      -DUHDR_WRITE_XMP=1 -DUHDR_WRITE_ISO=1 ../ && ninja
```
⚠️ `UHDR_WRITE_XMP` defaults **OFF** — a stock build emits ISO 21496-1 metadata only, and older Adobe-era readers expect the `hdrgm` XMP. Turn both on.

```bash
# raw 10-bit PQ HDR buffer + SDR base -> Ultra HDR
ffmpeg -y -i logo.png -vf "…same chain…,format=p010le" -frames:v 1 -f rawvideo hdr_p010.yuv
ffmpeg -y -i logo.png -q:v 2 sdr.jpg
ultrahdr_app -m 0 -p hdr_p010.yuv -a 0 -i sdr.jpg -w 800 -h 800 \
             -C 2 -t 2 -R 1 -q 96 -Q 95 -s 4 -M 1 -D 1 -L 800 -z cotera_uhdr.jpg
ultrahdr_app -m 1 -j cotera_uhdr.jpg -P     # probe: dump gain-map metadata
```
Key flags: `-C` HDR gamut [0 bt709, 1 p3, 2 bt2100] · `-t` HDR transfer [0 linear, 1 hlg, 2 pq] · `-s` gain-map downsample 1–128 · `-M` multi-channel 0/1 · `-k`/`-K` min/max content boost (linear) · `-L` target display peak nits, **[203, 10000]** · `-G` gamma · `-P` probe. Constraint: *"hlg, pq shall be paired with rgba1010102 or p010."*

Gain-map AVIF (libavif ≥ 1.2.0):
```bash
avifgainmaputil combine sdr.png hdr_pq.png out.avif \
  --cicp-base 1/13/6 --cicp-alternate 9/16/9 \
  -q 90 --qgain-map 90 --depth-gain-map 10 --yuv-gain-map 444 -y 444 -d 10 --max-headroom 2.0
avifgainmaputil printmetadata out.avif
```

### Step 5 — Inject/repair PNG chunks as the LAST step

**Almost every re-save destroys the tag.** Verified: ImageMagick 6.9.12 `convert` strips `cICP`/`mDCV`/`cLLI`; a plain Pillow `open().save()` strips everything; sharp strips it. **OxiPNG is the one optimizer documented to preserve `cICP`.** Make chunk injection the final build step, and re-verify after any CDN/CMS/optimizer pass.

```python
# pure stdlib chunk builder — works with zero binaries
import struct, zlib
def chunk(typ, data):
    return (struct.pack('>I', len(data)) + typ + data
            + struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff))

cICP = chunk(b'cICP', bytes([9, 16, 0, 1]))            # BT.2100 PQ, full range

def mDCV(maxl=800.0, minl=0.0001):
    prim = ((0.708,0.292), (0.170,0.797), (0.131,0.046))          # BT.2020 R,G,B
    d  = b''.join(struct.pack('>HH', round(x/0.00002), round(y/0.00002)) for x,y in prim)
    d += struct.pack('>HH', round(0.3127/0.00002), round(0.3290/0.00002))   # D65
    d += struct.pack('>II', round(maxl/0.0001), round(minl/0.0001))
    return chunk(b'mDCV', d)                                       # exactly 24 bytes

def cLLI(maxcll=800.0, maxfall=80.0):
    return chunk(b'cLLI', struct.pack('>II', round(maxcll/0.0001), round(maxfall/0.0001)))
```
Insert `cICP` + `mDCV` + `cLLI` immediately after `IHDR` (all three MUST precede PLTE and IDAT), and drop any pre-existing `sRGB`/`gAMA`/`cHRM`/`iCCP` that would contradict them (`cICP` outranks them all, but stripping avoids decoder disagreement).

### Step 6 — Verify, then upload

Run the checklist in §8. Then upload **directly as JPEG**, no cropping or editing in LinkedIn's composer. Ship the `*-normal-no-glow.jpg` rollback file alongside it.

---

## 7. Pure-Python fallback (no ffmpeg, no ImageMagick, no libavif, no Node)

Confirmed working with **Pillow 12.3.0 + numpy 2.4.6** ✅ (both installed here). This is the route that runs anywhere.

### 7.1 Capability boundaries (all verified)

| Want | Pure Python? |
|---|---|
| 8-bit PQ JPEG + Rec.2100 PQ ICC | ✅ Pillow `save(..., icc_profile=...)` |
| 8-bit PNG + `cICP` | ✅ `PngImagePlugin.PngInfo().add(b"cICP", bytes([9,16,0,1]))` — lands correctly between IHDR and IDAT |
| **16-bit RGB/RGBA PNG** | ❌ Pillow cannot (`_OUTMODES` has `I;16`/`I;16B` greyscale only; `Image.fromarray(uint16 HxWx4)` raises `TypeError`). **→ hand-write it with `struct` + `zlib`, ~40 lines** |
| Gain-map JPEG (Ultra HDR) | ✅ the repo's `ultrahdr.py` does it; `@monogrid/gainmap-js` does it in pure Node |
| **AVIF with CICP** | ❌ **Impossible.** Pillow's `AvifImagePlugin` exposes no `cicp`/`nclx` option; neither does pillow-avif-plugin 1.6.0; sharp/libvips exposes no CICP control either. You need a binary. |

### 7.2 The whole pipeline in numpy

```python
import numpy as np, struct, zlib
from PIL import Image, PngImagePlugin

SDR_WHITE = 203.0                      # ITU-R Report BT.2408
PEAK      = 800.0                      # target nits for the mark
M1, M2 = 2610/16384, 2523/4096*128
C1, C2, C3 = 3424/4096, 2413/4096*32, 2392/4096*32
SRGB_TO_2020 = np.array([[0.62740390, 0.32928304, 0.04331307],
                         [0.06909729, 0.91954040, 0.01136232],
                         [0.01639144, 0.08801331, 0.89559525]])

def srgb_to_linear(c):
    return np.where(c <= 0.04045, c/12.92, ((c+0.055)/1.055)**2.4)

def pq_inv_eotf(nits):                 # linear nits -> PQ code 0..1
    y = np.clip(nits/10000.0, 0.0, 1.0)
    return ((C1 + C2*y**M1) / (1.0 + C3*y**M1))**M2

img = Image.open("cotera-mark.png").convert("RGB")
rgb = srgb_to_linear(np.asarray(img).astype(np.float64)/255.0)

# 1. gamut FIRST (skipping this oversaturates every brand colour)
rgb2020 = rgb @ SRGB_TO_2020.T

# 2. smoothstep gate on BT.2020 relative luminance — lift near-white only
Y = 0.2627*rgb2020[...,0] + 0.6780*rgb2020[...,1] + 0.0593*rgb2020[...,2]
t = np.clip((Y - 0.55) / (0.90 - 0.55), 0.0, 1.0)
t = t*t*(3.0 - 2.0*t)
gain = 1.0 + (PEAK/SDR_WHITE - 1.0) * t**1.5

# 3. scale to absolute luminance, then PQ-encode
nits = rgb2020 * SDR_WHITE * gain[..., None]
code = pq_inv_eotf(nits)

# --- Output A: 8-bit PQ JPEG + ICC  (the LinkedIn payload) ---
out8 = np.round(np.clip(code, 0, 1) * 255.0).astype(np.uint8)
icc  = open("rec2100-pq.icc", "rb").read()
Image.fromarray(out8).save("cotera-hdr.jpg", quality=96, subsampling=0,
                           progressive=True, icc_profile=icc)

# --- Output B: 8-bit PNG + cICP (flat art only; banding risk on ramps) ---
info = PngImagePlugin.PngInfo()
info.add(b"cICP", bytes([9, 16, 0, 1]))
Image.fromarray(out8).save("cotera-hdr-8bit.png", pnginfo=info)
```

### 7.3 16-bit RGBA PNG writer (stdlib only — Pillow can't)

```python
def write_png16(path, rgba16, extra_chunks=()):
    """rgba16: uint16 array HxWx4 (big-endian written), colour_type 6, bit_depth 16."""
    h, w, _ = rgba16.shape
    raw = b''.join(b'\x00' + rgba16[y].astype('>u2').tobytes() for y in range(h))  # filter 0
    ihdr = struct.pack('>IIBBBBB', w, h, 16, 6, 0, 0, 0)
    out  = [b'\x89PNG\r\n\x1a\n', chunk(b'IHDR', ihdr)]
    out += list(extra_chunks)                       # cICP, mDCV, cLLI — before IDAT
    out += [chunk(b'IDAT', zlib.compress(raw, 9)), chunk(b'IEND', b'')]
    open(path, 'wb').write(b''.join(out))

write_png16("cotera-hdr-16bit.png",
            np.dstack([np.round(np.clip(code,0,1)*65535).astype(np.uint16),
                       np.full(code.shape[:2], 65535, np.uint16)]),
            extra_chunks=(cICP, mDCV(800.0), cLLI(800.0, 80.0)))
```
Verified round-trip: `ffprobe` reads it back as `pix_fmt=rgba64be, color_transfer=smpte2084, color_primaries=bt2020`; exiftool populates the `PNG-cICP` group. ✅

### 7.4 Getting a Rec.2100 PQ ICC profile without Adobe

Three options: **(1)** use the one already in this repo — `.claude/skills/hdr-logo-glow/scripts/icc_pq.py` builds it programmatically (8,776 bytes, v4.3, sampled 4096-entry `curv` TRCs, lcms2-accepted ✅); **(2)** copy Apple's from `/System/Library/ColorSync/Profiles` on a Mac; **(3)** W3C's `ITUR_2100_PQ_FULL.ICC` from `github.com/w3c/png-hdr-pq`. **PQ cannot be expressed as an ICC `parametricCurveType`** — it must be a sampled `curveType` with enough entries (4096 is comfortable). A validator that sees a `para` tag where PQ is claimed is looking at a broken profile.

### 7.5 Node fallback

`sharp` handles SVG rasterisation (via librsvg) and JPEG/PNG encode, but **cannot tag CICP** — no `cicp`/`nclx` option exists in its API, and it silently downconverts 16-bit PNG input to 8-bit unless you call `.toColourspace('rgb16')`. (libvips *does* attach a default nclx profile via `heifsave.c`, so a `colr` box usually exists in its AVIFs — you just can't choose its values from sharp.) Pair sharp with a ~30-line Buffer/zlib PNG chunk injector, and use `@monogrid/gainmap-js`'s `encodeJPEGMetadata()` for the Ultra HDR container (pure JS; both `mimeType: 'image/jpeg'` fields are mandatory or it throws).

---

## 8. Verification checklist — proving a file is genuinely HDR

Run these in order. Everything marked ✅ was executed here against Cotera's files.

### A. File level — before you ever look at a screen

**PQ + ICC JPEG (the LinkedIn payload):**
```bash
exiftool -a -G1 -s cotera-hdr.jpg | grep -iE 'ProfileDescription|ColorSpaceData|EncodingProcess|YCbCrSubSampling|MPF|hdrgm'
python3 .claude/skills/hdr-logo-glow/scripts/validate.py cotera-hdr.jpg
```
Expect: a profile description naming Rec.2100/Rec.2020 PQ · `ColorSpaceData: RGB` · `ProfileConnectionSpace: XYZ` · `Progressive DCT` · `YCbCr4:4:4 (1 1)` · **no MPF, no XMP-hdrgm** · TRC is a sampled `curv` with ≥4096 samples · TRC midpoint ≈ 0.009 (a plain gamma curve would be ~0.2) · lcms2 accepts the profile. ✅ *All of these pass on Cotera's current output.*

**PNG:**
```bash
python3 -c "
import struct;d=open('f.png','rb').read();p=8
while p<len(d):
    ln=struct.unpack('>I',d[p:p+4])[0];t=d[p+4:p+8].decode()
    print(t,ln,d[p+8:p+8+min(ln,24)].hex())
    if t=='IDAT':break
    p+=12+ln"
ffprobe -v error -show_entries stream=pix_fmt,color_transfer,color_primaries -of default f.png
exiftool -G1 -a -s f.png | grep PNG-cICP
pngcheck -v f.png          # validates cICP, mDCV, cLLI (not installed here)
```
Expect: `cICP 4 09100001` before IDAT; `color_transfer=smpte2084`, `color_primaries=bt2020`. ✅

**AVIF — use `avifdec --info`, not ffprobe:**
```bash
avifdec --info f.avif      # AUTHORITATIVE: reads the MIAF nclx colr box
ffprobe -v error -show_entries stream=pix_fmt,color_primaries,color_transfer,color_space,color_range -of csv=p=0 f.avif
```
They can and do disagree — `avifdec` reads the `colr` box (spec-authoritative), ffprobe reads the AV1 sequence-header OBU. I patched a `colr` box from TC 16→18 and `avifdec` reported 18 while ffprobe still said `smpte2084`. **[SOLID]**

**Ultra HDR JPEG:**
```bash
exiftool -a -G1 -s f.jpg | grep -iE 'hdrgm|DirectoryItem|MPImage|NumberOfImages'
ultrahdr_app -m 1 -j f.jpg -P
```
Expect: `XMP-hdrgm Version 1.0` · `DirectoryItemSemantic Primary` + `GainMap` · `MPF0 NumberOfImages 2` · two `MPImage` entries with plausible lengths and offsets. ✅

⚠️ **exiftool reads PNG `cICP` but cannot write it, and has no `mDCV`/`cLLI` support at all** (v12.76; `PNG.pm` on master defines only a read-only `cICP` SubDirectory). `exiftool -PNG:ColorPrimaries=9` returns *"Sorry, PNG:ColorPrimaries doesn't exist or isn't writable."* ✅

### B. Numeric level — is the luminance actually where you think?

Decode the PQ and print percentiles: p50 / p90 / p99 / p100 in nits, **% of pixels above 203 nits**, and peak glow ratio. Those four numbers *are* the design brief in numeric form. Cotera's build already emits this into `*-build.json` (`peak_nits`, `mean_nits`, `sdr_white_multiple`, `frac_above_sdr_white`, `apl_vs_sdr_white`). ✅

### C. Renderer level — the decisive tag test

**Serve over `http://`** (a `file://` canvas is tainted: *"The canvas has been tainted by cross-origin data"*), draw an 8×8 solid patch to a 2D canvas and read it back with `getImageData`. Identical pixel bytes render differently depending only on the 4-byte tag. Measured in Chromium 141 on an SDR surface:

| File | RGB read back |
|---|---|
| `gray130_plain.png` (untagged) | 130,130,130 |
| `gray130_pq.png` (cICP `09 10 00 01`) | **158,158,158** |
| `gray130_hlg.png` (cICP `09 12 00 01`) | **126,126,126** |
| `g130_pq.avif` (`--cicp 9/16/9`) | **158,158,158** |

**[SOLID]** — this is the cheapest possible proof the tag is being honoured.

⚠️ **Canvas readback cannot prove the *glow*.** Chrome tone-maps/clips HDR to the canvas colour space: a 1000-nit white reads back as 255,255,255 in both `srgb` and `display-p3`. `rec2100-pq` is **not** a valid `PredefinedColorSpace` in Chromium 141 (throws). Runtime capability probe: `matchMedia('(dynamic-range: high)').matches`.

### D. Eyeball level — only on real hardware

Browser only. **A screenshot cannot capture the effect** — macOS tone-maps to SDR on capture, so 4,000 nits collapses to plain white. You cannot review this in Slack, a deck, or Figma. Send the file, or a self-contained HTML page with images inlined as data URIs.

Build a verify page with: (1) flat PQ probes at 600/800/1200 nits beside a plain `#ffffff` CSS swatch — **if the probes don't outshine the swatch, the display is the limiting factor, not the file**; (2) a LinkedIn-dark row and a **LinkedIn-light row** (`#f4f5f7` — LinkedIn's default is light mode, and a coloured tile on white behaves differently); (3) the SDR control beside the HDR file.

If nothing glows, work down this list: brightness at 100% (try ~70%) → Low Power Mode → backgrounded window → viewing in Finder/Quick Look/Preview → non-XDR external monitor.

⚠️ The two practitioner toolchains **directly contradict each other** on whether macOS Preview/Finder shows or flattens HDR. Unresolved — **trust the browser**, which is where LinkedIn renders anyway.

### E. Post-upload — the test nobody has actually run

Download the served `media.licdn.com` rendition and exiftool it. Confirm the ICC profile is still present, at what byte size, and whether size variants (`shrink_200_200` vs `shrink_100_100`) differ. **This is the single most valuable unpublished experiment in this whole area** and you are one `curl` away from it.

---

## 9. Failure modes

1. **Washed-out grey soup.** A PQ-tagged image decoded as sRGB: diffuse white (PQ 0.581) paints as 58% grey, 100 nits becomes 50% grey, and 1 nit lifts to 15% (8-bit 38 vs ~20 in sRGB). Crushed contrast, milky blacks, no white point. **[SOLID — arithmetic]**
2. **Hard clipping.** A non-tone-mapping renderer crushes everything above SDR white to white and everything below the floor to black. The reference fix is a real operator (BT.2390's ICtCp working space + Hermite-spline knee, or BT.2446), with BT.2408 supplying the 203-nit anchor. **[LIKELY]**
3. **Too dark, not too bright.** Engines that parse the tag but have no HDR pipeline render nclx-tagged images *very darkly* — the opposite failure. Firefox does this. **[LIKELY]**
4. **Silent profile loss.** Screenshots, editor re-saves, messenger compression (WhatsApp/iMessage), copy-paste, and LinkedIn's own composer all strip it. Because the pixels are PQ, losing the tag doesn't restore the original — it produces failure mode 1. **[SOLID]**
5. **Gain maps have none of these failure modes** — which is exactly why the abuse case avoids them and why LinkedIn stripping them removes the glow cleanly rather than breaking the image.
6. **On an SDR-only panel there is no mechanism to exploit.** Headroom is 1.0 by definition; the best case is a correct tone-map back to diffuse white.

---

## 10. Platform clamping status as of August 2026

### Web (the layer that matters)

**CSS `dynamic-range-limit`** — CSS Color HDR Level 1. Grammar: `standard | no-limit | constrained | <dynamic-range-limit-mix()>`. **Initial value: `no-limit`. Inherited: yes.** Animation type: by `dynamic-range-limit-mix()`. **[SOLID — read from the editor's draft source]**
- `standard` = "the highest luminance color displayed is the same as HDR Reference White, i.e. the CSS color `white`"
- `constrained` = "somewhat greater… such that a mix of SDR and HDR content can be comfortably viewed together"
- `no-limit` = "much greater… the precise level is not specified"
- `dynamic-range-limit-mix()` converts values internally to stops above HDR Reference White; *"for privacy reasons, the actual calculated result is not exposed"* (headroom is a fingerprinting vector).
- **Keywords were renamed:** `high` → `no-limit`, `constrained-high` → `constrained` (WG resolution, #11698). Any article using the old names is stale.

**Shipping:** Chrome/Edge 136 (Apr/May 2025) — the Chromium runtime flag `CSSDynamicRangeLimit` is `status: "stable"` ✅. Safari **26.0, released September 15, 2025**: *"Added partial support for the dynamic-range-limit property: `standard` and `no-limit`, non-animatable. (144486108)"* — `constrained` was **not** shipped in 26.0–26.4, though WebKit trunk's `CSSProperties.json` now parses all three with initial `no-limit`, gated behind `supportHDRDisplayEnabled`; what remains unimplemented is animation (`webkit.org/b/293339`). Firefox: no support. **[SOLID]**

**The CSSWG explicitly rejected making `standard` the default.** Issue #11711 (Sam Weinig, 14 Feb 2025) proposed initial `standard` + a UA rule `video { dynamic-range-limit: no-limit }`. **Closed "Rejected as Wontfix by CSSWG Resolution", 9 July 2025.** Companion #11429 closed "Accepted", spec retains `Initial: no-limit`. **So the web still defaults to unclamped HDR, and a feed gets flashbanged unless the site opts out.** **[SOLID]**

**The one proposal aimed squarely at ad abuse is open and unimplemented.** csswg-drafts **#11704** (13 Feb 2025) — an iframe permissions policy (`allow="constrained-extended-dynamic-range"`) to irreversibly cap EDR inside third-party frames. Still labelled "needs design/proposal", no PRs. Until it exists, an embedding page cannot stop an ad iframe re-raising its own limit. **[SOLID]**

WebKit argued for a clamped default and lost: Simon Fraser on WebKit/standards-positions#312 — *"I am also not convinced that the default value for `high` is appropriate. `constrained-high` seems like a more reasonable default."* Said Abou-Hallawa's proposed `auto` value (#11558), which would resolve to `constrained` except in cases like fullscreen video, is **not in the current spec grammar**. **[LIKELY]**

Safari 26.x point releases have been **fixing HDR gaps, not clamping**: 26.2 (Dec 12 2025) fixed HDR images in CSS backgrounds/borders/SVG (158076668); 26.3 (Feb 11 2026) and 26.4 (Mar 24 2026) fixed positioned/transformed/opacity-altered `<img>` with HDR JPEG gain maps rendering as SDR (163517157, 156858374). No 26.x release imposes a platform-side brightness limit. **[SOLID]**

### OS

- **iOS 26** added `UITraitCollection.hdrHeadroomUsageLimit` (iOS/iPadOS/Mac Catalyst/tvOS/visionOS 26.0): *"Headroom usage is disabled in certain UI configurations, such as when all an application's windows are in the background."* Enum `UIHDRHeadroomUsageLimit`: `.active` / `.inactive` / `.unspecified`. It **advises** apps to restrict; it doesn't hard-clamp their output. **[SOLID]**
- Per-view limiting has existed since **iOS 17**: `UIImage.DynamicRange` `.standard` / `.constrainedHigh` / `.high` / `.unspecified`, via `UIImageView.preferredImageDynamicRange`, `UITraitCollection.imageDynamicRange`, SwiftUI `View.allowedDynamicRange(_:)`. **[SOLID]**
- User-facing: **Settings → Photos → "View Full HDR"** (Photos-scoped, not system-wide; developers **cannot read its state** — confirmed by Apple Developer Forums thread 765582, where a DTS engineer directs the poster to file an enhancement request). **[SOLID for the API gap]**
- **Android 15 (API 35)**: `Window.setDesiredHdrHeadroom(float)` — *"an example would be a messaging app or gallery thumbnail view where some amount of HDR pop is desired without overly influencing the perceived brightness of the majority SDR content."* Must be ≥1.0, range 0.0–10000.0, 0.0 = system default. Google's guidance: **~2× for mixed SDR/HDR UI**, 5–8× for fully-HDR scenes. **[SOLID]**
- **Android 16 QPR**: user-facing **"Enhanced HDR brightness"** toggle + intensity slider (Settings → Display & touch), on by default, spotted in QPR1 Beta 1 (June 2025), reported stable with QPR2 (Dec 2025). The most consequential consumer counter to this technique on Android. **[LIKELY]**
- **SMPTE ST 2094-50** (Google + Apple + NBCUniversal): adaptive metadata with a Reference White Anchor and headroom-adaptive gain curves. The direction of travel is *HDR that adapts to headroom*, which structurally weakens fixed-PQ absolute-nit assets. **[LIKELY]**

### Social platforms

- **Instagram/Meta: no HDR clamp was found.** Extensive searching turned up **no** announcement, press report, engineering post or changelog showing Meta clamping HDR in 2025 in response to abuse. Meta appears to have moved the *other* way. Treat "Instagram clamped HDR" as **unsupported** — but note this is an argument from absence under blocked egress, not proof. **[hedged negative]** The only Meta brake found is the viewer toggle *"Disable HDR video playback"* (Settings → Media quality), reported since ~Aug 2023 and sourced to a **single third-party tweet**, not Meta docs. **[UNVERIFIED path/date]**
- **TikTok**: accepts HDR, tone-maps server-side, shipped a viewer-side HDR-off toggle ~Oct 2025; dims its own UI chrome during HDR playback. **[LIKELY]**
- **X/Twitter**: reportedly the one major platform passing gain-map HDR through to profile pictures; flattens HDR video. **[LIKELY]**
- **Bluesky**: no HDR support; request open since Nov 2024 (social-app#6172). **Mastodon**: strips metadata, killing gain maps (mastodon#31233) — a de-facto clamp. **[SOLID/LIKELY]**
- **Slack / Discord**: HDR renders in the desktop clients and Chrome; some mobile clients down-convert. **[LIKELY]**
- **Email**: dead end. Can I Email lists HDR image support as unsupported in Apple Mail, Gmail, Outlook, Yahoo. **[LIKELY]**
- **The tooling trend runs the other way:** WordPress 7.1 (Jul 2026) detects gain-map files on upload and preserves them through every generated sub-size. Don't count on platforms passively stripping HDR. **[LIKELY]**
- **Instagram is reported to strip or reject the ICC/PQ trick**, needing gain maps instead. **LinkedIn is currently the outlier.** **[LIKELY]**

### LinkedIn

No public statement, help-centre entry, policy update, or enforcement action was found — in either direction. The technique reportedly still worked in August 2026. LinkedIn could kill it with one config change (normalize or drop ICC on re-encode, or render logos through a clamped surface). **[LIKELY]**

---

## 11. Risks and accessibility

**Technical risks, ranked by likelihood:**
1. **LinkedIn normalizes or drops ICC profiles on re-encode.** One config change, silent, kills every PQ-in-ICC asset instantly. Undocumented pipeline; the repo that documented it says so itself.
2. **OS/browser clamping spreads** (Android's Enhanced HDR brightness, iOS 26 headroom limits, a WebKit `auto` default, LinkedIn adopting `dynamic-range-limit: constrained` on feed images). This *degrades* rather than breaks the asset — you lose the glow, not the logo.
3. **Policy action.** No platform rule currently names HDR brightness. The closest analogues are Meta's Advertising Standards barring *"overly disruptive tactics, such as flashing screens"* and Google Ads rejecting strobing display creatives — neither has been applied to static HDR.

**Mitigation, non-negotiable:** always ship an SDR-correct base — a gain-map file where possible, and a `*-normal-no-glow.jpg` rollback in the same folder — so a clamp costs the glow, not the logo. Treat this as a **months-long stunt, not a permanent mark**.

**Accessibility — real, and stated plainly by the people shipping the technique:**
- *"A bright patch in a night-time feed is genuinely uncomfortable, and worse for anyone with migraine or light sensitivity."*
- The CSS Color HDR spec's Accessibility Considerations, verbatim: *"Some individuals may have a sensitivity to very bright colors, so user agents **should** provide a mechanism to limit the maximum luminance at user option. The toe and knee procedure in section 5.4.1 … of [Rec BT.2390] is suggested as suitable."* (By contrast, Security Considerations reads: *"No Security concerns have been raised on this document."*) **[SOLID]**
- **There is still no `prefers-reduced-hdr` media feature anywhere.** Media Queries Level 5 has only `dynamic-range` and `video-dynamic-range` (capability queries: standard/high). **A page that wants to be polite has no signal to respond to.** **[SOLID]**
- Every major consumer HDR off-switch that exists was built in response to user discomfort — Instagram (2023), TikTok (2025), Android's toggle+slider (2025), iOS "View Full HDR", Reduce White Point, third-party YouTube HDR disablers, and a Chrome extension ("Glowless", Aug 2026) built specifically to suppress glowing LinkedIn icons. That is the strongest available evidence the objection is real and already actioned.
- ⚠️ **Do NOT repeat the "14% of the population have scotopic sensitivity" statistic.** It comes from a satirical/commentary outlet, is not backed by any medical source I could reach, and would be indefensible in a brand document. **[refuted]**
- **The technique's own documenters call it abuse.** Tom Nick's write-up is titled *"(Ab)use HDR images for marketing"* and says the use is *"firmly in abusive territory."* `swankjesse/hdr-emojis` describes itself as *"a quarantine of some extremely bright PNG files"* with three explicit cautions against workplace use.
- **Mitigation is lit-area, not nits.** Reducing the lit fraction (Cotera is at 13.6%) does more for comfort than reducing peak nits, and preserves the effect.

**Power:** HDR content costs measurable panel power — Samsung Display + Intel announced "SmartPower HDR" (Jan 2026), analysing per-frame peak brightness to feed the TCON an optimal driving voltage, reclaiming up to 22% of OLED emissive power in standard usage and **up to 17% on HDR content**. A persistent bright logo in a scrolling feed is the pathological case. **[LIKELY]**

**Reputational:** *"It reads as clever from a startup and as desperate from anyone else."* And copying the originator's exact treatment (inverted polarity, near-full-field glow) reads as a copy rather than your own idea. The tragedy-of-the-commons critique is now the dominant framing: the mechanism only works because it's rare.

---

## 12. Refuted claims — do not reintroduce these

| Widely repeated | Reality |
|---|---|
| "Use `exposure=exposure=N` in ffmpeg; `npl` doesn't scale brightness" | `npl` on the **delinearize** step (`t=smpte2084:npl=N`) sets it exactly, in one step. Verified ✅ |
| "iPhone headroom = 1600/1000 = 1.6×" | Invalid arithmetic. Apple states iPhone XDR "up to 8× SDR headroom"; headroom ≈ max brightness ÷ *current* SDR brightness |
| "OLED peak is measured at ~3% APL" | Not a spec-defined point. VESA uses a 10% centre patch; vendors quote 1–10% |
| "CICP 12 = DCI-P3" | 11 = DCI-P3 (RP 431-2); **12 = Display P3 / P3-D65** (EG 432-1) |
| MatrixCoefficients list jumping 14→16 | **15 = IPT-C2 (SMPTE ST 2128)** exists; 3 is reserved |
| "avifenc doesn't convert pixel values" | It does RGB→YUV matrixing, depth scaling and subsampling — it just does no transfer/gamut conversion |
| "avifenc without `--cicp` falls back to 1/13/6" | On an ffmpeg PNG (cICP + cHRM) it emits **9/2/6** — primaries right, transfer *Unspecified*. More dangerous |
| "sharp/libvips AVIFs have no `colr` box" | `heifsave.c` sets `output_nclx_profile`; a box normally exists. sharp just gives you no control over it |
| "Safari 26.0 dynamic-range-limit is radar 141784069" | It's **144486108**. HDR images = 134397601, WebGPU canvas HDR = 128164668 (the published list is off by one) |
| "4000 nits is what everyone uses" | One tool's argparse default; an independent tool targets 10,000; no industry standard exists |
| "Structure beats noise 7:1" | Invalid statistic — divides a 16-code *range* by a 2.2-code *σ* |
| "Five independent tools confirm ICC survives LinkedIn" | One source (Tom Nick); the rest are downstream. Common-source fallacy |
| "AirDrop converts HDR to SDR" | AirDrop does a HEIC→JPEG *format* transcode, not tone mapping |
| "Instagram clamped HDR in 2025 after abuse" | No announcement, post, or changelog found in either direction |
| "PNG cICP is not the LinkedIn route" | Superwhite states PNG cICP **is** the company-page variant; JPEG+ICC is the feed-post variant. Contested — test both |
| Lusha / Brandlight / Artisan used HDR logos | **No evidence whatsoever.** Do not repeat |
| "14% of the population have scotopic sensitivity" | Satirical-outlet statistic, no medical backing |

---

## 13. Open questions and gaps

**Blocking for Cotera — cheap to answer, nobody has:**
1. **Does the ICC profile survive a `media.licdn.com` round trip, and does it survive size variants?** Upload → download the served rendition → exiftool. Nobody has published this. One `curl` away.
2. **Does the ICC `desc` string matter, or only the TRC?** Live LinkedIn files carry Apple's `Rec2020 Gamut with PQ Transfer` (with a 12-byte `cicp` tag); Cotera's carries `Rec. ITU-R BT.2100 PQ` (no `cicp` tag). Test both, and **add the `cicp` tag** regardless.
3. **PQ+ICC vs gain-map, head to head on the same surface.** Your build already emits both — upload both and compare. This is the experiment the whole field is missing.
4. **Native LinkedIn app vs mobile web vs desktop Chrome.** Every source says "on an iPhone" without stating the client. Android app behaviour is completely undocumented. **This is the single biggest unknown for estimating real-world reach.**
5. **8-bit banding on Cotera's specific bloom.** Your multi-sigma halo is exactly the construction that bands under PQ at 8 bits. Compare `-800nits.jpg` against `-800nits.png` (16-bit) side by side.
6. **Company-page logo vs feed post vs personal profile photo**, same file, each surface, exiftool on the way back down.

**Spec-level gaps:**
- ITU-T H.273 itself was unreachable (itu.int blocked). All code points come from libavif + FFmpeg, which cite it and agree with the PNG spec's worked examples — but not verified against the ITU text.
- ISO 21496-1:2025 is paywalled. Field names come from libavif/libultrahdr; the spec's own snake_case spelling, `version`/`minimum_version`/`writer_version` fields, and the exact bit layout of the ISO metadata blob are **unverified**.
- PNG spec text was read from the w3c/png **Fourth Edition editor's draft**. `cICP`/`mDCV`/`cLLI` wording is believed identical to the published Third Edition; **`hRWL` is 4th-Edition-only**.
- The AVIF `tmap` derived-item ISOBMFF box structure was never read from the AVIF spec directly — libavif's struct is the proxy.
- No exact Chrome milestone was confirmed for PNG `cICP`/`mDCV`/`cLLI` (chromestatus blocked); behaviour verified empirically in Chromium 141 only.

**Measurement gaps:**
- **No quantitative measurement of delivered luminance** — what a given file actually produces in nits on a given phone at a given brightness, after ABL and system tone mapping. Every nits figure in this brief is an *encoded code value*, not measured emission.
- Whether MaxCLL 4000 vs 1000 changes anything on iOS/macOS/Android compositors is untested.
- No incremental battery-draw measurement for a glowing logo in a scrolling feed.
- No peer-reviewed study on photosensitivity/migraine risk specifically from feed-embedded HDR stills.

**Unresolved contradictions:**
- macOS Preview/Finder: one toolchain says it flattens HDR, the other says to verify there. Unresolved; trust the browser.
- Superwhite maps PNG cICP → company page and JPEG+ICC → feed post; another tool maps PNG cICP → "your own site only". Directly contradictory.
- Whether a PQ-ICC trick works inside a WebP `ICCP` chunk was never tested (and WebP's 8-bit limit makes it moot).

**Commercial-bias warning:** much of the practitioner corpus (Superwhite, hdr.chiefcontentmarketer.com, adamodigi.com, xhdr.org) sells or promotes tooling while describing LinkedIn's pipeline. Their claims mutually corroborate but are not independent of a shared incentive to say the trick works.