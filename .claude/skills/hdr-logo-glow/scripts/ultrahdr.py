"""
ultrahdr -- build a gain-map HDR JPEG (Google Ultra HDR / ISO 21496-1 style).

Why this format matters more than PQ for a social feed: a PQ image is an
*absolute* instruction ("emit 800 cd/m^2 here"). Anything that does not
understand it -- an SDR display, a lazy decoder, a thumbnailer -- shows a
washed-out mess. A gain-map file is an ordinary SDR JPEG that *also* carries a
recipe for brightening. Ignore the recipe and you still get a correct picture.

File layout produced here:

    SOI
    APP0  JFIF                      (from the JPEG encoder)
    APP1  XMP  -- GContainer directory naming the two images
    APP2  MPF  -- CIPA DC-007 multi-picture index (offsets/sizes)
    ...primary SDR JPEG entropy data... EOI
    ...gain map JPEG, APP1 XMP with hdrgm: metadata... EOI

The gain map itself is, per pixel:

    encoded = ( (log2((Yhdr+offHDR)/(Ysdr+offSDR)) - MIN) / (MAX-MIN) ) ^ (1/gamma)

and a display with log2 headroom H reconstructs:

    w    = clamp((H - CapacityMin)/(CapacityMax - CapacityMin), 0, 1)
    Yhdr = (Ysdr + offSDR) * 2^( (encoded^gamma * (MAX-MIN) + MIN) * w ) - offHDR

so a phone with only 2x headroom gets a proportionate share of the effect
rather than all or nothing.
"""

import io
import struct
import numpy as np
from PIL import Image

XMP_SIG = b'http://ns.adobe.com/xap/1.0/\x00'
MPF_SIG = b'MPF\x00'

# CIPA DC-007 MP entry attribute bits, as used by libultrahdr
MP_TYPE_PRIMARY = 0x00030000
MP_FORMAT_JPEG = 0x00000000


# --------------------------------------------------------------------------
# Gain map computation
# --------------------------------------------------------------------------

def compute_gainmap(hdr_nits, sdr_nits, offset_sdr=1.0 / 64, offset_hdr=1.0 / 64,
                    gamma=1.0, sdr_white=203.0):
    """Return (encoded gain map uint8, metadata dict).

    Both inputs are linear BT.709 nits. They are normalised against SDR white
    first, so the maths is in the same 'relative to diffuse white' units the
    spec assumes.
    """
    hdr = np.clip(np.asarray(hdr_nits, np.float64) / sdr_white, 0, None)
    sdr = np.clip(np.asarray(sdr_nits, np.float64) / sdr_white, 0, None)

    # Single-channel gain map: use luminance-ish max across channels so no
    # channel is ever under-boosted.
    ratio = (hdr.max(axis=2) + offset_hdr) / (sdr.max(axis=2) + offset_sdr)
    log_gain = np.log2(np.clip(ratio, 1e-8, None))

    gmin = float(log_gain.min())
    gmax = float(log_gain.max())
    if gmax - gmin < 1e-6:
        gmax = gmin + 1e-6

    norm = (log_gain - gmin) / (gmax - gmin)
    encoded = np.clip(norm, 0, 1) ** (1.0 / gamma)
    arr = np.round(encoded * 255).astype(np.uint8)

    meta = dict(
        version='1.0',
        gain_map_min=gmin,
        gain_map_max=gmax,
        gamma=gamma,
        offset_sdr=offset_sdr,
        offset_hdr=offset_hdr,
        hdr_capacity_min=0.0,
        hdr_capacity_max=max(gmax, 0.0),
        base_rendition_is_hdr=False,
    )
    return arr, meta


def reconstruct(sdr_nits, gain_u8, meta, headroom_stops, sdr_white=203.0):
    """Decoder-side reconstruction -- used to prove the file is self-consistent
    and to render honest previews at a given display headroom."""
    sdr = np.asarray(sdr_nits, np.float64) / sdr_white
    enc = np.asarray(gain_u8, np.float64) / 255.0
    m = meta
    span = m['hdr_capacity_max'] - m['hdr_capacity_min']
    w = 0.0 if span <= 0 else np.clip(
        (headroom_stops - m['hdr_capacity_min']) / span, 0.0, 1.0)
    log_rec = (enc ** m['gamma']) * (m['gain_map_max'] - m['gain_map_min']) + m['gain_map_min']
    gain = 2.0 ** (log_rec * w)
    out = (sdr + m['offset_sdr']) * gain[..., None] - m['offset_hdr']
    return np.clip(out, 0, None) * sdr_white


# --------------------------------------------------------------------------
# XMP payloads
# --------------------------------------------------------------------------

def _primary_xmp(gainmap_len):
    return (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about=""'
        ' xmlns:Container="http://ns.google.com/photos/1.0/container/"'
        ' xmlns:Item="http://ns.google.com/photos/1.0/container/item/"'
        ' xmlns:hdrgm="http://ns.adobe.com/hdr-gain-map/1.0/"'
        ' hdrgm:Version="1.0">'
        '<Container:Directory>'
        '<rdf:Seq>'
        '<rdf:li rdf:parseType="Resource">'
        '<Container:Item Item:Semantic="Primary" Item:Mime="image/jpeg"/>'
        '</rdf:li>'
        '<rdf:li rdf:parseType="Resource">'
        f'<Container:Item Item:Semantic="GainMap" Item:Mime="image/jpeg" Item:Length="{gainmap_len}"/>'
        '</rdf:li>'
        '</rdf:Seq>'
        '</Container:Directory>'
        '</rdf:Description>'
        '</rdf:RDF>'
        '</x:xmpmeta>'
        '<?xpacket end="w"?>'
    ).encode('utf-8')


