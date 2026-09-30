"""Download the two typefaces happyin.work uses into tools/fonts/.

Both come from google/fonts at a pinned commit and are checked against a
SHA-256, so a rebuild months later typesets from exactly the same outlines.
"""

import hashlib
import os
import sys
import urllib.request

FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
RAW = "https://raw.githubusercontent.com/google/fonts"

# (commit, path in google/fonts, local name, sha256)
PINNED = [
    ("6e4b84c976cadb3c49a40fd9a1c203e4f7fcf2da", "ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
     "JetBrainsMono[wght].ttf",
     "48715a42ec242c21e9f02692891e147d022299a52e48d5e413e1a942193ffeda"),
    ("0b58fb370093f9a9f4ff785d94405710b79de67c", "ofl/instrumentserif/InstrumentSerif-Regular.ttf",
     "InstrumentSerif-Regular.ttf",
     "498efd461f6ddfcb7a111bf9a565709d2085d48201d501ead960d93e84ffbb88"),
    ("0b58fb370093f9a9f4ff785d94405710b79de67c", "ofl/instrumentserif/InstrumentSerif-Italic.ttf",
     "InstrumentSerif-Italic.ttf",
     "08939b8bdf534afec24ae0ef5e03f948940cd9a8fe08e7fecbad040e62327385"),
]


def main():
    os.makedirs(FONTS, exist_ok=True)
    bad = 0
    for commit, src, name, want in PINNED:
        dst = os.path.join(FONTS, name)
        if not os.path.exists(dst):
            with urllib.request.urlopen(f"{RAW}/{commit}/{src}", timeout=60) as r:
                data = r.read()
            with open(dst, "wb") as fh:
                fh.write(data)
        with open(dst, "rb") as fh:
            got = hashlib.sha256(fh.read()).hexdigest()
        ok = got == want
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {name:32s} {got}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
