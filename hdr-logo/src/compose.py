"""
compose -- build the HDR logo scene in linear nits, then encode it.

The scene is deliberately simple and physically stated:

    background   a dark brand-indigo wash, a few nits
    bloom        a multi-scale gaussian halo around the mark, brand indigo,
                 peaking well above SDR white
    mark         the Cotera arrow, white, at the configured peak luminance

Everything is composited in linear light at a supersampled resolution and only
then resampled down, which is what keeps the edges clean: averaging *gamma
encoded* pixels around a 4x brightness step produces the classic dark fringe.
"""

import os
import subprocess
import numpy as np
from scipy.ndimage import gaussian_filter, zoom

import hdrkit as k


# --------------------------------------------------------------------------
# Rasterising the mark
# --------------------------------------------------------------------------

def render_svg_alpha(svg_path, px, pad_frac=0.0):
    """Rasterise an SVG to an alpha mask of shape (px, px), float64 in [0,1]."""
    from PIL import Image
    import io
    out = subprocess.run(
        ['rsvg-convert', '-w', str(px), '-h', str(px), '-b', 'none', svg_path],
        check=True, capture_output=True).stdout
    im = Image.open(io.BytesIO(out)).convert('RGBA')
    return np.asarray(im, np.float64)[..., 3] / 255.0


def render_svg_rgba(svg_path, px):
    """Rasterise an SVG to (H,W,4) float in [0,1], straight (un-premultiplied)
    sRGB plus alpha. Needed for the brand tile, where the artwork carries its
    own gradient rather than being a flat silhouette."""
    from PIL import Image
    import io
    out = subprocess.run(
        ['rsvg-convert', '-w', str(px), '-h', str(px), '-b', 'none', svg_path],
        check=True, capture_output=True).stdout
    arr = np.asarray(Image.open(io.BytesIO(out)).convert('RGBA'), np.float64) / 255.0
    rgb, a = arr[..., :3], arr[..., 3:4]
    # rsvg gives premultiplied-looking output over transparency; recover straight
    # colour so scaling luminance later does not darken the edges.
    rgb = rgb / np.clip(a, 1e-6, None)
    return np.concatenate([np.clip(rgb, 0, 1), a], axis=2)


def fit_rgba(rgba, canvas, mark_frac, y_shift=0.0):
    """Same placement as fit_mask, but carrying colour through."""
    cw, ch = canvas
    a = rgba[..., 3]
    ys, xs = np.nonzero(a > 1e-3)
    sub = rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = sub.shape[:2]
    scale = (mark_frac * min(cw, ch)) / max(h, w)
    sub = np.stack([np.clip(zoom(sub[..., c], scale, order=3, mode='constant', cval=0.0), 0, 1)
                    for c in range(4)], axis=2)
    h, w = sub.shape[:2]
    out = np.zeros((ch, cw, 4), np.float64)
    top = max(0, min(ch - h, int(round((ch - h) / 2 + y_shift * ch))))
    left = max(0, min(cw - w, int(round((cw - w) / 2))))
    out[top:top + h, left:left + w] = sub
    return out


def fit_mask(mask, canvas, mark_frac=0.52, y_shift=0.0):
    """Trim a mask to its ink bounds and re-place it on a canvas of size
    (width, height) so the mark occupies `mark_frac` of the SHORT axis."""
    cw, ch = canvas
    ys, xs = np.nonzero(mask > 1e-3)
    if len(xs) == 0:
        raise ValueError('mask is empty')
    sub = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = sub.shape
    target = mark_frac * min(cw, ch)
    sub = np.clip(zoom(sub, target / max(h, w), order=3, mode='constant', cval=0.0), 0.0, 1.0)
    h, w = sub.shape

    out = np.zeros((ch, cw), np.float64)
    top = int(round((ch - h) / 2 + y_shift * ch))
    left = int(round((cw - w) / 2))
    top = max(0, min(ch - h, top))
    left = max(0, min(cw - w, left))
    out[top:top + h, left:left + w] = sub
    return out


# --------------------------------------------------------------------------
# Bloom
# --------------------------------------------------------------------------

