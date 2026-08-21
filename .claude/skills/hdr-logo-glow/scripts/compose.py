"""
compose -- build an HDR logo scene in linear nits, for any brand.

Nothing here is brand-specific: colours, gradient, and backdrop artwork are all
inputs. The scene is stated physically, in cd/m^2:

    ground      a dark wash, a few nits (only visible in the 'inset'/'mark' layouts)
    backdrop    the brand panel -- a procedural gradient, or supplied artwork
    glow        a multi-scale gaussian halo around the mark, in a brand colour
    mark        the logo mark, at the configured peak luminance

Two rules govern everything and are worth internalising rather than copying:

1. Composite and downsample in LINEAR light. Averaging gamma-encoded pixels
   across a 4x brightness step produces a dark fringe around the mark -- the
   classic "why does my glowing logo have an outline" artefact.

2. Separate geometry from luminance. The HDR and SDR renditions must be the
   same picture at different brightnesses. If they differ in shape, the gain map
   between them encodes shape as well as light, which is the exact artefact gain
   maps exist to avoid.
"""

import os
import subprocess

import numpy as np
from scipy.ndimage import gaussian_filter, zoom

import hdrkit as k


# --------------------------------------------------------------------------
# Rasterising
# --------------------------------------------------------------------------

def _rasterise(path, px):
    """Rasterise an SVG (via rsvg-convert) or load a raster, to RGBA float [0,1]."""
    from PIL import Image
    import io
    if str(path).lower().endswith('.svg'):
        out = subprocess.run(
            ['rsvg-convert', '-w', str(px), '-h', str(px), '-b', 'none', str(path)],
            check=True, capture_output=True).stdout
        im = Image.open(io.BytesIO(out)).convert('RGBA')
    else:
        im = Image.open(path).convert('RGBA')
        im = im.resize((px, px), Image.LANCZOS)
    return np.asarray(im, np.float64) / 255.0


def load_alpha(path, px):
    """Alpha channel only -- the silhouette of the mark."""
    return _rasterise(path, px)[..., 3]


def load_rgba(path, px):
    """Straight (un-premultiplied) sRGB + alpha.

    Rasterisers hand back colour that looks premultiplied over transparency;
    dividing it out keeps edges from darkening when the luminance is scaled.
    """
    arr = _rasterise(path, px)
    rgb, a = arr[..., :3], arr[..., 3:4]
    rgb = rgb / np.clip(a, 1e-6, None)
    return np.concatenate([np.clip(rgb, 0, 1), a], axis=2)


