"""
icc_pq.py — generate a real Rec.2100 / Rec.2020 PQ (SMPTE ST 2084) ICC profile.

There is no PQ profile shipped with Pillow, cairosvg, or Debian/Ubuntu base
images, so this module *builds* a valid ICC v4.4 RGB matrix/shaper profile from
first principles rather than falling back to sRGB.

What the profile contains
-------------------------
* BT.2020 primaries, chromatically adapted D65 -> D50 (Bradford) for the
  ICC PCS, with the adaptation matrix stored in the ``chad`` tag.
* rTRC/gTRC/bTRC: 4096-entry sampled ``curv`` tables holding the ST.2084 PQ
  EOTF, normalised so that the BT.2408 HDR reference white (203 nits by
  default) lands on PCS 1.0.  A colour-managed *SDR* viewer that honours the
  TRC therefore reproduces the artwork correctly and simply clips the
  above-reference-white arrow to white -- which is exactly the SDR fallback
  we want.
* A ``cicp`` tag (ICC v4.4, ISO 15076-1:2024) carrying
  colour_primaries = 9 (BT.2020), transfer_characteristics = 16 (ST.2084 PQ),
  matrix_coefficients = 0 (RGB), full_range = 1.  This is the tag that modern
  HDR-aware pipelines (ColorSync on macOS/iOS, Chrome/Skia, Android) read to
  decide "this is PQ HDR content", and it is what makes the arrow actually
  emit above SDR white.
"""

from __future__ import annotations

import hashlib
import struct
from datetime import datetime, timezone

# Fixed creation date so profiles -- and therefore the JPEGs that embed them --
# are byte-reproducible across runs instead of churning on every build.
PROFILE_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)

import numpy as np

MAX_PQ_NITS = 10000.0
BT2408_REFERENCE_WHITE_NITS = 203.0

# --------------------------------------------------------------------------
# ST.2084 PQ
# --------------------------------------------------------------------------

_M1 = 2610.0 / 16384.0
_M2 = 2523.0 / 32.0
_C1 = 3424.0 / 4096.0
_C2 = 2413.0 / 128.0
_C3 = 2392.0 / 128.0


def pq_oetf(luminance_nits):
    """ST.2084 PQ OETF.  Absolute nits in -> normalised PQ code value 0..1."""
    L = np.clip(np.asarray(luminance_nits, dtype=np.float64) / MAX_PQ_NITS, 0.0, 1.0)
    numerator = _C1 + _C2 * (L ** _M1)
    denominator = 1.0 + _C3 * (L ** _M1)
    return (numerator / denominator) ** _M2


def pq_eotf(code_value):
    """ST.2084 PQ EOTF.  Normalised PQ code value 0..1 in -> absolute nits."""
    N = np.clip(np.asarray(code_value, dtype=np.float64), 0.0, 1.0) ** (1.0 / _M2)
    num = np.maximum(N - _C1, 0.0)
    den = _C2 - _C3 * N
    return MAX_PQ_NITS * (num / den) ** (1.0 / _M1)


# --------------------------------------------------------------------------
# Colour science helpers
# --------------------------------------------------------------------------

BT2020_PRIMARIES = {"R": (0.708, 0.292), "G": (0.170, 0.797), "B": (0.131, 0.046)}
BT709_PRIMARIES = {"R": (0.640, 0.330), "G": (0.300, 0.600), "B": (0.150, 0.060)}
D65_XY = (0.3127, 0.3290)

# ICC PCS illuminant, fixed by the spec at the s15Fixed16 values below.
D50_XYZ = np.array([0.9642, 1.0, 0.8249])

_BRADFORD = np.array(
    [
        [0.8951, 0.2664, -0.1614],
        [-0.7502, 1.7135, 0.0367],
        [0.0389, -0.0685, 1.0296],
    ]
)


def xy_to_xyz(x, y):
    return np.array([x / y, 1.0, (1.0 - x - y) / y])


def rgb_to_xyz_matrix(primaries, white_xy=D65_XY):
    """Linear RGB -> XYZ for a set of xy primaries and a white point."""
    m = np.column_stack([xy_to_xyz(*primaries[c]) for c in ("R", "G", "B")])
    scale = np.linalg.solve(m, xy_to_xyz(*white_xy))
    return m * scale


def bradford_adaptation(src_xyz, dst_xyz):
    """Von Kries / Bradford chromatic adaptation matrix, src white -> dst white."""
    src_cone = _BRADFORD @ src_xyz
    dst_cone = _BRADFORD @ dst_xyz
    return np.linalg.inv(_BRADFORD) @ np.diag(dst_cone / src_cone) @ _BRADFORD


def linear_rgb_conversion_matrix(src_primaries, dst_primaries, white_xy=D65_XY):
    """Linear RGB -> linear RGB between two gamuts sharing a white point."""
    return np.linalg.inv(rgb_to_xyz_matrix(dst_primaries, white_xy)) @ rgb_to_xyz_matrix(
        src_primaries, white_xy
    )


# --------------------------------------------------------------------------
# ICC serialisation primitives
# --------------------------------------------------------------------------


def _s15f16(value):
    return struct.pack(">i", int(round(float(value) * 65536.0)))


def _pad4(data):
    return data + b"\x00" * ((4 - len(data) % 4) % 4)


def _mluc(text):
    payload = text.encode("utf-16-be")
    return (
        b"mluc"
        + b"\x00" * 4
        + struct.pack(">III", 1, 12, 0x656E5553)  # 1 record, 12 bytes each, 'enUS'
        + struct.pack(">II", len(payload), 28)
        + payload
    )


def _xyz_type(xyz):
    return b"XYZ " + b"\x00" * 4 + b"".join(_s15f16(v) for v in xyz)


