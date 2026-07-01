#!/usr/bin/env python3
"""
33_collect_quote_circulation.py — how much does each quote actually TRAVEL online?
=================================================================================

Takes the candidate quote strings from 32_collect_quote_strings.py and, for each,
asks Google (via SerpAPI) how many indexed pages contain that EXACT phrase. A line
that circulates ("You can't handle the truth", "Why so serious") returns many
results; a forgettable line returns few. This is a direct, per-line measure of
realized circulation — the thing the theory is actually about — as opposed to the
curated wikiquote_count.

Two measures per quote:
  results_exact  — q = "<quote>"                 (raw circulation of the phrase)
  results_film   — q = "<quote>" <title>         (circulation attributable to THIS film)
The film-anchored count guards against generic phrases inflating the raw count.
Set --anchor off to save quota (one query per quote instead of two).

Reuses SERPAPI_KEY. Mirrors 08b's hands-off rate-limit handling: on the Starter
plan's 200/hour cap it PARKS and resumes, and the whole run is checkpoint/resume
(finished quotes are skipped; errors/rate-limited quotes are retried).

Output: data/quote_circulation.json — list of
  {title, year, quote, results_exact, results_film, status}

Usage
-----
  python scripts/33_collect_quote_circulation.py \
      --input data/quote_candidates.json \
      --output data/quote_circulation.json
  # cheaper single-query variant:
  python scripts/33_collect_quote_circulation.py --anchor off ...
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

# Load SERPAPI_KEY from .env automatically (same as 07_youtube_trailer_collector.py)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass


def load_pairs(path: str) -> list[dict]:
    """Flatten candidate file into one row per (film, quote)."""
    data = json.load(Path(path).open())
    pairs = []
    for r in data:
        for q in r.get("quotes", []) or []:
            pairs.append({"title": r.get("title"), "year": r.get("year"), "quote": q})
    return pairs


def _serp_total(query: str, api_key: str, sleep: float, retries: int,
                cooldown: int, max_waits: int) -> tuple[int | None, str | None]:
    """Return (total_results, error). Parks on rate-limit, like 08b."""
    params = {"engine": "google", "q": query, "api_key": api_key, "num": 10}
    last = None
    attempt = 0
    waits = 0
    while True:
        try:
            time.sleep(sleep)
            r = requests.get(SERP_ENDPOINT, params=params, timeout=45)
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
                    return None, "rate_limited_timeout"
                waits += 1
                print(f"      ...SerpAPI hourly cap: pausing {cooldown//60} min, "
                      f"then resuming (wait {waits}/{max_waits})")
                time.sleep(cooldown)
                continue
            if r.status_code in (500, 502, 503):
                last = f"http_{r.status_code}"
                attempt += 1
                if attempt >= retries:
                    return None, last
                time.sleep(3 * attempt)
                continue
            r.raise_for_status()
            d = r.json()
            total = (d.get("search_information", {}) or {}).get("total_results")
            return (int(total) if total is not None else None), None
        except requests.exceptions.RequestException as e:
            last = str(e)
            attempt += 1
            if attempt >= retries:
                return None, last
            time.sleep(2 * attempt)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=str(DATA / "quote_candidates.json"))
    ap.add_argument("--output", default=str(DATA / "quote_circulation.json"))
    ap.add_argument("--api-key", default=os.environ.get("SERPAPI_KEY"))
    ap.add_argument("--anchor", choices=["on", "off", "only"], default="on",
                    help="on = both exact and \"quote\"+title (2 q/quote); off = exact only "
                         "(1 q/quote); only = film-anchored only (1 q/quote, for re-verifying "
                         "short quotes)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--cooldown", type=int, default=300)
    ap.add_argument("--max-waits", type=int, default=24)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not args.api_key:
        sys.exit("ERROR: set SERPAPI_KEY (env or --api-key).")

    pairs = load_pairs(args.input)
    if args.limit:
        pairs = pairs[: args.limit]
    out = Path(args.output)

    done: dict[tuple, dict] = {}
    if out.exists() and not args.force:
        for r in json.load(out.open()):
            if r.get("status") == "success":
                done[(r.get("title"), r.get("year"), r.get("quote"))] = r

    rows = list(done.values())
    n = len(pairs)
    for i, p in enumerate(pairs, 1):
        key = (p["title"], p["year"], p["quote"])
        if key in done:
            continue
        q = p["quote"]
        print(f"[{i}/{n}] {p['title']}: \"{q[:48]}{'...' if len(q) > 48 else ''}\"")
        exact = film = None
        err = None
        if args.anchor in ("on", "off"):
            exact, err = _serp_total(f'"{q}"', args.api_key, args.sleep,
                                     args.retries, args.cooldown, args.max_waits)
        if err is None and args.anchor in ("on", "only"):
            film, err2 = _serp_total(f'"{q}" {p["title"]}', args.api_key, args.sleep,
                                     args.retries, args.cooldown, args.max_waits)
            err = err or err2
        block = {"title": p["title"], "year": p["year"], "quote": q,
                 "results_exact": exact, "results_film": film,
                 "status": "success" if err is None else "error",
                 **({"error": err} if err else {})}
        print("      -> "
              + (f"exact≈{exact}" if args.anchor in ("on", "off") else "")
              + (f" | +title≈{film}" if args.anchor in ("on", "only") else "")
              + (f" | ERROR {err}" if err else ""))
        rows.append(block)
        if i % 15 == 0:
            json.dump(rows, out.open("w"), indent=2, ensure_ascii=False)
    json.dump(rows, out.open("w"), indent=2, ensure_ascii=False)
    ok = sum(1 for r in rows if r.get("status") == "success")
    print(f"\nWrote {len(rows)} quote rows -> {out}  ({ok} success)")


if __name__ == "__main__":
    main()