def multiscale_bloom(mask, sigmas_frac, weights, ref_px):
    """Sum of gaussians at several scales -- a wide, soft falloff that survives
    tone mapping instead of collapsing into a hard ring.

    Computed at half resolution (bloom is low-frequency by definition) and
    upsampled, which is ~4x faster with no visible difference.
    """
    small = zoom(mask, 0.5, order=1, mode='constant', cval=0.0)
    acc = np.zeros_like(small)
    for sf, w in zip(sigmas_frac, weights):
        sigma = max(sf * ref_px * 0.5, 0.6)
        acc += w * gaussian_filter(small, sigma, mode='constant', cval=0.0)
    acc = zoom(acc, (mask.shape[0] / acc.shape[0], mask.shape[1] / acc.shape[1]),
               order=1, mode='constant', cval=0.0)
    acc = np.clip(acc, 0.0, None)
    peak = acc.max()
    return acc / peak if peak > 0 else acc


# --------------------------------------------------------------------------
# Scene
# --------------------------------------------------------------------------

# The logo's own gradient: stops and axis lifted straight out of cotera-logo.svg,
# which runs bottom-right (dark) to top-left (bright) across a 200x200 box.
BRAND_GRADIENT = [
    (0.00, '#322f82'), (0.19, '#403fa4'), (0.42, '#4f50c5'),
    (0.64, '#5a5cde'), (0.83, '#6063ec'), (1.00, '#6366f2'),
]
BRAND_GRADIENT_AXIS = ((174.41, 170.89), (25.26, 28.80))   # in the 200x200 viewBox


def brand_gradient(w, h):
    """The Cotera gradient across an arbitrary canvas, interpolated in LINEAR
    light. Interpolating the stops in sRGB instead darkens the midpoints --
    the classic muddy-gradient artefact."""
    (x0, y0), (x1, y1) = BRAND_GRADIENT_AXIS
    sx, sy = w / 200.0, h / 200.0
    ax, ay = (x1 - x0) * sx, (y1 - y0) * sy
    denom = ax * ax + ay * ay
    xx, yy = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
    t = np.clip(((xx - x0 * sx) * ax + (yy - y0 * sy) * ay) / denom, 0.0, 1.0)

    offs = np.array([o for o, _ in BRAND_GRADIENT])
    cols = np.array([k.hex_to_linear_rgb(c) for _, c in BRAND_GRADIENT])
    out = np.empty((h, w, 3), np.float64)
    for ch in range(3):
        out[..., ch] = np.interp(t, offs, cols[:, ch])
    return out


DEFAULTS = dict(
    canvas=1200,          # square shorthand; width/height override it
    supersample=3,
    mark_frac=0.46,
    y_shift=0.0,

    # --- luminance, in nits. This is the whole trick, stated plainly. ---
    peak_nits=900.0,          # the white arrow: ~4.4x SDR white
    bloom_peak_nits=330.0,    # light spilling off the arrow: ~1.6x SDR white
    bg_top_nits=5.0,          # background gradient, top
    bg_bottom_nits=1.1,       # background gradient, bottom

    # --- the SDR rendition of the same artwork ---
    sdr_peak_nits=203.0,      # mark sits exactly at SDR white
    sdr_bloom_nits=90.0,     # halo stays indigo instead of clipping to white

    mark_hex='#ffffff',
    bloom_hex='#6366f2',      # Cotera indigo, light stop of the brand gradient
    bg_hex='#322f82',         # Cotera indigo, dark stop
    style='brand-tile',      # indigo-mark | white-mark | brand-tile
    tile_nits=203.0,          # what #ffffff *inside the tile artwork* means, in
                              # nits. At SDR white the tile is exactly the brand
                              # colour; raise it to lift the whole tile.
    tile_frac=0.80,           # how much of the canvas the tile fills; >1.0 bleeds
    clip_bloom_to_tile=True,  # keep the glow inside the logo, no edge ring
    tile_svg='assets/cotera-tile.svg',
    mark_hex_indigo='#6366f2',  # Cotera indigo, bright stop
    core_hex='#c9c8ff',       # white-hot core inside the indigo mark
    core_frac=0.45,           # how much of the mark reads as hot core
    bloom_sigmas=(0.008, 0.022, 0.055, 0.120),
    bloom_weights=(0.50, 0.32, 0.18, 0.12),
)


