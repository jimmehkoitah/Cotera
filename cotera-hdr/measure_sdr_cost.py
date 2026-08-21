#!/usr/bin/env python3
"""
measure_sdr_cost.py -- what the HDR files look like to an SDR viewer.

Most people scrolling LinkedIn are on an SDR screen.  A browser that recognises
the PQ tagging does NOT ignore it there: it tone-maps the content down to the
display's (nonexistent) headroom, so the whole image renders darker and the
arrow stops being pure white.  That cost is invisible to a colour-management
round trip -- lcms applies the ICC TRC, which is a different code path from the
one Chrome actually takes -- so it has to be measured in a real browser.

Renders each file in headless Chromium (no HDR headroom, i.e. the SDR case) and
reports the background and arrow values against the sRGB control.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"

FILES = [
    ("cotera-linkedin-sdr-icon.jpg", "SDR control (sRGB)"),
    ("cotera-linkedin-hdr-icon-600nits.jpg", "HDR 600 nits"),
    ("cotera-linkedin-hdr-icon-800nits.jpg", "HDR 800 nits"),
    ("cotera-linkedin-hdr-icon-1200nits.jpg", "HDR 1200 nits"),
    ("cotera-linkedin-hdr-icon-800nits-fullrange.jpg", "HDR 800 full-range ICC"),
    ("cotera-linkedin-hdr-icon-800nits-cicp.png", "HDR 800 PNG cICP"),
]


async def render_all(size=400):
    from playwright.async_api import async_playwright

    exe = "/opt/pw-browsers/chromium"
    results = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
        page = await browser.new_page(viewport={"width": size, "height": size}, device_scale_factor=1)
        for fname, _ in FILES:
            await page.goto((OUT / fname).as_uri(), wait_until="load")
            await page.wait_for_timeout(250)
            shot = await page.screenshot(clip={"x": 0, "y": 0, "width": size, "height": size})
            import io

            results[fname] = np.asarray(Image.open(io.BytesIO(shot)).convert("RGB")).astype(int)
        await browser.close()
    return results


def main():
    shots = asyncio.run(render_all())
    ref = shots["cotera-linkedin-sdr-icon.jpg"]
    h, w, _ = ref.shape
    bg = (slice(6, 40), slice(6, 40))                       # top-left gradient corner
    arrow = (slice(h // 2 - 12, h // 2 + 12), slice(w // 2 - 12, w // 2 + 12))

    def sample(a, region):
        return a[region].reshape(-1, 3).mean(axis=0)

    ref_bg, ref_arrow = sample(ref, bg), sample(ref, arrow)
    print(f"{'file':<48}{'background':>22}{'arrow':>20}{'vs control':>14}")
    print("-" * 104)
    report = {}
    for fname, label in FILES:
        a = shots[fname]
        b, ar = sample(a, bg), sample(a, arrow)
        # Perceived lightness change of the background, as a percentage.
        drop = (1.0 - float(b.mean()) / float(ref_bg.mean())) * 100.0
        report[fname] = {
            "label": label,
            "background_rgb": [round(v, 1) for v in b],
            "arrow_rgb": [round(v, 1) for v in ar],
            "background_darker_pct": round(drop, 1),
            "arrow_is_pure_white": bool(ar.min() >= 254.0),
        }
        print(f"{label:<48}{str([round(v) for v in b]):>22}{str([round(v) for v in ar]):>20}"
              f"{('—' if drop < 0.5 else f'{drop:.0f}% darker'):>14}")

    (OUT / "sdr-cost-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nControl background {[round(v) for v in ref_bg]}, arrow {[round(v) for v in ref_arrow]}")
    print("Rendered in headless Chromium, which has no HDR headroom — i.e. the SDR-viewer case.")
    print(f"wrote {OUT / 'sdr-cost-report.json'}")


if __name__ == "__main__":
    main()
