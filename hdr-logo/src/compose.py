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


def fit_mask(mask, canvas_px, mark_frac=0.52, y_shift=0.0):
    """Trim a mask to its ink bounds and re-place it on a square canvas so the
    mark occupies `mark_frac` of the canvas along its longest axis."""
    ys, xs = np.nonzero(mask > 1e-3)
    if len(xs) == 0:
        raise ValueError('mask is empty')
    sub = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = sub.shape
    target = mark_frac * canvas_px
    scale = target / max(h, w)
    sub = zoom(sub, scale, order=3, mode='constant', cval=0.0)
    sub = np.clip(sub, 0.0, 1.0)
    h, w = sub.shape

    out = np.zeros((canvas_px, canvas_px), np.float64)
    top = int(round((canvas_px - h) / 2 + y_shift * canvas_px))
    left = int(round((canvas_px - w) / 2))
    top = max(0, min(canvas_px - h, top))
    left = max(0, min(canvas_px - w, left))
    out[top:top + h, left:left + w] = sub
    return out


# --------------------------------------------------------------------------
# Bloom
# --------------------------------------------------------------------------

def multiscale_bloom(mask, sigmas_frac, weights, px):
    """Sum of gaussians at several scales -- a wide, soft falloff that survives
    tone mapping instead of collapsing into a hard ring.

    Computed at half resolution (bloom is low-frequency by definition) and
    upsampled, which is ~4x faster with no visible difference.
    """
    small = zoom(mask, 0.5, order=1, mode='constant', cval=0.0)
    acc = np.zeros_like(small)
    for sf, w in zip(sigmas_frac, weights):
        sigma = max(sf * px * 0.5, 0.6)
        acc += w * gaussian_filter(small, sigma, mode='constant', cval=0.0)
    acc = zoom(acc, (mask.shape[0] / acc.shape[0], mask.shape[1] / acc.shape[1]),
               order=1, mode='constant', cval=0.0)
    acc = np.clip(acc, 0.0, None)
    peak = acc.max()
    return acc / peak if peak > 0 else acc


# --------------------------------------------------------------------------
# Scene
# --------------------------------------------------------------------------

DEFAULTS = dict(
    canvas=1200,
    supersample=3,
    mark_frac=0.46,
    y_shift=0.0,

    # --- luminance, in nits. This is the whole trick, stated plainly. ---
    peak_nits=800.0,          # the white mark: ~3.9x SDR white
    bloom_peak_nits=300.0,    # the halo at its hottest: ~1.5x SDR white
    bg_top_nits=5.0,          # background gradient, top
    bg_bottom_nits=1.1,       # background gradient, bottom

    # --- the SDR rendition of the same artwork ---
    sdr_peak_nits=203.0,      # mark sits exactly at SDR white
    sdr_bloom_nits=118.0,     # halo stays indigo instead of clipping to white

    mark_hex='#ffffff',
    bloom_hex='#6366f2',      # Cotera indigo, light stop of the brand gradient
    bg_hex='#322f82',         # Cotera indigo, dark stop
    bloom_sigmas=(0.010, 0.030, 0.075, 0.170),
    bloom_weights=(0.44, 0.30, 0.17, 0.16),
)


def build_layers(svg_path, cfg=None):
    """Rasterise once and return the geometry as resolution-independent layers.

    Separating geometry from luminance matters: the HDR and SDR renditions must
    be the *same picture* at different brightnesses, otherwise the gain map
    between them encodes shape as well as light, which is exactly the artefact
    gain maps exist to avoid.
    """
    c = dict(DEFAULTS)
    if cfg:
        c.update(cfg)
    px = c['canvas'] * c['supersample']
    s = c['supersample']
    h = c['canvas']

    mask = fit_mask(render_svg_alpha(svg_path, px), px, c['mark_frac'], c['y_shift'])
    bloom = multiscale_bloom(mask, c['bloom_sigmas'], c['bloom_weights'], px)
    ramp = np.repeat((np.linspace(1.0, 0.0, px) ** 1.6)[:, None], px, axis=1)

    # Resolve supersampling here, once, on the geometry itself.
    if s > 1:
        mask = mask.reshape(h, s, h, s).mean(axis=(1, 3))
        bloom = bloom.reshape(h, s, h, s).mean(axis=(1, 3))
        ramp = ramp.reshape(h, s, h, s).mean(axis=(1, 3))

    return dict(mask=np.clip(mask, 0, 1), bloom=np.clip(bloom, 0, 1),
                ramp=ramp, cfg=c)


def render(layers, peak_nits=None, bloom_nits=None, bg_top=None, bg_bottom=None):
    """Composite the layers at a given set of luminances -> linear BT.709 nits."""
    c = layers['cfg']
    peak = c['peak_nits'] if peak_nits is None else peak_nits
    bl = c['bloom_peak_nits'] if bloom_nits is None else bloom_nits
    top = c['bg_top_nits'] if bg_top is None else bg_top
    bot = c['bg_bottom_nits'] if bg_bottom is None else bg_bottom

    mask, bloom, ramp = layers['mask'], layers['bloom'], layers['ramp']

    bg = (bot + (top - bot) * ramp)[..., None] * k.tint_at_nits(c['bg_hex'], 1.0)
    scene = bg + (bloom * bl)[..., None] * k.tint_at_nits(c['bloom_hex'], 1.0)
    mark = (mask * peak)[..., None] * k.tint_at_nits(c['mark_hex'], 1.0)
    scene = scene * (1.0 - mask[..., None]) + mark
    return np.clip(scene, 0.0, k.PQ_MAX_NITS)


def render_hdr(layers):
    return render(layers)


def render_sdr(layers):
    """The SDR rendition -- authored, not tone-mapped. The mark lands exactly on
    SDR white and the halo stays below it, so this file is a correct standalone
    image on any display that never heard of HDR."""
    c = layers['cfg']
    return render(layers, peak_nits=c['sdr_peak_nits'], bloom_nits=c['sdr_bloom_nits'])


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
