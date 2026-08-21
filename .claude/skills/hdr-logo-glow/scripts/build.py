#!/usr/bin/env python3
"""
build -- generate HDR assets for a logo mark.

    python3 build.py --mark logo.svg --out out/
    python3 build.py --mark logo.svg --out out/ --gradient "#322f82,#6366f2"
    python3 build.py --mark logo.svg --out out/ --preset subtle --size 1080x1350
    python3 build.py --mark icon.svg --backdrop tile.svg --layout inset --out out/

Emits, by default: a gain-map JPEG (start here -- it is the only format whose
worst case is a correct image), a CICP-tagged AVIF and PNG, and an SDR control.
Add --icc-jpeg for the PQ + ICC profile experiment; read the warning it prints.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import compose        # noqa: E402
import encode         # noqa: E402
import hdrkit as k    # noqa: E402
import ultrahdr       # noqa: E402
import validate       # noqa: E402

SIZES = {
    'square': (1200, 1200),
    'portrait': (1080, 1350),
    'landscape': (1200, 627),
    'avatar': (400, 400),
    'icon': (800, 800),
}

# Peak luminance of the mark, and the halo that goes with it. Expressed in nits
# so the multiple of SDR white (203) is explicit.
PRESETS = {
    'subtle':    dict(peak_nits=450.0,  glow_nits=210.0),   # 2.2x SDR white
    'default':   dict(peak_nits=900.0,  glow_nits=330.0),   # 4.4x
    'strong':    dict(peak_nits=1400.0, glow_nits=480.0),   # 6.9x
    'obnoxious': dict(peak_nits=2400.0, glow_nits=800.0),   # 11.8x -- named as a warning
}


def parse_size(s):
    if s in SIZES:
        return SIZES[s]
    if 'x' in s.lower():
        w, h = s.lower().split('x')
        return int(w), int(h)
    return int(s), int(s)


def parse_gradient(s):
    if not s:
        return None
    cols = [c.strip() for c in s.split(',') if c.strip()]
    if len(cols) == 1:
        cols = cols * 2
    return [(i / (len(cols) - 1), c) for i, c in enumerate(cols)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--mark', required=True, help='the logo mark (SVG, or PNG with alpha)')
    ap.add_argument('--out', default='out')
    ap.add_argument('--name', default=None, help='output basename (default: the mark filename)')
    ap.add_argument('--layout', choices=['bleed', 'inset', 'mark'], default='bleed')
    ap.add_argument('--backdrop', default=None, help='panel artwork, for --layout inset')
    ap.add_argument('--size', default='square', help=f'{", ".join(SIZES)}, NNN, or WxH')
    ap.add_argument('--preset', choices=sorted(PRESETS), default='default')
    ap.add_argument('--peak', type=float, help='mark luminance in nits (overrides preset)')
    ap.add_argument('--glow', type=float, help='halo luminance in nits (overrides preset)')
    ap.add_argument('--gradient', default=None,
                    help='comma-separated hex stops for the bleed panel')
    ap.add_argument('--glow-hex', default=None)
    ap.add_argument('--bg-hex', default=None)
    ap.add_argument('--mark-hex', default=None)
    ap.add_argument('--mark-frac', type=float, default=None)
    ap.add_argument('--tight-glow', action='store_true',
                    help='narrower halo -- reads as "brighter mark" not "blurry mark"')
    ap.add_argument('--supersample', type=int, default=3)
    ap.add_argument('--icc-jpeg', action='store_true',
                    help='also emit an 8-bit PQ JPEG with a BT.2100 PQ ICC profile')
    ap.add_argument('--no-validate', action='store_true')
    a = ap.parse_args()

    w, h = parse_size(a.size)
    cfg = dict(PRESETS[a.preset], width=w, height=h, layout=a.layout,
               supersample=a.supersample, backdrop=a.backdrop,
               gradient_stops=parse_gradient(a.gradient),
               glow_hex=a.glow_hex, bg_hex=a.bg_hex, mark_hex=a.mark_hex,
               mark_frac=a.mark_frac)
    if a.peak:
        cfg['peak_nits'] = a.peak
    if a.glow:
        cfg['glow_nits'] = a.glow
    if a.tight_glow:
        cfg['glow_sigmas'] = (0.004, 0.011, 0.026, 0.052)
        cfg['glow_weights'] = (0.66, 0.26, 0.10, 0.04)

    os.makedirs(a.out, exist_ok=True)
    name = a.name or os.path.splitext(os.path.basename(a.mark))[0]
    p = lambda ext: os.path.join(a.out, f'{name}{ext}')

    peak = cfg['peak_nits']
    print(f'{name}: {w}x{h}, mark at {peak:.0f} nits '
          f'({peak / k.SDR_WHITE_NITS:.2f}x SDR white), layout "{a.layout}"')

    layers = compose.build_layers(a.mark, cfg)
    hdr, sdr = compose.render_hdr(layers), compose.render_sdr(layers)
    stats = compose.scene_stats(hdr)
    print('  scene: {frac_above_sdr_white:.1%} of the frame above SDR white, '
          'APL {apl_vs_sdr_white:.2f}x'.format(**stats))
    if not 0.02 <= stats['frac_above_sdr_white'] <= 0.25:
        print('  note: outside the 5-15% band that reads as a glowing mark rather '
              'than a bright rectangle; consider a smaller mark or lower peak.')

    written = {}
    sdr8 = encode.write_sdr(p('-sdr.png'), p('-sdr.jpg'), sdr)
    written['sdr'] = p('-sdr.jpg')

    gain, meta = ultrahdr.compute_gainmap(hdr, sdr)
    ultrahdr.build(p('-ultrahdr.jpg'), sdr8, gain, meta)
    written['gainmap'] = p('-ultrahdr.jpg')

    encode.write_avif_pq(p('-hdr-pq.avif'), hdr)
    written['avif'] = p('-hdr-pq.avif')
    encode.write_png_pq(p('-hdr-pq.png'), hdr)
    written['png'] = p('-hdr-pq.png')

    if a.icc_jpeg:
        import icc_pq
        icc = icc_pq.build_profile()
        with open(os.path.join(a.out, 'rec2100-pq.icc'), 'wb') as f:
            f.write(icc)
        encode.write_pq_jpeg(p('-pq-icc.jpg'), hdr, icc)
        written['icc_jpeg'] = p('-pq-icc.jpg')
        print('  note: the PQ+ICC JPEG survives re-encoding better than a gain map, '
              'but has no safe fallback -- a viewer that colour-manages it without '
              'HDR awareness renders it near-black. Do not ship it as the only file.')

    with open(p('-build.json'), 'w') as f:
        json.dump(dict(name=name, size=[w, h], scene=stats, gain_map=meta,
                       config={kk: (list(v) if isinstance(v, tuple) else v)
                               for kk, v in cfg.items()},
                       files={kk: os.path.basename(v) for kk, v in written.items()}),
                  f, indent=2)

    for kk, v in written.items():
        print(f'  {kk:<9} {os.path.basename(v):<40} {os.path.getsize(v):>9,} bytes')

    if not a.no_validate:
        print('\n— verifying the produced bytes —')
        ok = validate.main([v for kk, v in written.items()])
        if not ok:
            sys.exit(1)


if __name__ == '__main__':
    main()
