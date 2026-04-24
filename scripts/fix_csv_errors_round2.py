"""
Round-2 CSV-quality fix:

  1. "Frozen 2" (row 74) was a duplicate of "Frozen II" (row 13). Same year,
     same exact gross. Drop "Frozen 2" from every downstream data file.
     Keep "Frozen II" (the official Roman-numeral title); its API queries
     yielded better OMDb data (rating 6.8, the canonical value).

  2. "Dr. Seuss' Horton Hears a Who!" (row 105) had a title with an
     apostrophe + exclamation that broke API queries — wiki_views was 722
     (clearly bogus), wiki_langs 0, omdb 0/0, wikiquote not_found. The
     canonical Wikipedia article is just "Horton Hears a Who! (film)" so
     the CSV title is now "Horton Hears a Who!" (the "Dr. Seuss'" prefix
     dropped). Director also corrected to Jimmy Hayward (Steve Carell was
     a voice actor, not the director).

This script removes the bad rows from data/* and re-fetches every source
for the renamed Horton film.
"""

import json
import logging
import os
import re
import sys
import time
from collections import Counter
from typing import Dict
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")
sys.path.insert(0, SCRIPT_DIR)

# Reuse helpers
from fix_csv_errors import (  # noqa: E402
    fetch_wiki_pageviews, fetch_wiki_languages, fetch_reddit_mentions,
    fetch_tmdb, fetch_omdb, scrape_wikiquote, derive_reddit_features,
)

load_dotenv(os.path.join(PROJECT_DIR, ".env"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Films to remove (their titles as they sit in the data files right now)
REMOVE_TITLES = {
    ("Frozen 2", 2019),
    ("Dr. Seuss' Horton Hears a Who!", 2008),
}

# Film to refetch with a cleaned title
NEW_TITLE = "Horton Hears a Who!"
NEW_YEAR = 2008


def _filter_json_records(path, title_field, year_field):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        recs = json.load(f)
    before = len(recs)
    keep = [r for r in recs
            if (r.get(title_field), r.get(year_field)) not in REMOVE_TITLES]
    if len(keep) == before:
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(keep, f, ensure_ascii=False, indent=2)
    logger.info(f"  {os.path.basename(path)}: {before} -> {len(keep)}")


def _filter_csv(path, title_col="title", year_col="year"):
    if not os.path.exists(path):
        return
    df = pd.read_csv(path)
    before = len(df)
    mask = ~df.apply(
        lambda r: (r.get(title_col), int(r.get(year_col)) if pd.notna(r.get(year_col)) else None) in REMOVE_TITLES,
        axis=1,
    )
    df = df[mask]
    if len(df) == before:
        return
    df.to_csv(path, index=False)
    logger.info(f"  {os.path.basename(path)}: {before} -> {len(df)}")


def strip_bad_rows():
    logger.info("Stripping bad rows from all data files…")
    _filter_json_records(os.path.join(DATA_DIR, "live_api_data.json"),
                         "movie_title", "movie_year")
    _filter_json_records(os.path.join(DATA_DIR, "extended_api_data.json"),
                         "movie_title", "movie_year")
    _filter_json_records(os.path.join(DATA_DIR, "youtube_data.json"),
                         "movie_title", "movie_year")
    _filter_json_records(os.path.join(DATA_DIR, "star_power.json"),
                         "title", "year")
    _filter_json_records(os.path.join(DATA_DIR, "plot_embedding.json"),
                         "title", "year")
    _filter_json_records(os.path.join(DATA_DIR, "advanced_sentiment.json"),
                         "title", "year")
    _filter_json_records(os.path.join(DATA_DIR, "subtitle_raw.json"),
                         "title", "year")

    _filter_csv(os.path.join(DATA_DIR, "subtitle_features.csv"))
    _filter_csv(os.path.join(DATA_DIR, "subtitle_tfidf.csv"))
    _filter_csv(os.path.join(DATA_DIR, "advanced_sentiment.csv"))
    _filter_csv(os.path.join(DATA_DIR, "emotional_arc.csv"))


def collect_horton():
    title = NEW_TITLE
    year = NEW_YEAR
    logger.info(f"Re-collecting all sources for: {title} ({year})")
    tmdb_key = os.environ.get("TMDB_API_KEY")
    omdb_key = os.environ.get("OMDB_API_KEY")

    metrics: Dict = {}
    metrics["wikipedia_pageviews"] = fetch_wiki_pageviews(title, year)
    if metrics["wikipedia_pageviews"].get("status") == "success":
        wt = metrics["wikipedia_pageviews"]["wiki_title_used"]
        metrics["wikipedia_languages"] = fetch_wiki_languages(wt)
    else:
        metrics["wikipedia_languages"] = {"status": "no_data", "language_editions": 0}
    metrics["reddit_mentions"] = fetch_reddit_mentions(title, year)
    metrics["tmdb_data"] = fetch_tmdb(title, year, tmdb_key)
    metrics["omdb_awards"] = fetch_omdb(title, year, omdb_key)
    metrics["wikiquote_quotes"] = scrape_wikiquote(title, year)
    metrics["reddit_derived"] = derive_reddit_features(metrics["reddit_mentions"])
    metrics["google_trends"] = {"status": "skipped"}
    metrics["imsdb_script"] = {"status": "skipped"}

    record = {
        "movie_title": title,
        "movie_year": year,
        "collection_timestamp": "2026-04-23T17:00:00",
        "metrics": metrics,
    }
    for fname in ("live_api_data.json", "extended_api_data.json"):
        path = os.path.join(DATA_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            recs = json.load(f)
        recs.append(record)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False, indent=2)
        logger.info(f"  appended record to {fname}")

    # Print what we got so the human can sanity check
    logger.info("New Horton metrics:")
    for k in ("wikipedia_pageviews", "wikipedia_languages", "reddit_mentions",
              "tmdb_data", "omdb_awards", "wikiquote_quotes"):
        v = metrics[k]
        logger.info(f"  {k}: status={v.get('status')}, "
                    f"key_value={v.get('total_views') or v.get('language_editions') or v.get('post_count') or v.get('vote_count') or v.get('total_wins') or v.get('wikiquote_count')}")


def main():
    strip_bad_rows()
    collect_horton()
    logger.info("Done. Re-run downstream collectors with --resume:")
    logger.info("  03_1_subtitle_features --resume, 08_star_power --resume,")
    logger.info("  03_2 --resume, 03_3, 03_4, 10, 04_1, 04_2, 05_1, 05_2")


if __name__ == "__main__":
    main()
