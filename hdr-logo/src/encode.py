"""
encode -- write the linear-nits scene out in each HDR container.

Three delivery formats, in descending order of "will a social pipeline keep it":

  ultrahdr JPEG  base SDR JPEG + gain map. Degrades to a *correct* SDR image on
                 any display or any viewer that ignores the gain map.
  AVIF (PQ)      BT.2020 + ST 2084, 10-bit. Cleanest HDR, but an SDR viewer that
                 does not tone map shows a washed-out image.
  PNG (cICP)     16-bit BT.2020 + ST 2084 tagged with a cICP chunk. Same
                 caveat as AVIF; useful where only PNG is accepted.

Plus a plain SDR PNG/JPEG rendered from the same scene (not a tone map of it)
so there is always a clean fallback to hand a platform that strips everything.
"""

import struct
import subprocess
import zlib
import numpy as np
from PIL import Image

import hdrkit as k


# --------------------------------------------------------------------------
# PNG chunk surgery
# --------------------------------------------------------------------------

def _chunk(ctype: bytes, data: bytes) -> bytes:
    return (struct.pack('>I', len(data)) + ctype + data
            + struct.pack('>I', zlib.crc32(ctype + data) & 0xFFFFFFFF))


def _iter_chunks(png: bytes):
    assert png[:8] == b'\x89PNG\r\n\x1a\n', 'not a PNG'
    pos = 8
    while pos < len(png):
        ln = struct.unpack('>I', png[pos:pos + 4])[0]
        ctype = png[pos + 4:pos + 8]
        yield ctype, png[pos:pos + 12 + ln]
        pos += 12 + ln


def png_insert_chunks(png: bytes, new_chunks: list, drop=(b'iCCP', b'sRGB', b'gAMA', b'cHRM')) -> bytes:
    """Insert chunks immediately after IHDR, dropping any colour chunks that
    would out-rank cICP. Per the PNG spec, when cICP is present it takes
    precedence -- but decoders in the wild are inconsistent, so we remove the
    competition rather than rely on precedence.
    """
    out = [png[:8]]
    inserted = False
    for ctype, raw in _iter_chunks(png):
        if ctype in drop:
            continue
        out.append(raw)
        if ctype == b'IHDR' and not inserted:
            out.extend(new_chunks)
            inserted = True
    return b''.join(out)


def cicp_chunk(primaries=9, transfer=16, matrix=0, full_range=1) -> bytes:
    """PNG cICP chunk (PNG 3rd edition / W3C PNG spec).

    Four bytes, straight from ITU-T H.273 code points:
        colour_primaries         9  = BT.2020
        transfer_characteristics 16 = SMPTE ST 2084 (PQ)   [18 = ARIB STD-B67/HLG]
        matrix_coefficients      0  = Identity/RGB -- REQUIRED to be 0 in PNG,
                                      because PNG stores RGB, not YCbCr
        video_full_range_flag    1  = full range
    """
    assert matrix == 0, 'PNG requires matrix_coefficients == 0'
    return _chunk(b'cICP', bytes([primaries, transfer, matrix, full_range]))


def clli_chunk(max_cll_nits: float, max_fall_nits: float) -> bytes:
    """cLLI -- content light level. Both values in units of 0.0001 cd/m^2."""
    return _chunk(b'cLLI', struct.pack('>II',
                                       int(round(max_cll_nits * 10000)),
                                       int(round(max_fall_nits * 10000))))


def mdcv_chunk(max_lum_nits=1000.0, min_lum_nits=0.0001) -> bytes:
    """mDCV -- mastering display colour volume, BT.2020 primaries + D65.
    Chromaticities in units of 0.00002; luminances in units of 0.0001 cd/m^2."""
    # BT.2020 primaries R,G,B then white point D65
    chroma = [(0.708, 0.292), (0.170, 0.797), (0.131, 0.046), (0.3127, 0.3290)]
    vals = []
    for x, y in chroma:
        vals += [int(round(x / 0.00002)), int(round(y / 0.00002))]
    return _chunk(b'mDCV', struct.pack('>8H', *vals)
                  + struct.pack('>II', int(round(max_lum_nits * 10000)),
                                int(round(min_lum_nits * 10000))))


# --------------------------------------------------------------------------
# Quantisation
# --------------------------------------------------------------------------

def _dither(x, levels, rng):
    """Triangular probability density function dither -- one quantisation step
    wide, zero mean. Stops the bloom gradient from banding once it is squeezed
    into 10-bit PQ."""
    step = 1.0 / (levels - 1)
    noise = (rng.random(x.shape) - rng.random(x.shape)) * step * 0.5
    return x + noise


def scene_to_pq_rgb(scene_nits, bits=16, dither=True, seed=7):
    """Linear BT.709 nits -> PQ-encoded BT.2020 RGB integer array."""
    rgb2020 = k.bt709_to_bt2020(scene_nits)
    rgb2020 = np.clip(rgb2020, 0.0, k.PQ_MAX_NITS)
    pq = k.nits_to_pq(rgb2020)
    levels = 2 ** bits
    if dither:
        pq = _dither(pq, levels, np.random.default_rng(seed))
    pq = np.clip(pq, 0.0, 1.0)
    return np.round(pq * (levels - 1)).astype(np.uint16 if bits > 8 else np.uint8)


