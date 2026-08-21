#!/usr/bin/env python3
"""
make_hdr_logo.py -- build SDR + HDR/PQ LinkedIn test assets for the Cotera logo.

Pipeline
--------
1.  Parse ``logo-long-solid.svg`` when present, otherwise use the canonical
    Cotera icon/arrow geometry embedded below.
2.  Emit clean source assets: ``cotera-icon-solid.svg``,
    ``cotera-arrow-isolated.svg`` (and ``cotera-logo-long-solid.svg`` when a
    source lockup is available).
3.  Render each SVG with cairosvg at 4x supersampling, box-downsampled to the
    final 800x800 canvas.  Rendering the arrow on its own gives a clean,
    antialiased coverage mask that no colour-key can match.
4.  Composite the SDR control image (sRGB, no alpha).
5.  For the HDR variants: sRGB -> linear -> absolute nits (SDR white = 203) ->
    boost *only* the masked arrow pixels to the target peak -> BT.709 to
    BT.2020 -> ST.2084 PQ -> 8-bit.
6.  Save progressive, 4:4:4, quality-95+ JPEGs with the generated Rec.2100 PQ
    ICC profile embedded (see ``icc_pq.py``).

The arrow mask is the intersection of a *geometric* mask (the arrow rendered
alone) and a *photometric* near-white test on the composited pixels, so the
purple gradient and its brand glow are never touched.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cairosvg  # noqa: E402
from icc_pq import (  # noqa: E402
    BT2020_PRIMARIES,
    BT2408_REFERENCE_WHITE_NITS,
    BT709_PRIMARIES,
    build_rec2100_pq_icc,
    linear_rgb_conversion_matrix,
    normalize_icc_datetime,
    pq_oetf,
)

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

# --------------------------------------------------------------------------
# Canonical Cotera geometry (fallback when logo-long-solid.svg is absent)
# --------------------------------------------------------------------------

ICON_VIEWBOX = (0.0, 0.0, 200.0, 200.0)
ICON_CORNER_RADIUS = 32.0

GRADIENT_DEF = """<linearGradient id="cotera-gradient" x1="174.41" y1="170.89" x2="25.26" y2="28.8" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#322f82"/>
      <stop offset=".19" stop-color="#403fa4"/>
      <stop offset=".42" stop-color="#4f50c5"/>
      <stop offset=".64" stop-color="#5a5cde"/>
      <stop offset=".83" stop-color="#6063ec"/>
      <stop offset="1" stop-color="#6366f2"/>
    </linearGradient>"""

# Arrow paths in the icon's 200x200 user space -- the single source of truth
# for both the icon asset and the isolated arrow asset.
ARROW_PATHS = [
    "M64.64,140.13c9.3-11.23,21.79-17.41,35.18-17.41s25.88,6.18,35.18,17.41c.06,.07,.11,.13,.17,.2,"
    ".54,.66,1.53,.72,2.14,.11l10.49-10.49c.42-.42,.54-1.07,.29-1.62,0,0-31.51-106.08-48.08-106.08,"
    "-16.57,0-48.08,106.08-48.08,106.08-.25,.55-.13,1.19,.29,1.62l10.29,10.29c.6,.6,1.59,.55,2.13-.1h.01Z",
    "M99.81,138.7c-.1,0-.2,0-.3,0-14.2,.16-21.16,17.4-11.12,27.44l11.6,11.6,11.33-11.33c10.14-10.14,"
    "3.11-27.54-11.22-27.7-.1,0-.2,0-.3,0Z",
]

# Brand drop-glow behind the arrow (the <filter> in the source SVG).  cairosvg
# ignores SVG filters, so it is reproduced numerically in composite_icon().
GLOW_COLOR = (0x44, 0x38, 0xC9)
GLOW_OPACITY = 0.75
GLOW_STDDEV = 2.0  # in 200-unit user space

ARROW_JPEG_BACKGROUND = "#0b0b14"

DEFAULT_NIT_TARGETS = (600, 800, 1200)


# --------------------------------------------------------------------------
# Source SVG parsing
# --------------------------------------------------------------------------


def _is_whiteish(fill):
    if not fill:
        return False
    f = fill.strip().lower()
    return f in {"#fff", "#ffffff", "white", "rgb(255,255,255)"}


def parse_source_svg(path: Path):
    """Pull the gradient, white arrow paths and corner radius out of the source.

    Returns a dict with whatever could be recovered; missing pieces fall back to
    the canonical constants above so the pipeline always produces output.
    """
    result = {
        "gradient": GRADIENT_DEF,
        "arrow_paths": list(ARROW_PATHS),
        "corner_radius": ICON_CORNER_RADIUS,
        "viewbox": ICON_VIEWBOX,
        "wordmark_paths": [],
        "source": "built-in canonical geometry",
    }
    if not path or not path.exists():
        return result

    tree = ET.parse(path)
    root = tree.getroot()
    result["source"] = str(path)

    vb = root.get("viewBox")
    if vb:
        nums = [float(v) for v in re.split(r"[ ,]+", vb.strip())]
        if len(nums) == 4:
            result["viewbox"] = tuple(nums)

    grad = root.find(f".//{{{SVG_NS}}}linearGradient")
    if grad is not None:
        result["gradient"] = ET.tostring(grad, encoding="unicode").strip()

    rect = root.find(f".//{{{SVG_NS}}}rect")
    if rect is not None and rect.get("rx"):
        result["corner_radius"] = float(rect.get("rx"))

    # The icon square is the leftmost artwork; the wordmark sits to its right.
    # Split white paths on the icon's right edge so the arrow is isolated.
    icon_right = result["viewbox"][1] + result["viewbox"][3] if rect is None else (
        float(rect.get("x", 0)) + float(rect.get("width", result["viewbox"][2]))
    )
    arrow, wordmark = [], []
    for el in root.iter(f"{{{SVG_NS}}}path"):
        d = el.get("d")
        if not d or not _is_whiteish(el.get("fill")):
            continue
        xs = [float(m) for m in re.findall(r"M\s*(-?[\d.]+)", d)]
        (arrow if (not xs or min(xs) < icon_right) else wordmark).append(d)
    if arrow:
        result["arrow_paths"] = arrow
    result["wordmark_paths"] = wordmark
    return result


# --------------------------------------------------------------------------
# SVG asset generation
# --------------------------------------------------------------------------


def icon_svg(spec, *, corner_radius=None, with_glow=True):
    r = spec["corner_radius"] if corner_radius is None else corner_radius
    x, y, w, h = spec["viewbox"]
    glow_def = f"""
    <filter id="cotera-glow" filterUnits="userSpaceOnUse">
      <feOffset dx="0" dy="0"/>
      <feGaussianBlur result="blur" stdDeviation="{GLOW_STDDEV}"/>
      <feFlood flood-color="#{GLOW_COLOR[0]:02x}{GLOW_COLOR[1]:02x}{GLOW_COLOR[2]:02x}" flood-opacity="{GLOW_OPACITY}"/>
      <feComposite in2="blur" operator="in"/>
      <feComposite in="SourceGraphic"/>
    </filter>""" if with_glow else ""
    group_open = '<g filter="url(#cotera-glow)">' if with_glow else "<g>"
    paths = "\n    ".join(f'<path fill="#ffffff" d="{d}"/>' for d in spec["arrow_paths"])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="{SVG_NS}" viewBox="{x} {y} {w} {h}" width="{w}" height="{h}">
  <defs>
    {spec['gradient']}{glow_def}
  </defs>
  <rect fill="url(#cotera-gradient)" x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}"/>
  {group_open}
    {paths}
  </g>
</svg>
"""


