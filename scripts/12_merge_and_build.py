#!/usr/bin/env python3
"""
12_merge_and_build.py
=====================

Glue step for the sample expansion. Two sub-commands:

  combine   Merge the expansion collector outputs into the canonical data files
            (live_api_data.json, extended_api_data.json, subtitle_features.csv),
            backing up the originals to *.preexpansion.*. Run this AFTER the base
            collectors (06, 06_1, 03_1) and BEFORE the Trends/YouTube collectors
            (07, 09) — those read the canonical files and inject their blocks via
            their own --merge step, so the canonical files must already contain
            the new films.

  build     Run 04_1_build_index.py on the combined data to produce the expanded
            modelling dataset (data/pandora_full_dataset_expanded.csv). Run this
            LAST, after Trends/YouTube have been merged in.

Usage
-----
  python scripts/12_merge_and_build.py combine
  # ... run 07_google_trends_serpapi.py + 09_youtube_trailer_views.py (+ --merge) ...
  python scripts/12_merge_and_build.py build

Idempotent-ish: `combine` dedupes by (title, year), so re-running it will not
double-count films.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _load_json(p: Path) -> list:
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _dedupe_records(records: list) -> list:
    """Keep the LAST record per (movie_title, movie_year) — the richest one."""
    by_key = {}
    for r in records:
        by_key[(r.get("movie_title"), r.get("movie_year"))] = r
    return list(by_key.values())


def _backup(p: Path) -> None:
    if p.exists():
        bak = p.with_suffix(p.suffix + ".preexpansion")
        shutil.copy2(p, bak)
        print(f"  backed up {p.name} -> {bak.name}")


def combine() -> None:
    live = DATA / "live_api_data.json"
    extended = DATA / "extended_api_data.json"
    subs = DATA / "subtitle_features.csv"

    exp_live = DATA / "expansion_live_api_data.json"
    exp_extended = DATA / "expansion_extended_api_data.json"
    exp_subs = DATA / "expansion_subtitle_features.csv"

    missing = [p.name for p in (exp_live, exp_extended, exp_subs) if not p.exists()]
    if missing:
        sys.exit("ERROR: expansion outputs not found: " + ", ".join(missing) +
                 "\nRun collectors 06, 06_1 and 03_1 on the expansion seed first.")

    print("Combining live_api_data.json ...")
    _backup(live)
    combined_live = _dedupe_records(_load_json(live) + _load_json(exp_live))
    with live.open("w", encoding="utf-8") as f:
        json.dump(combined_live, f, indent=2, default=str)
    print(f"  -> {len(combined_live)} films")

    print("Combining extended_api_data.json ...")
    _backup(extended)
    # If the canonical extended is absent, fall back to live as the base.
    base_ext = _load_json(extended) or _load_json(DATA / "live_api_data.json.preexpansion")
    combined_ext = _dedupe_records(base_ext + _load_json(exp_extended))
    with extended.open("w", encoding="utf-8") as f:
        json.dump(combined_ext, f, indent=2, default=str)
    print(f"  -> {len(combined_ext)} films")

    print("Combining subtitle_features.csv ...")
    _backup(subs)
    base_subs = pd.read_csv(subs) if subs.exists() else pd.DataFrame()
    add_subs = pd.read_csv(exp_subs)
    combined_subs = pd.concat([base_subs, add_subs], ignore_index=True)
    combined_subs = combined_subs.drop_duplicates(subset=["title", "year"], keep="last")
    combined_subs.to_csv(subs, index=False)
    print(f"  -> {len(combined_subs)} films")

    print("\nDone. Next: run 07_google_trends_serpapi.py and 09_youtube_trailer_views.py "
          "(then each with --merge), then: python scripts/12_merge_and_build.py build")


def build() -> None:
    all_movies = DATA / "all_movies.csv"
    if not all_movies.exists():
        sys.exit(f"ERROR: {all_movies} not found — run 10_build_expansion_seed.py first.")

    cmd = [
        sys.executable, str(ROOT / "scripts" / "04_1_build_index.py"),
        "--movies", str(all_movies),
        "--extended", str(DATA / "extended_api_data.json"),
        "--live-api", str(DATA / "live_api_data.json"),
        "--subtitles", str(DATA / "subtitle_features.csv"),
        "--youtube", str(DATA / "youtube_data.json"),
        "--youtube-trailer-views", str(DATA / "youtube_trailer_data.json"),
        "--cfi-out", str(DATA / "cultural_footprint_expanded.csv"),
        "--full-out", str(DATA / "pandora_full_dataset_expanded.csv"),
    ]
    print("Running:", " ".join(cmd), "\n")
    subprocess.run(cmd, check=True)
    print("\nBuilt -> data/pandora_full_dataset_expanded.csv")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["combine", "build"])
    args = ap.parse_args()
    if args.mode == "combine":
        combine()
    else:
        build()


if __name__ == "__main__":
    main()
