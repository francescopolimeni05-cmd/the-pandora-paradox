#!/usr/bin/env python3
"""
08b_reddit_serpapi.py
=====================

Second, independent Reddit DISCUSSION VOLUME signal: Google's estimated number of
indexed reddit.com pages mentioning the film, via SerpAPI (engine=google,
q='site:reddit.com "<title>" movie'). Cross-validates the PullPush thread count.

No Reddit app needed; reuses the SERPAPI_KEY you already have.

Output: data/reddit_serpapi.json  — list of
  {movie_title, movie_year, reddit_serp_results, status}
Joined into the modelling dataset during the analysis phase (by title+year).

Usage
-----
  python scripts/08b_reddit_serpapi.py --input data/all_movies.csv \
      --output data/reddit_serpapi.json
  python scripts/08b_reddit_serpapi.py --input data/expansion_candidates.csv \
      --output data/reddit_serpapi_test.json --limit 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SERP_ENDPOINT = "https://serpapi.com/search.json"


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


def fetch_serp_volume(title: str, year: int, api_key: str, sleep: float,
                      retries: int, cooldown: int = 300, max_waits: int = 24) -> dict:
    """SerpAPI Google volume for one film. Handles the Starter plan's 200/hour
    cap gracefully: on a rate-limit it PARKS for `cooldown` seconds and retries
    the same film (up to max_waits times ≈ 2h), so a full run is hands-off."""
    query = f'site:reddit.com "{title}" movie'
    params = {"engine": "google", "q": query, "api_key": api_key, "num": 10}
    last = None
    attempt = 0
    waits = 0
    while True:
        try:
            time.sleep(sleep)
            r = requests.get(SERP_ENDPOINT, params=params, timeout=45)
            # Detect SerpAPI rate limit (429, or a 200 whose error mentions hour/rate).
            err_txt = ""
            if r.status_code != 429:
                try:
                    err_txt = (r.json().get("error") or "") if r.headers.get(
                        "content-type", "").startswith("application/json") else ""
                except Exception:
                    err_txt = ""
            rate_limited = (r.status_code == 429) or \
                any(w in err_txt.lower() for w in ("per hour", "hour", "rate"))
            if rate_limited:
                if waits >= max_waits:
                    return {"movie_title": title, "movie_year": year, "status": "error",
                            "error": "rate_limited_timeout", "source": "serpapi_google"}
                waits += 1
                print(f"      ...limite orario SerpAPI: pausa {cooldown//60} min, "
                      f"poi riprendo (attesa {waits}/{max_waits})")
                time.sleep(cooldown)
                continue
            if r.status_code in (500, 502, 503):
                last = f"http_{r.status_code}"
                attempt += 1
                if attempt >= retries:
                    break
                time.sleep(3 * attempt)
                continue
            r.raise_for_status()
            d = r.json()
            total = (d.get("search_information", {}) or {}).get("total_results")
            organic = len(d.get("organic_results", []) or [])
            return {
                "movie_title": title,
                "movie_year": year,
                "reddit_serp_results": int(total) if total is not None else None,
                "reddit_serp_organic_on_page": organic,
                "status": "success",
                "source": "serpapi_google",
            }
        except requests.exceptions.RequestException as e:
            last = str(e)
            attempt += 1
            if attempt >= retries:
                break
            time.sleep(2 * attempt)
    return {"movie_title": title, "movie_year": year, "status": "error",
            "error": last, "source": "serpapi_google"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--api-key", default=os.environ.get("SERPAPI_KEY"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not args.api_key:
        sys.exit("ERROR: set SERPAPI_KEY (env or --api-key).")

    films = load_films(args.input)
    if args.limit:
        films = films[: args.limit]
    out = Path(args.output)

    # Keep ALL prior rows in the file, but only treat SUCCESSFUL ones as "done"
    # so that error/rate-limited films are retried on resume.
    prior = {}
    done = {}
    if out.exists() and not args.force:
        for r in json.load(out.open()):
            key = (r.get("movie_title"), r.get("movie_year"))
            prior[key] = r
            if r.get("status") == "success":
                done[key] = r

    rows = [r for r in prior.values() if r.get("status") == "success"]
    for i, f in enumerate(films, 1):
        key = (f["movie_title"], f["movie_year"])
        if key in done:
            print(f"[{i}/{len(films)}] skip (done): {key[0]}")
            continue
        print(f"[{i}/{len(films)}] SerpAPI: {f['movie_title']} ({f['movie_year']})")
        try:
            block = fetch_serp_volume(f["movie_title"], f["movie_year"],
                                      args.api_key, args.sleep, args.retries)
        except Exception as e:  # never let one film abort the whole run
            block = {"movie_title": f["movie_title"], "movie_year": f["movie_year"],
                     "status": "error", "error": str(e), "source": "serpapi_google"}
        if block.get("status") == "error":
            print(f"      -> ERROR: {block.get('error')}")
        else:
            print(f"      -> {block.get('status')} | google results ≈ "
                  f"{block.get('reddit_serp_results')}")
        rows.append(block)
        if i % 10 == 0:
            json.dump(rows, out.open("w"), indent=2)
    json.dump(rows, out.open("w"), indent=2)
    ok = sum(1 for r in rows if r.get("status") == "success")
    print(f"\nWrote {len(rows)} films -> {out}  ({ok} success)")


if __name__ == "__main__":
    main()
