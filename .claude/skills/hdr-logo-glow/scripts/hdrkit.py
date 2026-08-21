"""
hdrkit -- colour science + scene construction for HDR logo assets.

Everything here works in *linear light measured in nits* (cd/m^2), which is the
only representation in which "make this part of the logo emit more light than
SDR white" is a meaningful statement.

Reference points used throughout:
  * SDR diffuse white  = 203 nits   (ITU-R BT.2408 reference white for HDR/SDR
                                     interchange -- i.e. what a #ffffff pixel in
                                     a normal image is understood to mean)
  * PQ signal range    = 0 .. 10000 nits (SMPTE ST 2084 is *absolute*)

So a logo authored at 800 nits is asking the display for ~3.9x the light of a
plain white pixel next to it in the feed. That ratio, not the absolute number,
is what the eye reads as "glowing".
"""

import numpy as np

# --------------------------------------------------------------------------
# Reference luminance
# --------------------------------------------------------------------------

SDR_WHITE_NITS = 203.0      # BT.2408 reference/diffuse white
PQ_MAX_NITS = 10000.0       # ST 2084 encodes an absolute 0..10000 cd/m^2 range


# --------------------------------------------------------------------------
# Transfer functions
# --------------------------------------------------------------------------

def srgb_to_linear(x):
    """sRGB EOTF: gamma-encoded [0,1] -> linear [0,1]."""
    x = np.asarray(x, np.float64)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x):
    """sRGB inverse EOTF: linear [0,1] -> gamma-encoded [0,1]."""
    x = np.clip(np.asarray(x, np.float64), 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * (x ** (1 / 2.4)) - 0.055)


# SMPTE ST 2084 (PQ) constants, exact rational forms from the standard.
_PQ_M1 = 2610.0 / 16384.0             # 0.1593017578125
_PQ_M2 = 2523.0 / 4096.0 * 128.0      # 78.84375
_PQ_C1 = 3424.0 / 4096.0              # 0.8359375
_PQ_C2 = 2413.0 / 4096.0 * 32.0       # 18.8515625
_PQ_C3 = 2392.0 / 4096.0 * 32.0       # 18.6875


def nits_to_pq(nits):
    """ST 2084 inverse EOTF (OETF): absolute nits -> PQ code value [0,1]."""
    y = np.clip(np.asarray(nits, np.float64) / PQ_MAX_NITS, 0.0, 1.0)
    ym = y ** _PQ_M1
    return ((_PQ_C1 + _PQ_C2 * ym) / (1.0 + _PQ_C3 * ym)) ** _PQ_M2


def pq_to_nits(code):
    """ST 2084 EOTF: PQ code value [0,1] -> absolute nits."""
    e = np.clip(np.asarray(code, np.float64), 0.0, 1.0) ** (1.0 / _PQ_M2)
    num = np.maximum(e - _PQ_C1, 0.0)
    den = _PQ_C2 - _PQ_C3 * e
    return PQ_MAX_NITS * (num / den) ** (1.0 / _PQ_M1)


def nits_to_hlg(nits, peak_nits=1000.0):
    """ARIB STD-B67 (HLG) OETF, scene-referred. Included for completeness."""
    a, b, c = 0.17883277, 0.28466892, 0.55991073
    e = np.clip(np.asarray(nits, np.float64) / peak_nits, 0.0, 1.0)
    return np.where(e <= 1.0 / 12.0,
                    np.sqrt(np.maximum(e, 0.0) * 3.0),
                    a * np.log(np.maximum(12.0 * e - b, 1e-12)) + c)


# --------------------------------------------------------------------------
# Colour gamut conversion (linear light)
# --------------------------------------------------------------------------

# BT.709 (== sRGB primaries) linear RGB -> BT.2020 linear RGB, D65, Bradford-free
# (both are D65 so no chromatic adaptation is needed).
BT709_TO_BT2020 = np.array([
    [0.62740389, 0.32928304, 0.04331307],
    [0.06909729, 0.91954058, 0.01136213],
    [0.01639144, 0.08801331, 0.89559525],
], np.float64)

BT2020_TO_BT709 = np.linalg.inv(BT709_TO_BT2020)

# Luminance weights
BT709_LUMA = np.array([0.2126, 0.7152, 0.0722], np.float64)
BT2020_LUMA = np.array([0.2627, 0.6780, 0.0593], np.float64)


def apply_matrix(img, m):
    """Apply a 3x3 colour matrix to an (H,W,3) linear image."""
    return np.einsum('ij,hwj->hwi', m, np.asarray(img, np.float64))


def bt709_to_bt2020(img):
    return apply_matrix(img, BT709_TO_BT2020)


def luminance(img, weights=BT709_LUMA):
    return np.einsum('hwc,c->hw', np.asarray(img, np.float64), weights)


# --------------------------------------------------------------------------
# Colour helpers
# --------------------------------------------------------------------------

def hex_to_linear_rgb(hex_str):
    """'#6366f2' -> linear-light BT.709 RGB triple normalised so max component
    scaling is left to the caller (i.e. relative, unit-less)."""
    h = hex_str.lstrip('#')
    if len(h) == 3:
        h = ''.join(ch * 2 for ch in h)
    srgb = np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float64)
    return srgb_to_linear(srgb)


def tint_at_nits(hex_str, nits):
    """Return a linear BT.709 RGB triple for `hex_str` whose *luminance* is
    exactly `nits`. Keeps the hue/chroma of the brand colour while letting us
    talk about how bright it is in absolute terms."""
    lin = hex_to_linear_rgb(hex_str)
    y = float(np.dot(lin, BT709_LUMA))
    if y <= 0:
        return np.zeros(3, np.float64)
    return lin * (nits / y)
