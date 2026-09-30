"""Shape text with HarfBuzz and place it as SVG glyph outlines.

GitHub shows README images through its camo proxy as plain <img> SVGs, and an
<img> SVG cannot load a webfont, so every letter here ships as an outline in
the faces happyin.work uses: JetBrains Mono, Instrument Serif italic for
window headings, and a Times-metric serif (Tinos) for running text.

Each glyph is drawn once, in font units, into the document's <defs>; a run of
text is one scaled group of <use> references. That keeps a text-heavy card
at a fraction of the size of inlining every letter's path.
"""

import os
from functools import lru_cache

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen

FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# face name -> (file, variation axes, id prefix); the site loads JetBrains Mono at 400/700
FACES = {
    "mono": ("JetBrainsMono[wght].ttf", {"wght": 400}, "m"),
    "mono-bold": ("JetBrainsMono[wght].ttf", {"wght": 700}, "b"),
    "serif-italic": ("InstrumentSerif-Italic.ttf", {}, "i"),  # RHead: window headings
    "times": ("Tinos-Regular.ttf", {}, "t"),  # running text the site sets in `Times, serif`
    "times-italic": ("Tinos-Italic.ttf", {}, "u"),
}

# Glyphs placed since the last glyph_defs() call: one document at a time.
_placed = {}


@lru_cache(maxsize=None)
def _font(face):
    file, axes, _ = FACES[face]
    hb_face = hb.Face(hb.Blob.from_file_path(os.path.join(FONTS, file)))
    font = hb.Font(hb_face)
    if axes:
        font.set_variations(axes)
    return font, hb_face.upem


@lru_cache(maxsize=None)
def _outline(face, gid):
    font, _ = _font(face)
    pen = SVGPathPen(None, ntos=lambda v: str(round(v)))
    font.draw_glyph_with_pen(gid, pen)
    return pen.getCommands()


def _shape(face, text):
    font, upem = _font(face)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf)
    for info in buf.glyph_infos:
        if info.codepoint == 0:
            raise ValueError(f"{face} has no glyph for {text[info.cluster]!r} in {text!r}")
    return upem, buf


def _num(v, places):
    return f"{v:.{places}f}".rstrip("0").rstrip(".") or "0"


def typeset(face, text, size, x=0.0, y=0.0, tracking=0.0, attrs=""):
    """Return (markup, advance) for `text` with its baseline at y.

    `tracking` is letter-spacing in em, as in the site's CSS; it goes between
    glyphs, not after the last one. `attrs` lands on the run's group.
    """
    upem, buf = _shape(face, text)
    prefix = FACES[face][2]
    scale = size / upem
    uses, cursor = [], 0.0
    last = len(buf.glyph_infos) - 1
    for i, (info, pos) in enumerate(zip(buf.glyph_infos, buf.glyph_positions)):
        d = _outline(face, info.codepoint)
        if d:
            key = f"{prefix}{info.codepoint}"
            _placed[key] = d
            gx, gy = round(cursor + pos.x_offset), round(pos.y_offset)
            uses.append(f'<use href="#{key}" x="{gx}"' + (f' y="{gy}"' if gy else "") + "/>")
        cursor += pos.x_advance + (tracking * upem if i < last else 0)
    markup = (f'<g transform="matrix({_num(scale, 6)} 0 0 {_num(-scale, 6)} {_num(x, 2)} {_num(y, 2)})"{attrs}>'
              f'{"".join(uses)}</g>') if uses else ""
    return markup, cursor * scale


def width(face, text, size, tracking=0.0):
    upem, buf = _shape(face, text)
    adv = sum(p.x_advance for p in buf.glyph_positions)
    return (adv + tracking * upem * max(len(buf.glyph_positions) - 1, 0)) * size / upem


def glyph_defs():
    """<path> definitions for every glyph placed since the last call, then forget them."""
    out = "".join(f'<path id="{k}" d="{d}"/>' for k, d in sorted(_placed.items()))
    _placed.clear()
    return out
