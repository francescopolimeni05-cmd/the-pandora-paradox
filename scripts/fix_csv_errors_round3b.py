"""
Round-3b follow-up: fix wiki_langs <= 5 (broken language_editions count)
for films that the round-3 audit missed because their views were already
> 10,000.

Strategy:
  - Resolve wiki_title_used through MediaWiki redirects API.
  - If canonical differs and gives more langs (and pageviews don't go down
    by more than 50%), accept it. Otherwise, just refetch langlinks on the
    existing wiki_title_used in case the original collector got it wrong.
"""

import json
import logging
import os
import time
from typing import Dict, Optional
from urllib.parse import quote

import requests
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")

load_dotenv(os.path.join(PROJECT_DIR, ".env"))

HEADERS = {
    "User-Agent": "PandoraParadoxCapstone/1.0 (Academic Research)",
    "Accept-Language": "en-US,en;q=0.9",
}
LANGS_THRESHOLD = 5

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def resolve_canonical_title(title: str) -> Optional[Dict]:
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "redirects": "true",
                "prop": "langlinks|info", "lllimit": "max",
                "format": "json", "titles": title,
            },
            headers=HEADERS, timeout=30,
        )
        time.sleep(0.3)
        if r.status_code != 200:
            return None
        pages = r.json().get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            if page_id == "-1":
                return None
            ll = page.get("langlinks", []) or []
            return {
                "canonical_title": page.get("title", "").replace(" ", "_"),
                "language_editions": len(ll) + 1,
            }
        return None
    except requests.RequestException as e:
        logger.warning(f"  resolve_canonical_title({title}): {e}")
        return None


def fetch_pageviews(wiki_title: str) -> Optional[Dict]:
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


def main():
    paths = [os.path.join(DATA_DIR, "extended_api_data.json"),
             os.path.join(DATA_DIR, "live_api_data.json")]
    with open(paths[0], "r", encoding="utf-8") as f:
        recs = json.load(f)

    fixes = {}
    for r in recs:
        m = r.get("metrics", {}) or {}
        wp = m.get("wikipedia_pageviews", {}) or {}
        if wp.get("status") != "success":
            continue
        old_views = wp.get("total_views", 0) or 0
        old_langs = (m.get("wikipedia_languages", {}) or {}).get("language_editions", 0) or 0
        if old_langs > LANGS_THRESHOLD:
            continue
        title = r.get("movie_title")
        year = r.get("movie_year")
        wiki_title = wp.get("wiki_title_used")
        if not wiki_title:
            continue

        canon = resolve_canonical_title(wiki_title)
        if canon is None:
            logger.info(f"  SKIP (no canonical): {title} ({year})")
            continue

        if canon["language_editions"] <= old_langs:
            logger.info(f"  SKIP (no improvement): {title} ({year}) "
                        f"old_langs={old_langs} new_langs={canon['language_editions']}")
            continue

        # If canonical title differs, also refetch pageviews
        new_pv = None
        if canon["canonical_title"] != wiki_title:
            new_pv = fetch_pageviews(canon["canonical_title"])
            if new_pv is None or new_pv["total_views"] < old_views * 0.5:
                # Don't accept the new canonical if views regress by > 50%.
                # Keep existing pageviews but still update langs (which used
                # the canonical title via the redirect-following query).
                logger.info(f"  PARTIAL: {title} ({year}) "
                            f"canonical {wiki_title} -> {canon['canonical_title']} "
                            f"would drop views ({old_views} -> {new_pv['total_views'] if new_pv else 'None'}); "
                            f"only updating langs")
                new_pv = None

        old_lang_dict = m.get("wikipedia_languages", {}) or {}
        new_lang_dict = {
            "status": "success",
            "language_editions": canon["language_editions"],
            "wiki_title_used": canon["canonical_title"],
        }

        patch = {"wikipedia_languages": new_lang_dict}
        if new_pv is not None:
            new_pv["movie_title"] = title
            new_pv["movie_year"] = year
            patch["wikipedia_pageviews"] = new_pv
            logger.info(f"  FIX: {title} ({year})  views {old_views:>9} -> {new_pv['total_views']:>10}, "
                        f"langs {old_langs:>3} -> {canon['language_editions']:>3}  "
                        f"({wiki_title} -> {canon['canonical_title']})")
        else:
            logger.info(f"  FIX (langs only): {title} ({year})  langs {old_langs} -> {canon['language_editions']}")
        fixes[(title, year)] = patch

    logger.info(f"Total fixes: {len(fixes)}")

    if not fixes:
        return

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
            for k, v in patch.items():
                m[k] = v
            n += 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False, indent=2)
        logger.info(f"  patched {n} films in {os.path.basename(path)}")


if __name__ == "__main__":
    main()