def backdrop_svg(spec):
    """The gradient with square corners -- fills the JPEG behind the rounded icon."""
    return icon_svg(spec, corner_radius=0, with_glow=False).replace(
        '<path fill="#ffffff"', '<path fill="none"'
    )


def arrow_only_svg(spec, viewbox=None):
    x, y, w, h = viewbox or spec["viewbox"]
    paths = "\n  ".join(f'<path fill="#ffffff" d="{d}"/>' for d in spec["arrow_paths"])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="{SVG_NS}" viewBox="{x} {y} {w} {h}" width="{w}" height="{h}">
  {paths}
</svg>
"""


def arrow_isolated_svg(spec, viewbox):
    x, y, w, h = viewbox
    paths = "\n  ".join(f'<path fill="currentColor" d="{d}"/>' for d in spec["arrow_paths"])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- Cotera arrow glyph, isolated. fill="currentColor" so it inherits colour. -->
<svg xmlns="{SVG_NS}" viewBox="{x:.2f} {y:.2f} {w:.2f} {h:.2f}">
  {paths}
</svg>
"""


def long_lockup_svg(spec):
    """Cleaned long lockup -- only emitted when the source supplied a wordmark."""
    if not spec["wordmark_paths"]:
        return None
    x, y, w, h = spec["viewbox"]
    icon_r = spec["corner_radius"]
    arrow = "\n    ".join(f'<path fill="#ffffff" d="{d}"/>' for d in spec["arrow_paths"])
    word = "\n  ".join(f'<path fill="#ffffff" d="{d}"/>' for d in spec["wordmark_paths"])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="{SVG_NS}" viewBox="{x} {y} {w} {h}">
  <defs>
    {spec['gradient']}
  </defs>
  <rect fill="url(#cotera-gradient)" width="200" height="200" rx="{icon_r}" ry="{icon_r}"/>
  <g>
    {arrow}
  </g>
  {word}