def build_layers(svg_path, cfg=None):
    """Rasterise once and return the geometry as reusable layers.

    Separating geometry from luminance matters: the HDR and SDR renditions must
    be the *same picture* at different brightnesses, otherwise the gain map
    between them encodes shape as well as light, which is exactly the artefact
    gain maps exist to avoid.
    """
    c = dict(DEFAULTS)
    if cfg:
        c.update(cfg)
    cw, ch = c.get('width', c['canvas']), c.get('height', c['canvas'])
    s = c['supersample']
    sw, sh = cw * s, ch * s
    tile = None

    if c['style'] == 'brand-tile':
        # Resolve the tile artwork relative to this package, so the default
        # works regardless of the caller's working directory.
        if not os.path.isabs(c['tile_svg']):
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cand = os.path.join(root, c['tile_svg'])
            if os.path.exists(cand):
                c['tile_svg'] = cand

        # The tile and the arrow come from the same 200x200 viewBox, so
        # rasterising both at one size and pasting at one offset keeps them in
        # exact register -- no independent bbox fitting, no drift.
        r = int(round(c['tile_frac'] * min(sw, sh)))
        top = (sh - r) // 2 + int(round(c['y_shift'] * sh))
        left = (sw - r) // 2

        def place(src):
            """Paste an r x r raster centred on the canvas, cropping whatever
            falls outside. Lets tile_frac exceed 1.0 for a full-bleed tile."""
            shape = (sh, sw) + src.shape[2:]
            out = np.zeros(shape, np.float64)
            sy0, sx0 = max(0, -top), max(0, -left)
            dy0, dx0 = max(0, top), max(0, left)
            hgt = min(r - sy0, sh - dy0)
            wid = min(r - sx0, sw - dx0)
            if hgt > 0 and wid > 0:
                out[dy0:dy0 + hgt, dx0:dx0 + wid] = src[sy0:sy0 + hgt, sx0:sx0 + wid]
            return out

        tile = place(render_svg_rgba(c['tile_svg'], r))
        mask = place(render_svg_alpha(svg_path, r)[..., None])[..., 0]
    else:
        mask = fit_mask(render_svg_alpha(svg_path, max(sw, sh)),
                        (sw, sh), c['mark_frac'], c['y_shift'])
        if c['style'] == 'bleed':
            tile = np.concatenate([brand_gradient(sw, sh),
                                   np.ones((sh, sw, 1), np.float64)], axis=2)

    bloom = multiscale_bloom(mask, c['bloom_sigmas'], c['bloom_weights'], min(sw, sh))
    ramp = np.repeat((np.linspace(1.0, 0.0, sh) ** 1.6)[:, None], sw, axis=1)

    if s > 1:
        mask = mask.reshape(ch, s, cw, s).mean(axis=(1, 3))
        bloom = bloom.reshape(ch, s, cw, s).mean(axis=(1, 3))
        ramp = ramp.reshape(ch, s, cw, s).mean(axis=(1, 3))
        if tile is not None:
            tile = tile.reshape(ch, s, cw, s, 4).mean(axis=(1, 3))

    layers = dict(mask=np.clip(mask, 0, 1), bloom=np.clip(bloom, 0, 1),
                  ramp=ramp, cfg=c)
    if tile is not None:
        layers['tile'] = tile

    if c['style'] == 'indigo-mark':
        # A hotter, lighter core inside the indigo mark, the way a real emitter
        # reads: saturated at the edges, near-white where it is brightest.
        core = gaussian_filter(layers['mask'], max(min(cw, ch) * 0.012, 0.6),
                               mode='constant', cval=0.0)
        core = np.clip((core - (1.0 - c['core_frac'])) / max(c['core_frac'], 1e-6), 0, 1)
        layers['core'] = core * layers['mask']

    return layers


