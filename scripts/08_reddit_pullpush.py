#!/usr/bin/env python3
"""
08_reddit_pullpush.py
=====================

Reddit discussion metrics via **PullPush.io** — a free, public Pushshift mirror —
instead of the official Reddit API (which now 403-blocks unauthenticated access
and requires an OAuth app Francesco couldn't create). No key, no app.

It returns the SAME fields collect_reddit_mentions() produced, so the rest of the
pipeline (flatten_live_api, CFI build) works unchanged.

Modes
-----
  collect : query PullPush for every film in --input, save reddit blocks to --output.
  merge   : inject the reddit_mentions block + recomputed reddit_derived into
            live_api_data.json and extended_api_data.json (matching on title+year).

--input may be a movies CSV (needs title,year) or a live_api_data-style JSON.

For a uniform metric across the WHOLE sample, run collect on the combined film
list (old + new) and then merge — this replaces the old, now-unreproducible
Reddit-API numbers with one consistent PullPush-based measure.

Usage
-----
  # smoke test on 5 films
  python scripts/08_reddit_pullpush.py collect --input data/expansion_movies.csv \
      --output data/reddit_pullpush_expansion.json --limit 5
  # full + merge
  python scripts/08_reddit_pullpush.py collect --input data/all_movies.csv \
      --output data/reddit_pullpush.json
  python scripts/08_reddit_pullpush.py merge --pullpush data/reddit_pullpush.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ENDPOINT = "https://api.pullpush.io/reddit/search/submission/"
HEADERS = {"User-Agent": "pandora-paradox-research/1.0 (academic capstone)"}


def _load_derive_fn():
    """Reuse derive_reddit_community_features from 06_1 (digit-prefixed module)."""
    path = ROOT / "scripts" / "06_1_extended_collectors.py"
    spec = importlib.util.spec_from_file_location("ext061", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.derive_reddit_community_features


def load_films(path: str) -> list[dict]:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        import csv
        with p.open() as f:
            return [{"movie_title": r["title"], "movie_year": int(float(r["year"]))}
                    for r in csv.DictReader(f) if r.get("title")]
    with p.open() as f:
        data = json.load(f)
    return [{"movie_title": d.get("movie_title"), "movie_year": d.get("movie_year")}
            for d in data if d.get("movie_title")]


def _page(query: str, size: int, before, sleep: float, retries: int):
    """One PullPush page. Returns (posts|None, error)."""
    params = {"q": query, "size": size, "sort": "desc", "sort_type": "created_utc"}
    if before:
        params["before"] = before
    err = None
    for attempt in range(retries):
        try:
            time.sleep(sleep * (attempt + 1))
            r = requests.get(ENDPOINT, params=params, headers=HEADERS, timeout=45)
            if r.status_code in (429, 500, 502, 503):
                err = f"http_{r.status_code}"
                time.sleep(3 * (attempt + 1))
                continue
            r.raise_for_status()
            return (r.json().get("data", []) or []), None
        except requests.exceptions.RequestException as e:
            err = str(e)
            time.sleep(2 * (attempt + 1))
    return None, err


def fetch_reddit(title: str, year: int, size: int, sleep: float,
                 retries: int, max_pages: int) -> dict:
    """Measure Reddit DISCUSSION VOLUME via PullPush (paginated).

    NOTE: PullPush/Pushshift records a post's score & comment count at archival
    time (≈0), so those magnitudes are NOT reliable. The trustworthy signal is
    the VOLUME of submissions mentioning the film and their subreddit spread —
    that is what we use. `post_count` carries the volume so it flows straight
    into the existing CFI pipeline (reddit_posts).
    """
    query = f"{title} movie"
    all_posts: list[dict] = []
    before = None
    status = "success"
    last_err = None
    for _ in range(max_pages):
        posts, err = _page(query, size, before, sleep, retries)
        if posts is None:
            status = "partial" if all_posts else "error"
            last_err = err
            break
        all_posts.extend(posts)
        if len(posts) < size:
            break  # exhausted — fewer than a full page means we counted them all
        before = posts[-1].get("created_utc")
        if not before:
            break

    if status == "error" and not all_posts:
        return {"movie_title": title, "movie_year": year, "status": "error",
                "error": last_err or "unknown", "source": "pullpush"}

    n = len(all_posts)
    if n == 0:
        return {"movie_title": title, "movie_year": year, "post_count": 0,
                "submission_volume": 0, "status": "no_data", "source": "pullpush"}

    def _i(p, k):
        v = p.get(k, 0)
        return int(v) if isinstance(v, (int, float)) else 0

    top_posts = sorted(all_posts, key=lambda p: _i(p, "num_comments"), reverse=True)[:25]
    saturated = (status == "success" and n >= size * max_pages)
    return {
        "movie_title": title,
        "movie_year": year,
        # VOLUME metric (reliable): number of submissions mentioning the film.
        "submission_volume": n,
        "post_count": n,                      # carried into CFI as reddit_posts
        "volume_saturated": saturated,        # True = hit the page cap, real count is higher
        "pages_fetched": (n + size - 1) // size,
        # Magnitudes below are at-archival-time (UNRELIABLE) — kept for transparency only.
        "total_comments_at_ingest": sum(_i(p, "num_comments") for p in all_posts),
        "posts": [
            {
                "title": p.get("title"),
                "subreddit": p.get("subreddit"),
                "comments": _i(p, "num_comments"),
                "url": p.get("full_link") or p.get("url"),
            } for p in top_posts
        ],
        "status": "success" if status == "success" else "partial",
        "source": "pullpush",
    }


def collect(args) -> None:
    films = load_films(args.input)
    if args.limit:
        films = films[: args.limit]
    out_path = Path(args.output)

    done = {}
    if out_path.exists() and not args.force:
        for r in json.load(out_path.open()):
            done[(r.get("movie_title"), r.get("movie_year"))] = r

    rows = list(done.values())
    for i, f in enumerate(films, 1):
        key = (f["movie_title"], f["movie_year"])
        if key in done:
            print(f"[{i}/{len(films)}] skip (done): {key[0]}")
            continue
        print(f"[{i}/{len(films)}] PullPush: {f['movie_title']} ({f['movie_year']})")
        block = fetch_reddit(f["movie_title"], f["movie_year"],
                             size=args.size, sleep=args.sleep, retries=args.retries,
                             max_pages=args.max_pages)
        sat = " (saturated, real count higher)" if block.get("volume_saturated") else ""
        if block.get("status") == "error":
            print(f"      -> ERROR: {block.get('error')}")
        else:
            print(f"      -> {block.get('status')} | discussion volume = "
                  f"{block.get('submission_volume', 0)} thread{sat}")
        rows.append(block)
        if i % 10 == 0:
            json.dump(rows, out_path.open("w"), indent=2)
    json.dump(rows, out_path.open("w"), indent=2)
    ok = sum(1 for r in rows if r.get("status") == "success")
    print(f"\nWrote {len(rows)} films -> {out_path}  ({ok} success)")


def _merge_into(path: Path, by_key: dict, derive_fn) -> int:
    if not path.exists():
        print(f"  skip {path.name} (missing)")
        return 0
    data = json.load(path.open())
    updated = 0
    for entry in data:
        key = (entry.get("movie_title"), entry.get("movie_year"))
        if key in by_key:
            block = by_key[key]
            m = entry.setdefault("metrics", {})
            m["reddit_mentions"] = block
            m["reddit_derived"] = derive_fn(block)
            updated += 1
    backup = path.with_suffix(".pre_pullpush.json")
    if not backup.exists():
        json.dump(data, backup.open("w"), indent=2)  # one-time safety copy
    json.dump(data, path.open("w"), indent=2)
    print(f"  merged {updated} films into {path.name} (backup: {backup.name})")
    return updated


def merge(args) -> None:
    if not Path(args.pullpush).exists():
        print("PullPush output not found — nothing to merge (skipping).")
        return
    pull = json.load(Path(args.pullpush).open())
    by_key = {(d["movie_title"], d.get("movie_year")): d
              for d in pull if d.get("status") == "success"}
    if not by_key:
        print("No successful PullPush rows (service likely down) — skipping merge, "
              "pipeline continues with SerpAPI as the Reddit signal.")
        return
    derive_fn = _load_derive_fn()
    for name in ("live_api_data.json", "extended_api_data.json"):
        _merge_into(DATA / name, by_key, derive_fn)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)

    c = sub.add_parser("collect")
    c.add_argument("--input", required=True, help="movies CSV (title,year) or live_api JSON")
    c.add_argument("--output", required=True)
    c.add_argument("--limit", type=int, default=None)
    c.add_argument("--size", type=int, default=100, help="submissions per page")
    c.add_argument("--max-pages", type=int, default=5,
                   help="pages to paginate per film (volume cap = size*max_pages; default 5 -> 500)")
    c.add_argument("--sleep", type=float, default=1.0, help="base seconds between requests")
    c.add_argument("--retries", type=int, default=3)
    c.add_argument("--force", action="store_true", help="ignore existing output checkpoint")
    c.set_defaults(func=collect)

    m = sub.add_parser("merge")
    m.add_argument("--pullpush", required=True, help="output JSON from collect mode")
    m.set_defaults(func=merge)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
