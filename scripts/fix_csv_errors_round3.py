"""
Round-3 CSV-quality fix (audit of wiki_views <= 10,000):

  1. "Incredibles" (row 23, 2004) duplicates "The Incredibles" (row 53, 2004) —
     identical worldwide gross ($633,026,024) and director (Brad Bird).
     Drop the bare-title row, keep "The Incredibles" (the canonical name).

  2. For every film with wiki_views <= 10,000, resolve its current
     wiki_title_used through Wikipedia's redirects API. If it resolves to a
     different canonical article, refetch pageviews + langlinks on that
     canonical title. This catches the disambiguator-URL trap where
     `Foo_(YYYY_film)` redirects to a canonical article that holds all the
     real traffic.

     Safety: only accept the new canonical pageviews if the canonical
     article exists (no redlink) AND the new total_views is strictly
     larger AND the new langlinks count is >= the old one. We never
     overwrite a fully-correct row with worse data.

This script DOES NOT rename CSV titles (unlike rounds 1+2). It only:
  - drops the duplicate row from data/* files
  - patches wikipedia_pageviews + wikipedia_languages on
    extended_api_data.json (and live_api_data.json) for affected films.
"""

import csv
import io
import json
import logging
import os
import sys
import time
from typing import Dict, Optional, Tuple
from urllib.parse import quote, unquote

import requests
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")
sys.path.insert(0, SCRIPT_DIR)

load_dotenv(os.path.join(PROJECT_DIR, ".env"))

HEADERS = {
    "User-Agent": "PandoraParadoxCapstone/1.0 (Academic Research)",
    "Accept-Language": "en-US,en;q=0.9",
}
THRESHOLD = 10_000

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Films to remove (their (title, year) as they sit in the data files now).
REMOVE_TITLES = {
    ("Incredibles", 2004),
}


# --------------------------------------------------------------------------
# Step 1: drop the bare-title duplicate from every data file
# --------------------------------------------------------------------------
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
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    if title_col not in header or year_col not in header:
        return
    ti = header.index(title_col)
    yi = header.index(year_col)
    before = len(rows)
    keep = []
    for row in rows:
        try:
            year_val = int(row[yi]) if row[yi] not in ("", None) else None
        except (ValueError, IndexError):
            year_val = None
        if (row[ti], year_val) in REMOVE_TITLES:
            continue
        keep.append(row)
    if len(keep) == before:
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(keep)
    logger.info(f"  {os.path.basename(path)}: {before} -> {len(keep)}")


def strip_bad_rows():
    logger.info("Stripping duplicate Incredibles (2004) row from all data files...")
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


# --------------------------------------------------------------------------
# Step 2: bulk wiki redirect resolution for views <= 10,000
# --------------------------------------------------------------------------
def resolve_canonical_title(title: str) -> Optional[Dict]:
    """
    Use the MediaWiki API to follow redirects from `title` and return the
    canonical article title plus its langlinks count. Returns None if the
    page doesn't exist.
    """
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "redirects": "true",
                "prop": "langlinks|info",
                "lllimit": "max",
                "format": "json",
                "titles": title,
            },
            headers=HEADERS,
            timeout=30,
        )
        time.sleep(0.3)
        if r.status_code != 200:
            return None
        data = r.json().get("query", {})
        pages = data.get("pages", {})
        for page_id, page in pages.items():
            if page_id == "-1":
                return None  # missing page
            ll = page.get("langlinks", []) or []
            return {
                "canonical_title": page.get("title", "").replace(" ", "_"),
                "language_editions": len(ll) + 1,
                "pageid": page.get("pageid"),
            }
        return None
    except requests.RequestException as e:
        logger.warning(f"  resolve_canonical_title({title}): {e}")
        return None


def fetch_pageviews(wiki_title: str) -> Optional[Dict]:
    """Fetch monthly pageviews on en.wikipedia for the given (URL-form) title."""
    try:
        encoded = quote(wiki_title, safe="_():,!")
        url = (
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"en.wikipedia/all-access/all-agents/{encoded}/monthly/"
            "2023040100/2026040100"
        )
        time.sleep(0.4)
        r = requests.get(url, headers=HEADERS, timeout=45)
        if r.status_code != 200:
            return None
        items = r.json().get("items", [])
        if not items:
            return None
        views = [d.get("views", 0) for d in items]
        total = sum(views)
        return {
            "status": "success",
            "wiki_title_used": wiki_title,
            "total_views": total,
            "average_monthly_views": total / len(views) if views else 0,
            "max_monthly_views": max(views) if views else 0,
            "min_monthly_views": min(views) if views else 0,
            "views_count": len(items),
        }
    except requests.RequestException as e:
        logger.warning(f"  fetch_pageviews({wiki_title}): {e}")
        return None


