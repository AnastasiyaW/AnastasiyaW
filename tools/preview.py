"""Render README.md the way GitHub will, to look at it before pushing.

The README goes through GitHub's Markdown API in "markdown" mode (the one
README files get; "gfm" would turn every newline into a <br>) and is
wrapped in github-markdown-css at the width of a profile README column,
once light and once dark. Output: preview/index.html (gitignored).

    python tools/preview.py
    python -m http.server 8765        # from the repo root, then open /preview/
"""

import json
import os
import re
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = "https://cdn.jsdelivr.net/npm/github-markdown-css@5.8.1/github-markdown-{}.css"
ARTICLE = 846  # the profile README's article width at a 1280px window

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AnastasiyaW profile preview</title>
<link rel="stylesheet" href="{light}"><link rel="stylesheet" href="{dark}" media="none" id="dark">
<style>
body{{margin:0;background:#f6f8fa;font:14px system-ui}} .bar{{padding:10px 16px}}
.frame{{max-width:{w}px;margin:0 auto 40px;padding:24px;border:1px solid #d0d7de;border-radius:6px;background:#fff}}
.markdown-body.dark{{color-scheme:dark}} .dk .frame{{background:#0d1117;border-color:#30363d}} .dk{{background:#010409;color:#e6edf3}}
</style></head><body>
<div class="bar"><label><input type="checkbox" id="t"> dark</label></div>
<div class="frame"><article class="markdown-body">{body}</article></div>
<script>
const t=document.getElementById('t'),d=document.getElementById('dark'),l=document.querySelector('link');
function set(on){{t.checked=on;d.media=on?'all':'none';l.media=on?'none':'all';document.body.classList.toggle('dk',on)}}
t.onchange=()=>set(t.checked);set(location.hash==='#dark');
</script></body></html>
"""


def render(markdown):
    req = urllib.request.Request(
        "https://api.github.com/markdown",
        data=json.dumps({"text": markdown, "mode": "markdown", "context": "AnastasiyaW/AnastasiyaW"}).encode(),
        headers={"Accept": "application/vnd.github+json", "User-Agent": "AnastasiyaW-profile"})
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def main():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        html = render(fh.read())
    # the API points images at the not-yet-pushed repo; serve the local build instead
    html = re.sub(r'(src|srcset)="(?:https://github\.com/AnastasiyaW/AnastasiyaW/(?:raw|blob)/[^/]+/)?assets/',
                  lambda m: f'{m.group(1)}="../assets/', html)
    out = os.path.join(ROOT, "preview")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(PAGE.format(light=CSS.format("light"), dark=CSS.format("dark"), w=ARTICLE, body=html))
    print(os.path.join(out, "index.html"))


if __name__ == "__main__":
    main()
