#!/usr/bin/env python3
"""
Generate the LinkedIn HDR test set for the Cotera icon.

    python3 make-linkedin-hdr-assets.py [--out output]

Produces, for three visual variants, an SDR control plus HDR renditions at 600 /
800 / 1200 nits, in two different HDR encodings:

  *-<n>nits.jpg           8-bit PQ / BT.2020 JPEG with an embedded
                          Rec. ITU-R BT.2100 PQ ICC profile   (the ICC bet)
  *-<n>nits-gainmap.jpg   gain-map HDR JPEG, SDR base + gain map (the proven path)

Both are worth uploading, because they fail in opposite directions and testing
them side by side is the only way to learn what LinkedIn's pipeline does.

Everything is composited in linear light in absolute nits; the purple panel is
held at SDR white (203 nits, per BT.2408) so only the arrow and the light
spilling off it exceed it.
"""

import argparse
import json
import os
import sys

import numpy as np

SKILL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     '.claude', 'skills', 'hdr-logo-glow', 'scripts')
sys.path.insert(0, SKILL)

import compose            # noqa: E402
import encode             # noqa: E402
import hdrkit as k        # noqa: E402
import icc_pq             # noqa: E402
import ultrahdr           # noqa: E402
import validate           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ARROW = os.path.join(HERE, 'hdr-logo', 'assets', 'cotera-arrow.svg')

CANVAS = 800
NIT_TARGETS = [600, 800, 1200]

# Cotera brand inputs, taken from cotera.co/logo.svg
BRAND = dict(
    gradient_stops=[(0.00, '#322f82'), (0.19, '#403fa4'), (0.42, '#4f50c5'),
                    (0.64, '#5a5cde'), (0.83, '#6063ec'), (1.00, '#6366f2')],
    gradient_axis=((0.872, 0.854), (0.126, 0.144)),   # bottom-right -> top-left
    glow_hex='#6366f2',
    bg_hex='#322f82',
    mark_hex='#ffffff',
)

# Standard arrow is 0.55 of the short axis; 0.48 is 12.7% smaller, inside the
# 10-15% range asked for, and reads with noticeably more breathing room.
VARIANTS = {
    'standard': dict(
        mark_frac=0.55,
        glow_sigmas=(0.008, 0.022, 0.055, 0.120), glow_weights=(0.50, 0.32, 0.18, 0.12)),
    'smaller': dict(
        mark_frac=0.48,
        glow_sigmas=(0.008, 0.022, 0.055, 0.120), glow_weights=(0.50, 0.32, 0.18, 0.12)),
    'smaller-tightglow': dict(
        mark_frac=0.48,
        # Narrower kernels with the weight pushed onto the tightest one, so the
        # effect reads as "the arrow is brighter" rather than "the arrow is blurry".
        glow_sigmas=(0.004, 0.011, 0.026, 0.052), glow_weights=(0.66, 0.26, 0.10, 0.04)),
}


def glow_for(peak):
    """Hold the halo at a fixed fraction of the mark. Letting it track the mark
    keeps the look consistent across nit targets; pinning it would make the
    1200-nit version read as a bare white shape with no light around it."""
    return peak * 0.37


def cfg_for(variant, peak, layout='bleed'):
    c = dict(BRAND, width=CANVAS, height=CANVAS, supersample=3, layout=layout,
             peak_nits=float(peak), glow_nits=glow_for(peak),
             panel_white_nits=k.SDR_WHITE_NITS,      # the purple stays SDR
             sdr_peak_nits=k.SDR_WHITE_NITS, sdr_glow_nits=glow_for(peak) * 0.28)
    c.update(VARIANTS[variant])
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, 'output'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    icc = icc_pq.build_profile()
    icc_path = os.path.join(a.out, 'rec2100-pq.icc')
    with open(icc_path, 'wb') as f:
        f.write(icc)
    print(f'· built Rec. ITU-R BT.2100 PQ ICC profile ({len(icc):,} bytes) -> {icc_path}')

    manifest = []

    def emit(name, layers, peak, sdr_only=False):
        hdr = compose.render(layers, peak_nits=peak, glow_nits=glow_for(peak))
        sdr = compose.render_sdr(layers)
        rows = []
        if sdr_only:
            p = os.path.join(a.out, f'{name}.jpg')
            encode.write_sdr(None, p, sdr)
            rows.append((p, 'SDR control', None))
        else:
            p = os.path.join(a.out, f'{name}-{peak}nits.jpg')
            encode.write_pq_jpeg(p, hdr, icc)
            rows.append((p, f'PQ + ICC @ {peak} nits', peak))

            g, meta = ultrahdr.compute_gainmap(hdr, sdr)
            sdr8 = encode.write_sdr(None, None, sdr)
            p2 = os.path.join(a.out, f'{name}-{peak}nits-gainmap.jpg')
            ultrahdr.build(p2, sdr8, g, meta, base_quality=96, gain_quality=95)
            rows.append((p2, f'gain map @ {peak} nits', peak))

        for path, kind, nits in rows:
            st = compose.scene_stats(sdr if sdr_only else hdr)
            manifest.append(dict(file=os.path.basename(path), kind=kind,
                                 bytes=os.path.getsize(path),
                                 peak_nits=nits,
                                 sdr_white_multiple=round(st['sdr_white_multiple'], 2)))
            print(f'  · {os.path.basename(path):<58} {kind}')

    for variant in VARIANTS:
        print(f'\n[{variant}]')
        layers = compose.build_layers(ARROW, cfg_for(variant, 800))
        emit(f'cotera-linkedin-sdr-icon-{variant}', layers, k.SDR_WHITE_NITS, sdr_only=True)
        for peak in NIT_TARGETS:
            emit(f'cotera-linkedin-hdr-icon-{variant}', layers, peak)

    # arrow alone, no purple panel
    print('\n[arrow only]')
    la = compose.build_layers(ARROW, cfg_for('smaller-tightglow', 800, layout='mark'))
    emit('cotera-linkedin-sdr-arrow', la, k.SDR_WHITE_NITS, sdr_only=True)
    emit('cotera-linkedin-hdr-arrow', la, 800)

    # CICP-tagged renditions of the recommended variant -- the encodings that
    # browsers actually honour, for comparison against the JPEG experiments.
    print('\n[CICP reference encodings]')
    lp = compose.build_layers(ARROW, cfg_for('smaller-tightglow', 800))
    hdr = compose.render(lp, peak_nits=800, glow_nits=glow_for(800))
    for fn, w in [('cotera-linkedin-hdr-icon-smaller-tightglow-800nits.avif', encode.write_avif_pq),
                  ('cotera-linkedin-hdr-icon-smaller-tightglow-800nits.png', encode.write_png_pq)]:
        p = os.path.join(a.out, fn)
        w(p, hdr)
        manifest.append(dict(file=fn, kind='CICP 9/16 (BT.2020 + PQ)',
                             bytes=os.path.getsize(p), peak_nits=800,
                             sdr_white_multiple=round(800 / k.SDR_WHITE_NITS, 2)))
        print(f'  · {fn:<58} CICP-tagged')

    with open(os.path.join(a.out, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f'\n{len(manifest)} files -> {a.out}')


if __name__ == '__main__':
    main()
