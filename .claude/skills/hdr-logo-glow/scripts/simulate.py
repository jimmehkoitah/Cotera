#!/usr/bin/env python3
"""
simulate -- show, on an ordinary SDR screen, what an HDR file actually does.

    python3 simulate.py --mark logo.svg --out headroom.png

An SDR screen cannot display "brighter than white", so a screenshot of an HDR
image is always a lie. The honest way to show the effect is to hold the panel
peak fixed and let the SDR reference white fall away as display headroom grows:
the mark stays white while everything else -- including a plain #ffffff pixel,
which is what the rest of a feed is made of -- goes grey.

That inversion is the actual perceptual experience. The logo does not look
whiter; the rest of the screen looks dim.
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compose        # noqa: E402
import hdrkit as k    # noqa: E402
import ultrahdr       # noqa: E402

LEVELS = [
    (0.0, 'SDR display', 'no headroom'),
    (1.0, '2x headroom', 'phone at low brightness'),
    (2.15, '4.4x headroom', 'iPhone / MacBook XDR'),
    (2.80, 'beyond authored peak', 'clamped, never overshoots'),
]


def _font(sz, bold=False):
    path = '/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf' % ('-Bold' if bold else '')
    try:
        return ImageFont.truetype(path, sz)
    except OSError:
        return ImageFont.load_default()


def build_sheet(mark, out_path, panel=420, cfg_over=None):
    cfg = dict(width=panel, height=panel, supersample=3)
    if cfg_over:
        cfg.update(cfg_over)
    layers = compose.build_layers(mark, cfg)
    hdr, sdr = compose.render_hdr(layers), compose.render_sdr(layers)
    gain, meta = ultrahdr.compute_gainmap(hdr, sdr)

    panels = []
    for stops, title, sub in LEVELS:
        rec = ultrahdr.reconstruct(sdr, gain, meta, stops)
        rec[12:52, 12:132] = k.SDR_WHITE_NITS            # reference white swatch
        peak = max(k.luminance(rec).max(), k.SDR_WHITE_NITS)
        srgb = k.linear_to_srgb(np.clip(rec / peak, 0, 1))
        panels.append((np.round(srgb * 255).astype(np.uint8), title, sub, peak))

    pad, gap, foot = 16, 12, 112
    h, w = panels[0][0].shape[:2]
    sheet = Image.new('RGB', (pad * 2 + w * len(panels) + gap * (len(panels) - 1),
                              pad + h + foot), (11, 11, 15))
    d = ImageDraw.Draw(sheet)
    for i, (arr, title, sub, peak) in enumerate(panels):
        x = pad + i * (w + gap)
        sheet.paste(Image.fromarray(arr), (x, pad))
        d.text((x, pad + h + 16), title, fill=(232, 232, 242), font=_font(17, True))
        d.text((x, pad + h + 40), sub, fill=(150, 150, 172), font=_font(15))
        d.text((x, pad + h + 62), f'mark {peak:.0f} nits', fill=(120, 120, 145), font=_font(14))
    d.text((pad, pad + h + 90),
           'The white bar in each panel is an ordinary #ffffff pixel — SDR white, '
           '203 nits — i.e. the brightest thing the rest of the feed can be.',
           fill=(118, 118, 140), font=_font(14))
    sheet.save(out_path)
    return out_path, sheet.size


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--mark', required=True)
    ap.add_argument('--out', default='headroom-simulation.png')
    ap.add_argument('--layout', default='bleed')
    ap.add_argument('--gradient', default=None)
    a = ap.parse_args()
    over = dict(layout=a.layout)
    if a.gradient:
        cols = [c.strip() for c in a.gradient.split(',')]
        over['gradient_stops'] = [(i / max(len(cols) - 1, 1), c) for i, c in enumerate(cols)]
    p, size = build_sheet(a.mark, a.out, cfg_over=over)
    print(f'wrote {p} {size}')
