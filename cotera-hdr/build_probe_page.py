#!/usr/bin/env python3
"""
build_probe_page.py -- assemble the self-contained in-browser HDR probe page.

Embeds the real generated files as data: URIs so that a viewer on an HDR-capable
browser and display sees the actual effect rather than a picture of it.  Writes
output/cotera-hdr-probe.html.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from icc_pq import pq_oetf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"

ASSETS = {
    "sdr": ("cotera-linkedin-sdr-icon.jpg", "image/jpeg"),
    "n600": ("cotera-linkedin-hdr-icon-600nits.jpg", "image/jpeg"),
    "n800": ("cotera-linkedin-hdr-icon-800nits.jpg", "image/jpeg"),
    "n1200": ("cotera-linkedin-hdr-icon-1200nits.jpg", "image/jpeg"),
    "full": ("cotera-linkedin-hdr-icon-800nits-fullrange.jpg", "image/jpeg"),
    "png": ("cotera-linkedin-hdr-icon-800nits-cicp.png", "image/png"),
    "arrowSdr": ("cotera-linkedin-sdr-arrow.jpg", "image/jpeg"),
    "arrowHdr": ("cotera-linkedin-hdr-arrow-800nits.jpg", "image/jpeg"),
    "simSdr": ("preview-panels/sim-sdr.jpg", "image/jpeg"),
    "sim800": ("preview-panels/sim-800nits.jpg", "image/jpeg"),
    "sim1200": ("preview-panels/sim-1200nits.jpg", "image/jpeg"),
}


def data_uri(rel, mime):
    raw = (OUT / rel).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}", len(raw)


def main():
    uris, sizes = {}, {}
    for key, (rel, mime) in ASSETS.items():
        uris[key], sizes[key] = data_uri(rel, mime)

    # Position the luminance ruler by PQ code: PQ is itself a perceptual scale,
    # so equal distance on this ruler is equal perceived step.
    def pct(nits):
        return round(float(pq_oetf(nits)) * 100.0, 2)

    marks = [
        (203, "SDR white", "reference"),
        (600, "600 nits", "tier"),
        (800, "800 nits", "tier"),
        (1000, "Chrome cap", "cap"),
        (1200, "1200 nits", "tier"),
    ]
    # The tiers cluster between 69% and 78%, so each mark gets its own row and
    # anything past the midpoint hangs its label to the left of the tick.
    ruler = "".join(
        f'<div class="tick {cls}" style="left:{pct(n)}%">'
        f'<span class="tick-l{" flip" if pct(n) > 55 else ""}" style="top:{8 + i * 19}px">'
        f'{label} · code {round(float(pq_oetf(n)) * 255)}</span></div>'
        for i, (n, label, cls) in enumerate(marks)
    )

    html = TEMPLATE
    for key, uri in uris.items():
        html = html.replace(f"__URI_{key.upper()}__", uri)
    html = html.replace("__RULER__", ruler)
    html = html.replace("__SIZES__", json.dumps({k: v for k, v in sizes.items()}))

    dest = OUT / "cotera-hdr-probe.html"
    dest.write_text(html, encoding="utf-8")
    kb = dest.stat().st_size / 1024
    print(f"wrote {dest}  ({kb:,.0f} KB)")
    assert "__URI_" not in html, "unsubstituted asset placeholder"
    assert "__RULER__" not in html
    print("all placeholders substituted")


TEMPLATE = r"""<title>Cotera HDR Probe</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>
/* This page is a luminance instrument. It commits to a single dark ground on
   purpose: you cannot judge highlight headroom against a bright page, and a
   bright surround raises eye adaptation and destroys the effect being measured.
   Every colour is therefore painted explicitly rather than inherited. */
