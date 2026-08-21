#!/usr/bin/env python3
"""
simulate -- show, on an ordinary SDR screen, what the HDR file actually does.

An SDR screen cannot display "brighter than white", so a screenshot of an HDR
image is always a lie. The honest way to show the effect is to hold the panel
peak fixed and let the SDR reference white fall away as display headroom grows:
the mark stays white while everything else -- including a plain #ffffff pixel,
which is what the rest of the feed is made of -- goes grey.

That is precisely the perceptual experience: the logo does not look "whiter",
the entire rest of the screen looks dim next to it.
"""

import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compose
import hdrkit as k
import ultrahdr

LEVELS = [
    (0.0, 'SDR display', 'no headroom'),
    (1.0, '2x headroom', 'phone at low brightness'),
    (1.98, '4x headroom', 'iPhone / MacBook XDR'),
    (2.60, 'beyond authored peak', 'clamped, never overshoots'),
]


def build_sheet(svg, out_path, canvas=420, supersample=3, cfg_over=None):
    cfg = dict(compose.DEFAULTS, canvas=canvas, supersample=supersample)
    if cfg_over:
        cfg.update(cfg_over)
    layers = compose.build_layers(svg, cfg)
    hdr, sdr = compose.render_hdr(layers), compose.render_sdr(layers)
    gain, meta = ultrahdr.compute_gainmap(hdr, sdr)

    panels = []
    for stops, title, sub in LEVELS:
        rec = ultrahdr.reconstruct(sdr, gain, meta, stops)
        rec[12:52, 12:132] = k.SDR_WHITE_NITS          # reference white swatch
        peak = max(k.luminance(rec).max(), k.SDR_WHITE_NITS)
        srgb = k.linear_to_srgb(np.clip(rec / peak, 0, 1))
        panels.append((np.round(srgb * 255).astype(np.uint8), title, sub, peak))

    pad, gap, foot = 16, 12, 112
    w = panels[0][0].shape[1]
    h = panels[0][0].shape[0]
    W = pad * 2 + w * len(panels) + gap * (len(panels) - 1)
    sheet = Image.new('RGB', (W, pad + h + foot), (11, 11, 15))
    d = ImageDraw.Draw(sheet)

    def font(sz, bold=False):
        base = '/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf' % ('-Bold' if bold else '')
        try:
            return ImageFont.truetype(base, sz)
        except OSError:
            return ImageFont.load_default()

    for i, (arr, title, sub, peak) in enumerate(panels):
        x = pad + i * (w + gap)
        sheet.paste(Image.fromarray(arr), (x, pad))
        d.text((x, pad + h + 16), title, fill=(232, 232, 242), font=font(17, True))
        d.text((x, pad + h + 40), sub, fill=(150, 150, 172), font=font(15))
        d.text((x, pad + h + 62), f'mark {peak:.0f} nits', fill=(120, 120, 145), font=font(14))

    d.text((pad, pad + h + 90),
           'The white bar in each panel is an ordinary #ffffff pixel — SDR white, '
           '203 nits — i.e. the brightest thing the rest of the feed can be.',
           fill=(118, 118, 140), font=font(14))
    sheet.save(out_path)
    return out_path, sheet.size


if __name__ == '__main__':
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p, size = build_sheet(
        sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, 'assets/cotera-arrow.svg'),
        os.path.join(here, 'out/cotera-arrow-headroom-simulation.png'))
    print(f'wrote {p} {size}')
