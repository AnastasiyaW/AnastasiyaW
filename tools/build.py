"""Build the SVG artwork for the AnastasiyaW GitHub profile README.

Everything here quotes happyin.work. Colours and type come from the site's
pages/_assets/UI-KIT-REFERENCE.md, shapes from page-shell.jsx: the pixel
starfield (CosmosBG), the striped Mac title bar, the Win 3.1 windows with a
3px accent strip and a hard black shadow, the `$` prompts, the menu bar and
the taskbar. Copy is the site's own (pages-data.jsx, site-data.js); the
repository numbers are read from the GitHub API on every build.

Type ships as outlines: GitHub serves README images through camo as <img>,
and an <img> SVG cannot load webfonts. Desktop artwork is drawn 900px wide,
which GitHub's profile column shows at about 0.94. A second set of the
full-width panels in assets/mobile/ is drawn 420px wide for phones, where the
README swaps it in with <picture><source media="(max-width: 600px)">: desktop
art scaled to a phone would put body text at 5px.

    python tools/fetch_fonts.py
    uv run --no-project --with fonttools --with uharfbuzz python tools/build.py
"""

import json
import math
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

W, WM = 900, 420  # desktop: GitHub's README column; mobile: a ~340px phone column


def n(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def rect(x, y, w, h, fill, extra=""):
    return f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" fill="{fill}"{extra}/>'


def hline(x0, x1, y, stroke, dash):
    return f'<path d="M{n(x0)} {n(y)}H{n(x1)}" stroke="{stroke}" stroke-dasharray="{dash}"/>'


# --------------------------------------------------------------------------
# Text: plain lines, styled runs, and word wrap over styled runs
# --------------------------------------------------------------------------

def style(face, fill, **kw):
    return dict(face=face, fill=fill, **kw)


def fit(face, s, size, maxw, tracking=0.0):
    """One-line copy must fit its slot; fail the build rather than clip it."""
    got = width(face, s, size, tracking)
    if got > maxw:
        raise SystemExit(f"{s!r} is {got:.0f}px, its slot is {maxw:.0f}px")
    return s


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


def paragraph(parts, size, x, y, maxw, lead, max_lines=None):
    """Wrapped styled runs, first baseline at y; returns (markup, next_y)."""
    lines = wrap(parts, size, maxw)
    if max_lines and len(lines) > max_lines:
        raise SystemExit(f"{''.join(s for s, _ in parts)!r} wraps to {len(lines)} lines, allowed {max_lines}")
    out = []
    for line in lines:
        out.append(runs(line, size, x, y)[0])
        y += lead
    return "".join(out), y


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
    tw = width("mono", fit("mono", title, size, w - 60, tr), size, tr)
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


BODY_TOP = 25  # title bar 22 + accent strip 3


def window(svg, x, y, w, h, title, accent, body="#fff", body_opacity=None):
    """RetroWin: white body, 1px black border, 3px 3px 0 0 #000 shadow."""
    op = f' fill-opacity="{body_opacity}"' if body_opacity is not None else ""
    bar, bh = title_bar(svg, x, y, w, title)
    before = "".join([rect(x + 3, y + 3, w, h, "#000"), rect(x, y, w, h, body, op), bar,
                      rect(x, y + bh, w, 3, accent)])
    after = rect(x + 0.5, y + 0.5, w - 1, h - 1, "none", ' stroke="#000"')
    return before, after


def panel(w, h, title, accent, dark, parts, label):
    """A full-width window image: the window, its shadow, and nothing else."""
    svg = Svg(w, h + 3, label)
    before, after = window(svg, 0, 0, w - 4, h, title, accent, VOID if dark else "#fff")
    svg.add(before, *parts, after)
    return svg.render()


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

def menu_bar(w, mobile):
    h, size, tr, base = 32, 11, 0.1, 20
    out = [rect(0, 0, w, h, PANEL), rect(0, h - 1, w, 1, RULE)]
    x = 14 if mobile else 22
    items = [("◆ HAPPYIN.WORK", PHOSPHOR, "mono-bold")]
    if not mobile:
        items += [("HOME", MUTED, "mono"), ("CV", MUTED, "mono"), ("COMFYUI", MUTED, "mono"), ("BLOG", MUTED, "mono")]
    items += [("GITHUB", PHOSPHOR, "mono")]
    for label, fill, face in items:
        out.append(text(face, label, size, x, base, fill, tr))
        x += width(face, label, size, tr) + 18
    if not mobile:
        out.append(rect(x - 4, 9, 1, 14, RULE))
        x += 10
        out.append(text("mono", "MY PROJECTS", size, x, base, MUTED, tr))
        x += width("mono", "MY PROJECTS", size, tr) + 6
        out.append(text("mono", "▼", 8, x, base - 1, MUTED))
        out.append(text("mono", "HAPPYINHAPPY · BELGRADE", size, w - 22, base, CAPTION, tr, "end"))
    return "".join(out), h


def crumb(y, w, where, mobile):
    h, size, tr = 30, 11, 0.1
    parts, _ = runs([("~/", style("mono", WARM, tracking=tr)), (" / ", style("mono", CAPTION, tracking=tr)),
                     (where, style("mono", IVORY, tracking=tr))], size, 14 if mobile else 22, y + 19)
    return rect(0, y, w, h, PANEL, ' fill-opacity="0.55"') + rect(0, y + h - 1, w, 1, RULE) + parts, h


def terminal_body(svg, x, y, w, mobile):
    """The home page's terminal, trimmed to what fits a README header."""
    pad = 16 if mobile else 22
    size, lead = (13, 22) if mobile else (12.5, 21.5)
    head = 26 if mobile else 38  # THead: 38px, 26px on phones
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
    who, y = paragraph([("anastasiia butova — comfyui specialist", style("mono", IVORY))],
                       size, ix + 14, y, iw - 14, lead, max_lines=None if mobile else 1)
    out.append(who)
    out.append(prompt("cat /etc/timezone", size, ix, y))
    y += lead
    out.append(runs([("Europe/Belgrade — ", style("mono", IVORY)), ("Belgrade, Serbia", style("mono", MUTED))],
                    size, ix + 14, y)[0])
    y += 22 + head * 0.78
    out.append(runs([(">_", style("mono-bold", PHOSPHOR)), (" Anastasiia Butova", style("mono-bold", IVORY))],
                    head, ix, y)[0])
    y += 24
    sub, y = paragraph([("image-processing pipelines · diffusion models · computer vision", style("mono", MUTED))],
                       12, ix, y, iw, 18, max_lines=None if mobile else 1)
    out.append(sub)
    y += 12
    out.append(prompt("", size, ix, y))
    out.append(typing(svg, "typed", "open https://happyin.work", size, ix + width("mono", "$ ", size), y, IVORY))
    return "".join(out), y + pad


def readme_body(x, y, w, mobile):
    """The README.md window from the home page's right column."""
    px, py = (14, 12) if mobile else (16, 14)
    ix, iw = x + px, w - 2 * px
    ink, link = style("times", "#000"), style("times", WIN_BLUE, underline=True)
    it = style("serif-italic", "#000")
    size, lead = (14.5, 19.5) if mobile else (14, 19)
    out = []
    y += py + 22
    out.append(runs([("Hi, I'm ", it), ("Anastasiia", style("serif-italic", "#000", hilite=HILITE)), (".", it)],
                    26 if mobile else 27, ix, y)[0])
    y += 24
    p1, y = paragraph([("ComfyUI", link), (" specialist. Turnkey image-processing pipelines for businesses, from "
                       "image assessment to a GPU service. Diffusion models, computer vision, ComfyUI & Diffusers "
                       "stacks.", ink)], size, ix, y, iw, lead)
    out.append(p1)
    y += 6
    p2, y = paragraph([("Production AI for 4M+ users · 80×H200 cluster · custom CNN/U-Net training · "
                        "32K+ Habr reach.", ink)], size, ix, y, iw, lead)
    out.append(p2)
    y += 2
    out.append(hline(ix, ix + iw, y, "#999", "3 3"))
    y += 17
    grey, blue = style("mono", "#555"), style("mono", WIN_BLUE)
    for k, v in [("web", "happyin.work"), ("telegram", "@happy_in_happy"),
                 ("linkedin", "in/happyinhappy"), ("habr", "@Sonia_Black")]:
        out.append(runs([(f"{k} · ", grey), (v, blue)], 10.5, ix, y)[0])
        y += 16.5
    return "".join(out), y - 16.5 + 4 + py


def header(mobile=False):
    w = WM if mobile else W
    pad = 14 if mobile else 26
    probe = Svg(w, 0, "")
    menu, mh = menu_bar(w, mobile)
    cr, ch = crumb(mh, w, "github", mobile)
    y0 = mh + ch + (16 if mobile else 26)
    if mobile:
        term_w = w - 2 * pad - 3
        term_inner, term_end = terminal_body(probe, pad, y0 + BODY_TOP, term_w, True)
        win_x, win_y, win_w = pad, term_end + 18, term_w
    else:
        term_w = 522
        term_inner, term_end = terminal_body(probe, pad, y0 + BODY_TOP, term_w, False)
        win_x, win_y = pad + term_w + 24, y0
        win_w = w - pad - win_x
    readme_inner, readme_end = readme_body(win_x, win_y + BODY_TOP, win_w, mobile)
    H = int(max(term_end, readme_end) + (18 if mobile else 30))

    svg = Svg(w, H, "Anastasiia Butova — ComfyUI specialist; image-processing pipelines, diffusion models, "
                    "computer vision. Belgrade, Serbia. happyin.work")
    svg.defs = probe.defs
    svg.add(rect(0, 0, w, H, VOID), cosmos(svg, w, H, seed=1440, count=45 if mobile else 90), menu, cr)
    before, after = window(svg, pad, y0, term_w, term_end - y0, "happyinhappy@happyin.work — github",
                           PHOSPHOR, VOID, 0.62)
    svg.add(before, term_inner, after)
    before, after = window(svg, win_x, win_y, win_w, readme_end - win_y, "README.md", WIN_BLUE)
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

def project_card(project, side, body_h=None):
    """Half of a two-up row. The image is half the column; the right card is
    inset so both windows are equal and the right one ends exactly where the
    full-width panels end (x = W - 4).

    Desktop only: GitHub pulls an <img> out of a linked <picture>, so a card
    can have its link or a phone variant, not both, and the link matters more."""
    slug, name, kicker, blurb, swatch, accent = project
    half, gap = W // 2, 10
    inset = (gap - 4) / 2
    ww = half - 4 - inset
    x0 = inset if side else 0
    px = 16
    ix, iw = x0 + px, ww - 2 * px

    out, y = [], BODY_TOP + 14 + 22
    out.append(rect(ix, y - 14, 10, 9, swatch, ' stroke="#000"'))
    out.append(text("serif-italic", name, 26, ix + 17, y, "#000"))
    y += 21
    k, y = paragraph([(kicker.upper(), style("mono", "#555", tracking=0.08))], 10.5, ix, y, iw, 15.5)
    out.append(k)
    y += 7
    b, y = paragraph([(blurb, style("times", "#111"))], 15.5, ix, y, iw, 21)
    out.append(b)
    content_end = y
    if body_h is not None:
        y = BODY_TOP + body_h
    y += 4
    out.append(hline(ix, ix + iw, y, "#ccc", "1 2"))
    y += 16
    out.append(runs([("▸ ", style("mono", "#000")),
                     (f"happyin.work/{slug}/", style("mono", WIN_BLUE, underline=True))], 10.5, ix, y)[0])
    out.append(text("mono", "[enter →]", 10.5, ix + iw, y, WIN_GREEN, anchor="end"))
    h = y + 12

    svg = Svg(half, h + 3 + 6, f"{name} — {kicker}. {blurb}")
    before, after = window(svg, x0, 0, ww, h, f"{slug}.md", accent)
    svg.add(before, *out, after)
    return svg.render(), content_end - BODY_TOP


# --------------------------------------------------------------------------
# Open source: the site's open-source group as a terminal listing, live numbers
# --------------------------------------------------------------------------

OSS = [  # site-data.js, projectGroups "open source"; one-liners from the site's blurbs
    ("codex-claude-code-config", "Drop-in rulebook for Claude Code and Codex agents: 30 principles, 40+ hooks, 58 skills."),
    ("knowledge-space", "happyin.space: 1,287+ reference articles across 28 domains, written for AI agents."),
    ("mclaude", "Multi-session infrastructure for Claude Code: locks, handoffs, memory, messaging."),
]


def open_source(repos, mobile):
    w = WM if mobile else W
    pad = 16 if mobile else 22
    right = w - 4 - pad
    out, y = [], BODY_TOP + 6
    for i, (repo, (name, desc)) in enumerate(zip(repos, OSS)):
        top = y
        if i:
            out.append(hline(pad, right, top, RULE, "4 3"))
        forks = repo["forks_count"]
        meta = f"{(repo['language'] or 'markdown').upper()} · {forks} FORK{'' if forks == 1 else 'S'}"
        stars = str(repo["stargazers_count"])
        if mobile:
            base = top + 24
            out.append(text("mono-bold", stars, 13, pad, base, PHOSPHOR))
            sx = pad + width("mono-bold", stars, 13) + 10
            out.append(star(sx, base - 4.5, 6, PHOSPHOR))
            out.append(text("mono-bold", fit("mono-bold", name, 13, right - sx - 12), 13, sx + 12, base, IVORY))
            d, y = paragraph([(desc, style("mono", WARM))], 11.5, pad, base + 20, right - pad, 17)
            out.append(d)
            out.append(text("mono", meta, 9.5, pad, y + 1, MUTED, 0.12))
            y += 14
        else:
            base = top + 24
            col_star, col_name = pad + 40, pad + 66
            out.append(text("mono-bold", stars, 13, col_star, base, PHOSPHOR, anchor="end"))
            out.append(star(col_star + 10, base - 4.5, 6, PHOSPHOR))
            out.append(text("mono-bold", name, 13, col_name, base, IVORY))
            out.append(text("mono", meta, 9.5, right, base, MUTED, 0.12, "end"))
            out.append(text("mono", fit("mono", desc, 11, right - col_name), 11, col_name, base + 19, WARM))
            y = top + 52
    h = y + (4 if mobile else 6)
    title = "~/open-source" if mobile else "happyinhappy@happyin.work — ~/open-source"
    return panel(w, h, title, PHOSPHOR, True, out, "Open-source repositories: " + "; ".join(
        f"{name} — {desc}" for name, desc in OSS))


# --------------------------------------------------------------------------
# production.log: the home page's shipped / open-source window, as numbers
# --------------------------------------------------------------------------

def production_log(stars, mobile):
    w = WM if mobile else W
    px = 14 if mobile else 16
    groups = [
        ("shipped", [("4M+", "users of AI features shipped at Glam.ai"),
                     ("80×H200", "GPU training cluster I ran"),
                     ("1,500+", "active users of ois.gold")]),
        ("open-source", [(str(stars), "GitHub stars on public repos"),
                         ("1,287+", "reference articles on happyin.space"),
                         ("32K+", "readers reached on Habr")]),
    ]
    value_size = 22 if mobile else 27
    per_row = 3 if mobile else 6
    cell_w = (w - 4 - 2 * px) / per_row
    out, top, bottom = [], BODY_TOP + 16, 0

    def cell(cx, cy, value, caption, starred):
        out.append(text("mono-bold", fit("mono-bold", value, value_size, cell_w - 22), value_size, cx, cy,
                        LOG_GREEN))
        if starred:
            out.append(star(cx + width("mono-bold", value, value_size) + value_size * 0.45,
                            cy - value_size * 0.36, value_size * 0.33, LOG_GREEN))
        cap, end = paragraph([(caption.upper(), style("mono", "#555", tracking=0.08))], 9, cx, cy + 20,
                             cell_w - 14, 13.5, max_lines=None if mobile else 2)
        out.append(cap)
        return end

    for g, (title, cells) in enumerate(groups):
        if mobile:
            gx, gy = px, top
        else:
            gx, gy = px + g * 3 * cell_w, top
        out.append(runs([("▸ ", style("mono", "#000")), (title, style("mono-bold", "#000"))], 11, gx, gy + 12)[0])
        ends = [cell(gx + i * cell_w, gy + 12 + value_size + 10, v, c, title == "open-source" and i == 0)
                for i, (v, c) in enumerate(cells)]
        bottom = max(ends)
        if mobile:
            top = bottom + 8
            if g == 0:
                out.append(hline(px, w - 4 - px, bottom - 2, "#000", "1 0"))
    if not mobile:
        out.append(rect(px + 3 * cell_w - 12, top + 2, 1, bottom - top - 12, "#000"))
    h = bottom + (2 if mobile else 6)
    return panel(w, h, "production.log", WIN_PURPLE, False, out, "production.log — " + "; ".join(
        f"{v} {c}" for _, cells in groups for v, c in cells))


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


def stack(mobile):
    w = WM if mobile else W
    pad = 16 if mobile else 22
    size, lead = (12, 19) if mobile else (12.5, 21)
    out, y = [], BODY_TOP + pad + 6
    for tag, items in STACK:
        body, y = paragraph([(f"# {tag}.", style("mono", CAPTION)), (" " + items, style("mono", WARM))],
                            size, pad, y, w - 4 - 2 * pad, lead)
        out.append(body)
        y += 4 if mobile else 3
    h = y - lead + pad - 2
    title = "stack.md" if mobile else "happyinhappy@happyin.work — stack.md"
    return panel(w, h, title, PHOSPHOR, True, out, "Stack — " + "; ".join(f"{t}: {v}" for t, v in STACK))


# --------------------------------------------------------------------------
# as-featured.md: what others say (site-data.js testimonials)
# --------------------------------------------------------------------------

QUOTES = [
    ("“I had the pleasure of working with Anastasia and can confidently say she is an exceptional AI "
     "specialist with a rare combination of technical depth, versatility, and strong ownership. … Overall, "
     "she is someone who doesn't just understand AI, but knows how to apply it in a way that brings real "
     "value, while also supporting and elevating the people around her.”",
     "Nikita Blinkov", "Head of People & Org Dev @ Glam AI · worked together at Glam.ai"),
    ("“Both highly professional and innovative, each project has felt more like a genuine collaboration.”",
     "Paul Miller", "Senior Luxury High Jewellery & Timepiece Retoucher · client"),
]


def as_featured(mobile):
    w = WM if mobile else W
    px = 14 if mobile else 16
    q = style("times-italic", "#222")
    qsize, qlead = (14, 19.5) if mobile else (15, 21)
    out, y = [], BODY_TOP + 14 + 22
    out.append(text("serif-italic", "What others say", 22 if mobile else 26, px, y, "#000"))
    top = y + 28

    def quote(x, y, maxw, body, who, role):
        b, y = paragraph([(body, q)], qsize, x, y, maxw, qlead)
        out.append(b)
        y += 2
        out.append(text("mono-bold", who, 10.5, x, y, "#000"))
        r, y = paragraph([(role, style("mono", "#555"))], 9.5, x, y + 15, maxw, 13.5)
        out.append(r)
        return y - 13.5

    if mobile:
        iw = w - 4 - 2 * px
        y = quote(px, top, iw, *QUOTES[0])
        y += 16
        out.append(rect(px, y - 4, iw, 1, "#000"))
        y = quote(px, y + 18, iw, *QUOTES[1])
        h = y + 16
    else:
        left_w = 540
        rx = px + left_w + 28
        ly = quote(px, top, left_w, *QUOTES[0])
        ry = quote(rx, top, w - 4 - px - rx, *QUOTES[1])
        out.append(rect(rx - 14, top - 14, 1, max(ly, ry) - top + 14, "#000"))
        h = max(ly, ry) + 18
    return panel(w, h, "as-featured.md", WIN_RUST, False, out,
                 "What others say — " + "; ".join(f"{who}, {role}: {body}" for body, who, role in QUOTES))


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

def taskbar(mobile):
    w, h, size = (WM if mobile else W), 34, 11
    svg = Svg(w, h, "happyin.work taskbar — agents.txt")
    out = [rect(0, 0, w, h, PANEL), rect(0, 0, w, 1, RULE), text("mono", "◆", size, 16, 21.5, PHOSPHOR)]
    x = 34
    tabs = ["github", "agents.txt"] if mobile else [
        "github", "README.md", "projects/", "open-source/", "production.log", "agents.txt"]
    for i, tab in enumerate(tabs):
        tw = width("mono", tab, size) + 20
        if i == 0:
            out.append(rect(x, 7, tw, 20, RULE))
            fill = IVORY
        else:
            out.append(rect(x + 0.5, 7.5, tw - 1, 19, "none", f' stroke="{RULE}"'))
            fill = GRASS if tab == "agents.txt" else MUTED
        out.append(text("mono", tab, size, x + 10, 21, fill))
        x += tw + 8
    out.append(text("mono", "uptime: since 2023", size, w - 34, 21, MUTED, anchor="end"))
    out.append(rect(w - 25, 10, 9, 14, PHOSPHOR)[:-2] +
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
    ("ois-gold", "ois.gold", "Jewellery retouching SaaS · sole tech lead",
     "End-to-end SaaS for jewellery image processing. CV pipeline for 6K-10K pixel images, "
     "1,500+ active users.", "#e0d090", WIN_RUST),
]

BUTTONS = [("happyin.work →", True), ("happyin.space", False), ("linkedin", False),
           ("telegram", False), ("habr", False)]

LABELS = [("bio", "cat bio.md"), ("production", "ls ~/projects/production"),
          ("open-source", "ls ~/projects/open-source"), ("log", "tail production.log"),
          ("stack", "cat stack.md"), ("featured", "cat as-featured.md"), ("contacts", "cat contacts.txt")]


def github(path):
    req = urllib.request.Request(f"https://api.github.com/{path}",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": f"{USER}-profile"})
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def write(name, content):
    path = os.path.join(OUT, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    print(f"{name:34s} {len(content) / 1024:6.1f} KB")


def main():
    repos = [r for r in github(f"users/{USER}/repos?per_page=100&type=owner") if not r["private"] and not r["fork"]]
    by_name = {r["name"]: r for r in repos}
    missing = [name for name, _ in OSS if name not in by_name]
    if missing:
        raise SystemExit(f"not public on {USER}: {', '.join(missing)}")
    stars = sum(r["stargazers_count"] for r in repos)
    showcase = [by_name[name] for name, _ in OSS]

    for slug, cmd in LABELS:
        write(f"label-{slug}.svg", label(cmd))
    for text_, primary in BUTTONS:
        write(f"button-{re.sub(r'[^a-z0-9]+', '-', text_.lower()).strip('-')}.svg", button(text_, primary))

    # equal-height windows: measure every card, then draw all at the tallest
    tallest = max(project_card(p, i % 2)[1] for i, p in enumerate(PRODUCTION))
    for i, p in enumerate(PRODUCTION):
        write(f"project-{p[0]}.svg", project_card(p, i % 2, body_h=tallest)[0])

    for mobile, prefix in [(False, ""), (True, "mobile/")]:
        write(f"{prefix}header.svg", header(mobile))
        write(f"{prefix}open-source.svg", open_source(showcase, mobile))
        write(f"{prefix}production-log.svg", production_log(stars, mobile))
        write(f"{prefix}stack.svg", stack(mobile))
        write(f"{prefix}as-featured.svg", as_featured(mobile))
        write(f"{prefix}taskbar.svg", taskbar(mobile))
    print(f"stars: {stars} across {len(repos)} public repositories")


if __name__ == "__main__":
    main()
