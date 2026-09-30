"""Build the SVG artwork for the AnastasiyaW GitHub profile README.

Everything here quotes happyin.work. Colours and type come from the site's
pages/_assets/UI-KIT-REFERENCE.md, shapes from page-shell.jsx: the pixel
starfield (CosmosBG), the striped Mac title bar, the Win 3.1 windows with a
3px accent strip and a hard black shadow, the `$` prompts, the menu bar and
the taskbar. Copy is the site's own (pages-data.jsx, site-data.js); the
repository numbers are read from the GitHub API on every build.

Type ships as outlines: GitHub serves README images through camo as <img>,
and an <img> SVG cannot load webfonts. Artwork is drawn at 900px, the width
of GitHub's README column, so it renders close to 1:1.

    python tools/fetch_fonts.py
    uv run --no-project --with fonttools --with uharfbuzz python tools/build.py
"""

import json
import os
import random
import re
import sys
import urllib.request
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from typeset import glyph_defs, typeset, width  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "assets")
USER = "AnastasiyaW"

# UI-KIT-REFERENCE.md colour tokens, plus the literals page-shell.jsx uses
VOID, PANEL, RULE, DASH = "#0a0907", "#14130f", "#2a2720", "#3a362d"
IVORY, WARM, MUTED, CAPTION = "#e8e4d4", "#c4baa3", "#a99c82", "#6b6558"
PHOSPHOR, GRASS = "#ff5b1f", "#6b9b5a"
WIN_BLUE, WIN_GREEN, WIN_PURPLE, WIN_RUST = "#0000aa", "#008000", "#800080", "#aa5500"
TITLE_BG, HILITE, LOG_GREEN = "#e8e8e8", "#ffff00", "#008800"

W = 900


def n(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def rect(x, y, w, h, fill, extra=""):
    return f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" fill="{fill}"{extra}/>'


# --------------------------------------------------------------------------
# Text: plain lines, styled runs, and word wrap over styled runs
# --------------------------------------------------------------------------

def style(face, fill, **kw):
    return dict(face=face, fill=fill, **kw)


def text(face, s, size, x, y, fill, tracking=0.0, anchor="start"):
    if anchor != "start":
        w = width(face, s, size, tracking)
        x -= w if anchor == "end" else w / 2
    return typeset(face, s, size, x, y, tracking, f' fill="{fill}"')[0]


def runs(parts, size, x, y):
    """Lay styled runs out on one baseline; return (markup, advance)."""
    merged = []
    for s, st in parts:
        if merged and merged[-1][1] is st:
            merged[-1] = (merged[-1][0] + s, st)
        else:
            merged.append((s, st))
    back, front, cx = [], [], x
    for s, st in merged:
        tr = st.get("tracking", 0.0)
        markup, w = typeset(st["face"], s, size, cx, y, tr, f' fill="{st["fill"]}"')
        if st.get("hilite"):
            back.append(rect(cx - 3, y - size * 0.8, w + 6, size * 1.05, st["hilite"]))
        front.append(markup)
        if st.get("underline"):
            front.append(rect(cx, y + size * 0.16, w, max(size * 0.07, 0.8), st["fill"]))
        cx += w + tr * size
    return "".join(back + front), cx - x


def wrap(parts, size, maxw):
    """Greedy word wrap over styled runs; returns a list of run lists."""
    words, cur = [], []
    for s, st in parts:
        for piece in re.split(r"( )", s):
            if piece == " ":
                words.append((cur, (" ", st)))
                cur = []
            elif piece:
                cur.append((piece, st))
    if cur:
        words.append((cur, None))

    lines, line, lw = [], [], 0.0
    for toks, space in words:
        ww = sum(width(st["face"], s, size, st.get("tracking", 0.0)) for s, st in toks)
        if line and lw + ww > maxw:
            if line[-1][0] == " ":
                line.pop()
            lines.append(line)
            line, lw = [], 0.0
        line.extend(toks)
        lw += ww
        if space:
            line.append(space)
            lw += width(space[1]["face"], " ", size)
    if line:
        if line[-1][0] == " ":
            line.pop()
        lines.append(line)
    return lines


def paragraph(parts, size, x, y, maxw, lead):
    """Wrapped styled runs, first baseline at y; returns (markup, next_y)."""
    out = []
    for line in wrap(parts, size, maxw):
        out.append(runs(line, size, x, y)[0])
        y += lead
    return "".join(out), y


def ellipsize(face, s, size, maxw, tracking=0.0):
    if width(face, s, size, tracking) <= maxw:
        return s
    while s and width(face, s + "…", size, tracking) > maxw:
        s = s[:-1].rstrip()
    return s + "…"


# --------------------------------------------------------------------------
# Glyphs JetBrains Mono lacks (the site gets them from a system font):
# drawn as shapes rather than hoping a fallback exists inside an <img>
# --------------------------------------------------------------------------

def sparkle(cx, cy, r, fill):
    k = r * 0.22
    d = (f"M{n(cx)} {n(cy - r)}Q{n(cx + k)} {n(cy - k)} {n(cx + r)} {n(cy)}"
         f"Q{n(cx + k)} {n(cy + k)} {n(cx)} {n(cy + r)}Q{n(cx - k)} {n(cy + k)} {n(cx - r)} {n(cy)}"
         f"Q{n(cx - k)} {n(cy - k)} {n(cx)} {n(cy - r)}Z")
    return f'<path d="{d}" fill="{fill}"/>'


def star(cx, cy, r, fill):
    import math
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append(f"{n(cx + rr * math.cos(a))},{n(cy + rr * math.sin(a))}")
    return f'<polygon points="{" ".join(pts)}" fill="{fill}"/>'


# --------------------------------------------------------------------------
# Site chrome: starfield, Mac title bar, Win 3.1 window
# --------------------------------------------------------------------------

class Svg:
    def __init__(self, w, h, label):
        self.w, self.h, self.label = w, h, label
        self.defs, self.parts = {}, []

    def define(self, key, markup):
        self.defs.setdefault(key, markup)

    def add(self, *markup):
        self.parts.extend(markup)

    def render(self):
        inner = "".join(self.defs.values()) + glyph_defs()
        defs = f"<defs>{inner}</defs>" if inner else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(self.w)}" height="{n(self.h)}" '
                f'viewBox="0 0 {n(self.w)} {n(self.h)}" role="img" aria-label="{escape(self.label)}">'
                f"<title>{escape(self.label)}</title>{defs}{''.join(self.parts)}</svg>\n")


