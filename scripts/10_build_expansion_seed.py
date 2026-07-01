#!/usr/bin/env python3
"""
10_build_expansion_seed.py
==========================

Turn the human-curated candidate list (data/expansion_candidates.csv) into a
machine-ready seed file in the SAME schema as data/top200_movies.csv, using
TMDB to fill in real budget / revenue / genre / runtime for each film.

Why this exists
---------------
The original 197-film seed came from the Wikipedia "highest-grossing films"
scrape (script 01), which already carried box-office + budget + genre. The
expansion films (cult / flop / low-budget / arthouse) are NOT on that list, so
we pull their financials straight from TMDB instead. No values are invented:
every budget/revenue/genre comes from the TMDB API response, and any film TMDB
cannot match is written to data/expansion_unmatched.csv for manual review
rather than guessed.

Output
------
  data/expansion_movies.csv   (top200 schema, expansion films only, deduped)
  data/all_movies.csv         (top200_movies.csv + expansion_movies.csv)
  data/expansion_unmatched.csv (films TMDB could not match — review by hand)

Usage
-----
  set -a; source .env; set +a
  python scripts/10_build_expansion_seed.py            # full run
  python scripts/10_build_expansion_seed.py --limit 5  # smoke test
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _load_collector_module():
    """Import the digit-prefixed 06 module so we reuse the EXACT TMDB call."""
    path = ROOT / "scripts" / "06_live_data_collectors.py"
    spec = importlib.util.spec_from_file_location("collectors06", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _norm(title: str) -> str:
    """Normalize a title for dedup (case/accents/punctuation-insensitive)."""
    t = unicodedata.normalize("NFKD", str(title)).encode("ascii", "ignore").decode()
    return "".join(ch for ch in t.lower() if ch.isalnum())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidates", default=str(DATA / "expansion_candidates.csv"))
    ap.add_argument("--top200", default=str(DATA / "top200_movies.csv"))
    ap.add_argument("--out", default=str(DATA / "expansion_movies.csv"))
    ap.add_argument("--all-out", default=str(DATA / "all_movies.csv"))
    ap.add_argument("--api-key", default=os.environ.get("TMDB_API_KEY"))
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if not args.api_key:
        sys.exit("ERROR: set TMDB_API_KEY (env or --api-key). Get one free at "
                 "https://www.themoviedb.org/settings/api")

    cand = pd.read_csv(args.candidates)
    if args.limit:
        cand = cand.head(args.limit)

    top = pd.read_csv(args.top200)
    existing_keys = {(_norm(r.title), int(r.year)) for r in top.itertuples()}
    start_rank = int(top["rank"].max()) + 1

    collectors = _load_collector_module()

    rows, unmatched, skipped_dupes = [], [], []
    rank = start_rank

    for i, c in enumerate(cand.itertuples(), 1):
        title, year = str(c.title), int(c.year)
        key = (_norm(title), year)
        if key in existing_keys:
            skipped_dupes.append((title, year))
            print(f"[{i}/{len(cand)}] SKIP (already in top200): {title} ({year})")
            continue

        print(f"[{i}/{len(cand)}] TMDB lookup: {title} ({year})")
        tm = collectors.collect_tmdb_movie_data(title, year, args.api_key)

        if tm.get("status") != "success":
            unmatched.append({"title": title, "year": year,
                              "category": getattr(c, "category", ""),
                              "tmdb_status": tm.get("status")})
            continue

        genres = tm.get("genres") or []
        companies = tm.get("production_companies") or []
        rows.append({
            "rank": rank,
            "title": title,                       # keep curated title (collectors query on it)
            "year": year,
            "worldwide_gross": tm.get("revenue", 0) or 0,
            "domestic_gross": "",                 # not provided by TMDB; left blank
            "budget": tm.get("budget", 0) or 0,
            "genre": genres[0] if genres else getattr(c, "category", ""),
            "franchise": "",                      # unknown for expansion films
            "director": "",                       # not needed by collectors
            "studio": companies[0] if companies else "",
            "is_sequel": False,
            "is_animated": "Animation" in genres,
            # extra provenance columns (ignored by downstream scripts, useful for QA)
            "expansion_category": getattr(c, "category", ""),
            "tmdb_id": tm.get("tmdb_id"),
            "tmdb_release_date": tm.get("release_date"),
        })
        existing_keys.add(key)
        rank += 1

    exp = pd.DataFrame(rows)
    exp.to_csv(args.out, index=False)
    print(f"\nWrote {len(exp)} expansion films -> {args.out}")

    if unmatched:
        um = pd.DataFrame(unmatched)
        um.to_csv(DATA / "expansion_unmatched.csv", index=False)
        print(f"WARNING: {len(um)} films unmatched on TMDB -> "
              f"{DATA / 'expansion_unmatched.csv'} (review manually)")
    if skipped_dupes:
        print(f"Skipped {len(skipped_dupes)} films already present in top200.")

    # Build the combined movie list (top200 schema columns only, in order).
    schema = ["rank", "title", "year", "worldwide_gross", "domestic_gross",
              "budget", "genre", "franchise", "director", "studio",
              "is_sequel", "is_animated"]
    combined = pd.concat([top[schema], exp[schema]], ignore_index=True)
    combined.to_csv(args.all_out, index=False)
    print(f"Wrote combined {len(combined)} films -> {args.all_out}")


if __name__ == "__main__":
    main()