def fix_wiki_views_safe():
    """
    For every film with wiki_views <= THRESHOLD, resolve its current
    wiki_title_used through MediaWiki's redirect API. If the canonical
    article is different and gets MORE pageviews (and >= the langlinks we
    had), update both pageviews and language_editions.
    """
    logger.info(f"Auditing films with wiki_views <= {THRESHOLD}...")
    paths = [os.path.join(DATA_DIR, "extended_api_data.json"),
             os.path.join(DATA_DIR, "live_api_data.json")]

    # Use extended as source of truth for which films to fix
    with open(paths[0], "r", encoding="utf-8") as f:
        recs = json.load(f)

    fixes: Dict[Tuple[str, int], Dict] = {}  # (title, year) -> new payload
    skipped_same = 0
    skipped_worse = 0
    skipped_missing = 0
    n_total = 0

    for r in recs:
        m = r.get("metrics", {}) or {}
        wp = m.get("wikipedia_pageviews", {}) or {}
        if wp.get("status") != "success":
            continue
        old_views = wp.get("total_views", 0) or 0
        if old_views > THRESHOLD:
            continue
        n_total += 1
        title = r.get("movie_title")
        year = r.get("movie_year")
        old_wiki_title = wp.get("wiki_title_used")
        old_langs = (m.get("wikipedia_languages", {}) or {}).get("language_editions", 0) or 0

        if not old_wiki_title:
            continue

        canon = resolve_canonical_title(old_wiki_title)
        if canon is None:
            logger.info(f"  SKIP (canonical missing): {title} ({year})")
            skipped_missing += 1
            continue

        if canon["canonical_title"] == old_wiki_title:
            # No redirect, current title is canonical; nothing to do
            skipped_same += 1
            continue

        # Found a redirect. Fetch pageviews on the canonical title.
        new_pv = fetch_pageviews(canon["canonical_title"])
        if new_pv is None:
            logger.info(f"  SKIP (canonical no pageviews): {title} ({year}) -> {canon['canonical_title']}")
            skipped_missing += 1
            continue

        if new_pv["total_views"] <= old_views:
            logger.info(f"  SKIP (canonical worse): {title} ({year}) "
                        f"old={old_views} new={new_pv['total_views']} "
                        f"({old_wiki_title} -> {canon['canonical_title']})")
            skipped_worse += 1
            continue

        if canon["language_editions"] < old_langs:
            logger.info(f"  SKIP (langs regress): {title} ({year}) "
                        f"old_langs={old_langs} new_langs={canon['language_editions']}")
            skipped_worse += 1
            continue

        logger.info(f"  FIX: {title} ({year})  views {old_views:>7} -> {new_pv['total_views']:>10}, "
                    f"langs {old_langs:>3} -> {canon['language_editions']:>3}  "
                    f"({old_wiki_title} -> {canon['canonical_title']})")
        new_pv["movie_title"] = title
        new_pv["movie_year"] = year
        fixes[(title, year)] = {
            "wikipedia_pageviews": new_pv,
            "wikipedia_languages": {
                "status": "success",
                "language_editions": canon["language_editions"],
                "wiki_title_used": canon["canonical_title"],
            },
        }

    logger.info(f"Audit summary: total={n_total}, fixed={len(fixes)}, "
                f"same_canonical={skipped_same}, worse={skipped_worse}, missing={skipped_missing}")

    if not fixes:
        return

    # Apply to all relevant data files
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            recs = json.load(f)
        n = 0
        for r in recs:
            key = (r.get("movie_title"), r.get("movie_year"))
            if key not in fixes:
                continue
            m = r.setdefault("metrics", {})
            patch = fixes[key]
            m["wikipedia_pageviews"] = patch["wikipedia_pageviews"]
            m["wikipedia_languages"] = patch["wikipedia_languages"]
            n += 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False, indent=2)
        logger.info(f"  patched {n} films in {os.path.basename(path)}")


def main():
    strip_bad_rows()
    fix_wiki_views_safe()
    logger.info("Done. Re-run downstream collectors / pipelines as needed:")
    logger.info("  04_1, 04_2, 05_1, 05_2 (CFI re-build)")


if __name__ == "__main__":
    main()