def fit(src, canvas, frac, y_shift=0.0):
    """Trim to ink bounds and centre on a (width, height) canvas so the artwork
    occupies `frac` of the short axis. Crops whatever falls outside, so frac may
    exceed 1.0 for a deliberate bleed."""
    cw, ch = canvas
    multi = src.ndim == 3
    a = src[..., 3] if multi else src
    ys, xs = np.nonzero(a > 1e-3)
    if len(xs) == 0:
        raise ValueError('artwork is empty -- nothing to place')
    sub = src[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = sub.shape[:2]
    scale = (frac * min(cw, ch)) / max(h, w)
    if multi:
        sub = np.stack([np.clip(zoom(sub[..., c], scale, order=3, mode='constant', cval=0.0),
                                0, 1) for c in range(sub.shape[2])], axis=2)
    else:
        sub = np.clip(zoom(sub, scale, order=3, mode='constant', cval=0.0), 0, 1)
    h, w = sub.shape[:2]

    shape = (ch, cw) + ((sub.shape[2],) if multi else ())
    out = np.zeros(shape, np.float64)
    top = (ch - h) // 2 + int(round(y_shift * ch))
    left = (cw - w) // 2
    sy, sx = max(0, -top), max(0, -left)
    dy, dx = max(0, top), max(0, left)
    hh, ww = min(h - sy, ch - dy), min(w - sx, cw - dx)
    if hh > 0 and ww > 0:
        out[dy:dy + hh, dx:dx + ww] = sub[sy:sy + hh, sx:sx + ww]
    return out


# --------------------------------------------------------------------------
# Glow
# --------------------------------------------------------------------------

def multiscale_glow(mask, sigmas_frac, weights, ref_px):
    """Sum of gaussians at several scales.

    One gaussian gives a halo with an obvious edge; several summed give a wide
    soft falloff that still reads as glow after a tone-mapper has had its way
    with it. Computed at half resolution -- glow is low-frequency by definition,
    so this is ~4x faster with no visible difference.
    """
    small = zoom(mask, 0.5, order=1, mode='constant', cval=0.0)
    acc = np.zeros_like(small)
    for sf, w in zip(sigmas_frac, weights):
        acc += w * gaussian_filter(small, max(sf * ref_px * 0.5, 0.6),
                                   mode='constant', cval=0.0)
    acc = zoom(acc, (mask.shape[0] / acc.shape[0], mask.shape[1] / acc.shape[1]),
               order=1, mode='constant', cval=0.0)
    acc = np.clip(acc, 0.0, None)
    peak = acc.max()
    return acc / peak if peak > 0 else acc


# --------------------------------------------------------------------------
# Gradient backdrop
# --------------------------------------------------------------------------

def gradient_panel(w, h, stops, axis=((0.87, 0.85), (0.13, 0.14))):
    """A linear gradient across the canvas, interpolated in LINEAR light.

    `stops` is [(offset, '#rrggbb'), ...]; `axis` is ((x0,y0),(x1,y1)) in
    normalised canvas coordinates, running from offset 0 to offset 1.

    Interpolating stops in sRGB instead darkens the midpoints -- the classic
    muddy-gradient artefact. Doing it in linear light keeps the ramp even.
    """
    (x0, y0), (x1, y1) = axis
    x0, y0, x1, y1 = x0 * w, y0 * h, x1 * w, y1 * h
    ax, ay = x1 - x0, y1 - y0
    denom = max(ax * ax + ay * ay, 1e-9)
    xx, yy = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
    t = np.clip(((xx - x0) * ax + (yy - y0) * ay) / denom, 0.0, 1.0)

    offs = np.array([o for o, _ in stops], np.float64)
    cols = np.array([k.hex_to_linear_rgb(c) for _, c in stops])
    order = np.argsort(offs)
    offs, cols = offs[order], cols[order]
    out = np.empty((h, w, 3), np.float64)
    for ch in range(3):
        out[..., ch] = np.interp(t, offs, cols[:, ch])
    return out


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

DEFAULTS = dict(
    width=1200, height=1200,
    supersample=3,
    layout='bleed',           # bleed | inset | mark
    mark_frac=0.55,           # mark size as a fraction of the short axis
    backdrop_frac=0.86,       # inset layout: how much of the canvas the panel fills
    y_shift=0.0,

    # --- luminance, in nits. This is the entire trick, stated plainly. ---
    # SDR white is 203 nits (BT.2408), so peak/203 is the multiple of "as bright
    # as an ordinary white pixel" the mark asks for.
    peak_nits=900.0,          # the mark            -> 4.4x SDR white
    glow_nits=330.0,          # the halo at its hottest -> 1.6x
    panel_white_nits=203.0,   # what #ffffff *inside the backdrop artwork* means
    bg_top_nits=5.0,          # the dark ground, top
    bg_bottom_nits=1.1,       # the dark ground, bottom

    # --- the SDR rendition of the same artwork ---
    sdr_peak_nits=203.0,      # the mark lands exactly on SDR white
    sdr_glow_nits=90.0,       # the halo stays tinted instead of clipping to white

    # --- brand inputs ---
    mark_hex='#ffffff',
    glow_hex='#6366f2',
    bg_hex='#322f82',
    gradient_stops=None,      # [(offset, hex), ...]; falls back to bg_hex->glow_hex
    gradient_axis=((0.87, 0.85), (0.13, 0.14)),
    backdrop=None,            # path to panel artwork, for the 'inset' layout

    clip_glow_to_backdrop=True,
    glow_sigmas=(0.008, 0.022, 0.055, 0.120),
    glow_weights=(0.50, 0.32, 0.18, 0.12),
)


def resolve(cfg=None):
    c = dict(DEFAULTS)
    if cfg:
        c.update({kk: vv for kk, vv in cfg.items() if vv is not None})
    if not c['gradient_stops']:
        c['gradient_stops'] = [(0.0, c['bg_hex']), (1.0, c['glow_hex'])]
    return c


# --------------------------------------------------------------------------
# Layers and rendering
# --------------------------------------------------------------------------

def build_layers(mark_path, cfg=None):
    """Rasterise once; return resolution-independent geometry layers."""
    c = resolve(cfg)
    cw, ch, s = c['width'], c['height'], c['supersample']
    sw, sh = cw * s, ch * s
    panel = None

    if c['layout'] == 'inset':
        if not c['backdrop']:
            raise ValueError("layout 'inset' needs --backdrop artwork")
        # Panel and mark are placed with ONE transform so they stay in register.
        # Fitting each to its own ink bounds independently makes the mark drift
        # inside the panel at different canvas sizes.
        r = int(round(c['backdrop_frac'] * min(sw, sh)))
        panel = fit(load_rgba(c['backdrop'], r), (sw, sh), 1.0, c['y_shift'])
        mask = fit(load_alpha(mark_path, r)[..., None], (sw, sh), 1.0, c['y_shift'])[..., 0]
    else:
        mask = fit(load_alpha(mark_path, max(sw, sh)), (sw, sh), c['mark_frac'], c['y_shift'])
        if c['layout'] == 'bleed':
            panel = np.concatenate(
                [gradient_panel(sw, sh, c['gradient_stops'], c['gradient_axis']),
                 np.ones((sh, sw, 1), np.float64)], axis=2)

    glow = multiscale_glow(mask, c['glow_sigmas'], c['glow_weights'], min(sw, sh))
    ramp = np.repeat((np.linspace(1.0, 0.0, sh) ** 1.6)[:, None], sw, axis=1)

    if s > 1:
        mask = mask.reshape(ch, s, cw, s).mean(axis=(1, 3))
        glow = glow.reshape(ch, s, cw, s).mean(axis=(1, 3))
        ramp = ramp.reshape(ch, s, cw, s).mean(axis=(1, 3))
        if panel is not None:
            panel = panel.reshape(ch, s, cw, s, 4).mean(axis=(1, 3))

    layers = dict(mask=np.clip(mask, 0, 1), glow=np.clip(glow, 0, 1), ramp=ramp, cfg=c)
    if panel is not None:
        layers['panel'] = panel
    return layers


def render(layers, peak_nits=None, glow_nits=None, panel_white=None):
    """Composite at a given set of luminances -> linear BT.709 nits."""
    c = layers['cfg']
    peak = c['peak_nits'] if peak_nits is None else peak_nits
    gl = c['glow_nits'] if glow_nits is None else glow_nits
    pw = c['panel_white_nits'] if panel_white is None else panel_white

    mask, glow, ramp = layers['mask'], layers['glow'], layers['ramp']
    panel = layers.get('panel')
    is_gradient = c['layout'] == 'bleed'

    # dark ground
    scene = (c['bg_bottom_nits']
             + (c['bg_top_nits'] - c['bg_bottom_nits']) * ramp)[..., None] \
        * k.tint_at_nits(c['bg_hex'], 1.0)

    alpha = None
    if panel is not None:
        prgb, alpha = panel[..., :3], panel[..., 3]
        # The gradient is already linear; rasterised artwork is sRGB.
        # Scale so #ffffff in the artwork lands on `pw` nits and every other
        # colour falls where the designer put it. Normalising by the artwork's
        # own brightest pixel instead stretches the brand colour toward white --
        # a deep indigo comes out lavender.
        lin = prgb if is_gradient else k.srgb_to_linear(prgb)
        scene = scene * (1.0 - alpha[..., None]) + (lin * pw) * alpha[..., None]

    # Glow goes ON TOP of the panel. Underneath it, the panel simply hides the
    # halo -- the opposite of light spilling out of the mark. And on an inset
    # panel it is clipped to the panel: let it run past the edge and it lights
    # the dark ground right at the boundary, drawing a bright rim around the
    # whole logo that reads as a barrier.
    spill = glow
    if alpha is not None and c['clip_glow_to_backdrop'] and not is_gradient:
        spill = glow * alpha
    scene = scene + (spill * gl)[..., None] * k.tint_at_nits(c['glow_hex'], 1.0)

    # the mark, the brightest thing in the frame
    scene = (scene * (1.0 - mask[..., None])
             + (mask * peak)[..., None] * k.tint_at_nits(c['mark_hex'], 1.0))
    return np.clip(scene, 0.0, k.PQ_MAX_NITS)


def render_hdr(layers):
    return render(layers)


def render_sdr(layers):
    """The SDR rendition -- authored, not tone-mapped. The mark lands exactly on
    SDR white and nothing exceeds it, so this file is a correct standalone image
    on any display that never heard of HDR."""
    c = layers['cfg']
    return render(layers, peak_nits=c['sdr_peak_nits'], glow_nits=c['sdr_glow_nits'],
                  panel_white=min(c['panel_white_nits'], c['sdr_peak_nits']))


def scene_stats(scene):
    """How hard this frame actually pushes the panel."""
    y = k.luminance(scene)
    return dict(
        peak_nits=float(y.max()),
        mean_nits=float(y.mean()),
        sdr_white_multiple=float(y.max() / k.SDR_WHITE_NITS),
        frac_above_sdr_white=float((y > k.SDR_WHITE_NITS).mean()),
        # Average picture level relative to a full-screen SDR white frame. OLEDs
        # dim the whole panel when this climbs (auto-brightness limiter), so a
        # bright mark on a dark frame holds its peak better than a bright frame.
        apl_vs_sdr_white=float(y.mean() / k.SDR_WHITE_NITS),
    )
