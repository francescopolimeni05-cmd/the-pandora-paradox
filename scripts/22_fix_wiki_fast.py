#!/usr/bin/env python3
"""
22_fix_wiki_fast.py — fast, Wikipedia-ONLY pageviews fix.

The original collector sometimes locked onto the '(YYYY film)' redirect (84
views/mo) instead of the canonical bare-title article (millions) — e.g. Inception,
Fight Club, Interstellar. The repo's fix_wiki_views_bulk.py also re-does OMDb +
Wikiquote per film (4 network calls each) and is slow/fragile. This script ONLY
re-queries pageviews for suspect films, tries several title candidates, keeps the
HIGHEST, and is error-tolerant (one bad film never aborts the run).

Updates BOTH live_api_data.json and extended_api_data.json in place.

  python scripts/22_fix_wiki_fast.py --threshold 300000
  python scripts/12_merge_and_build.py build
"""
from __future__ import annotations
import argparse, json, re, time
from pathlib import Path
from urllib.parse import quote
import requests

DATA = Path(__file__).resolve().parents[1] / "data"
HEADERS = {"User-Agent": "PandoraParadox/1.0 (academic research)"}
START, END = "2023040100", "2026040100"   # 3-year monthly window


def search_titles(clean: str, year) -> list[str]:
    """Ask Wikipedia's search API for the ACTUAL article titles for this film,
    instead of guessing the disambiguation suffix. Returns underscored titles."""
    out = []
    for q in (f"{clean} {year} film", f"{clean} film"):
        for attempt in range(3):
            try:
                time.sleep(0.2 * (attempt + 1))
                r = requests.get("https://en.wikipedia.org/w/api.php",
                                 params={"action": "query", "list": "search",
                                         "srsearch": q, "srlimit": 3, "format": "json"},
                                 headers=HEADERS, timeout=30)
                if r.status_code != 200:
                    time.sleep(1.0); continue
                for hit in r.json().get("query", {}).get("search", []):
                    t = hit.get("title", "").replace(" ", "_")
                    if t and t not in out:
                        out.append(t)
                break
            except requests.RequestException:
                time.sleep(1.0)
    return out


def candidates(title: str, year) -> list[str]:
    base = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
    clean_us = base.replace(" ", "_")
    # guessed forms first (cheap), then real article titles from Wikipedia search
    cs = [clean_us, f"{clean_us}_({year}_film)", f"{clean_us}_(film)", f"{clean_us}_({year})"]
    cs += search_titles(base, year)
    seen, out = set(), []
    for c in cs:
        if c and c not in seen:
            seen.add(c); out.append(c)
    return out


def best_pageviews(title: str, year) -> dict | None:
    best = None
    for cand in candidates(title, year):
        enc = quote(cand, safe="_():,!–-")
        url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
               f"en.wikipedia/all-access/all-agents/{enc}/monthly/{START}/{END}")
        items = None
        for attempt in range(4):                      # retry transient Wikimedia errors
            try:
                time.sleep(0.25 * (attempt + 1))
                r = requests.get(url, headers=HEADERS, timeout=30)
                if r.status_code == 404:              # this title simply doesn't exist
                    items = []
                    break
                if r.status_code != 200:              # 429/5xx → back off and retry
                    time.sleep(1.5 * (attempt + 1))
                    continue
                items = r.json().get("items", [])
                break
            except requests.RequestException:
                time.sleep(1.0 * (attempt + 1))
        if not items:
            continue
        views = [d.get("views", 0) for d in items]
        total = sum(views)
        if best is None or total > best["total_views"]:
            best = {"status": "success", "wiki_title_used": cand,
                    "total_views": total,
                    "average_monthly_views": total / len(views),
                    "max_monthly_views": max(views), "min_monthly_views": min(views),
                    "views_count": len(items)}
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=int, default=300000,
                    help="refetch films with current wiki total_views below this")
    args = ap.parse_args()

    files = {f: json.load((DATA / f).open()) for f in
             ("live_api_data.json", "extended_api_data.json")
             if (DATA / f).exists()}

    # collect suspect (title, year) from the extended (superset) file
    base_recs = files.get("extended_api_data.json") or next(iter(files.values()))
    suspects = []
    for rec in base_recs:
        wp = (rec.get("metrics", {}) or {}).get("wikipedia_pageviews", {}) or {}
        if (wp.get("total_views", 0) or 0) < args.threshold:
            suspects.append((rec.get("movie_title"), rec.get("movie_year")))
    print(f"{len(suspects)} suspect films to recheck (threshold {args.threshold})")

    fixed = 0
    new_by_key = {}
    for i, (title, year) in enumerate(suspects, 1):
        if not title:
            continue
        nb = best_pageviews(title, year)
        if nb:
            new_by_key[(title, year)] = nb
        print(f"[{i}/{len(suspects)}] {title[:40]:<40} -> "
              f"{nb['total_views'] if nb else 'n/a':>10} via {nb['wiki_title_used'] if nb else '-'}")

    # apply: only raise, never lower
    for recs in files.values():
        for rec in recs:
            key = (rec.get("movie_title"), rec.get("movie_year"))
            nb = new_by_key.get(key)
            if not nb:
                continue
            m = rec.setdefault("metrics", {})
            cur = (m.get("wikipedia_pageviews", {}) or {}).get("total_views", 0) or 0
            if nb["total_views"] > cur:
                nb2 = dict(nb); nb2["movie_title"] = key[0]; nb2["movie_year"] = key[1]
                m["wikipedia_pageviews"] = nb2

    for f, recs in files.items():
        json.dump(recs, (DATA / f).open("w"), ensure_ascii=False, indent=2)
    # count how many actually improved
    improved = sum(1 for k, nb in new_by_key.items())
    print(f"\nRechecked {improved} films; updated where higher. Wrote: {', '.join(files)}")
    print("Next: python scripts/12_merge_and_build.py build")


if __name__ == "__main__":
    main()