</svg>
"""


# --------------------------------------------------------------------------
# Rasterisation
# --------------------------------------------------------------------------


def render_rgba(svg_text, size, supersample):
    """Render an SVG to a float RGBA array in 0..1 at ``size`` px, box-filtered."""
    hi = size * supersample
    png = cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), output_width=hi, output_height=hi)
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    if supersample > 1:
        img = img.resize((size, size), Image.BOX)  # exact area average: no ringing
    return np.asarray(img).astype(np.float64) / 255.0


def blur1d(a, kernel, axis):
    r = (len(kernel) - 1) // 2
    pad = [(r, r) if i == axis else (0, 0) for i in range(a.ndim)]
    p = np.pad(a, pad, mode="constant")
    out = np.zeros_like(a)
    n = a.shape[axis]
    for j, w in enumerate(kernel):
        sl = [slice(None)] * a.ndim
        sl[axis] = slice(j, j + n)
        out += w * p[tuple(sl)]
    return out


def gaussian_blur(a, sigma):
    if sigma <= 0:
        return a
    r = max(1, int(math.ceil(sigma * 3)))
    x = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-(x ** 2) / (2.0 * sigma ** 2))
    k /= k.sum()
    return blur1d(blur1d(a, k, 0), k, 1)


# --------------------------------------------------------------------------
# Masking
# --------------------------------------------------------------------------


def smoothstep(lo, hi, x):
    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def near_white_score(rgb, white_lo=0.80, white_hi=0.94, sat_lo=0.06, sat_hi=0.20):
    """Photometric 'how white is this pixel' in 0..1, from gamma-encoded sRGB."""
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    return smoothstep(white_lo, white_hi, mn) * (1.0 - smoothstep(sat_lo, sat_hi, sat))


def build_arrow_mask(rgb, arrow_alpha, mode="both"):
    photometric = near_white_score(rgb)
    if mode == "geometric":
        mask = arrow_alpha
    elif mode == "photometric":
        mask = photometric
    else:
        mask = np.minimum(arrow_alpha, photometric)
    return np.clip(mask, 0.0, 1.0), photometric


# --------------------------------------------------------------------------
# HDR encode
# --------------------------------------------------------------------------


def srgb_eotf(v):
    v = np.clip(v, 0.0, 1.0)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def srgb_oetf(v):
    v = np.clip(v, 0.0, 1.0)
    return np.where(v <= 0.0031308, v * 12.92, 1.055 * v ** (1.0 / 2.4) - 0.055)


BT709_TO_BT2020 = linear_rgb_conversion_matrix(BT709_PRIMARIES, BT2020_PRIMARIES)


def encode_pq(linear_rgb, mask, target_nits, sdr_white_nits=BT2408_REFERENCE_WHITE_NITS):
    """Linear-light BT.709 RGB 0..1 + arrow mask -> 8-bit BT.2020 ST.2084 PQ."""
    nits = np.clip(linear_rgb, 0.0, None) * float(sdr_white_nits)

    # Only the masked arrow is lifted; everything else keeps its SDR luminance.
    boost = 1.0 + mask * (float(target_nits) / float(sdr_white_nits) - 1.0)
    nits = nits * boost[..., None]

    nits_2020 = np.clip(nits @ BT709_TO_BT2020.T, 0.0, None)
    code = pq_oetf(nits_2020)
    return np.clip(np.rint(code * 255.0), 0, 255).astype(np.uint8)


def to_uint8(rgb):
    return np.clip(np.rint(np.clip(rgb, 0.0, 1.0) * 255.0), 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------
# Compositing
# --------------------------------------------------------------------------


def hex_to_rgb01(value):
    v = value.lstrip("#")
    return np.array([int(v[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float64) / 255.0


def composite_icon(spec, size, supersample, glow=True):
    """Full-bleed gradient + brand glow + white arrow, composited in LINEAR light.

    Averaging gamma-encoded pixels across the arrow's 4x brightness step darkens
    the average and leaves a dark fringe around the glyph -- measured at up to
    34.7/255 on the antialiased edge before this was fixed.  Every blend below
    therefore happens in linear light and is re-encoded once at the end.

    Returns (linear BT.709 RGB, arrow coverage alpha).
    """
    backdrop = render_rgba(backdrop_svg(spec), size, supersample)
    icon = render_rgba(icon_svg(spec, with_glow=False), size, supersample)
    arrow = render_rgba(arrow_only_svg(spec), size, supersample)

    a_icon = icon[..., 3:4]
    lin = srgb_eotf(backdrop[..., :3]) * (1.0 - a_icon) + srgb_eotf(icon[..., :3]) * a_icon

    arrow_alpha = arrow[..., 3]
    if glow:
        sigma = GLOW_STDDEV * size / spec["viewbox"][2]
        glow_a = (gaussian_blur(arrow_alpha, sigma) * GLOW_OPACITY)[..., None]
        glow_lin = srgb_eotf(np.array(GLOW_COLOR, dtype=np.float64) / 255.0)
        lin = lin * (1.0 - glow_a) + glow_lin * glow_a

    a = arrow_alpha[..., None]
    lin = lin * (1.0 - a) + 1.0 * a  # white arrow on top, in linear light
    return np.clip(lin, 0.0, 1.0), arrow_alpha


def composite_arrow(spec, viewbox, size, supersample, background):
    """Isolated white arrow on a flat dark background, composited in linear light."""
    x, y, w, h = viewbox
    side = max(w, h)
    square_vb = (x - (side - w) / 2.0, y - (side - h) / 2.0, side, side)
    pad = side * 0.12
    padded_vb = (square_vb[0] - pad, square_vb[1] - pad, side + 2 * pad, side + 2 * pad)

    arrow = render_rgba(arrow_only_svg(spec, padded_vb), size, supersample)
    arrow_alpha = arrow[..., 3]
    bg = srgb_eotf(hex_to_rgb01(background))
    a = arrow_alpha[..., None]
    lin = bg * (1.0 - a) + 1.0 * a
    return np.clip(lin, 0.0, 1.0), arrow_alpha


def arrow_bbox_viewbox(spec, size=1024, margin=0.04):
    """Tight viewBox of the arrow glyph in the icon's user space."""
    arrow = render_rgba(arrow_only_svg(spec), size, 1)
    alpha = arrow[..., 3] > 0.004
    rows = np.where(alpha.any(axis=1))[0]
    cols = np.where(alpha.any(axis=0))[0]
    vx, vy, vw, vh = spec["viewbox"]
    sx, sy = vw / size, vh / size
    x0 = vx + cols[0] * sx
    x1 = vx + (cols[-1] + 1) * sx
    y0 = vy + rows[0] * sy
    y1 = vy + (rows[-1] + 1) * sy
    mx, my = (x1 - x0) * margin, (y1 - y0) * margin
    return (x0 - mx, y0 - my, (x1 - x0) + 2 * mx, (y1 - y0) + 2 * my)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def save_jpeg(path, array_u8, icc_profile, quality):
    Image.fromarray(array_u8, mode="RGB").save(
        path,
        format="JPEG",
        quality=quality,
        progressive=True,
        optimize=True,
        subsampling=0,          # 4:4:4 -- keep the arrow edges and PQ codes intact
        icc_profile=icc_profile,
    )
    return path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# cICP overrides iCCP/sRGB/gAMA/cHRM, so drop those rather than leaving them to