def cosmos(svg, w, h, seed, count):
    """CosmosBG: pixel stars on pxTwinkle (steps(2) over .25 -> 1 -> .25) and shooting stars."""
    rnd = random.Random(seed)
    out = []
    for _ in range(count):
        x, y = rnd.random() * w, rnd.random() * h
        s = 4 if rnd.random() > 0.88 else 2
        delay, dur = rnd.random() * 5, 2 + rnd.random() * 3
        out.append(
            f'<rect x="{n(x)}" y="{n(y)}" width="{s}" height="{s}" fill="{IVORY}" opacity="0.25">'
            f'<animate attributeName="opacity" values="0.25;0.62;1;0.62" dur="{n(dur)}s" '
            f'begin="-{n(delay)}s" calcMode="discrete" repeatCount="indefinite"/></rect>')
    svg.define("shoot", '<linearGradient id="shoot"><stop offset="0" stop-color="#e8e4d4" stop-opacity="0"/>'
                        '<stop offset=".45" stop-color="#e8e4d4"/><stop offset=".85" stop-color="#fff"/>'
                        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    for top, delay, gap in [(0.10, 5, 20), (0.28, 15, 28), (0.60, 9, 32)]:
        y0, x0 = top * h, -0.1 * w
        x1, y1 = x0 + 1.2 * w, y0 + 0.24 * h
        out.append(
            f'<g opacity="0">'
            f'<animate attributeName="opacity" values="0;1;0;0" keyTimes="0;0.02;0.1;1" dur="{gap}s" begin="{delay}s" repeatCount="indefinite"/>'
            f'<animateTransform attributeName="transform" type="translate" values="{n(x0)} {n(y0)};{n(x1)} {n(y1)};{n(x1)} {n(y1)}" '
            f'keyTimes="0;0.1;1" dur="{gap}s" begin="{delay}s" repeatCount="indefinite"/>'
            f'<rect width="80" height="2" fill="url(#shoot)" transform="rotate(14)"/></g>')
    return "".join(out)


def title_bar(svg, x, y, w, title):
    """MacTitleBar: 22px, stripes inset 3px at .22, close box left, zoom box right."""
    svg.define("stripes", '<pattern id="stripes" width="4" height="2" patternUnits="userSpaceOnUse">'
                          '<rect width="4" height="1" fill="#000"/></pattern>')
    h, size, tr = 22, 12, 0.02
    tw = width("mono", title, size, tr)
    return "".join([
        rect(x, y, w, h, TITLE_BG),
        rect(x, y + 3, w, h - 7, "url(#stripes)", ' opacity="0.22"'),
        rect(x + w / 2 - tw / 2 - 10, y + 1, tw + 20, h - 3, TITLE_BG),
        text("mono", title, size, x + w / 2 - tw / 2, y + 15, "#000", tr),
        rect(x + 7.5, y + 5.5, 11, 11, "#fff", ' stroke="#000"'),
        rect(x + w - 18.5, y + 5.5, 11, 11, "#fff", ' stroke="#000"'),
        rect(x + w - 16.5, y + 7.5, 5, 5, "#fff", ' stroke="#000"'),
        rect(x, y + h - 1, w, 1, "#000"),
    ]), h


def window(svg, x, y, w, h, title, accent, body="#fff", body_opacity=None):
    """RetroWin: white body, 1px black border, 3px 3px 0 0 #000 shadow."""
    op = f' fill-opacity="{body_opacity}"' if body_opacity is not None else ""
    bar, bh = title_bar(svg, x, y, w, title)
    before = "".join([rect(x + 3, y + 3, w, h, "#000"), rect(x, y, w, h, body, op), bar,
                      rect(x, y + bh, w, 3, accent)])
    after = rect(x + 0.5, y + 0.5, w - 1, h - 1, "none", ' stroke="#000"')
    return before, after, y + bh + 3


def prompt(cmd, size, x, y):
    return runs([("$", style("mono", PHOSPHOR)), (" " + cmd, style("mono", WARM))], size, x, y)[0]


def typing(svg, key, s, size, x, y, fill, per=0.11, hold=3.2, rest=0.8):
    """A command that types itself out, holds, clears; the cursor rides its end."""
    markup, w = typeset("mono", s, size, x, y, 0.0, f' fill="{fill}"')
    step = w / len(s)
    total = len(s) * per + hold + rest
    kt = [i * per / total for i in range(len(s) + 1)] + [(len(s) * per + hold) / total]
    widths = [i * step for i in range(len(s) + 1)] + [0]
    kts = ";".join(f"{k:.4f}" for k in kt)
    svg.define(key, f'<clipPath id="{key}"><rect x="{n(x)}" y="{n(y - size)}" width="0" height="{n(size * 1.6)}">'
                    f'<animate attributeName="width" values="{";".join(n(v) for v in widths)}" keyTimes="{kts}" '
                    f'dur="{n(total)}s" calcMode="discrete" repeatCount="indefinite"/></rect></clipPath>')
    cursor = (f'<g><animateTransform attributeName="transform" type="translate" '
              f'values="{";".join(n(v) + " 0" for v in widths)}" keyTimes="{kts}" dur="{n(total)}s" '
              f'calcMode="discrete" repeatCount="indefinite"/>'
              f'{rect(x + 1, y - size * 0.86, size * 0.6, size * 1.1, PHOSPHOR)[:-2]}>'
              f'<animate attributeName="opacity" values="1;0" dur="1.06s" calcMode="discrete" repeatCount="indefinite"/>'
              f'</rect></g>')
    # clip on an untransformed group: a clipPath reads the referencing element's own coordinates
    return f'<g clip-path="url(#{key})">{markup}</g>' + cursor


# --------------------------------------------------------------------------
# Header: menu bar, crumb, terminal + README.md window over the starfield
# --------------------------------------------------------------------------

def menu_bar(y):
    h, size, tr, base = 32, 11, 0.1, y + 20
    out = [rect(0, y, W, h, PANEL), rect(0, y + h - 1, W, 1, RULE)]
    x = 22
    for label, fill, face in [("◆ HAPPYIN.WORK", PHOSPHOR, "mono-bold"), ("HOME", MUTED, "mono"),
                              ("CV", MUTED, "mono"), ("COMFYUI", MUTED, "mono"), ("BLOG", MUTED, "mono"),
                              ("GITHUB", PHOSPHOR, "mono")]:
        out.append(text(face, label, size, x, base, fill, tr))
        x += width(face, label, size, tr) + 18
    out.append(rect(x - 4, y + 9, 1, 14, RULE))
    x += 10
    out.append(text("mono", "MY PROJECTS", size, x, base, MUTED, tr))
    x += width("mono", "MY PROJECTS", size, tr) + 6
    out.append(text("mono", "▼", 8, x, base - 1, MUTED))
    out.append(text("mono", "HAPPYINHAPPY · BELGRADE", size, W - 22, base, CAPTION, tr, "end"))
    return "".join(out), h


def crumb(y, where):
    h, size, tr, base = 30, 11, 0.1, y + 19
    parts, _ = runs([("~/", style("mono", WARM, tracking=tr)), (" / ", style("mono", CAPTION, tracking=tr)),
                     (where, style("mono", IVORY, tracking=tr))], size, 22, base)
    return rect(0, y, W, h, PANEL, ' fill-opacity="0.55"') + rect(0, y + h - 1, W, 1, RULE) + parts, h


def terminal_body(svg, x, y, w):
    """The home page's terminal, trimmed to what fits a README header."""
    pad, size, lead = 22, 12.5, 21.5
    ix, iw = x + pad, w - 2 * pad
    out = []
    y += pad + 8
    out.append(sparkle(ix + 4, y - 3.5, 4.5, PHOSPHOR))
    out.append(text("mono", "WELCOME TO HAPPYIN.WORK", 10, ix + 14, y, PHOSPHOR, 0.2))
    y += 24
    out.append(text("mono", "Last login: today on ttys001", size, ix, y, MUTED))
    y += lead + 2
    out.append(prompt("whoami", size, ix, y))
    y += lead
    body, y = paragraph([("anastasiia butova — comfyui specialist · image-processing pipelines",
                          style("mono", IVORY))], size, ix + 14, y, iw - 14, lead)
    out.append(body)
    out.append(prompt("cat /etc/timezone", size, ix, y))
    y += lead
    out.append(runs([("Europe/Belgrade — ", style("mono", IVORY)), ("Belgrade, Serbia", style("mono", MUTED))],
                    size, ix + 14, y)[0])
    y += 22 + 38 * 0.78
    out.append(runs([(">_", style("mono-bold", PHOSPHOR)), (" Anastasiia Butova", style("mono-bold", IVORY))],
                    38, ix, y)[0])
    y += 24
    sub, y = paragraph([("ComfyUI specialist · turnkey image-processing pipelines · diffusion models",
                         style("mono", MUTED))], 12, ix, y, iw, 18)
    out.append(sub)
    y += 12
    out.append(prompt("", size, ix, y))
    out.append(typing(svg, "typed", "open https://happyin.work", size, ix + width("mono", "$ ", size), y, IVORY))
    return "".join(out), y + pad


def readme_body(x, y, w):
    """The README.md window from the home page's right column."""
    px, py = 16, 14
    ix, iw = x + px, w - 2 * px
    ink, link = style("serif", "#000"), style("serif", WIN_BLUE, underline=True)
    it = style("serif-italic", "#000")
    out = []
    y += py + 22
    out.append(runs([("Hi, I'm ", it), ("Anastasiia", style("serif-italic", "#000", hilite=HILITE)), (".", it)],
                    27, ix, y)[0])
    y += 24
    p1, y = paragraph([("ComfyUI", link), (" specialist. Turnkey image-processing pipelines for businesses, from "
                       "image assessment to a GPU service. Diffusion models, computer vision, ComfyUI & Diffusers "
                       "stacks.", ink)], 14, ix, y, iw, 18.5)
    out.append(p1)
    y += 6
    p2, y = paragraph([("Production AI for 4M+ users · 80×H200 cluster · custom CNN/U-Net training · "
                        "32K+ Habr reach.", ink)], 14, ix, y, iw, 18.5)
    out.append(p2)
    y += 2
    out.append(f'<path d="M{n(ix)} {n(y)}H{n(ix + iw)}" stroke="#999" stroke-dasharray="3 3"/>')
    y += 17
    grey, blue = style("mono", "#555"), style("mono", WIN_BLUE)
    for k, v in [("web", "happyin.work"), ("telegram", "@happy_in_happy"),
                 ("linkedin", "in/happyinhappy"), ("habr", "@Sonia_Black")]:
        out.append(runs([(f"{k} · ", grey), (v, blue)], 10.5, ix, y)[0])
        y += 16.5
    return "".join(out), y - 16.5 + 4 + py


def header():
    top_pad, pad, gap = 26, 26, 24
    term_w = 522
    win_x = pad + term_w + gap
    win_w = W - pad - win_x

    probe = Svg(W, 0, "")
    menu, mh = menu_bar(0)
    cr, ch = crumb(mh, "github")
    y0 = mh + ch + top_pad
    term_inner, term_end = terminal_body(probe, pad, y0 + 25, term_w)
    readme_inner, readme_end = readme_body(win_x, y0 + 25 + 18, win_w)
    H = int(max(term_end, readme_end) + top_pad + 4)

    svg = Svg(W, H, "Anastasiia Butova — ComfyUI specialist, turnkey image-processing pipelines, "
                    "diffusion models. happyin.work")
    svg.defs = probe.defs
    svg.add(rect(0, 0, W, H, VOID), cosmos(svg, W, H, seed=1440, count=90), menu, cr)

    before, after, _ = window(svg, pad, y0, term_w, term_end - y0, "happyinhappy@happyin.work — github",
                              PHOSPHOR, VOID, 0.62)
    svg.add(before, term_inner, after)
    before, after, _ = window(svg, win_x, y0 + 18, win_w, readme_end - y0 - 18, "README.md", WIN_BLUE)
    svg.add(before, readme_inner, after)
    return svg.render()


# --------------------------------------------------------------------------
# Section labels: the site's `$ command` prompt as a small chip
# --------------------------------------------------------------------------

def label(cmd):
    size, pad, h = 12, 12, 30
    w = pad * 2 + width("mono", "$ " + cmd, size)
    svg = Svg(w, h, "$ " + cmd)
    svg.add(rect(0.5, 0.5, w - 1, h - 1, VOID, f' stroke="{RULE}"'), prompt(cmd, size, pad, 19.5))
    return svg.render()


# --------------------------------------------------------------------------
# Production work: one Win 3.1 window per project, two per row
# --------------------------------------------------------------------------

def project_card(slug, name, kicker, blurb, swatch, accent, body_h=None):
    cw, px, py = 440, 16, 14
    iw = cw - 2 * px
    svg = Svg(cw + 3, 0, f"{name} — {kicker}. {blurb}")
    out, y = [], 25 + py
    y += 22
    out.append(rect(px, y - 14, 10, 9, swatch, ' stroke="#000"'))
    out.append(text("serif-italic", name, 26, px + 18, y, "#000"))
    y += 21
    k, y = paragraph([(kicker.upper(), style("mono", "#666", tracking=0.08))], 9.5, px, y, iw, 15)
    out.append(k)
    y += 6
    b, y = paragraph([(blurb, style("serif", "#111"))], 15, px, y, iw, 20)
    out.append(b)
    content_end = y
    if body_h is not None:
        y = 25 + body_h
    y += 4
    out.append(f'<path d="M{px} {n(y)}H{n(cw - px)}" stroke="#ccc" stroke-dasharray="1 2"/>')
    y += 17
    out.append(runs([("▸ ", style("mono", "#000")), (f"happyin.work/{slug}/", style("mono", WIN_BLUE, underline=True))],
                    10.5, px, y)[0])
    out.append(text("mono", "[enter →]", 10.5, cw - px, y, WIN_GREEN, anchor="end"))
    h = y + py - 2
    before, after, _ = window(svg, 0, 0, cw, h, name, accent)
    svg.h = h + 3
    svg.add(before, *out, after)
    return svg.render(), content_end - 25


# --------------------------------------------------------------------------
# Open source: a terminal listing the public repositories, live numbers
# --------------------------------------------------------------------------

def open_source(repos):
    w, pad, size = W - 4, 22, 12.5
    svg = Svg(W, 0, "Open-source repositories: " + ", ".join(r["name"] for r in repos))
    out, y = [], 25 + pad + 8
    out.append(prompt(f"gh repo list {USER} --visibility public --source", size, pad, y))
    y += 16
    col_star, col_name, col_right = pad + 58, pad + 76, w - pad
    for i, r in enumerate(repos):
        top = y
        if i:
            out.append(f'<path d="M{pad} {n(top)}H{n(w - pad)}" stroke="{RULE}" stroke-dasharray="4 3"/>')
        base = top + 24
        out.append(text("mono-bold", str(r["stargazers_count"]), 13, col_star - 18, base, PHOSPHOR, anchor="end"))
        out.append(star(col_star - 8, base - 4.5, 6, PHOSPHOR))
        out.append(text("mono-bold", r["name"], 13, col_name, base, IVORY))
        lang = (r["language"] or "markdown").upper()
        meta = f"{lang} · {r['forks_count']} FORK{'S' if r['forks_count'] != 1 else ''}"
        out.append(text("mono", meta, 9.5, col_right, base, CAPTION, 0.12, "end"))
        desc = ellipsize("mono", r["description"] or "", 11, col_right - col_name)
        out.append(text("mono", desc, 11, col_name, base + 19, MUTED))
        y = top + 44
    y += pad - 6
    before, after, _ = window(svg, 0, 0, w, y, "happyinhappy@happyin.work — ~/open-source", PHOSPHOR, VOID)
    svg.h = y + 3
    svg.add(before, *out, after)
    return svg.render()


# --------------------------------------------------------------------------
# production.log: the home page's shipped / open-source window, as numbers
# --------------------------------------------------------------------------

def production_log(stars):
    w, px = W - 4, 16
    groups = [
        ("shipped", [("4M+", "users of the AI features I shipped at Glam.ai"),
                     ("80×H200", "GPU training cluster I ran"),
                     ("1,500+", "active users of the ois.gold jewellery SaaS")]),
        ("open-source", [(f"{stars}", "GitHub stars on my public repositories"),
                         ("1,287+", "reference articles on happyin.space"),
                         ("32K+", "readers reached on Habr")]),
    ]
    svg = Svg(W, 0, "production.log — " + "; ".join(f"{v} {t}" for _, cells in groups for v, t in cells))
    out, top = [], 25 + 16
    cell_w = (w - 2 * px) / 6
    bottom = 0
    for g, (title, cells) in enumerate(groups):
        gx = px + g * 3 * cell_w
        out.append(runs([("▸ ", style("mono", "#000")), (title, style("mono-bold", "#000"))], 11, gx, top + 12)[0])
        for i, (value, caption) in enumerate(cells):
            cx = gx + i * cell_w
            vx = cx
            out.append(text("mono-bold", value, 27, vx, top + 50, LOG_GREEN))
            if title == "open-source" and i == 0:
                out.append(star(vx + width("mono-bold", value, 27) + 12, top + 40, 9, LOG_GREEN))
            cap, cy = paragraph([(caption.upper(), style("mono", "#666", tracking=0.08))], 9, cx, top + 70,
                                cell_w - 16, 13.5)
            out.append(cap)
            bottom = max(bottom, cy)
    out.append(rect(px + 3 * cell_w - 12, top + 2, 1, bottom - top - 12, "#000"))
    h = bottom + 6
    before, after, _ = window(svg, 0, 0, w, h, "production.log", WIN_PURPLE)
    svg.h = h + 3
    svg.add(before, *out, after)
    return svg.render()


# --------------------------------------------------------------------------
# stack.md: the site's `# tag.` lines (THash), from the Person node's knowsAbout
# --------------------------------------------------------------------------

STACK = [
    ("pipelines", "ComfyUI graphs · custom nodes · ComfyUI API · Diffusers · headless GPU queues and APIs"),
    ("models", "FLUX.2 · Qwen Image Edit · Stable Diffusion · LoRA fine-tuning · SAM3 · YOLO · NAFNet"),
    ("vision", "segmentation · restoration and denoising · super-resolution · colour correction · 3D LUTs"),
    ("quality", "image quality assessment · measurable acceptance checks · fixed-seed comparison sheets"),
    ("engineering", "Python · PyTorch · ONNX Runtime · C++ · GPU infrastructure · MLOps"),
    ("agents", "Claude Code · Codex · MCP · hooks, skills and multi-session tooling"),
]


def stack():
    w, pad, size, lead = W - 4, 22, 12.5, 21
    svg = Svg(W, 0, "Stack — " + "; ".join(f"{t}: {v}" for t, v in STACK))
    out, y = [], 25 + pad + 8
    out.append(prompt("cat stack.md", size, pad, y))
    y += lead + 6
    for tag, items in STACK:
        body, y = paragraph([(f"# {tag}.", style("mono", CAPTION)), (" " + items, style("mono", WARM))],
                            size, pad, y, w - 2 * pad, lead)
        out.append(body)
        y += 3
    y += pad - lead + 2
    before, after, _ = window(svg, 0, 0, w, y, "happyinhappy@happyin.work — stack.md", PHOSPHOR, VOID)
    svg.h = y + 3
    svg.add(before, *out, after)
    return svg.render()


# --------------------------------------------------------------------------
# as-featured.md: what others say (site-data.js testimonials, press)
# --------------------------------------------------------------------------

def as_featured():
    w, px = W - 4, 16
    left_w = 540
    rx = px + left_w + 28
    rw = w - px - rx
    svg = Svg(W, 0, "What others say — Nikita Blinkov, Glam AI; Paul Miller, client; "
                    "as featured: AI Talks: Anastasia, OIS.AI retouch interview (Plain AI)")
    out, y = [], 25 + 14 + 24
    out.append(text("serif-italic", "What others say", 26, px, y, "#000"))
    q = style("serif-italic", "#222")
    top = y + 28
    body, ly = paragraph([("“I had the pleasure of working with Anastasia and can confidently say she is an "
                           "exceptional AI specialist with a rare combination of technical depth, versatility, "
                           "and strong ownership. … Overall, she is someone who doesn't just understand AI, but "
                           "knows how to apply it in a way that brings real value, while also supporting and "
                           "elevating the people around her.”", q)], 15, px, top, left_w, 20.5)
    out.append(body)
    ly += 2
    out.append(text("mono-bold", "Nikita Blinkov", 10.5, px, ly, "#000"))
    out.append(text("mono", "Head of People & Org Dev @ Glam AI · worked together at Glam.ai", 9.5, px, ly + 15, "#666"))
    ly += 15

    out.append(rect(rx - 14, top - 14, 1, ly - top + 14, "#000"))
    body, ry = paragraph([("“Both highly professional and innovative, each project has felt more like a genuine "
                           "collaboration.”", q)], 15, rx, top, rw, 20.5)
    out.append(body)
    ry += 2
    out.append(text("mono-bold", "Paul Miller", 10.5, rx, ry, "#000"))
    ry += 15
    who, ry = paragraph([("Luxury jewellery & timepiece retoucher · client", style("mono", "#666"))], 9.5, rx, ry,
                        rw, 13.5)
    out.append(who)
    ry += 4
    out.append(rect(rx, ry, rw, 1, "#000"))
    ry += 17
    out.append(text("mono", "▸ AS FEATURED", 9, rx, ry, "#666", 0.1))
    ry += 19
    press, ry = paragraph([("“AI Talks: Anastasia — OIS.AI retouch interview”",
                            style("serif-italic", WIN_BLUE))], 14.5, rx, ry, rw, 19)
    out.append(press)
    out.append(text("mono", "Plain AI · interview ↗", 9.5, rx, ry, "#666"))
    h = max(ly, ry) + 18
    before, after, _ = window(svg, 0, 0, w, h, "as-featured.md", WIN_RUST)
    svg.h = h + 3
    svg.add(before, *out, after)
    return svg.render()


# --------------------------------------------------------------------------
# Contacts: TBtn buttons, one image per link so each one clicks through
# --------------------------------------------------------------------------

def button(label, primary=False):
    size, px, h = 11.5, 18, 36
    face = "mono-bold" if primary else "mono"
    w = width(face, label, size, 0.06) + 2 * px
    svg = Svg(w, h, label)
    if primary:
        svg.add(rect(0, 0, w, h, PHOSPHOR), text(face, label, size, px, 23, VOID, 0.06))
    else:
        svg.add(rect(0.5, 0.5, w - 1, h - 1, VOID, f' stroke="{DASH}"'), text(face, label, size, px, 23, IVORY, 0.06))
    return svg.render()


# --------------------------------------------------------------------------
# Footer: the site's taskbar
# --------------------------------------------------------------------------

def taskbar():
    h, size = 34, 11
    svg = Svg(W, h, "happyin.work taskbar — agents.txt")
    out = [rect(0, 0, W, h, PANEL), rect(0, 0, W, 1, RULE), text("mono", "◆", size, 18, 21.5, PHOSPHOR)]
    x = 38
    for i, tab in enumerate(["github", "README.md", "projects/", "open-source/", "production.log", "agents.txt"]):
        tw = width("mono", tab, size) + 20
        if i == 0:
            out.append(rect(x, 7, tw, 20, RULE))
            fill = IVORY
        else:
            out.append(rect(x + 0.5, 7.5, tw - 1, 19, "none", f' stroke="{RULE}"'))
            fill = GRASS if tab == "agents.txt" else MUTED
        out.append(text("mono", tab, size, x + 10, 21, fill))
        x += tw + 8
    out.append(text("mono", "uptime: since 2023", size, W - 36, 21, MUTED, anchor="end"))
    out.append(rect(W - 27, 10, 9, 14, PHOSPHOR)[:-2] +
               '><animate attributeName="opacity" values="1;0" dur="1.06s" calcMode="discrete" '
               'repeatCount="indefinite"/></rect>')
    svg.add(*out)
    return svg.render()


# --------------------------------------------------------------------------

PRODUCTION = [  # site-data.js, projectGroups "production work"
    ("glam", "glam.ai", "ML engineering & team lead (ex-) · 4M+ users",
     "Identity-preserving photoshoot, multi-angle, trend looks, fix-everything. "
     "Five chained Qwen pipelines in production.", "#ffd0a0", WIN_BLUE),
    ("mashinki", "mashinki", "Dealer photo pipeline · architecture + ML",
     "Automated exterior and interior retouch for car dealerships: segmentation, glass relight, "
     "plate replacement, background replacement. Try it in the browser.", "#c0d8f0", WIN_GREEN),
    ("happyin-ai", "happyin.ai", "Own R&D studio · founder",
     "C++ Photoshop plugin + on-device retouching models. Custom-trained networks, "
     "novel hi-res tiling architectures.", "#f0c0d0", WIN_PURPLE),
    ("ois-gold", "ois.gold", "Jewelry retouching SaaS · sole tech lead",
     "End-to-end SaaS for jewelry image processing. CV pipeline for 6K-10K pixel images, "
     "1,500+ active users.", "#e0d090", WIN_RUST),
]

SHOWCASE = ["codex-claude-code-config", "knowledge-space", "mclaude", "happyin-labelstudio",
            "working-with-ai-agents"]

BUTTONS = [("happyin.work →", True), ("happyin.space", False), ("linkedin", False),
           ("telegram", False), ("habr", False)]


def github(path):
    req = urllib.request.Request(f"https://api.github.com/{path}",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": f"{USER}-profile"})
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def write(name, content):
    with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    print(f"{name:28s} {len(content) / 1024:6.1f} KB")


def main():
    repos = [r for r in github(f"users/{USER}/repos?per_page=100&type=owner") if not r["private"] and not r["fork"]]
    by_name = {r["name"]: r for r in repos}
    missing = [s for s in SHOWCASE if s not in by_name]
    if missing:
        raise SystemExit(f"not public on {USER}: {', '.join(missing)}")
    stars = sum(r["stargazers_count"] for r in repos)

    os.makedirs(OUT, exist_ok=True)
    write("header.svg", header())
    for slug, cmd in [("bio", "cat bio.md"), ("production", "ls ~/projects/production"),
                      ("open-source", "ls ~/projects/open-source"), ("log", "tail production.log"),
                      ("stack", "cat stack.md"), ("featured", "cat as-featured.md"),
                      ("contacts", "cat contacts.txt")]:
        write(f"label-{slug}.svg", label(cmd))

    # equal-height windows: measure every card, then draw all at the tallest
    tallest = max(project_card(*p)[1] for p in PRODUCTION)
    for p in PRODUCTION:
        write(f"project-{p[0]}.svg", project_card(*p, body_h=tallest)[0])

    write("open-source.svg", open_source([by_name[s] for s in SHOWCASE]))
    write("production-log.svg", production_log(stars))
    write("stack.svg", stack())
    write("as-featured.svg", as_featured())
    for label_text, primary in BUTTONS:
        slug = re.sub(r"[^a-z0-9]+", "-", label_text.lower()).strip("-")
        write(f"button-{slug}.svg", button(label_text, primary))
    write("taskbar.svg", taskbar())
    print(f"stars: {stars} across {len(repos)} public repositories")


if __name__ == "__main__":
    main()