def render(layers, peak_nits=None, bloom_nits=None, bg_top=None, bg_bottom=None,
           tile_nits=None):
    """Composite the layers at a given set of luminances -> linear BT.709 nits."""
    c = layers['cfg']
    peak = c['peak_nits'] if peak_nits is None else peak_nits
    bl = c['bloom_peak_nits'] if bloom_nits is None else bloom_nits
    top = c['bg_top_nits'] if bg_top is None else bg_top
    bot = c['bg_bottom_nits'] if bg_bottom is None else bg_bottom
    tl = c['tile_nits'] if tile_nits is None else tile_nits
    style = c['style']

    mask, bloom, ramp = layers['mask'], layers['bloom'], layers['ramp']
    bloom_tint = k.tint_at_nits(c['bloom_hex'], 1.0)

    # --- ground ---
    scene = (bot + (top - bot) * ramp)[..., None] * k.tint_at_nits(c['bg_hex'], 1.0)

    if style in ('brand-tile', 'bleed'):
        # The tile at its ordinary brand level, so the logo still reads as the
        # logo -- then the arrow's light laid ON TOP of it. Order matters: put
        # the halo behind the tile and the tile simply hides it, which is the
        # opposite of light spilling out of the mark.
        tile = layers['tile']
        trgb, ta = tile[..., :3], tile[..., 3]
        # Render the tile at its TRUE brand values: treat #ffffff in the artwork
        # as `tl` nits and let every other colour fall where the designer put it.
        # (Normalising by the tile's own brightest pixel instead would stretch
        # #6366f2 up toward white and turn the deep indigo into lavender.)
        # the procedural gradient is already linear; the rasterised tile is sRGB
        lin = trgb if style == 'bleed' else k.srgb_to_linear(trgb)
        tile_img = lin * tl
        scene = scene * (1.0 - ta[..., None]) + tile_img * ta[..., None]

        # Light spilling from the arrow. Clipped to the tile: let it run past
        # the edge and it lights the dark background right at the boundary,
        # which reads as a bright outline drawn around the whole logo.
        spill = (bloom * ta if (c['clip_bloom_to_tile'] and style == 'brand-tile')
                 else bloom)
        scene = scene + (spill * bl)[..., None] * bloom_tint

        # the arrow itself, driven well past everything around it
        scene = (scene * (1.0 - mask[..., None])
                 + (mask * peak)[..., None] * k.tint_at_nits(c['mark_hex'], 1.0))
        return np.clip(scene, 0.0, k.PQ_MAX_NITS)

    # --- halo, for the mark-only styles ---
    scene = scene + (bloom * bl)[..., None] * bloom_tint

    if style == 'indigo-mark':
        # Brand indigo at the full peak, with a hotter, lighter core.
        body = (mask * peak)[..., None] * k.tint_at_nits(c['mark_hex_indigo'], 1.0)
        core = layers.get('core')
        if core is not None:
            hot = (core * peak * 1.06)[..., None] * k.tint_at_nits(c['core_hex'], 1.0)
            body = body * (1.0 - core[..., None]) + hot
        scene = scene * (1.0 - mask[..., None]) + body

    else:  # white-mark
        body = (mask * peak)[..., None] * k.tint_at_nits(c['mark_hex'], 1.0)
        scene = scene * (1.0 - mask[..., None]) + body

    return np.clip(scene, 0.0, k.PQ_MAX_NITS)


def render_hdr(layers):
    return render(layers)


def render_sdr(layers):
    """The SDR rendition -- authored, not tone-mapped. The mark lands exactly on
    SDR white and the halo stays below it, so this file is a correct standalone
    image on any display that never heard of HDR."""
    c = layers['cfg']
    return render(layers, peak_nits=c['sdr_peak_nits'], bloom_nits=c['sdr_bloom_nits'],
                  tile_nits=min(c['tile_nits'], c['sdr_peak_nits']))


def build_scene(svg_path, cfg=None):
    """Backwards-compatible helper: returns (hdr scene in nits, mark mask)."""
    layers = build_layers(svg_path, cfg)
    return render_hdr(layers), layers['mask']


def scene_stats(scene):
    """Human-readable summary of how hard this frame pushes the panel."""
    y = k.luminance(scene)
    total = y.mean()
    return dict(
        peak_nits=float(y.max()),
        mean_nits=float(total),
        sdr_white_multiple=float(y.max() / k.SDR_WHITE_NITS),
        frac_above_sdr_white=float((y > k.SDR_WHITE_NITS).mean()),
        frac_above_2x=float((y > 2 * k.SDR_WHITE_NITS).mean()),
        # crude proxy for OLED auto-brightness-limiter pressure: average
        # picture level relative to a full-screen SDR white frame
        apl_vs_sdr_white=float(total / k.SDR_WHITE_NITS),
    )
