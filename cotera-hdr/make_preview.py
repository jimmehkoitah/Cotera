#!/usr/bin/env python3
"""
make_preview.py -- illustrate the HDR effect on an SDR medium, honestly.

The glow cannot be *shown* in an SDR image: "brighter than white" has no
representation in a file whose maximum value is white.  What can be shown is the
RATIO.  On an HDR display the arrow sits at the target peak (800 nits) while page
white sits at the BT.2408 reference of 203 nits -- a 3.94x linear-light ratio.

So the simulation scales the entire scene down in linear light by
203 / target_nits, which puts the arrow at SDR maximum and everything else
proportionally below it.  For the 800-nit file, page white lands on sRGB 138.
The result is a dim page with a blazing arrow, which is the correct *relative*
relationship and an incorrect *absolute* one -- on a real HDR display the page
still looks normally bright and the arrow looks super-bright.  Every panel is
labelled accordingly.

A bloom halo is added to the simulated panel.  This is not a cheat: a real
800-nit highlight scatters in the eye and in any camera photographing the
screen, so veiling glare is part of what the effect actually looks like.  It is
drawn only in the simulation, never in the shipped assets.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_hdr_logo as M  # noqa: E402

S = 2  # supersample factor for crisp text

# LinkedIn-ish light mode palette
PAGE_BG = (244, 242, 238)
CARD_BG = (255, 255, 255)
CARD_BORDER = (224, 223, 220)
TEXT_PRIMARY = (0, 0, 0)
TEXT_SECONDARY = (102, 102, 102)
ACTION_GREY = (95, 95, 95)

FONT_DIR = Path("/usr/share/fonts/truetype/liberation")
SDR_WHITE_NITS = 203.0


def font(name, size):
    return ImageFont.truetype(str(FONT_DIR / name), size * S)


def srgb_to_linear(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(a):
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1.0 / 2.4) - 0.055)


def circle_mask(size):
    m = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(m).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    return m.resize((size, size), Image.LANCZOS)


def build_card(icon_rgb, icon_mask, caption):
    """Render one LinkedIn-style feed post.  Returns (uint8 RGB, arrow mask float)."""
    pad, card_w = 26 * S, 720 * S
    img_side = card_w
    head_h, body_h, act_h = 84 * S, 46 * S, 56 * S
    card_h = head_h + body_h + img_side + act_h
    w = card_w + pad * 2
    h = card_h + pad * 2

    panel = Image.new("RGB", (w, h), PAGE_BG)
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle((pad, pad, pad + card_w, pad + card_h), radius=8 * S,
                        fill=CARD_BG, outline=CARD_BORDER, width=1 * S)

    # header: avatar + author
    av = 48 * S
    ax, ay = pad + 16 * S, pad + 16 * S
    avatar = Image.fromarray(
        (np.clip(icon_rgb, 0, 1) * 255).astype(np.uint8)
    ).resize((av, av), Image.LANCZOS)
    panel.paste(avatar, (ax, ay), circle_mask(av))

    tx = ax + av + 12 * S
    d.text((tx, ay + 1 * S), "Cotera", font=font("LiberationSans-Bold.ttf", 15), fill=TEXT_PRIMARY)
    d.text((tx, ay + 21 * S), "1,204 followers", font=font("LiberationSans-Regular.ttf", 12),
           fill=TEXT_SECONDARY)
    d.text((tx, ay + 38 * S), "2h  ·  Edited", font=font("LiberationSans-Regular.ttf", 12),
           fill=TEXT_SECONDARY)

    d.text((pad + 16 * S, pad + head_h - 6 * S), caption,
           font=font("LiberationSans-Regular.ttf", 14), fill=TEXT_PRIMARY)

    # the image itself
    iy = pad + head_h + body_h
    icon = Image.fromarray((np.clip(icon_rgb, 0, 1) * 255).astype(np.uint8)).resize(
        (img_side, img_side), Image.LANCZOS)
    panel.paste(icon, (pad, iy))

    # action bar
    by = iy + img_side + 16 * S
    f = font("LiberationSans-Bold.ttf", 13)
    x = pad + 24 * S
    for label in ("Like", "Comment", "Repost", "Send"):
        d.rounded_rectangle((x, by + 2 * S, x + 14 * S, by + 16 * S), radius=3 * S,
                            outline=ACTION_GREY, width=2)
        d.text((x + 22 * S, by), label, font=f, fill=ACTION_GREY)
        x += int(d.textlength(label, font=f)) + 68 * S

    # arrow mask in panel coordinates, matching the pasted image exactly
    mask_panel = np.zeros((h, w), dtype=np.float64)
    mres = np.asarray(
        Image.fromarray((icon_mask * 255).astype(np.uint8)).resize((img_side, img_side), Image.LANCZOS)
    ).astype(np.float64) / 255.0
    mask_panel[iy:iy + img_side, pad:pad + img_side] = mres
    return np.asarray(panel).astype(np.float64) / 255.0, mask_panel


def simulate_hdr(panel, mask, target_nits, bloom=True):
    """Scale the scene by the linear-light ratio so the arrow reaches SDR max."""
    ratio = SDR_WHITE_NITS / float(target_nits)
    lin = srgb_to_linear(panel) * ratio
    # The masked arrow is the one thing that keeps full linear value.
    lin = lin * (1.0 - mask[..., None]) + np.clip(srgb_to_linear(panel), 0, 1) * mask[..., None]

    if bloom:
        # Veiling glare: a real 800-nit highlight scatters in the eye and in any
        # camera pointed at the screen.  Two radii, weighted by the headroom.
        strength = min(1.0, (target_nits / SDR_WHITE_NITS - 1.0) / 4.0)
        halo = (0.16 * M.gaussian_blur(mask, 9 * S)
                + 0.10 * M.gaussian_blur(mask, 34 * S)) * strength
        lin = lin + halo[..., None] * np.array([1.0, 0.99, 0.97])

    return np.clip(linear_to_srgb(lin), 0, 1)


def label_strip(width, title, subtitle, height, accent=(20, 20, 24)):
    strip = Image.new("RGB", (width, height), (255, 255, 255))
    d = ImageDraw.Draw(strip)
    d.text((0, 2 * S), title, font=font("LiberationSans-Bold.ttf", 17), fill=accent)
    d.text((0, 26 * S), subtitle, font=font("LiberationSans-Regular.ttf", 13),
           fill=(110, 110, 118))
    return np.asarray(strip).astype(np.float64) / 255.0


def main():
    root = Path(__file__).resolve().parent.parent
    out = root / "output"
    spec = M.parse_source_svg(None)
    icon_lin, alpha = M.composite_icon(spec, 800, 4, glow=True)
    icon_rgb = M.srgb_oetf(icon_lin)   # composite_icon returns linear light
    icon_mask, _ = M.build_arrow_mask(icon_rgb, alpha, "both")

    sdr_panel, mask = build_card(icon_rgb, icon_mask, "Testing something.")
    h, w, _ = sdr_panel.shape

    panels = [
        (sdr_panel, "1 · SDR control",
         "What every viewer sees. Arrow and card white are both 203 nits."),
        (simulate_hdr(sdr_panel, mask, 800),
         "2 · HDR 800 nits — SIMULATED RATIO",
         f"Arrow reaches {800 / SDR_WHITE_NITS:.1f}x the card white. Page dimmed to fit the ratio."),
        (simulate_hdr(sdr_panel, mask, 1200),
         "3 · HDR 1200 nits — SIMULATED RATIO",
         f"Arrow reaches {1200 / SDR_WHITE_NITS:.1f}x the card white. Same trick, pushed harder."),
    ]

    lab_h = 52 * S
    gap = 30 * S
    margin = 34 * S
    foot_h = 74 * S
    total_w = margin * 2 + w * len(panels) + gap * (len(panels) - 1)
    total_h = margin + lab_h + h + foot_h + margin

    sheet = np.ones((total_h, total_w, 3), dtype=np.float64)
    for i, (p, title, sub) in enumerate(panels):
        x = margin + i * (w + gap)
        sheet[margin:margin + lab_h, x:x + w] = label_strip(w, title, sub, lab_h)
        sheet[margin + lab_h:margin + lab_h + h, x:x + w] = p

    # Say plainly what the simulation does and does not represent.
    foot = Image.new("RGB", (total_w - margin * 2, foot_h), (255, 255, 255))
    fd = ImageDraw.Draw(foot)
    fd.line((0, 6 * S, total_w - margin * 2, 6 * S), fill=(226, 226, 230), width=1 * S)
    fd.text((0, 20 * S),
            "Panels 2 and 3 are SIMULATIONS of the ratio, not of the appearance.",
            font=font("LiberationSans-Bold.ttf", 14), fill=(20, 20, 24))
    fd.text((0, 42 * S),
            "On a real HDR display the page still looks normally bright and only the arrow gets brighter. "
            "An SDR image cannot go above white, so the same 3.9x relationship is shown by dimming everything else instead. "
            "The bloom is real: an 800-nit highlight scatters in your eye and in any camera pointed at the screen.",
            font=font("LiberationSans-Regular.ttf", 12), fill=(110, 110, 118))
    sheet[margin + lab_h + h:margin + lab_h + h + foot_h, margin:total_w - margin] = (
        np.asarray(foot).astype(np.float64) / 255.0)

    img = Image.fromarray((np.clip(sheet, 0, 1) * 255).astype(np.uint8))
    img = img.resize((total_w // S, total_h // S), Image.LANCZOS)
    dest = out / "preview-hdr-simulation.png"
    img.save(dest, optimize=True)
    print(f"wrote {dest}  ({dest.stat().st_size:,} bytes, {img.width}x{img.height})")

    # Individual panels, for embedding in the interactive test page.
    panel_dir = out / "preview-panels"
    panel_dir.mkdir(exist_ok=True)
    for slug, (p_arr, _, _) in zip(("sdr", "800nits", "1200nits"), panels):
        im = Image.fromarray((np.clip(p_arr, 0, 1) * 255).astype(np.uint8))
        im = im.resize((im.width // (S * 2) * 2, im.height // (S * 2) * 2), Image.LANCZOS)
        dst = panel_dir / f"sim-{slug}.jpg"
        im.save(dst, quality=88, optimize=True, progressive=True)
        print(f"  wrote {dst.name}  ({dst.stat().st_size:,} B, {im.width}x{im.height})")

    # A tight arrow-only crop makes the ratio easiest to read.
    crops = []
    for p, _, _ in panels:
        c = Image.fromarray((np.clip(p, 0, 1) * 255).astype(np.uint8)).crop(
            (26 * S, 130 * S + 260 * S, 26 * S + 720 * S, 130 * S + 260 * S + 420 * S))
        crops.append(np.asarray(c))
    strip = Image.fromarray(np.hstack(crops))
    strip = strip.resize((strip.width // (S * 2), strip.height // (S * 2)), Image.LANCZOS)
    dest2 = out / "preview-hdr-ratio-strip.png"
    strip.save(dest2, optimize=True)
    print(f"wrote {dest2}  ({dest2.stat().st_size:,} bytes, {strip.width}x{strip.height})")

    for t in (600, 800, 1200):
        print(f"  {t:>4} nits -> page white simulated at sRGB "
              f"{round(float(linear_to_srgb(np.array(SDR_WHITE_NITS / t))) * 255)}/255")


if __name__ == "__main__":
    main()