:root{
  dynamic-range-limit: no-limit;   /* inherits — defends against a host setting `standard` */
  --ground:#0C0C13;
  --panel:#15151F;
  --panel-2:#1B1B27;
  --line:#282838;
  --line-soft:#1F1F2C;
  --ink:#ECECF6;
  --ink-mid:#A6A6BE;
  --ink-low:#74748C;
  --accent:#6366F2;
  --accent-dim:#4B4DC4;
  --ok:#3FD6A8;
  --warn:#F0A93B;
  --no:#E05A6B;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --sans:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--sans); font-size:15px; line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1080px; margin:0 auto; padding:48px 24px 96px}

/* ---------- masthead ---------- */
.mast{display:flex; flex-direction:column; gap:14px; padding-bottom:28px; border-bottom:1px solid var(--line)}
.kicker{font-family:var(--mono); font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--accent)}
h1{margin:0; font-size:clamp(30px,4.4vw,46px); line-height:1.08; font-weight:600; letter-spacing:-.02em; text-wrap:balance}
.dek{margin:0; max-width:62ch; color:var(--ink-mid); font-size:16px}

/* ---------- module scaffold ---------- */
section{margin-top:56px}
.head{display:flex; align-items:baseline; gap:14px; padding-bottom:10px; border-bottom:1px solid var(--line-soft); margin-bottom:22px}
.num{font-family:var(--mono); font-size:12px; color:var(--accent); font-weight:500}
h2{margin:0; font-size:20px; font-weight:600; letter-spacing:-.01em}
.head p{margin:0 0 0 auto; font-family:var(--mono); font-size:11px; color:var(--ink-low); letter-spacing:.04em}
p{margin:0 0 14px}
.note{color:var(--ink-mid); max-width:70ch}
strong{font-weight:600; color:var(--ink)}
code{font-family:var(--mono); font-size:.88em; background:var(--panel-2); padding:1px 5px; border-radius:3px; color:#C9C9E4}

/* ---------- readout ---------- */
.readout{display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:1px; background:var(--line); border:1px solid var(--line); border-radius:8px}
.cell{background:var(--panel); padding:16px 18px; display:flex; flex-direction:column; gap:6px}
.cell .k{font-family:var(--mono); font-size:10px; letter-spacing:.14em; text-transform:uppercase; color:var(--ink-low)}
.cell .v{font-family:var(--mono); font-size:17px; font-weight:500; color:var(--ink)}
.cell .v.ok{color:var(--ok)} .cell .v.warn{color:var(--warn)} .cell .v.no{color:var(--no)}
.verdict{margin-top:16px; padding:16px 18px; border-left:2px solid var(--accent); background:var(--panel); border-radius:0 6px 6px 0; color:var(--ink-mid)}
.verdict b{color:var(--ink)}

/* ---------- HDR-SAFE ZONE ------------------------------------------------
   Nothing on the ancestor chain of a test image may use filter, backdrop-filter,
   opacity<1, mix-blend-mode, transform, will-change, isolation, contain:paint,
   overflow:hidden or a CSS mask. Any of those force the subtree through an SDR
   intermediate buffer and silently clamp the arrow to paper white — which would
   make this whole page report a false negative. Keep this chain boring. */
.bench{display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:18px; align-items:start}
.slab{display:flex; flex-direction:column; gap:0; border:1px solid var(--line); border-radius:8px}
.slab img{display:block; width:100%; height:auto; border-radius:7px 7px 0 0}
.slab .cap{padding:11px 13px; font-family:var(--mono); font-size:11px; line-height:1.5; color:var(--ink-mid); border-top:1px solid var(--line)}
.slab .cap b{display:block; color:var(--ink); font-size:12px; margin-bottom:3px; font-weight:600}
.white-ref{background:#FFFFFF; aspect-ratio:1/1; border-radius:7px 7px 0 0; display:flex; align-items:center; justify-content:center; text-align:center; padding:20px}
.white-ref span{font-family:var(--mono); font-size:12px; color:#15151F; line-height:1.5}

.controls{display:flex; flex-wrap:wrap; gap:8px; margin-bottom:20px}
button{
  font-family:var(--mono); font-size:12px; letter-spacing:.03em;
  background:var(--panel); color:var(--ink-mid); border:1px solid var(--line);
  padding:8px 13px; border-radius:6px; cursor:pointer;
}
button:hover{border-color:var(--accent-dim); color:var(--ink)}
button[aria-pressed="true"]{background:var(--accent); border-color:var(--accent); color:#fff}
button:focus-visible{outline:2px solid var(--accent); outline-offset:2px}

/* ---------- luminance ruler ---------- */
.ruler{position:relative; height:150px; margin:26px 0 8px; border:1px solid var(--line); border-radius:8px; background:var(--panel)}
.ruler .bar{position:absolute; left:0; right:0; bottom:16px; height:8px; background:linear-gradient(90deg,#101019 0%,#2A2A46 45%,#6366F2 62%,#C9C9FF 82%,#FFFFFF 100%); border-radius:4px}
.tick{position:absolute; top:0; bottom:0; width:0; border-left:1px dashed var(--line)}
.tick .tick-l{position:absolute; left:7px; font-family:var(--mono); font-size:10.5px; letter-spacing:.04em; color:var(--ink-mid); white-space:nowrap}
.tick .tick-l.flip{left:auto; right:7px}
.tick.reference{border-left:2px solid var(--ok)} .tick.reference .tick-l{color:var(--ok)}
.tick.cap{border-left:1px solid var(--warn)} .tick.cap .tick-l{color:var(--warn)}
.tick.tier{border-left:1px solid var(--accent)} .tick.tier .tick-l{color:#A9AAF7}

/* ---------- LinkedIn mock ---------- */
.li-shell{border:1px solid var(--line); border-radius:8px; padding:22px; background:#F3F2EF}
.li-shell[data-mode="dark"]{background:#1B1F23}
.li-card{width:100%; max-width:552px; margin:0 auto; background:#FFFFFF; border-radius:8px; box-shadow:0 0 0 1px rgba(0,0,0,.08)}
.li-shell[data-mode="dark"] .li-card{background:#1D2226; box-shadow:0 0 0 1px hsla(0,0%,100%,.12)}
.li-head{display:flex; gap:8px; padding:12px 16px 0; align-items:flex-start}
.li-av{width:48px; height:48px; border-radius:50%; display:block}
.li-name{font-size:14px; line-height:20px; font-weight:600; color:rgba(0,0,0,.9)}
.li-sub{font-size:12px; line-height:16px; color:rgba(0,0,0,.6)}
.li-shell[data-mode="dark"] .li-name{color:hsla(0,0%,100%,.9)}
.li-shell[data-mode="dark"] .li-sub{color:hsla(0,0%,100%,.6)}
.li-body{padding:12px 16px; font-size:14px; line-height:20px; color:rgba(0,0,0,.9)}
.li-shell[data-mode="dark"] .li-body{color:hsla(0,0%,100%,.9)}
.li-media{display:block; width:100%; height:auto}
.li-rule{height:1px; margin:8px 16px 0; background:rgba(0,0,0,.08)}
.li-shell[data-mode="dark"] .li-rule{background:hsla(0,0%,100%,.12)}
.li-acts{display:flex; padding:6px 8px}
.li-act{flex:1; text-align:center; font-size:13px; font-weight:600; color:rgba(0,0,0,.6); padding:8px 0}
.li-shell[data-mode="dark"] .li-act{color:hsla(0,0%,100%,.6)}
.mock-tag{font-family:var(--mono); font-size:10px; letter-spacing:.1em; text-transform:uppercase; color:var(--ink-low); margin-bottom:10px}

/* ---------- matrix table ---------- */
.tablewrap{overflow-x:auto; border:1px solid var(--line); border-radius:8px}
table{width:100%; border-collapse:collapse; font-size:14px; min-width:620px}
th,td{text-align:left; padding:12px 16px; border-bottom:1px solid var(--line-soft); vertical-align:top}
th{font-family:var(--mono); font-size:10px; letter-spacing:.14em; text-transform:uppercase; color:var(--ink-low); font-weight:500; background:var(--panel-2)}
tr:last-child td{border-bottom:0}
td:first-child{font-family:var(--mono); font-size:12.5px; color:var(--ink)}
.pill{display:inline-block; font-family:var(--mono); font-size:10.5px; letter-spacing:.06em; padding:3px 8px; border-radius:99px; font-weight:500}
.pill.ok{background:rgba(63,214,168,.14); color:var(--ok)}
.pill.warn{background:rgba(240,169,59,.14); color:var(--warn)}
.pill.no{background:rgba(224,90,107,.14); color:var(--no)}

ol.proto{margin:0; padding-left:0; list-style:none; counter-reset:s}
ol.proto li{counter-increment:s; position:relative; padding:14px 0 14px 44px; border-bottom:1px solid var(--line-soft); color:var(--ink-mid)}
ol.proto li:last-child{border-bottom:0}
ol.proto li::before{content:counter(s,decimal-leading-zero); position:absolute; left:0; top:15px; font-family:var(--mono); font-size:11px; color:var(--accent)}
ol.proto b{color:var(--ink)}

.foot{margin-top:64px; padding-top:22px; border-top:1px solid var(--line); font-size:13px; color:var(--ink-low); max-width:74ch}
@media (prefers-reduced-motion:reduce){*{animation:none!important; transition:none!important}}
</style>

<div class="wrap">

  <header class="mast">
    <div class="kicker">Luminance probe · Cotera arrow</div>
    <h1>Does the arrow actually exceed white on this screen?</h1>
    <p class="dek">This page embeds the real generated files. On a browser and display that handle HDR
    stills, the arrow below is driven above SDR white — you are looking at the effect itself, not a
    picture of it. Everything here is measured or cited; where the answer is unproven it says so.</p>
  </header>

  <section>
    <div class="head"><span class="num">01</span><h2>Your display, right now</h2><p id="engine">detecting…</p></div>
    <div class="readout">
      <div class="cell"><span class="k">dynamic-range: high</span><span class="v" id="dr">—</span></div>
      <div class="cell"><span class="k">dynamic-range-limit</span><span class="v" id="drl">—</span></div>
      <div class="cell"><span class="k">Colour depth</span><span class="v" id="depth">—</span></div>
      <div class="cell"><span class="k">Likely engine</span><span class="v" id="eng">—</span></div>
    </div>
    <div class="verdict" id="verdict">Checking…</div>
    <p class="note" style="margin-top:14px"><strong>Capability is not activation.</strong> The media query reports
    what the display <em>can</em> do, not whether HDR is switched on right now. A MacBook in Low Power Mode,
    a monitor not in HDR mode, or a bright room can all report <code>high</code> and still show you nothing.
    The A/B toggle in module 02 is the only trustworthy proof.</p>
  </section>

  <section>
    <div class="head"><span class="num">02</span><h2>The test bench</h2><p>real embedded files</p></div>
    <p class="note">The middle slab is pure <code>#FFFFFF</code> — the brightest thing an SDR page can
    produce. If HDR is working, the arrow on the left out-glows it. If the two whites look identical,
    HDR is not reaching this image.</p>
    <div class="controls" role="group" aria-label="Choose the file under test">
      <button data-src="n800" aria-pressed="true">800 nits · JPEG PQ</button>
      <button data-src="n600" aria-pressed="false">600 nits</button>
      <button data-src="n1200" aria-pressed="false">1200 nits</button>
      <button data-src="full" aria-pressed="false">800 · full-range ICC</button>
      <button data-src="png" aria-pressed="false">800 · PNG cICP</button>
      <button data-src="arrowHdr" aria-pressed="false">arrow on black</button>
    </div>
    <div class="controls">
      <button id="ab" aria-pressed="false">Clamp to SDR (A/B test)</button>
      <span style="font-family:var(--mono); font-size:11px; color:var(--ink-low); align-self:center">
        toggles <code>dynamic-range-limit</code> on the test image only</span>
    </div>
    <div class="bench">
      <div class="slab">
        <img id="test" src="__URI_N800__" alt="Cotera icon, HDR PQ encoded" width="800" height="800">
        <div class="cap"><b id="testname">HDR · 800 nits · JPEG + PQ ICC</b><span id="testmeta">arrow encoded at PQ code 186</span></div>
      </div>
      <div class="slab">
        <div class="white-ref"><span>#FFFFFF<br>SDR maximum<br>— the thing to beat —</span></div>
        <div class="cap"><b>Reference white</b>Plain CSS white. Cannot exceed SDR.</div>
      </div>
      <div class="slab">
        <img src="__URI_SDR__" alt="Cotera icon, SDR control" width="800" height="800">
        <div class="cap"><b>SDR control · sRGB</b>Negative control. Must never glow.</div>
      </div>
    </div>
    <p class="note" style="margin-top:18px"><strong>Reading a negative result.</strong> If the
    <code>PNG cICP</code> variant glows but the JPEG does not, the JPEG's ICC route is what failed, not your
    display — PNG's <code>cICP</code> chunk is the documented HDR-still path, while "JPEG + PQ ICC profile"
    is undocumented on Apple's stack. If nothing glows, including the PNG, the display or browser is not
    delivering HDR at all.</p>
  </section>

  <section>
    <div class="head"><span class="num">03</span><h2>In a feed card</h2><p>mockup, not LinkedIn</p></div>
    <div class="controls" role="group" aria-label="Feed appearance">
      <button id="li-light" aria-pressed="true">Light</button>
      <button id="li-dark" aria-pressed="false">Dark</button>
    </div>
    <div class="mock-tag">Illustrative mockup — not a real LinkedIn page</div>
    <div class="li-shell" id="li-shell" data-mode="light">
      <article class="li-card">
        <div class="li-head">
          <img class="li-av" src="__URI_SDR__" alt="" width="48" height="48">
          <div>
            <div class="li-name">Cotera</div>
            <div class="li-sub">1,204 followers</div>
            <div class="li-sub">2h · Edited</div>
          </div>
        </div>
        <div class="li-body">Testing something.</div>
        <img class="li-media" id="li-media" src="__URI_N800__" alt="Cotera icon" width="800" height="800">
        <div class="li-rule"></div>
        <div class="li-acts"><span class="li-act">Like</span><span class="li-act">Comment</span><span class="li-act">Repost</span><span class="li-act">Send</span></div>
      </article>
    </div>
    <p class="note" style="margin-top:16px">Light mode is the harder test and the one that matters: the white
    card sits directly against the arrow, so any extra emission is unmissable. The image is full-bleed and
    uncropped at 552 px in LinkedIn's desktop feed column.</p>
  </section>

  <section>
    <div class="head"><span class="num">04</span><h2>If your screen is SDR</h2><p>simulated ratio</p></div>
    <p class="note">These panels cannot show the effect — no SDR image can go above white. They show the
    <em>ratio</em> instead, by scaling the whole scene down in linear light by 203 ÷ peak so the arrow lands
    at SDR maximum. Page white falls to sRGB 138 at 800 nits and 114 at 1200. On a real HDR display the page
    stays normally bright and only the arrow climbs.</p>
    <div class="bench">
      <div class="slab"><img src="__URI_SIMSDR__" alt="SDR control panel"><div class="cap"><b>SDR control</b>Arrow = card white = 203 nits.</div></div>
      <div class="slab"><img src="__URI_SIM800__" alt="800 nit ratio simulation"><div class="cap"><b>800 nits · simulated</b>Arrow at 3.9× card white.</div></div>
      <div class="slab"><img src="__URI_SIM1200__" alt="1200 nit ratio simulation"><div class="cap"><b>1200 nits · simulated</b>Arrow at 5.9× card white.</div></div>
    </div>
    <p class="note" style="margin-top:16px">The bloom is legitimate but exaggerated. A real highlight scatters
    in the eye — the effect Spencer et al. formalised in 1995 and Yoshida et al. measured at a 20–35 % perceived
    brightness gain — but an energy-preserving glare at physiological strength would lift adjacent page white
    from 138 only to about 141. The halo here is turned up to read at thumbnail size.</p>
  </section>

  <section>
    <div class="head"><span class="num">05</span><h2>What it costs everyone else</h2><p>measured in Chromium</p></div>
    <p class="note">This is the part that decides whether to ship. A browser that honours the PQ tagging does
    <em>not</em> ignore it on an SDR screen — it tone-maps the content down to the headroom that isn't there.
    Rendering every variant in headless Chromium (no HDR headroom, i.e. the ordinary viewer) gives:</p>
    <div class="tablewrap"><table>
      <thead><tr><th>File</th><th>Background</th><th>Arrow</th><th>vs control</th></tr></thead>
      <tbody>
        <tr><td>SDR control (sRGB)</td><td>99, 102, 243</td><td>255, 255, 255</td><td><span class="pill ok">reference</span></td></tr>
        <tr><td>HDR 600 nits</td><td>76, 78, 188</td><td>237, 237, 237</td><td><span class="pill warn">23% darker</span></td></tr>
        <tr><td>HDR 800 nits</td><td>76, 78, 188</td><td>247, 247, 247</td><td><span class="pill warn">23% darker</span></td></tr>
        <tr><td>HDR 1200 nits</td><td>76, 78, 188</td><td>255, 255, 255</td><td><span class="pill warn">23% darker</span></td></tr>
      </tbody>
    </table></div>
    <p class="note" style="margin-top:16px">Chrome maps the 203-nit reference white to <strong>191</strong>, not 255,
    because it holds back range for the highlight it now knows is in the file. So an SDR viewer sees a logo about
    a quarter dimmer than the plain sRGB version, and the darkening is identical across all three tiers — it is
    caused by the PQ tagging itself, not by how hard the arrow is pushed.</p>
    <p class="note"><strong>That is the trade.</strong> HDR-display viewers get the glow; everyone else gets a
    duller mark. A colour-managed non-HDR application (Photoshop, Preview) is unaffected and renders it correctly
    to within 1.43/255 — this darkening is specific to browsers that recognise the PQ signal.</p>
  </section>

  <section>
    <div class="head"><span class="num">06</span><h2>Where the tiers actually sit</h2><p>8-bit PQ code values</p></div>
    <div class="ruler"><div class="bar"></div>__RULER__</div>
    <p class="note">Positions are PQ code values, which is already a perceptual scale, so equal distance here is
    roughly equal perceived step. The uncomfortable part: <strong>600, 800 and 1200 nits are code 178, 186 and
    197</strong> — 19 code values apart in total. They encode cleanly (the flat arrow interior comes back
    byte-exact at quality 98), but after the browser tone-maps to whatever headroom your display currently has,
    do not expect to reliably tell the three apart. Chrome also assumes a 1000-nit ceiling for a JPEG with no
    mastering-luminance box, so the 1200-nit file is pushing past what it will render anyway.</p>
  </section>

  <section>
    <div class="head"><span class="num">07</span><h2>Where this works</h2><p>evidence, not hope</p></div>
    <div class="tablewrap"><table>
      <thead><tr><th>Environment</th><th>Result</th><th>Why</th></tr></thead>
      <tbody>
        <tr><td>Chrome / Edge ≥ 108, desktop, HDR display</td><td><span class="pill ok">works</span></td>
        <td>Chromium reads the ICC v4.4 <code>cicp</code> tag and <em>prefers</em> it over the profile's curves; our tuple (9, 16, 0, 1) is the accepted case, and Skia's PQ reference white is 203 nits — the same anchor we encoded to.</td></tr>
        <tr><td>Chrome on Android 14+, HDR panel</td><td><span class="pill warn">likely</span></td>
        <td>Same Blink code path, but untested here.</td></tr>
        <tr><td>Safari 26+ on macOS 26+</td><td><span class="pill warn">unproven</span></td>
        <td>WebKit asks ColorSync, and nothing in Apple's stack is documented to read the ICC <code>cicp</code> tag. Safari's announced no-gain-map HDR stills all signal PQ at the container level — PNG <code>cICP</code>, AVIF/HEIF/JXL CICP. JPEG is the one format on that list carrying a gain-map caveat. Test it; don't assume it.</td></tr>
        <tr><td>iPhone / iPad, any browser</td><td><span class="pill no">no</span></td>
        <td>Every iOS browser is WebKit underneath, so the Blink path that makes this work simply is not present.</td></tr>
        <tr><td>Firefox, any OS</td><td><span class="pill no">no</span></td>
        <td>No HDR still-image support at all.</td></tr>
        <tr><td>Screenshots, thumbnails, this page's preview card</td><td><span class="pill no">no</span></td>
        <td>Cannot carry HDR. Judge with your eyes on the live page.</td></tr>
      </tbody>
    </table></div>
    <p class="note" style="margin-top:16px"><strong>Before blaming the file:</strong> GPU acceleration must be on
    (software rendering kills HDR), macOS EDR headroom collapses toward nothing at high panel brightness — test
    around 50–75 % in a dim room — and Low Power Mode disables EDR outright. This page also runs inside a
    sandboxed iframe, which is its own wild card; if it fails here, open the file directly from
    <code>output/</code> before concluding anything.</p>
  </section>

  <section>
    <div class="head"><span class="num">08</span><h2>Then test LinkedIn</h2><p>a separate question</p></div>
    <p class="note">Success on this page proves the encoder and your display. It proves <em>nothing</em> about
    LinkedIn's upload pipeline, which re-encodes and may strip the profile.</p>
    <ol class="proto">
      <li><b>Post the SDR control first.</b> Establishes what normal looks like in your own feed on this device.</li>
      <li><b>Post the 800-nit JPEG.</b> The primary file. Compare it against the white post card beside it.</li>
      <li><b>Only then try 1200.</b> And only if 800 reads as too subtle on your display.</li>
      <li><b>Use your personal profile, never the company page.</b> If LinkedIn strips the profile, the PQ codes get read as sRGB and the logo renders as a washed-out grey-lilac square — the failure is ugly, not neutral. Post it, look, delete if wrong.</li>
      <li><b>If it doesn't glow, fetch what LinkedIn served.</b> Copy the posted image URL, download it, and run <code>exiftool</code> on it. Profile still there means the problem is display-side; profile gone or replaced with sRGB means LinkedIn stripped it and the trick is dead for that path.</li>
    </ol>
  </section>

  <p class="foot">Files generated by <code>cotera-hdr/make_hdr_logo.py</code> and verified by
  <code>cotera-hdr/verify_assets.py</code>. The arrow region is masked as the intersection of a geometric
  coverage mask and a photometric near-white test, so the purple gradient is never lifted: measured background
  peak stays at 202–210 nits against a 203-nit reference. This technique is not a supported LinkedIn feature
  and may stop working without notice.</p>
</div>

<script>
(function () {
  "use strict";
  var SIZES = __SIZES__;
  var SRC = {
    n600:  "__URI_N600__",
    n800:  "__URI_N800__",
    n1200: "__URI_N1200__",
    full:  "__URI_FULL__",
    png:   "__URI_PNG__",
    arrowHdr: "__URI_ARROWHDR__"
  };
  var META = {
    n600:  ["HDR · 600 nits · JPEG + PQ ICC", "arrow encoded at PQ code 178"],
    n800:  ["HDR · 800 nits · JPEG + PQ ICC", "arrow encoded at PQ code 186"],
    n1200: ["HDR · 1200 nits · JPEG + PQ ICC", "arrow encoded at PQ code 197 — above Chrome's assumed cap"],
    full:  ["HDR · 800 nits · full-range ICC", "canonical 10000-nit curve; renders dark if not HDR-handled"],
    png:   ["HDR · 800 nits · PNG cICP", "documented HDR-still path — the diagnostic control"],
    arrowHdr: ["HDR · 800 nits · arrow on black", "highest contrast, most sensitive test"]
  };

  function $(id) { return document.getElementById(id); }
  function safeMatch(q) {
    try {
      var m = window.matchMedia(q);
      return { supported: m.media !== "not all", matches: !!m.matches, mql: m };
    } catch (e) { return { supported: false, matches: false, mql: null }; }
  }

  // ---- module 01: capability readout ----
  var hi = safeMatch("(dynamic-range: high)");
  var drl = false;
  try { drl = !!(window.CSS && CSS.supports && CSS.supports("dynamic-range-limit", "no-limit")); } catch (e) {}

  var ua = navigator.userAgent || "";
  var engine = /Firefox\//.test(ua) ? "Gecko (Firefox)"
    : (/Edg\//.test(ua) ? "Blink (Edge)"
    : (/Chrome\/|Chromium\//.test(ua) ? "Blink (Chrome)"
    : (/Safari\//.test(ua) ? "WebKit (Safari)" : "unknown")));
  var isBlink = /Blink/.test(engine);
  var isWebKit = /WebKit/.test(engine);
  var iOS = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);

  function paint() {
    var el = $("dr");
    if (!hi.supported) { el.textContent = "unsupported"; el.className = "v warn"; }
    else if (hi.matches) { el.textContent = "yes"; el.className = "v ok"; }
    else { el.textContent = "no"; el.className = "v no"; }

    $("drl").textContent = drl ? "supported" : "not supported";
    $("drl").className = "v " + (drl ? "ok" : "warn");
    $("depth").textContent = (window.screen && screen.colorDepth ? screen.colorDepth + "-bit" : "unknown");
    $("eng").textContent = engine;
    $("engine").textContent = engine + (iOS ? " · iOS" : "");

    var v = $("verdict"), msg;
    if (iOS) {
      msg = "<b>Expect nothing here.</b> Every browser on iOS is WebKit underneath, and the code path that renders a PQ-tagged JPEG as HDR only exists in Blink. The PNG cICP variant in module 02 is your one long shot.";
    } else if (!hi.supported) {
      msg = "<b>This browser can't tell us.</b> It doesn't support the <code>dynamic-range</code> media query, which usually means it's old enough that HDR still images are out of reach too. Fall back to module 04.";
    } else if (!hi.matches) {
      msg = "<b>This display reports standard dynamic range.</b> There is no headroom above white here, so the arrow will look identical to the SDR control — correctly so. Module 04 shows the ratio instead; module 05 shows what you would be shipping to everyone.";
    } else if (isBlink) {
      msg = "<b>Best case.</b> A Blink browser reporting a high-dynamic-range display is the combination with direct source evidence behind it. If the arrow doesn't out-glow the white slab in module 02, check GPU acceleration and screen brightness before blaming the file.";
    } else if (isWebKit) {
      msg = "<b>Unproven combination.</b> Your display has headroom, but Safari's HDR path for JPEG is documented as gain-map-only. Try the <code>PNG cICP</code> variant in module 02 — if that glows and the JPEG doesn't, the JPEG's ICC route is the thing that failed.";
    } else {
      msg = "<b>Display has headroom.</b> Whether this engine delivers HDR to a still image is untested — use the A/B toggle in module 02 to find out.";
    }
    v.innerHTML = msg;
  }
  paint();
  if (hi.mql && hi.mql.addEventListener) {
    hi.mql.addEventListener("change", function (e) { hi.matches = e.matches; paint(); });
  }

  // ---- module 02: file switcher + A/B clamp ----
  var img = $("test"), name = $("testname"), meta = $("testmeta");
  var buttons = document.querySelectorAll("[data-src]");
  Array.prototype.forEach.call(buttons, function (b) {
    b.addEventListener("click", function () {
      Array.prototype.forEach.call(buttons, function (o) { o.setAttribute("aria-pressed", "false"); });
      b.setAttribute("aria-pressed", "true");
      var k = b.getAttribute("data-src");
      img.src = SRC[k];
      name.textContent = META[k][0];
      var kb = SIZES[k] ? " · " + Math.round(SIZES[k] / 1024) + " KB" : "";
      meta.textContent = META[k][1] + kb;
    });
  });

  var ab = $("ab"), clamped = false;
  ab.addEventListener("click", function () {
    clamped = !clamped;
    ab.setAttribute("aria-pressed", String(clamped));
    ab.textContent = clamped ? "Release to HDR" : "Clamp to SDR (A/B test)";
    try { img.style.setProperty("dynamic-range-limit", clamped ? "standard" : "no-limit"); } catch (e) {}
    if (!drl) {
      meta.textContent = "dynamic-range-limit unsupported here — this toggle does nothing";
    }
  });

  // ---- module 03: feed appearance ----
  var shell = $("li-shell"), lt = $("li-light"), dk = $("li-dark");
  function mode(m) {
    shell.setAttribute("data-mode", m);
    lt.setAttribute("aria-pressed", String(m === "light"));
    dk.setAttribute("aria-pressed", String(m === "dark"));
  }
  lt.addEventListener("click", function () { mode("light"); });
  dk.addEventListener("click", function () { mode("dark"); });
})();
</script>
"""


if __name__ == "__main__":
    main()
