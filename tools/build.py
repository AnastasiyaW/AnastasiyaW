"""Build the SVG artwork for the AnastasiyaW GitHub profile README.

Everything here quotes happyin.work. Colours and type come from the site's
pages/_assets/UI-KIT-REFERENCE.md, shapes from page-shell.jsx: the pixel
starfield (CosmosBG), the striped Mac title bar, the Win 3.1 windows with a
3px accent strip and a hard black shadow, the `$` prompts and the menu bar.
Copy is the site's own (tools/happyin-copy.json); the knowledge-base numbers
come from the snapshot tools/kb_stats.py writes, and the model count from the
Hugging Face API on every build.

Type ships as outlines: GitHub serves README images through camo as <img>,
and an <img> SVG cannot load webfonts. Desktop artwork is drawn 900px wide,
which GitHub's profile column shows at about 0.94. A second set in
assets/mobile/ is drawn 420px wide for phones, where the README swaps it in
with <picture><source media="(max-width: 600px)">: desktop art scaled to a
phone would put body text at 5px. (GitHub's Markdown API pulls the <img> out
of a linked <picture>, but github.com itself keeps it, so the local preview
cannot show the phone set.)

    python tools/fetch_fonts.py
    uv run --no-project --with fonttools --with uharfbuzz python tools/build.py
"""

import datetime as dt
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

# UI-KIT-REFERENCE.md colour tokens, plus the literals page-shell.jsx uses
VOID, PANEL, RULE = "#0a0907", "#14130f", "#2a2720"
IVORY, WARM, MUTED, CAPTION = "#e8e4d4", "#c4baa3", "#a99c82", "#6b6558"
PHOSPHOR = "#ff5b1f"
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


NBSP, SEP = " ", " · "


def unbreakable_list(s):
    """`a b · c d` -> items that never split, a separator glued to the item before it.

    The site's copy strings lists with " · ". Wrapping one inside an item, or
    starting a line with "·", reads as broken; so each item holds together, the
    line may only break after a separator, and wrap() drops a separator that
    lands at the end of a line."""
    def glue(item):  # only the spaces inside an item; its edges still break
        core = item.strip(" ")
        head, tail = item[:len(item) - len(item.lstrip(" "))], item[len(item.rstrip(" ")):]
        return head + core.replace(" ", NBSP) + tail

    return (NBSP + "· ").join(glue(item) for item in s.split(SEP)) if SEP in s else s


def wrap(parts, size, maxw, rest_maxw=None):
    """Greedy word wrap over styled runs; returns a list of run lists.

    `rest_maxw` narrows every line after the first (a hanging indent)."""
    rest_maxw = maxw if rest_maxw is None else rest_maxw
    narrowest = min(maxw, rest_maxw)
    words, cur = [], []
    for s, st in parts:
        for piece in re.split(r"( )", unbreakable_list(s)):
            if piece == " ":
                words.append((cur, (" ", st)))
                cur = []
            elif piece:
                cur.append((piece, st))
    if cur:
        words.append((cur, None))

    def close(line):
        if line[-1][0] == " ":
            line.pop()
        s, st = line[-1]
        if s.endswith(NBSP + "·"):
            line[-1] = (s[:-2], st)
        lines.append(line)

    def measure(toks):
        return sum(width(st["face"], s, size, st.get("tracking", 0.0)) for s, st in toks)

    # a list item wider than the whole line breaks at its own spaces after all
    split = []
    for toks, space in words:
        if len(toks) == 1 and NBSP in toks[0][0] and measure(toks) > narrowest:
            s, st = toks[0]
            parts_ = s.split(NBSP)
            if parts_[-1] == "·":
                parts_[-2:] = [parts_[-2] + NBSP + "·"]
            split += [([(p, st)], (" ", st)) for p in parts_[:-1]] + [([(parts_[-1], st)], space)]
        else:
            split.append((toks, space))

    lines, line, lw = [], [], 0.0
    for toks, space in split:
        ww = measure(toks)
        limit = rest_maxw if lines else maxw
        if ww > narrowest:
            raise SystemExit(f"{''.join(s for s, _ in toks)!r} is {ww:.0f}px and cannot wrap into {narrowest:.0f}px")
        if line and lw + ww > limit:
            close(line)
            line, lw = [], 0.0
        line.extend(toks)
        lw += ww
        if space:
            line.append(space)
            lw += width(space[1]["face"], " ", size)
    if line:
        close(line)
    return lines