# argue with it.
_PNG_DROP = {b"iCCP", b"sRGB", b"gAMA", b"cHRM"}


def save_png_cicp(path, array_u8, primaries=9, transfer=16, matrix=0, full_range=1):
    """Write a PNG carrying a cICP chunk declaring BT.2020 + ST.2084 PQ.

    PNG's cICP chunk is the *documented* no-gain-map HDR still-image path in
    Safari 26 (and Chrome reads it too), whereas "baseline JPEG + PQ ICC profile"
    is undocumented on Apple's stack.  This file is therefore the control that
    separates "this display/browser cannot do HDR at all" from "the JPEG's ICC
    route specifically is what failed".
    """
    import io
    import zlib

    buf = io.BytesIO()
    Image.fromarray(array_u8, mode="RGB").save(buf, format="PNG", optimize=True)
    raw = buf.getvalue()
    assert raw[:8] == PNG_SIGNATURE

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    out = bytearray(PNG_SIGNATURE)
    i = 8
    while i < len(raw):
        (length,) = struct.unpack(">I", raw[i:i + 4])
        kind = raw[i + 4:i + 8]
        end = i + 12 + length
        if kind not in _PNG_DROP:
            out += raw[i:end]
        if kind == b"IHDR":
            # cICP must precede PLTE and IDAT.
            out += chunk(b"cICP", struct.pack(">BBBB", primaries, transfer, matrix, full_range))
        i = end

    Path(path).write_bytes(bytes(out))
    return Path(path)


