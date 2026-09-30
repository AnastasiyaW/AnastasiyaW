"""Refresh tools/kb-stats.json: the happyin.space numbers the knowledge-base window shows.

Page views come from Cloudflare's zone analytics for happyin.space: every HTML
page served, to people and to AI agents alike. The knowledge base is written for
agents first, so their reads are its audience, not noise. Article and domain
counts come from the public AnastasiyaW/knowledge-space tree.

Auth: CLOUDFLARE_API_TOKEN (Analytics Read on the zone), or else
CLOUDFLARE_GLOBAL_API_EMAIL + CLOUDFLARE_GLOBAL_API_KEY, from the environment.

    python tools/kb_stats.py
"""

import datetime as dt
import json
import os
import sys
import urllib.request
from collections import defaultdict

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kb-stats.json")
HOST, REPO = "happyin.space", "AnastasiyaW/knowledge-space"


def cloudflare_headers():
    if os.environ.get("CLOUDFLARE_API_TOKEN"):
        return {"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}"}
    if os.environ.get("CLOUDFLARE_GLOBAL_API_EMAIL") and os.environ.get("CLOUDFLARE_GLOBAL_API_KEY"):
        return {"X-Auth-Email": os.environ["CLOUDFLARE_GLOBAL_API_EMAIL"],
                "X-Auth-Key": os.environ["CLOUDFLARE_GLOBAL_API_KEY"]}
    raise SystemExit("set CLOUDFLARE_API_TOKEN, or CLOUDFLARE_GLOBAL_API_EMAIL and CLOUDFLARE_GLOBAL_API_KEY")


def fetch(url, headers, body=None):
    req = urllib.request.Request(url, headers={**headers, "Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def daily_page_views(headers):
    zone = fetch(f"https://api.cloudflare.com/client/v4/zones?name={HOST}", headers)["result"][0]
    start = dt.date.fromisoformat(zone["created_on"][:10])
    today = dt.date.today()
    query = """query($z: String!, $from: Date!, $to: Date!) { viewer { zones(filter: {zoneTag: $z}) {
      httpRequests1dGroups(limit: 100, filter: {date_geq: $from, date_leq: $to}) {
        dimensions { date } sum { pageViews } } } } }"""
    days = {}
    lo = start
    while lo <= today:  # 90-day windows keep each query inside the plan's range limit
        hi = min(lo + dt.timedelta(days=89), today)
        out = fetch("https://api.cloudflare.com/client/v4/graphql", headers,
                    {"query": query, "variables": {"z": zone["id"], "from": lo.isoformat(), "to": hi.isoformat()}})
        if out.get("errors"):
            raise SystemExit(f"Cloudflare GraphQL: {out['errors']}")
        for row in out["data"]["viewer"]["zones"][0]["httpRequests1dGroups"]:
            days[row["dimensions"]["date"]] = row["sum"]["pageViews"]
        lo = hi + dt.timedelta(days=1)
    return start, today, days


def article_counts():
    tree = fetch(f"https://api.github.com/repos/{REPO}/git/trees/HEAD?recursive=1",
                 {"Accept": "application/vnd.github+json", "User-Agent": "AnastasiyaW-profile"})
    if tree.get("truncated"):
        raise SystemExit("GitHub tree listing was truncated; counts would be wrong")
    docs = [e["path"].split("/") for e in tree["tree"] if e["type"] == "blob"
            and e["path"].startswith("docs/") and e["path"].endswith(".md")]
    articles = [p for p in docs if len(p) >= 3 and p[-1] != "index.md"]
    return len(articles), len({p[1] for p in articles})


def main():
    start, today, days = daily_page_views(cloudflare_headers())
    months = defaultdict(int)
    for day, views in days.items():
        months[day[:7]] += views
    last30 = sum(v for d, v in days.items() if dt.date.fromisoformat(d) > today - dt.timedelta(days=30))
    articles, domains = article_counts()
    stats = {
        "_source": f"Cloudflare zone analytics for {HOST} (httpRequests1dGroups.pageViews: people and AI agents); "
                   f"article counts from {REPO} docs/",
        "as_of": today.isoformat(), "since": start.isoformat(),
        "page_views_total": sum(days.values()), "page_views_30d": last30,
        "months": sorted(months.items()), "articles": articles, "domains": domains,
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(stats, fh, indent=1)
        fh.write("\n")
    print(json.dumps(stats, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