def _filter_scanlines(raw, bpp, width, height):
    """Adaptive PNG filtering: per row, pick the filter type with the smallest
    sum of absolute differences (the heuristic the spec itself recommends)."""
    stride = width * bpp
    prev = np.zeros(stride, np.uint8)
    out = bytearray()
    for y in range(height):
        line = raw[y * stride:(y + 1) * stride]
        a = np.zeros(stride, np.uint8)          # left neighbour
        a[bpp:] = line[:-bpp]
        b = prev                                # above
        c = np.zeros(stride, np.uint8)          # above-left
        c[bpp:] = prev[:-bpp]

        cands = {
            0: line,
            1: (line.astype(np.int16) - a).astype(np.uint8),
            2: (line.astype(np.int16) - b).astype(np.uint8),
            3: (line.astype(np.int16) - ((a.astype(np.int16) + b) // 2)).astype(np.uint8),
        }
        # Paeth
        p = a.astype(np.int16) + b.astype(np.int16) - c.astype(np.int16)
        pa, pb, pc = np.abs(p - a), np.abs(p - b), np.abs(p - c)
        pred = np.where((pa <= pb) & (pa <= pc), a, np.where(pb <= pc, b, c))
        cands[4] = (line.astype(np.int16) - pred).astype(np.uint8)

        ft = min(cands, key=lambda f: int(
            np.minimum(cands[f], 256 - cands[f].astype(np.int16)).sum()))
        out.append(ft)
        out.extend(cands[ft].tobytes())
        prev = line
    return bytes(out)


def save_png16(path, arr16):
    """Write a bare 16-bit RGB PNG from scratch -- IHDR + IDAT + IEND only.

    Pillow cannot write 16-bit RGB PNGs, and every other encoder insists on
    stamping gAMA/cHRM/sRGB chunks that compete with cICP. Emitting the file
    directly is both simpler and safer.
    """
    h, w, _ = arr16.shape
    raw = np.ascontiguousarray(arr16.astype('>u2')).tobytes()
    raw = np.frombuffer(raw, np.uint8)
    idat = zlib.compress(_filter_scanlines(raw, 6, w, h), 9)
    ihdr = struct.pack('>IIBBBBB', w, h, 16, 2, 0, 0, 0)   # 16-bit, truecolour
    png = (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', ihdr)
           + _chunk(b'IDAT', idat) + _chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(png)
    return path


# --------------------------------------------------------------------------
# Writers
# --------------------------------------------------------------------------

def write_png_pq(path, scene_nits, stats=None):
    """16-bit PQ/BT.2020 PNG carrying cICP + cLLI + mDCV."""
    arr = scene_to_pq_rgb(scene_nits, bits=16, dither=False)   # 16-bit: no dither needed
    save_png16(path, arr)
    with open(path, 'rb') as f:
        png = f.read()
    y = k.luminance(scene_nits)
    chunks = [
        cicp_chunk(9, 16, 0, 1),
        mdcv_chunk(max_lum_nits=1000.0),
        clli_chunk(float(y.max()), float(y.mean())),
    ]
    with open(path, 'wb') as f:
        f.write(png_insert_chunks(png, chunks))
    return path


def write_avif_pq(path, scene_nits, quality=90, depth=10, speed=4):
    """BT.2020 + PQ AVIF via avifenc.

    --cicp 9/16/9 : primaries=BT.2020, transfer=ST2084(PQ), matrix=BT.2020-NCL
    -r full       : full-range signal
    We hand avifenc RGB that is *already* PQ-encoded; it does no colour
    management, it only tags and converts RGB->YCbCr with the given matrix.
    """
    tmp = str(path) + '.tmp16.png'
    arr = scene_to_pq_rgb(scene_nits, bits=16, dither=True)
    save_png16(tmp, arr)
    subprocess.run(
        ['avifenc', '--cicp', '9/16/9', '-r', 'full', '-d', str(depth),
         '-y', '444', '-q', str(quality), '-s', str(speed), tmp, str(path)],
        check=True, capture_output=True)
    subprocess.run(['rm', '-f', tmp], check=False)
    return path


def write_sdr(path_png, path_jpg, scene_nits, sdr_white=k.SDR_WHITE_NITS,
              knee=0.82):
    """A clean SDR rendition of the same scene.

    Not a naive clip: everything up to `knee` of SDR white passes through
    linearly, and the range above rolls off with a Reinhard shoulder, so the
    mark stays white and the bloom keeps its shape instead of flat-topping.
    """
    rel = np.clip(scene_nits / sdr_white, 0.0, None)
    out = np.where(rel <= knee, rel,
                   knee + (1.0 - knee) * (1.0 - np.exp(-(rel - knee) / (1.0 - knee))))
    srgb = k.linear_to_srgb(np.clip(out, 0.0, 1.0))
    arr8 = np.round(srgb * 255).astype(np.uint8)
    im = Image.fromarray(arr8, 'RGB')
    if path_png:
        im.save(path_png)
    if path_jpg:
        im.save(path_jpg, quality=95, subsampling=0, optimize=True)
    return arr8
