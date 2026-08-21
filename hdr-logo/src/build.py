#!/usr/bin/env python3
"""
build -- generate the full set of Cotera HDR logo assets.

    python3 src/build.py                    # default: 1200x1200, 800 nit mark
    python3 src/build.py --peak 600         # gentler
    python3 src/build.py --size 1200x627    # landscape
    python3 src/build.py --preset subtle

Every output is written to out/ and then validated by src/validate.py.
"""

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import compose
import encode
import hdrkit as k
import ultrahdr
import validate


# LinkedIn surface -> pixel dimensions. Portrait wins the most feed height on
# mobile, which is where HDR displays actually are.
SIZES = {
    'square':    (1200, 1200),   # standard feed image
    'portrait':  (1080, 1350),   # tallest allowed in-feed; most screen real estate
    'landscape': (1200, 627),    # link-preview shape
    'avatar':    (400, 400),     # company page / profile avatar
}


PRESETS = {
    # peak nits, bloom nits -- expressed as multiples of SDR white in the docs
    'subtle':      dict(peak_nits=450.0,  bloom_peak_nits=210.0),   # 2.2x SDR white
    'default':     dict(peak_nits=900.0,  bloom_peak_nits=330.0),   # 4.4x
    'strong':      dict(peak_nits=1400.0, bloom_peak_nits=480.0),   # 6.9x
    'obnoxious':   dict(peak_nits=2400.0, bloom_peak_nits=800.0),   # 11.8x -- named
}


def build_all(svg, outdir, cfg, name='cotera-arrow', quiet=False):
    os.makedirs(outdir, exist_ok=True)
    t0 = time.time()

    def say(*a):
        if not quiet:
            print(*a, flush=True)

    say(f'· compositing {cfg.get("width", cfg["canvas"])}x{cfg.get("height", cfg["canvas"])} '
        f'at x{cfg["supersample"]} supersample …')
    layers = compose.build_layers(svg, cfg)
    hdr = compose.render_hdr(layers)
    sdr = compose.render_sdr(layers)

    stats = compose.scene_stats(hdr)
    say('· scene: peak {peak_nits:.0f} nits = {sdr_white_multiple:.2f}x SDR white, '
        '{frac_above_sdr_white:.1%} of frame above SDR white, APL {apl_vs_sdr_white:.2f}x'
        .format(**stats))

    p = lambda ext: os.path.join(outdir, f'{name}{ext}')
    written = {}

    # --- SDR rendition (also the base layer of the gain-map file) ---
    sdr8 = encode.write_sdr(p('-sdr.png'), p('-sdr.jpg'), sdr)
    written['sdr_png'] = p('-sdr.png')
    written['sdr_jpg'] = p('-sdr.jpg')
    say('· SDR fallback written')

    # --- gain-map HDR JPEG ---
    gain, meta = ultrahdr.compute_gainmap(hdr, sdr)
    info = ultrahdr.build(p('-ultrahdr.jpg'), sdr8, gain, meta)
    written['ultrahdr_jpg'] = p('-ultrahdr.jpg')
    say(f'· Ultra HDR JPEG written ({info["total"]:,} bytes: '
        f'{info["primary_bytes"]:,} base + {info["gainmap_bytes"]:,} gain map)')

    # --- PQ renditions ---
    encode.write_avif_pq(p('-hdr-pq.avif'), hdr)
    written['avif'] = p('-hdr-pq.avif')
    say('· AVIF (BT.2020 / PQ, 10-bit) written')

    encode.write_png_pq(p('-hdr-pq.png'), hdr)
    written['png'] = p('-hdr-pq.png')
    say('· PNG (BT.2020 / PQ, 16-bit, cICP) written')

    meta_out = dict(
        source_svg=svg, name=name, config={kk: (list(v) if isinstance(v, tuple) else v)
                                           for kk, v in cfg.items()},
        scene=stats, gain_map=meta, ultrahdr_container=info,
        sdr_white_nits=k.SDR_WHITE_NITS, files=written,
        built_seconds=round(time.time() - t0, 1),
    )
    with open(os.path.join(outdir, f'{name}-build.json'), 'w') as f:
        json.dump(meta_out, f, indent=2)

    say(f'· done in {meta_out["built_seconds"]}s')
    return written, hdr, sdr, gain, meta


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--svg', default=os.path.join(here, 'assets/cotera-arrow.svg'))
    ap.add_argument('--out', default=os.path.join(here, 'out'))
    ap.add_argument('--name', default=None, help='output basename (defaults to cotera-arrow-<size>)')
    ap.add_argument('--size', default='square',
                    help='a named size (%s), NNN, or WxH' % ', '.join(SIZES))
    ap.add_argument('--supersample', type=int, default=3)
    ap.add_argument('--preset', choices=sorted(PRESETS), default='default')
    ap.add_argument('--style', choices=['bleed', 'brand-tile', 'indigo-mark', 'white-mark'],
                    default='bleed',
                    help='bleed: brand gradient edge to edge, no frame (default). '
                         'brand-tile: the rounded logo tile on a dark ground.')
    ap.add_argument('--tile-nits', type=float,
                    help='what #ffffff inside the tile artwork means, in nits')
    ap.add_argument('--peak', type=float, help='mark luminance in nits (overrides preset)')
    ap.add_argument('--bloom', type=float, help='halo luminance in nits (overrides preset)')
    ap.add_argument('--mark-frac', type=float, default=None,
                    help='arrow size as a fraction of the short axis')
    ap.add_argument('--no-validate', action='store_true')
    a = ap.parse_args()

    cfg = dict(compose.DEFAULTS)
    cfg.update(PRESETS[a.preset])
    if a.size in SIZES:
        cfg['width'], cfg['height'] = SIZES[a.size]
    elif 'x' in a.size:
        w, h = a.size.lower().split('x')
        cfg['width'], cfg['height'] = int(w), int(h)
    else:
        cfg['width'] = cfg['height'] = int(a.size)
    cfg['canvas'] = cfg['width']
    cfg['supersample'] = a.supersample
    # the bleed layout has no tile edge to sit inside, so the arrow can be larger
    cfg['mark_frac'] = a.mark_frac if a.mark_frac else (0.55 if a.style == 'bleed' else 0.46)
    if a.style == 'brand-tile':
        cfg['tile_frac'] = 0.86
    cfg['style'] = a.style
    if a.tile_nits:
        cfg['tile_nits'] = a.tile_nits
    if a.peak:
        cfg['peak_nits'] = a.peak
    if a.bloom:
        cfg['bloom_peak_nits'] = a.bloom

    suffix = {'bleed': 'bleed', 'brand-tile': 'tile'}.get(a.style, a.style)
    name = a.name or f'cotera-logo-{a.size}-{suffix}'
    print(f'Cotera HDR logo build — {cfg["width"]}x{cfg["height"]}, preset "{a.preset}", '
          f'mark at {cfg["peak_nits"]:.0f} nits '
          f'({cfg["peak_nits"] / k.SDR_WHITE_NITS:.2f}x SDR white)')
    written, *_ = build_all(a.svg, a.out, cfg, name)

    if not a.no_validate:
        print('\n— validating produced files —')
        ok = True
        ok &= validate.report(validate.check_ultrahdr(written['ultrahdr_jpg']))
        ok &= validate.report(validate.check_png_cicp(written['png']))
        ok &= validate.report(validate.check_avif(written['avif']))
        if not ok:
            sys.exit(1)


if __name__ == '__main__':
    main()