def _sf32(matrix):
    return b"sf32" + b"\x00" * 4 + b"".join(_s15f16(v) for v in np.asarray(matrix).ravel())


def _curv(samples):
    # Sampled curves are stored verbatim: ICC allows a non-strictly-monotonic
    # curv table, and the PQ curve legitimately has a flat top once it passes
    # reference white.  Do NOT "fix" ties by nudging values upward -- near black
    # many consecutive samples share a code and any nudge compounds into a
    # large black lift (it cost ~2.4x on the darkest tones during development).
    q = np.clip(np.rint(np.asarray(samples) * 65535.0), 0, 65535).astype(">u2")
    return b"curv" + b"\x00" * 4 + struct.pack(">I", q.size) + q.tobytes()


def _cicp(primaries=9, transfer=16, matrix=0, full_range=1):
    return b"cicp" + b"\x00" * 4 + struct.pack(">BBBB", primaries, transfer, matrix, full_range)


def pq_trc_samples(sdr_white_nits=BT2408_REFERENCE_WHITE_NITS, size=4096):
    """PQ code value -> PCS-relative linear luminance, clipped at reference white."""
    code = np.linspace(0.0, 1.0, size)
    return np.clip(pq_eotf(code) / float(sdr_white_nits), 0.0, 1.0)


def build_rec2100_pq_icc(
    description="Cotera Rec.2100 PQ (BT.2020 primaries, SMPTE ST 2084)",
    copyright_text="Public Domain. Generated by cotera-hdr/icc_pq.py.",
    sdr_white_nits=BT2408_REFERENCE_WHITE_NITS,
    trc_size=4096,
    created=PROFILE_EPOCH,
):
    """Return a complete ICC v4.4 Rec.2100 PQ profile as bytes."""
    d65_xyz = xy_to_xyz(*D65_XY)
    adapt = bradford_adaptation(d65_xyz, D50_XYZ)
    colorants = adapt @ rgb_to_xyz_matrix(BT2020_PRIMARIES, D65_XY)

    trc = _curv(pq_trc_samples(sdr_white_nits, trc_size))

    tags = [
        (b"desc", _mluc(description)),
        (b"cprt", _mluc(copyright_text)),
        (b"wtpt", _xyz_type(D50_XYZ)),
        (b"chad", _sf32(adapt)),
        (b"rXYZ", _xyz_type(colorants[:, 0])),
        (b"gXYZ", _xyz_type(colorants[:, 1])),
        (b"bXYZ", _xyz_type(colorants[:, 2])),
        (b"rTRC", trc),
        (b"gTRC", trc),
        (b"bTRC", trc),
        (b"cicp", _cicp()),
        (b"lumi", _xyz_type([0.0, MAX_PQ_NITS, 0.0])),
    ]

    header_size = 128
    table_size = 4 + 12 * len(tags)
    offset = header_size + table_size
    table, blob, seen = b"", b"", {}
    for sig, data in tags:
        key = bytes(data)
        if key in seen:  # the three TRCs are identical; share one element
            table += struct.pack(">4sII", sig, *seen[key])
            continue
        seen[key] = (offset, len(data))
        table += struct.pack(">4sII", sig, offset, len(data))
        padded = _pad4(data)
        blob += padded
        offset += len(padded)

    table = struct.pack(">I", len(tags)) + table
    total = header_size + len(table) + len(blob)
    now = created

    header = b"".join(
        [
            struct.pack(">I", total),
            b"COTR",                                    # preferred CMM
            struct.pack(">I", 0x04400000),              # ICC version 4.4.0
            b"mntr",                                    # display device class
            b"RGB ",
            b"XYZ ",
            struct.pack(">HHHHHH", now.year, now.month, now.day, now.hour, now.minute, now.second),
            b"acsp",
            b"APPL",                                    # primary platform
            struct.pack(">I", 0),                       # profile flags
            struct.pack(">I", 0),                       # device manufacturer
            struct.pack(">I", 0),                       # device model
            struct.pack(">Q", 0),                       # device attributes
            struct.pack(">I", 0),                       # rendering intent: perceptual
            b"".join(_s15f16(v) for v in D50_XYZ),      # PCS illuminant
            b"COTR",                                    # profile creator
            b"\x00" * 16,                               # profile ID (filled below)
            b"\x00" * 28,                               # reserved
        ]
    )
    assert len(header) == header_size, len(header)

    profile = bytearray(header + table + blob)
    # Profile ID is the MD5 of the profile with flags, rendering intent and the
    # ID field itself zeroed (ICC.1 clause 7.2.18) -- all already zero here.
    profile[84:100] = hashlib.md5(bytes(profile)).digest()
    return bytes(profile)


def normalize_icc_datetime(profile: bytes, created=PROFILE_EPOCH) -> bytes:
    """Stamp a fixed creation date on a third-party profile and refresh its ID.

    littleCMS writes the current time into the sRGB profile it synthesises,
    which makes every build of the SDR controls a different file.  Rewriting the
    date (and recomputing the profile ID per ICC.1 clause 7.2.18) makes the whole
    output byte-reproducible.
    """
    buf = bytearray(profile)
    buf[24:36] = struct.pack(
        ">HHHHHH", created.year, created.month, created.day,
        created.hour, created.minute, created.second,
    )
    scratch = bytearray(buf)
    scratch[44:48] = b"\x00" * 4   # profile flags
    scratch[64:68] = b"\x00" * 4   # rendering intent
    scratch[84:100] = b"\x00" * 16  # profile ID itself
    buf[84:100] = hashlib.md5(bytes(scratch)).digest()
    return bytes(buf)


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "Rec2100-PQ.icc"
    data = build_rec2100_pq_icc()
    with open(out, "wb") as fh:
        fh.write(data)
    print(f"wrote {out} ({len(data)} bytes)")
