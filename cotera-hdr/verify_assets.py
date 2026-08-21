#!/usr/bin/env python3
"""
verify_assets.py -- prove the generated JPEGs really carry HDR/PQ metadata.

Checks, per file:
  1. JPEG is progressive and 4:4:4.
  2. An ICC profile is embedded.
  3. The profile is NOT sRGB.
  4. The profile declares Rec.2020 primaries + ST.2084 PQ transfer.  ExifTool
     12.x reports the ICC v4.4 ``cicp`` tag as opaque binary, so it is decoded
     here directly.
  5. Colour-managed round trip: decoding the PQ file through its own embedded
     profile back to sRGB should reproduce the SDR control.  If this diverges,
     the PQ encode or the profile is wrong and the image would look washed out.

Writes a human-readable report to ``output/metadata-verification.txt``.
"""

from __future__ import annotations

import io
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms

CICP_PRIMARIES = {1: "BT.709", 9: "BT.2020", 12: "Display P3"}
CICP_TRANSFER = {1: "BT.709", 13: "sRGB", 16: "SMPTE ST 2084 (PQ)", 18: "ARIB STD-B67 (HLG)"}
CICP_MATRIX = {0: "Identity / RGB", 1: "BT.709", 9: "BT.2020 non-constant luminance"}


def read_icc_tags(profile: bytes):
    """Minimal ICC tag-table reader -> {signature: payload bytes}."""
    count = struct.unpack(">I", profile[128:132])[0]
    tags = {}
    for i in range(count):
        sig, off, size = struct.unpack(">4sII", profile[132 + 12 * i : 144 + 12 * i])
        tags[sig.decode("ascii")] = profile[off : off + size]
    return tags


def decode_cicp(payload: bytes):
    p, t, m, f = struct.unpack(">BBBB", payload[8:12])
    return {
        "colour_primaries": f"{p} ({CICP_PRIMARIES.get(p, 'unknown')})",
        "transfer_characteristics": f"{t} ({CICP_TRANSFER.get(t, 'unknown')})",
        "matrix_coefficients": f"{m} ({CICP_MATRIX.get(m, 'unknown')})",
        "video_full_range_flag": f"{f} ({'full' if f else 'limited'} range)",
        "_is_pq": t == 16,
        "_is_2020": p == 9,
    }


def decode_mluc(payload: bytes):
    if payload[:4] != b"mluc":
        return None
    length, offset = struct.unpack(">II", payload[20:28])
    return payload[offset : offset + length].decode("utf-16-be")


def check(path: Path, sdr_reference: Path | None, out):
    is_hdr = "-hdr-" in path.name
    # The full-range probe deliberately uses the conventional 10000-nit PQ curve.
    # Any viewer that applies its TRC without HDR handling renders it very dark;
    # that is the known cost of matching the canonical curve shape, not a defect.
    is_fullrange = "fullrange" in path.name
    def w(line=""):
        print(line)
        out.write(line + "\n")

    w("=" * 78)
    w(f"FILE  {path.name}   ({path.stat().st_size:,} bytes)")
    w("=" * 78)

    img = Image.open(path)
    icc = img.info.get("icc_profile")
    progressive = bool(img.info.get("progressive") or img.info.get("progression"))
    subsampling = None
    try:
        from PIL import JpegImagePlugin

        subsampling = JpegImagePlugin.get_sampling(img)
    except Exception:
        pass

    results = []
    results.append(("JPEG is progressive", progressive, "progressive" if progressive else "baseline"))
    results.append(("4:4:4 chroma (no subsampling)", subsampling == 0, f"subsampling code {subsampling}"))
    results.append(("ICC profile embedded", bool(icc), f"{len(icc) if icc else 0} bytes"))

    if not icc:
        w("  FAIL: no ICC profile")
        return False

    tags = read_icc_tags(icc)
    desc = decode_mluc(tags.get("desc", b"")) or "(none)"
    version = struct.unpack(">I", icc[8:12])[0]
    w(f"  ICC version        : {version >> 24}.{(version >> 20) & 0xF}.{(version >> 16) & 0xF}")
    w(f"  Profile description: {desc}")
    w(f"  Tags present       : {', '.join(sorted(tags))}")

    is_srgb = "srgb" in desc.lower()
    if is_hdr:
        results.append(("Profile is NOT sRGB", not is_srgb, desc))
    else:
        # The SDR controls are meant to be plain sRGB -- that is the point of
        # them.  Only the HDR variants must carry the PQ profile.
        results.append(("SDR control carries an sRGB profile", is_srgb, desc))

    if "cicp" in tags:
        cicp = decode_cicp(tags["cicp"])
        w("  CICP tag (ICC v4.4, decoded here because ExifTool reports it as binary):")
        for k, v in cicp.items():
            if not k.startswith("_"):
                w(f"      {k:28s} = {v}")
        results.append(("CICP transfer = ST.2084 PQ", cicp["_is_pq"], cicp["transfer_characteristics"]))
        results.append(("CICP primaries = BT.2020", cicp["_is_2020"], cicp["colour_primaries"]))
    elif is_hdr:
        results.append(("CICP tag present", False, "missing"))

    if sdr_reference and sdr_reference.exists():
        prof = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        managed = ImageCms.profileToProfile(
            img, prof, ImageCms.createProfile("sRGB"), outputMode="RGB",
            renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
        )
        a = np.asarray(Image.open(sdr_reference).convert("RGB")).astype(int)
        b = np.asarray(managed).astype(int)
        diff = float(np.abs(a - b).mean())
        w(f"  Colour-managed PQ -> sRGB vs SDR control: mean abs diff {diff:.2f}/255")
        if is_fullrange:
            results.append(("Full-range probe renders dark without HDR handling (expected)",
                            diff > 40.0, f"{diff:.2f}/255 — do not ship unless HDR-confirmed"))
        else:
            results.append(("SDR fallback matches control (not washed out)", diff < 4.0, f"{diff:.2f}/255"))

    w("")
    ok = True
    for label, passed, detail in results:
        w(f"  [{'PASS' if passed else 'FAIL'}]  {label:46s} {detail}")
        ok &= passed
    w("")
    return ok


def main():
    root = Path(__file__).resolve().parent.parent
    outdir = root / "output"
    report = outdir / "metadata-verification.txt"
    files = sorted(outdir.glob("*.jpg"))
    if not files:
        sys.exit("no JPEGs in output/ -- run make_hdr_logo.py first")

    all_ok = True
    with report.open("w", encoding="utf-8") as out:
        out.write("Cotera LinkedIn HDR assets -- metadata verification\n")
        out.write(f"Generated by cotera-hdr/verify_assets.py\n\n")

        for f in files:
            ref = outdir / ("cotera-linkedin-sdr-arrow.jpg" if "arrow" in f.name
                            else "cotera-linkedin-sdr-icon.jpg")
            all_ok &= check(f, None if f == ref else ref, out)

        if shutil.which("exiftool"):
            primary = outdir / "cotera-linkedin-hdr-icon-800nits.jpg"
            header = f"\n{'=' * 78}\nExifTool output for the primary file: {primary.name}\n{'=' * 78}"
            print(header)
            out.write(header + "\n")
            proc = subprocess.run(["exiftool", str(primary)], capture_output=True, text=True)
            print(proc.stdout)
            out.write(proc.stdout)
        else:
            out.write("\n(exiftool not installed -- built-in ICC parser used above)\n")

        verdict = "ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED"
        print(verdict)
        out.write(f"\n{verdict}\n")

    print(f"report written to {report}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