def _gainmap_xmp(m):
    def f(x):
        return repr(round(float(x), 6))
    return (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about=""'
        ' xmlns:hdrgm="http://ns.adobe.com/hdr-gain-map/1.0/"'
        ' hdrgm:Version="1.0"'
        f' hdrgm:GainMapMin="{f(m["gain_map_min"])}"'
        f' hdrgm:GainMapMax="{f(m["gain_map_max"])}"'
        f' hdrgm:Gamma="{f(m["gamma"])}"'
        f' hdrgm:OffsetSDR="{f(m["offset_sdr"])}"'
        f' hdrgm:OffsetHDR="{f(m["offset_hdr"])}"'
        f' hdrgm:HDRCapacityMin="{f(m["hdr_capacity_min"])}"'
        f' hdrgm:HDRCapacityMax="{f(m["hdr_capacity_max"])}"'
        ' hdrgm:BaseRenditionIsHDR="False"/>'
        '</rdf:RDF>'
        '</x:xmpmeta>'
        '<?xpacket end="w"?>'
    ).encode('utf-8')


# --------------------------------------------------------------------------
# JPEG segment plumbing
# --------------------------------------------------------------------------

def _app_segment(marker_byte, payload):
    seg = XMP_SIG + payload if marker_byte == 0xE1 else payload
    if len(seg) + 2 > 0xFFFF:
        raise ValueError('APP segment too large')
    return bytes([0xFF, marker_byte]) + struct.pack('>H', len(seg) + 2) + seg


def _insert_after_headers(jpeg, segments):
    """Insert APP segments after SOI (and after an existing APP0/JFIF)."""
    assert jpeg[:2] == b'\xff\xd8', 'not a JPEG'
    pos = 2
    while jpeg[pos:pos + 2] in (b'\xff\xe0',):          # skip JFIF APP0
        ln = struct.unpack('>H', jpeg[pos + 2:pos + 4])[0]
        pos += 2 + ln
    return jpeg[:pos] + b''.join(segments) + jpeg[pos:]


def _mpf_segment(primary_size, secondary_size, secondary_offset):
    """CIPA DC-007 MP Index IFD for a 2-image file, big-endian."""
    body = b'MM' + struct.pack('>H', 42) + struct.pack('>I', 8)   # TIFF header
    entries = [
        (0xB000, 7, 4, b'0100'),                                   # MPFVersion
        (0xB001, 4, 1, struct.pack('>I', 2)),                      # NumberOfImages
        (0xB002, 7, 32, None),                                     # MPEntry -> offset
    ]
    ifd_start = 8
    ifd_len = 2 + 12 * len(entries) + 4
    mpentry_off = ifd_start + ifd_len

    ifd = struct.pack('>H', len(entries))
    for tag, typ, count, val in entries:
        if val is None:
            ifd += struct.pack('>HHII', tag, typ, count, mpentry_off)
        elif len(val) <= 4:
            ifd += struct.pack('>HHI', tag, typ, count) + val.ljust(4, b'\x00')
        else:
            raise ValueError('inline value too large')
    ifd += struct.pack('>I', 0)                                    # no next IFD

    mpentries = (
        struct.pack('>IIIHH', MP_TYPE_PRIMARY | MP_FORMAT_JPEG, primary_size, 0, 0, 0)
        + struct.pack('>IIIHH', MP_FORMAT_JPEG, secondary_size, secondary_offset, 0, 0)
    )
    return _app_segment(0xE2, MPF_SIG + body + ifd + mpentries)


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def build(path, sdr_rgb_u8, gain_u8, meta, base_quality=92, gain_quality=94):
    """Write a complete Ultra HDR JPEG."""
    # 1. gain map image, carrying the hdrgm metadata
    buf = io.BytesIO()
    Image.fromarray(gain_u8, 'L').save(buf, 'JPEG', quality=gain_quality, optimize=True)
    gainmap = _insert_after_headers(buf.getvalue(),
                                    [_app_segment(0xE1, _gainmap_xmp(meta))])

    # 2. primary SDR image
    buf = io.BytesIO()
    Image.fromarray(sdr_rgb_u8, 'RGB').save(buf, 'JPEG', quality=base_quality,
                                            subsampling=0, optimize=True)
    base = buf.getvalue()

    # 3. splice in XMP + a placeholder MPF, then patch the offsets once the
    #    final primary size is known (the segment length never changes, so a
    #    single pass is enough).
    xmp_seg = _app_segment(0xE1, _primary_xmp(len(gainmap)))
    mpf_seg = _mpf_segment(0, 0, 0)
    primary = _insert_after_headers(base, [xmp_seg, mpf_seg])

    mpf_pos = primary.find(b'\xff\xe2' + struct.pack('>H', len(mpf_seg) - 2) + MPF_SIG)
    if mpf_pos < 0:
        raise RuntimeError('MPF segment not found after insertion')
    endian_off = mpf_pos + 4 + len(MPF_SIG)          # start of the 'MM' TIFF header

    real_mpf = _mpf_segment(len(primary), len(gainmap), len(primary) - endian_off)
    assert len(real_mpf) == len(mpf_seg), 'MPF length drifted'
    primary = primary[:mpf_pos] + real_mpf + primary[mpf_pos + len(mpf_seg):]

    with open(path, 'wb') as f:
        f.write(primary + gainmap)
    return dict(path=str(path), primary_bytes=len(primary),
                gainmap_bytes=len(gainmap), total=len(primary) + len(gainmap),
                mpf_endian_offset=endian_off, secondary_offset=len(primary) - endian_off)
