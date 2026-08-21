# The compositing pipeline

Read this before changing `compose.py`. The model is small; the ordering
constraints are what matter.

## The scene, in absolute nits

Everything is built in linear light measured in cd/m², because that is the only
representation in which "brighter than white" is a meaningful statement.

```
ground     a dark wash, a few nits          (visible in 'inset' and 'mark' layouts)
panel      the brand surface                (gradient, or supplied artwork)
glow       multi-scale gaussian halo        (a brand colour, above SDR white)
mark       the logo mark                    (the brightest thing in the frame)
```

`hdrkit.py` holds the transfer functions (ST 2084 PQ, HLG) and the BT.709↔BT.2020
matrices. `SDR_WHITE_NITS = 203` per BT.2408 is the anchor for every ratio.

## Layouts

- **`bleed`** — a procedural brand gradient edge to edge, mark centred. No frame,
  no border, so no edge artefacts are possible. The safest default.
- **`inset`** — supplied panel artwork placed on a dark ground at
  `backdrop_frac`. Use when the brand asset is a specific shape (a rounded icon
  tile) that must be preserved.
- **`mark`** — the mark alone on a dark ground.

In `inset`, panel and mark are placed with **one** transform so they stay in
register. Fitting each to its own ink bounds independently makes the mark drift
inside the panel as the canvas size changes.

## Ordering constraints

**Linear light throughout, including the downsample.** Composite supersampled,
then average in linear light. Averaging gamma-encoded pixels across a 4×
brightness step biases the result dark, producing a fringe around the mark.

**Geometry separate from luminance.** `build_layers()` rasterises and returns
masks; `render()` applies luminances. That separation is what lets the HDR and SDR
renditions be the same picture at different brightnesses, which the gain map
depends on. Never produce the SDR rendition by tone-mapping the HDR one — author
it, with the mark landing exactly on 203 nits.

**Brand artwork at true values.** Scale so `#ffffff` in the artwork maps to
`panel_white_nits` and let other colours land where the designer put them.
Normalising by the artwork's own brightest pixel stretches the brand colour toward
white. A gradient from `#322f82` to `#6366f2` came out lavender this way — the
kind of error a client spots instantly and a developer does not.

**Gradients interpolate in linear light too.** Interpolating stops in sRGB
darkens the midpoints — the classic muddy-gradient look.

**Glow on top of the panel, clipped to it.** Composited underneath, the panel
hides the halo, which is the opposite of light spilling out of the mark. And
where a panel meets a darker ground, an unclipped halo lights that ground at the
boundary and draws a bright rim around the entire logo. That rim reads as a
deliberate border and is the most common "this looks wrong but I can't say why"
complaint.

## Glow construction

A single gaussian gives a halo with a discernible edge. Summing several at
different radii gives a wide, soft falloff that still reads as glow after a
tone-mapper has compressed it. Weights push the character:

- **broad glow** — `sigmas (0.008, 0.022, 0.055, 0.120)`, `weights (0.50, 0.32, 0.18, 0.12)`
- **tight glow** — `sigmas (0.004, 0.011, 0.026, 0.052)`, `weights (0.66, 0.26, 0.10, 0.04)`

Tight reads as "the mark is brighter"; broad reads as "the mark is blurry". When
someone asks for more glow they usually mean *brighter*, so try tightening the
kernel and raising `peak_nits` before widening anything.

Sigmas are fractions of the short axis, so the look holds across canvas sizes.
Glow is low-frequency, so it is computed at half resolution — about 4× faster,
visually identical.

## Adding a format

Write the encoder in `encode.py`, taking the linear-nits scene, and add a matching
byte-level check to `validate.py` plus a branch in `validate.classify()`. A format
without a validator will eventually ship mistagged; the validator is the point,
not paperwork.

## Gain map, in code terms

`ultrahdr.compute_gainmap(hdr, sdr)` returns the encoded map plus metadata;
`ultrahdr.build()` assembles the container; `ultrahdr.reconstruct()` is the
decoder side. Use `reconstruct()` both to prove a file is self-consistent and to
render honest previews at a chosen headroom — it is what `simulate.py` draws.

A single-channel gain map is exact when the HDR and SDR renditions differ only in
level, which authored renditions do. If you ever make them differ in hue, you need
three channels.
