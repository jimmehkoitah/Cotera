"""
validate -- prove a produced file is genuinely HDR, without an HDR display.

Everything here parses the actual bytes rather than trusting the encoder.
"""

import struct
import subprocess
import sys


def _jpeg_segments(data):
    pos = 2
    while pos < len(data) - 1:
        if data[pos] != 0xFF:
            break
        marker = data[pos + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        ln = struct.unpack('>H', data[pos + 2:pos + 4])[0]
        yield pos, marker, data[pos + 4:pos + 2 + ln]
        if marker == 0xDA:                       # start of scan: entropy data follows
            break
        pos += 2 + ln


def check_ultrahdr(path):
    data = open(path, 'rb').read()
    out = {'file': path, 'bytes': len(data), 'ok': True, 'checks': []}

    def note(ok, msg):
        out['checks'].append(('PASS' if ok else 'FAIL', msg))
        if not ok:
            out['ok'] = False

    note(data[:2] == b'\xff\xd8', 'starts with JPEG SOI')

    xmp = mpf = None
    mpf_pos = None
    for pos, marker, payload in _jpeg_segments(data):
        if marker == 0xE1 and payload.startswith(b'http://ns.adobe.com/xap/1.0/\x00'):
            xmp = payload[29:]
        if marker == 0xE2 and payload.startswith(b'MPF\x00'):
            mpf, mpf_pos = payload[4:], pos + 4 + 4

    note(xmp is not None, 'primary image carries an APP1 XMP packet')
    if xmp:
        s = xmp.decode('utf-8', 'replace')
        note('Item:Semantic="Primary"' in s, 'XMP GContainer declares a Primary item')
        note('Item:Semantic="GainMap"' in s, 'XMP GContainer declares a GainMap item')
        note('hdr-gain-map/1.0' in s, 'XMP declares the hdrgm namespace')

    note(mpf is not None, 'primary image carries an APP2 MPF segment')
    if mpf:
        endian = mpf[:2]
        note(endian in (b'MM', b'II'), 'MPF TIFF header byte order is valid')
        be = '>' if endian == b'MM' else '<'
        magic, ifd_off = struct.unpack(be + 'HI', mpf[2:8])
        note(magic == 42, 'MPF TIFF magic is 42')
        n = struct.unpack(be + 'H', mpf[ifd_off:ifd_off + 2])[0]
        tags = {}
        for i in range(n):
            o = ifd_off + 2 + 12 * i
            tag, typ, cnt = struct.unpack(be + 'HHI', mpf[o:o + 8])
            tags[tag] = (typ, cnt, mpf[o + 8:o + 12])
        note(0xB000 in tags, 'MPF has MPFVersion (0xB000)')
        note(0xB001 in tags, 'MPF has NumberOfImages (0xB001)')
        note(0xB002 in tags, 'MPF has MPEntry (0xB002)')
        if 0xB001 in tags:
            num = struct.unpack(be + 'I', tags[0xB001][2])[0]
            note(num == 2, f'MPF NumberOfImages == 2 (got {num})')
        if 0xB002 in tags:
            eoff = struct.unpack(be + 'I', tags[0xB002][2])[0]
            entries = []
            for i in range(2):
                o = eoff + 16 * i
                attr, size, off, d1, d2 = struct.unpack(be + 'IIIHH', mpf[o:o + 16])
                entries.append((attr, size, off))
            out['mp_entries'] = entries
            note(entries[0][2] == 0, 'MPF primary image offset is 0, per spec')
            note(entries[0][1] > 0, 'MPF primary image size is set')
            # the decisive check: does the secondary offset land on a JPEG SOI?
            abs_off = mpf_pos + entries[1][2]
            out['secondary_abs_offset'] = abs_off
            note(data[abs_off:abs_off + 2] == b'\xff\xd8',
                 f'MPF secondary offset {abs_off} lands exactly on a JPEG SOI')
            note(abs_off + entries[1][1] == len(data),
                 'MPF secondary offset + size == end of file')
            note(entries[0][1] == abs_off,
                 'MPF primary size == start of the gain map')

            # gain map metadata
            gm = data[abs_off:]
            gxmp = None
            for pos, marker, payload in _jpeg_segments(gm):
                if marker == 0xE1 and payload.startswith(b'http://ns.adobe.com/xap/1.0/\x00'):
                    gxmp = payload[29:].decode('utf-8', 'replace')
            note(gxmp is not None, 'gain map image carries its own APP1 XMP')
            if gxmp:
                for field in ('GainMapMin', 'GainMapMax', 'Gamma', 'OffsetSDR',
                              'OffsetHDR', 'HDRCapacityMin', 'HDRCapacityMax',
                              'BaseRenditionIsHDR'):
                    note(f'hdrgm:{field}' in gxmp, f'gain map XMP has hdrgm:{field}')
    return out


def check_png_cicp(path):
    import zlib
    data = open(path, 'rb').read()
    out = {'file': path, 'bytes': len(data), 'ok': True, 'checks': []}

    def note(ok, msg):
        out['checks'].append(('PASS' if ok else 'FAIL', msg))
        if not ok:
            out['ok'] = False

    note(data[:8] == b'\x89PNG\r\n\x1a\n', 'PNG signature')
    pos, order, chunks = 8, [], {}
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        crc = struct.unpack('>I', data[pos + 8 + ln:pos + 12 + ln])[0]
        note(crc == (zlib.crc32(ctype + body) & 0xFFFFFFFF),
             f'{ctype.decode()} chunk CRC is valid')
        order.append(ctype)
        chunks[ctype] = body
        pos += 12 + ln
    out['chunk_order'] = [c.decode() for c in order]

    note(b'cICP' in chunks, 'cICP chunk present')
    if b'cICP' in chunks:
        p, t, m, r = chunks[b'cICP']
        out['cicp'] = dict(primaries=p, transfer=t, matrix=m, full_range=r)
        note(p == 9, f'colour_primaries == 9 (BT.2020), got {p}')
        note(t in (16, 18), f'transfer == 16 (PQ) or 18 (HLG), got {t}')
        note(m == 0, f'matrix_coefficients == 0 (required for PNG), got {m}')
        note(r == 1, f'video_full_range_flag == 1, got {r}')
        note(order.index(b'cICP') < order.index(b'IDAT'), 'cICP precedes IDAT')
    for competing in (b'iCCP', b'sRGB', b'gAMA', b'cHRM'):
        note(competing not in chunks,
             f'no {competing.decode()} chunk competing with cICP')
    ihdr = chunks[b'IHDR']
    w, h, depth, ctype_ = struct.unpack('>IIBB', ihdr[:10])
    out['image'] = dict(width=w, height=h, bit_depth=depth, colour_type=ctype_)
    note(depth == 16, f'bit depth 16 (got {depth})')
    return out


def check_avif(path):
    out = {'file': path, 'ok': True, 'checks': []}
    r = subprocess.run(['avifdec', '--info', path], capture_output=True, text=True)
    txt = r.stdout + r.stderr
    out['raw'] = txt

    def grab(label):
        for line in txt.splitlines():
            if label in line:
                return line.split(':', 1)[1].strip()
        return None

    def note(ok, msg):
        out['checks'].append(('PASS' if ok else 'FAIL', msg))
        if not ok:
            out['ok'] = False

    note(grab('Color Primaries') == '9', f"colour primaries 9 (got {grab('Color Primaries')})")
    note(grab('Transfer Char.') in ('16', '18'), f"transfer {grab('Transfer Char.')}")
    note(grab('Range') == 'Full', f"full range (got {grab('Range')})")
    note(grab('ICC Profile') == 'Absent', 'no ICC profile overriding the nclx box')
    note(grab('Bit Depth') in ('10', '12'), f"bit depth {grab('Bit Depth')}")
    return out


def report(res):
    print(f"\n=== {res['file']} ===")
    for k_, v in res.items():
        if k_ not in ('checks', 'raw', 'file'):
            print(f'  {k_}: {v}')
    for status, msg in res['checks']:
        print(f'  [{status}] {msg}')
    print(f"  ==> {'ALL CHECKS PASSED' if res['ok'] else 'FAILURES PRESENT'}")
    return res['ok']


def classify(path):
    """What kind of file is this, actually? Decided from the bytes, not the
    extension -- an SDR control file must not be reported as a broken HDR one."""
    data = open(path, 'rb').read(1 << 16)
    if data[:2] == b'\xff\xd8':
        return 'ultrahdr' if b'MPF\x00' in data else 'sdr-jpeg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png-cicp' if b'cICP' in data else 'sdr-png'
    if data[4:12] == b'ftypavif' or b'ftypavif' in data[:64]:
        return 'avif'
    return 'unknown'


def main(paths):
    ok = True
    for p in paths:
        kind = classify(p)
        if kind == 'ultrahdr':
            ok &= report(check_ultrahdr(p))
        elif kind == 'png-cicp':
            ok &= report(check_png_cicp(p))
        elif kind == 'avif':
            ok &= report(check_avif(p))
        elif kind in ('sdr-jpeg', 'sdr-png'):
            print(f'\n=== {p} ===')
            print(f'  ==> SDR control file ({kind}) — carries no HDR tagging, as intended')
        else:
            print(f'\n=== {p} ===')
            print('  ==> UNRECOGNISED file type')
            ok = False
    return ok


if __name__ == '__main__':
    sys.exit(0 if main(sys.argv[1:]) else 1)