def srgb_icc():
    """Embed a real sRGB profile in the SDR controls (never in the HDR files)."""
    from PIL import ImageCms

    raw = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    return normalize_icc_datetime(raw)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    root = Path(__file__).resolve().parent.parent
    ap.add_argument("--source", type=Path, default=root / "logo-long-solid.svg")
    ap.add_argument("--outdir", type=Path, default=root / "output")
    ap.add_argument("--size", type=int, default=800)
    ap.add_argument("--supersample", type=int, default=4)
    ap.add_argument("--quality", type=int, default=98)
    ap.add_argument("--sdr-white", type=float, default=BT2408_REFERENCE_WHITE_NITS)
    ap.add_argument("--nits", type=int, nargs="+", default=list(DEFAULT_NIT_TARGETS))
    ap.add_argument("--arrow-nits", type=int, default=800)
    ap.add_argument("--arrow-bg", default=ARROW_JPEG_BACKGROUND)
    ap.add_argument("--mask-mode", choices=["geometric", "photometric", "both"], default="both")
    ap.add_argument("--no-glow", action="store_true", help="drop the brand drop-glow behind the arrow")
    args = ap.parse_args()

    out = args.outdir
    out.mkdir(parents=True, exist_ok=True)

    spec = parse_source_svg(args.source)
    print(f"geometry source : {spec['source']}")
    print(f"arrow subpaths  : {len(spec['arrow_paths'])}")

    # -- 1. source SVG assets ------------------------------------------------
    arrow_vb = arrow_bbox_viewbox(spec)
    (out / "cotera-icon-solid.svg").write_text(icon_svg(spec), encoding="utf-8")
    (out / "cotera-arrow-isolated.svg").write_text(arrow_isolated_svg(spec, arrow_vb), encoding="utf-8")
    lockup = long_lockup_svg(spec)
    if lockup:
        (out / "cotera-logo-long-solid.svg").write_text(lockup, encoding="utf-8")
        print("wrote cotera-logo-long-solid.svg (cleaned from source lockup)")
    else:
        print("skipped cotera-logo-long-solid.svg (no wordmark paths in source)")

    # -- 2. profiles ---------------------------------------------------------
    pq_profile = build_rec2100_pq_icc(sdr_white_nits=args.sdr_white)
    (out / "Rec2100-PQ.icc").write_bytes(pq_profile)
    # Second profile with the conventional full-range (10000-nit) PQ curve and
    # the canonical description.  Apple's ColorSync is not documented to read the
    # ICC cicp tag, and PQ recognition elsewhere in the ecosystem is keyed to
    # profile identity, so this variant exists to A/B that on Safari/iOS.
    pq_profile_full = build_rec2100_pq_icc(
        description="ITU-R BT.2100 PQ Full",
        sdr_white_nits=args.sdr_white,
        trc_mode="full",
    )
    (out / "Rec2100-PQ-fullrange.icc").write_bytes(pq_profile_full)
    srgb_profile = srgb_icc()

    manifest = []

    def emit(name, u8, profile, note):
        p = save_jpeg(out / name, u8, profile, args.quality)
        manifest.append({"file": name, "bytes": p.stat().st_size, "note": note})
        print(f"  {name:44s} {p.stat().st_size:>8,d} B  {note}")

    # -- 3. square icon ------------------------------------------------------
    print("\nsquare icon (800x800, full-bleed gradient):")
    lin, arrow_alpha = composite_icon(spec, args.size, args.supersample, glow=not args.no_glow)
    rgb = srgb_oetf(lin)   # gamma-encoded, for the SDR file and the near-white test
    mask, photometric = build_arrow_mask(rgb, arrow_alpha, args.mask_mode)
    coverage = float(mask.mean())
    print(f"  arrow mask coverage: {coverage * 100:.2f}% of canvas "
          f"(geometric {arrow_alpha.mean() * 100:.2f}%, photometric {photometric.mean() * 100:.2f}%)")
    if coverage > 0.35:
        print("  WARNING: mask covers >35% of the canvas -- the whole image may glow.")

    emit("cotera-linkedin-sdr-icon.jpg", to_uint8(rgb), srgb_profile, "SDR control, sRGB")
    for nits in args.nits:
        emit(
            f"cotera-linkedin-hdr-icon-{nits}nits.jpg",
            encode_pq(lin, mask, nits, args.sdr_white),
            pq_profile,
            f"HDR, arrow at {nits} nits",
        )

    # Safari/ColorSync probe: identical pixels, conventional full-range PQ curve.
    emit(
        f"cotera-linkedin-hdr-icon-{args.arrow_nits}nits-fullrange.jpg",
        encode_pq(lin, mask, args.arrow_nits, args.sdr_white),
        pq_profile_full,
        f"HDR, arrow at {args.arrow_nits} nits, full-range PQ curve",
    )

    png_name = f"cotera-linkedin-hdr-icon-{args.arrow_nits}nits-cicp.png"
    png_path = save_png_cicp(out / png_name, encode_pq(lin, mask, args.arrow_nits, args.sdr_white))
    manifest.append({"file": png_name, "bytes": png_path.stat().st_size,
                     "note": "HDR control, PNG cICP chunk (documented Safari path)"})
    print(f"  {png_name:44s} {png_path.stat().st_size:>8,d} B  PNG cICP control")

    # -- 4. isolated arrow ---------------------------------------------------
    print(f"\nisolated arrow (800x800 on {args.arrow_bg}):")
    a_lin, a_alpha = composite_arrow(spec, arrow_vb, args.size, args.supersample, args.arrow_bg)
    a_rgb = srgb_oetf(a_lin)
    a_mask, _ = build_arrow_mask(a_rgb, a_alpha, args.mask_mode)
    print(f"  arrow mask coverage: {a_mask.mean() * 100:.2f}% of canvas")
    emit("cotera-linkedin-sdr-arrow.jpg", to_uint8(a_rgb), srgb_profile, "SDR control, sRGB")
    emit(
        f"cotera-linkedin-hdr-arrow-{args.arrow_nits}nits.jpg",
        encode_pq(a_lin, a_mask, args.arrow_nits, args.sdr_white),
        pq_profile,
        f"HDR, arrow at {args.arrow_nits} nits",
    )

    # -- 5. round-trip sanity check -----------------------------------------
    # Decode the saved JPEG and confirm the arrow reaches its target while the
    # purple background stays at or below SDR reference white.  JPEG ringing at
    # the arrow edge is the thing to watch: in PQ code space a couple of code
    # values is hundreds of nits, which is why quality stays >= 98 and the mask
    # is never feathered.
    from icc_pq import pq_eotf

    print("\nround trip (decoded back out of the saved JPEGs):")
    report = {}
    tolerance = args.sdr_white * 1.05
    # Pixels touching the glyph legitimately carry some of the arrow's light
    # through antialiasing, so hold them out: this check is for mask leakage
    # into the purple field, not for the edge itself.
    near_arrow = mask > 0.001
    for _ in range(2):
        near_arrow = (near_arrow
                      | np.roll(near_arrow, 1, 0) | np.roll(near_arrow, -1, 0)
                      | np.roll(near_arrow, 1, 1) | np.roll(near_arrow, -1, 1))
    field = ~near_arrow
    for nits in args.nits:
        arr = np.asarray(Image.open(out / f"cotera-linkedin-hdr-icon-{nits}nits.jpg"))
        decoded = pq_eotf(arr.astype(np.float64).max(axis=2) / 255.0)
        interior = mask > 0.999
        background = field
        over = int((decoded[background] > args.sdr_white).sum())
        way_over = int((decoded[background] > tolerance).sum())
        report[f"{nits}nits"] = {
            "arrow_median_nits": round(float(np.percentile(decoded[interior], 50)), 1),
            "arrow_p99_9_nits": round(float(np.percentile(decoded[interior], 99.9)), 1),
            "background_peak_nits": round(float(decoded[background].max()), 1),
            "background_pixels_above_sdr_white": over,
            "background_pixels_above_tolerance": way_over,
        }
        # A handful of edge pixels a few nits over reference white is JPEG
        # ringing, not mask leakage; only a real spill is worth flagging.
        flag = "ok" if way_over == 0 else f"WARNING: {way_over} background px above {tolerance:.0f} nits"
        print(f"  {nits:>4} nits -> arrow median {report[f'{nits}nits']['arrow_median_nits']:>7.0f} nits, "
              f"background peak {report[f'{nits}nits']['background_peak_nits']:>6.0f} nits  [{flag}]")

    (out / "build-manifest.json").write_text(
        json.dumps(
            {
                "size": args.size,
                "quality": args.quality,
                "sdr_white_nits": args.sdr_white,
                "mask_mode": args.mask_mode,
                "mask_coverage_pct": round(coverage * 100, 3),
                "round_trip": report,
                "files": manifest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {len(manifest)} JPEGs to {out}")


if __name__ == "__main__":
    main()