def paragraph(parts, size, x, y, maxw, lead, max_lines=None, hang=0.0):
    """Wrapped styled runs, first baseline at y; returns (markup, next_y).

    `hang` indents every line after the first (a `# tag.` line's text column)."""
    lines = wrap(parts, size, maxw, maxw - hang)
    if max_lines and len(lines) > max_lines:
        raise SystemExit(f"{''.join(s for s, _ in parts)!r} wraps to {len(lines)} lines, allowed {max_lines}")
    out = []
    for i, line in enumerate(lines):
        out.append(runs(line, size, x + (hang if i else 0), y)[0])
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
    out.append(prompt("uptime", size, ix, y))
    y += lead
    up, y = paragraph([("20+ years in graphics · 4+ years of neural networks for images",
                        style("mono", IVORY))], size, ix + 14, y, iw - 14, lead)
    out.append(up)
    y += 22 + head * 0.78 - lead
    out.append(runs([(">_", style("mono-bold", PHOSPHOR)), (" Anastasiia Butova", style("mono-bold", IVORY))],
                    head, ix, y)[0])
    y += 24
    sub, y = paragraph([("image-processing pipelines · diffusion models · Belgrade, Serbia", style("mono", MUTED))],
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
    # the site's production facts, one per line (RList) so they read the same at every width
    y += 2
    for fact in ["production AI for 4M+ users", "80×H200 GPU cluster", "custom CNN/U-Net training",
                 "32K+ Habr reach"]:
        out.append(runs([("▸ ", style("mono", "#555")), (fact, style("mono", "#000"))], 11, ix, y)[0])
        y += 17
    y -= 6
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
    probe = Svg(w, 0, "")  # collects defs while the windows are measured
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
    if not mobile:  # side by side: both windows end on the same line, as on the site
        term_end = readme_end = max(term_end, readme_end)
    H = int(max(term_end, readme_end) + (18 if mobile else 30))

    svg = Svg(w, H, "Anastasiia Butova — ComfyUI specialist; 20+ years in graphics, 4+ years of neural networks "
                    "for images; image-processing pipelines, diffusion models. Belgrade, Serbia. happyin.work")
    svg.defs = probe.defs
    svg.add(rect(0, 0, w, H, VOID), cosmos(svg, w, H, seed=1440, count=45 if mobile else 90), menu, cr)
    before, after = window(svg, pad, y0, term_w, term_end - y0, "happyinhappy@happyin.work — github",
                           PHOSPHOR, VOID, 0.62)
    svg.add(before, term_inner, after)
    before, after = window(svg, win_x, win_y, win_w, readme_end - win_y, "README.md", WIN_BLUE)
    svg.add(before, readme_inner, after)
    return svg.render()


# --------------------------------------------------------------------------
# Production work: one Win 3.1 window per project, two per row
# --------------------------------------------------------------------------

def project_card(project, side, mobile, body_h=None):
    """Half of a two-up row. The image is half the column; the right card is
    inset so both windows are equal and the right one ends exactly where the
    full-width panels end (x = total - 4). The phone card keeps the name and
    the kicker and drops the blurb, which could not be read at that size."""
    slug, name, kicker, blurb, swatch, accent = project
    total = WM if mobile else W
    half = total // 2
    gap = 8 if mobile else 10
    inset = (gap - 4) / 2
    ww = half - 4 - inset
    x0 = inset if side else 0
    px = 12 if mobile else 16
    ix, iw = x0 + px, ww - 2 * px

    out, y = [], BODY_TOP + (10 + 18 if mobile else 14 + 22)
    out.append(rect(ix, y - (12 if mobile else 14), 10, 9, swatch, ' stroke="#000"'))
    out.append(text("serif-italic", name, 21 if mobile else 26, ix + 17, y, "#000"))
    y += 17 if mobile else 21
    k, y = paragraph([(kicker.upper(), style("mono", "#555", tracking=0.08))], 10.5, ix, y, iw,
                     15 if mobile else 15.5)
    out.append(k)
    if not mobile:
        y += 7
        b, y = paragraph([(blurb, style("times", "#111"))], 15.5, ix, y, iw, 21)
        out.append(b)
    content_end = y
    if body_h is not None:
        y = BODY_TOP + body_h
    y += 4
    out.append(hline(ix, ix + iw, y, "#ccc", "1 2"))
    y += 16
    if mobile:
        out.append(text("mono", "[enter →]", 10.5, ix, y, WIN_GREEN))
    else:
        out.append(runs([("▸ ", style("mono", "#000")),
                         (f"happyin.work/{slug}/", style("mono", WIN_BLUE, underline=True))], 10.5, ix, y)[0])
        out.append(text("mono", "[enter →]", 10.5, ix + iw, y, WIN_GREEN, anchor="end"))
    h = y + (10 if mobile else 12)

    # no bottom margin: the shadow plus the inline image's line gap make the row gap
    svg = Svg(half, h + 3, f"{name} — {kicker}. {blurb}")
    before, after = window(svg, x0, 0, ww, h, f"{slug}.md", accent)
    svg.add(before, *out, after)
    return svg.render(), content_end - BODY_TOP


# --------------------------------------------------------------------------
# happyin.space: the knowledge base and its reach, month by month
# --------------------------------------------------------------------------

MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
KB_SWATCH = "#f0e3a0"  # the site's projects/ list colour for happyin.space


def compact(v):
    """241741 -> '241K', 2239 -> '2.2K'. Rounded down, so a figure never claims more than was counted."""
    v = int(v)
    if v >= 10_000:
        return f"{v // 1000}K"
    return f"{v // 100 / 10:g}K" if v >= 1000 else str(v)


def bars(x, y, w, h, months, as_of):
    """Monthly page views as the site would draw them: flat bars, 1px black edge."""
    out, months = [], months[-12:]
    top_label, bottom_label = 16, 18
    base = y + h - bottom_label
    tallest = max(v for _, v in months)
    slot = w / len(months)
    bar_w = min(slot * 0.56, 44)
    for i, (ym, views) in enumerate(months):
        year, month = int(ym[:4]), int(ym[5:])
        days = (dt.date(year + month // 12, month % 12 + 1, 1) - dt.timedelta(days=1)).day
        partial = (year, month) == (as_of.year, as_of.month) and as_of.day < days
        bh = (h - top_label - bottom_label - 4) * views / tallest
        cx = x + slot * i + slot / 2
        out.append(rect(cx - bar_w / 2, base - bh, bar_w, bh, LOG_GREEN,
                        ' stroke="#000"' + (' fill-opacity="0.45"' if partial else "")))
        out.append(text("mono", compact(views), 9.5, cx, base - bh - 5, "#000", anchor="middle"))
        out.append(text("mono", MONTHS[month - 1], 9, cx, base + 14, "#555", 0.08, "middle"))
    out.append(rect(x, base, w, 1, "#000"))
    return "".join(out)


def knowledge_base(stats, kb, mobile):
    w = WM if mobile else W
    px = 14 if mobile else 16
    inner = w - 4 - 2 * px
    col_w = inner if mobile else 420
    out, y = [], BODY_TOP + 14 + 24
    out.append(rect(px, y - 15, 10, 9, KB_SWATCH, ' stroke="#000"'))
    out.append(text("serif-italic", "happyin.space", 24 if mobile else 30, px + 17, y, "#000"))
    y += 21
    articles = stats["articles"] // 100 * 100
    kicker = f"knowledge base · {articles:,}+ articles · {stats['domains']} domains"
    k, y = paragraph([(kicker.upper(), style("mono", "#555", tracking=0.08))], 10.5, px, y, col_w, 15.5)
    out.append(k)
    y += 7
    b, y = paragraph([(kb["blurb"], style("times", "#111"))], 15.5, px, y, col_w, 21)
    out.append(b)

    since = dt.date.fromisoformat(stats["since"])
    # the daily average, not the 30-day sum: at a month's end that sum is the last bar's label again
    cells = [(compact(stats["page_views_total"]), f"page views since {MONTHS[since.month - 1].title()} {since.year}"),
             (compact(stats["page_views_30d"] / 30), "page views a day, last 30 days")]
    vy, ends = y + 32, []
    for i, (value, caption) in enumerate(cells):
        cx = px + i * col_w / 2
        out.append(text("mono-bold", value, 32 if not mobile else 28, cx, vy, LOG_GREEN))
        cap, end = paragraph([(caption.upper(), style("mono", "#555", tracking=0.08))], 9, cx, vy + 19,
                             col_w / 2 - 16, 13.5, max_lines=2)
        out.append(cap)
        ends.append(end)
    left_end = max(ends) - 13.5

    note = "page views per month · Cloudflare · people and AI agents"
    if mobile:
        chart_y, chart_h = left_end + 22, 118
        out.append(bars(px, chart_y, inner, chart_h, stats["months"], dt.date.fromisoformat(stats["as_of"])))
        n_, bottom = paragraph([(note.upper(), style("mono", "#555", tracking=0.08))], 9, px, chart_y + chart_h + 16,
                               inner, 13.5)
        out.append(n_)
        bottom -= 13.5
    else:
        cx0 = px + col_w + 44
        chart_y = BODY_TOP + 18
        chart_h = max(left_end - 18 - chart_y, 130)  # its caption shares the numbers' last caption line
        out.append(rect(cx0 - 22, BODY_TOP + 16, 1, chart_h + 22, "#000"))
        out.append(bars(cx0, chart_y, w - 4 - px - cx0, chart_h, stats["months"],
                        dt.date.fromisoformat(stats["as_of"])))
        out.append(text("mono", note.upper(), 9, cx0, chart_y + chart_h + 18, "#555", 0.08))
        bottom = max(left_end, chart_y + chart_h + 18)

    y = bottom + 14
    out.append(hline(px, w - 4 - px, y, "#ccc", "1 2"))
    y += 16
    out.append(runs([("▸ ", style("mono", "#000")), ("happyin.space", style("mono", WIN_BLUE, underline=True))],
                    10.5, px, y)[0])
    out.append(text("mono", "[enter →]", 10.5, w - 4 - px, y, WIN_GREEN, anchor="end"))
    h = y + 12
    label = (f"happyin.space — knowledge base, {articles:,}+ articles in {stats['domains']} domains. "
             f"{stats['page_views_total']:,} page views since {stats['since']} and {stats['page_views_30d']:,} "
             f"in the 30 days to {stats['as_of']} (Cloudflare; people and AI agents).")
    return panel(w, h, "knowledge-base.md", WIN_GREEN, False, out, label)


# --------------------------------------------------------------------------
# stack.md: the site's `# tag.` lines (THash), closing on the open models
# --------------------------------------------------------------------------

def stack(models, mobile):
    w = WM if mobile else W
    pad = 16 if mobile else 22
    size, lead = (12, 19) if mobile else (12.5, 21)
    lines = STACK + [("huggingface", f"{len(models)} open models on huggingface.co/{HF['user']} · {HF['summary']}")]
    out, y = [], BODY_TOP + pad + 6
    for tag, items in lines:
        body, y = paragraph([(f"# {tag}.", style("mono", CAPTION)), (" " + items, style("mono", WARM))],
                            size, pad, y, w - 4 - 2 * pad, lead, hang=width("mono", f"# {tag}. ", size))
        out.append(body)
        y += 4 if mobile else 3
    h = y - lead + pad - 2
    title = "stack.md" if mobile else "happyinhappy@happyin.work — stack.md"
    return panel(w, h, title, PHOSPHOR, True, out, "Stack — " + "; ".join(f"{t}: {v}" for t, v in lines))


# --------------------------------------------------------------------------

# The site's copy is data, not code: happyin-copy.json (sources named inside).
with open(os.path.join(HERE, "happyin-copy.json"), encoding="utf-8") as _fh:
    COPY = json.load(_fh)

# swatch (the site's projects/ list) and window accent, in the order of COPY["production"]
CARD_COLOURS = [("#ffd0a0", WIN_BLUE), ("#c0d8f0", WIN_GREEN), ("#f0c0d0", WIN_PURPLE), ("#e0d090", WIN_RUST)]
PRODUCTION = [(p["slug"], p["name"], p["kicker"], p["blurb"], *colours)
              for p, colours in zip(COPY["production"], CARD_COLOURS, strict=True)]
STACK = [tuple(x) for x in COPY["stack"]]
KB, HF = COPY["knowledge_base"], COPY["huggingface"]


def write(name, content):
    path = os.path.join(OUT, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    print(f"{name:34s} {len(content) / 1024:6.1f} KB")


def main():
    # tools/kb_stats.py refreshes this snapshot; the build itself needs no Cloudflare access
    with open(os.path.join(HERE, "kb-stats.json"), encoding="utf-8") as fh:
        kb_stats = json.load(fh)
    req = urllib.request.Request(f"https://huggingface.co/api/models?author={HF['user']}&limit=100",
                                 headers={"User-Agent": "AnastasiyaW-profile"})
    with urllib.request.urlopen(req, timeout=30) as r:
        models = [m for m in json.load(r) if not m.get("private")]
    if not models:
        raise SystemExit(f"no public models found for huggingface.co/{HF['user']}")

    for mobile, prefix in [(False, ""), (True, "mobile/")]:
        write(f"{prefix}header.svg", header(mobile))
        # equal-height windows: measure every card, then draw all at the tallest
        tallest = max(project_card(p, i % 2, mobile)[1] for i, p in enumerate(PRODUCTION))
        for i, p in enumerate(PRODUCTION):
            write(f"{prefix}project-{p[0]}.svg", project_card(p, i % 2, mobile, body_h=tallest)[0])
        write(f"{prefix}knowledge-base.svg", knowledge_base(kb_stats, KB, mobile))
        write(f"{prefix}stack.svg", stack(models, mobile))
    print(f"knowledge base as of {kb_stats['as_of']}; {len(models)} public models on Hugging Face")


if __name__ == "__main__":
    main()
