"""
Patch extended_api_data.json for films whose titles contain parenthetical
year suffixes — those titles broke the Wikipedia / Wikiquote / OMDb
lookups in the original collection run.

Specifically affected (year suffix in CSV title):
  - The Lion King (1994)
  - The Lion King (2019)
  - Beauty and the Beast (1991)
  - Beauty and the Beast (2017)

For each of these films we re-query:
  - Wikipedia pageviews          (using clean title + year disambiguation)
  - Wikipedia language editions   (Wikidata sitelinks count)
  - Wikiquote dialogue blocks     (Wikiquote page lookup)
  - OMDb awards / IMDb rating     (OMDb by title + year)

Also re-derives the meme/community block from the existing reddit posts
because that piece doesn't depend on the title; we only re-run it for
consistency after we've touched the record.

Usage:
  python scripts/fix_disambiguation_titles.py
"""

import json
import logging
import os
import re
import time
from collections import Counter
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")

load_dotenv(os.path.join(PROJECT_DIR, ".env"))

HEADERS = {
    "User-Agent": "PandoraParadoxCapstone/1.0 (Academic Research)",
    "Accept-Language": "en-US,en;q=0.9",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Films to patch. Map original CSV title -> cleaned title used for API lookup.
TITLES_TO_FIX = {
    "The Lion King (1994)": "The Lion King",
    "The Lion King (2019)": "The Lion King",
    "Beauty and the Beast (1991)": "Beauty and the Beast",
    "Beauty and the Beast (2017)": "Beauty and the Beast",
}

# Subreddits considered primarily meme/humour oriented (mirrors 06_1).
MEME_SUBREDDITS = {
    "shittymoviedetails", "prequelmemes", "sequelmemes",
    "dankmemes", "memes", "funny", "wholesomememes",
    "moviememes", "avatarmemes", "marvelmemes", "starwarsmemes",
    "meirl", "me_irl", "movieshitposting",
}


# ============================================================
# Wikipedia pageviews (re-run with disambiguation fallback)
# ============================================================

def fetch_wiki_pageviews(clean_title: str, year: int) -> Dict:
    """Mirror logic from 06_live_data_collectors.py with multiple title candidates."""
    base = clean_title.replace(" ", "_")
    candidates = [f"{base}_({year}_film)", base, f"{base}_(film)"]

    for cand in candidates:
        try:
            from urllib.parse import quote
            encoded = quote(cand, safe="_()")
            url = (
                "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
                f"en.wikipedia/all-access/all-agents/{encoded}/monthly/"
                "2023040100/2026040100"
            )
            time.sleep(0.5)
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                continue
            data = r.json().get("items", [])
            if not data:
                continue
            views = [d.get("views", 0) for d in data]
            return {
                "status": "success",
                "movie_title": clean_title,
                "movie_year": year,
                "wiki_title_used": cand,
                "total_views": sum(views),
                "average_monthly_views": sum(views) / len(views),
                "max_monthly_views": max(views),
                "min_monthly_views": min(views),
                "views_count": len(data),
            }
        except requests.RequestException as e:
            logger.warning(f"  wiki pageviews {cand}: {e}")
    return {"status": "no_data"}


# ============================================================
# Wikipedia language editions (Wikidata sitelinks)
# ============================================================

def fetch_wiki_languages(clean_title: str, year: int) -> Dict:
    """Look up the Wikidata entity for the film and count its sitelinks."""
    base = clean_title.replace(" ", "_")
    candidates = [f"{base}_({year}_film)", base, f"{base}_(film)"]
    for cand in candidates:
        try:
            from urllib.parse import quote
            encoded = quote(cand, safe="_()")
            r = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query", "prop": "langlinks",
                    "lllimit": "max", "format": "json", "titles": cand,
                },
                headers=HEADERS, timeout=30,
            )
            if r.status_code != 200:
                continue
            pages = r.json().get("query", {}).get("pages", {})
            for page_id, page in pages.items():
                if page_id == "-1":
                    continue
                ll = page.get("langlinks", []) or []
                # Add 1 for English itself
                return {
                    "status": "success",
                    "wiki_title_used": cand,
                    "language_editions": len(ll) + 1,
                }
            time.sleep(0.3)
        except requests.RequestException:
            continue
    return {"status": "no_data"}


# ============================================================
# Wikiquote (mirrors 06_1_extended_collectors.py)
# ============================================================

_WIKIQUOTE_TITLE_SUFFIXES = ["_({year}_film)", "", "_(film)"]


def scrape_wikiquote(clean_title: str, year: int) -> Dict:
    base = clean_title.replace(" ", "_")
    candidates = [f"{base}{suffix.format(year=year)}" for suffix in _WIKIQUOTE_TITLE_SUFFIXES]
    last_error = None
    for cand in candidates:
        try:
            url = f"https://en.wikiquote.org/wiki/{cand}"
            time.sleep(0.5)
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                last_error = "not_found"
                continue
            if r.status_code != 200:
                last_error = f"HTTP {r.status_code}"
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            if soup.select_one(".noarticletext"):
                last_error = "noarticletext"
                continue
            content = soup.find(id="mw-content-text")
            if content is None:
                continue
            dl_count = len(content.find_all("dl"))
            li_count = len(content.find_all("li"))
            return {
                "status": "success",
                "wikiquote_title": cand,
                "wikiquote_url": url,
                "wikiquote_dl_count": dl_count,
                "wikiquote_li_count": li_count,
                "wikiquote_count": dl_count,
            }
        except requests.RequestException as e:
            last_error = str(e)
    return {"status": "not_found", "wikiquote_count": 0, "error": last_error}


# ============================================================
# OMDb (mirrors 06_1_extended_collectors.py)
# ============================================================

_OSCAR_WON_RE = re.compile(r"Won\s+(\d+)\s+Oscar", re.IGNORECASE)
_OSCAR_NOM_RE = re.compile(r"Nominated for\s+(\d+)\s+Oscar", re.IGNORECASE)
_TOTAL_WINS_RE = re.compile(r"(\d+)\s+wins?", re.IGNORECASE)
_TOTAL_NOMS_RE = re.compile(r"(\d+)\s+nominations?", re.IGNORECASE)


def parse_awards_string(s: str) -> Dict:
    if not s or s.strip().lower() == "n/a":
        return {"oscar_wins": 0, "oscar_nominations": 0,
                "total_wins": 0, "total_nominations": 0,
                "awards_raw": s or ""}
    out = {"awards_raw": s}
    for key, pat in (("oscar_wins", _OSCAR_WON_RE),
                     ("oscar_nominations", _OSCAR_NOM_RE),
                     ("total_wins", _TOTAL_WINS_RE),
                     ("total_nominations", _TOTAL_NOMS_RE)):
        m = pat.search(s)
        out[key] = int(m.group(1)) if m else 0
    if out["oscar_wins"] and not out["total_wins"]:
        out["total_wins"] = out["oscar_wins"]
    if out["oscar_nominations"] and not out["total_nominations"]:
        out["total_nominations"] = out["oscar_nominations"]
    return out


def fetch_omdb(clean_title: str, year: int, api_key: str) -> Dict:
    if not api_key:
        return {"status": "skipped", "reason": "no key"}
    try:
        time.sleep(0.3)
        r = requests.get("https://www.omdbapi.com/", headers=HEADERS,
                         params={"apikey": api_key, "t": clean_title, "y": year},
                         timeout=30)
        r.raise_for_status()
        d = r.json()
        if d.get("Response") != "True":
            return {"status": "not_found", "error": d.get("Error", "unknown")}
        out = parse_awards_string(d.get("Awards", ""))
        out.update({
            "status": "success",
            "imdb_id": d.get("imdbID"),
            "imdb_rating": (float(d["imdbRating"]) if d.get("imdbRating", "N/A") != "N/A" else None),
            "metascore": (int(d["Metascore"]) if d.get("Metascore", "N/A") != "N/A" else None),
        })
        votes_raw = d.get("imdbVotes", "N/A")
        if votes_raw and votes_raw != "N/A":
            try:
                out["imdb_votes"] = int(votes_raw.replace(",", ""))
            except ValueError:
                out["imdb_votes"] = None
        else:
            out["imdb_votes"] = None
        return out
    except requests.RequestException as e:
        return {"status": "error", "error": str(e)}


# ============================================================
# Reddit-derived (no API call)
# ============================================================

def derive_reddit_features(reddit_block: Dict) -> Dict:
    posts = reddit_block.get("posts", []) if isinstance(reddit_block, dict) else []
    if not posts:
        return {"meme_post_count": 0, "subreddit_diversity": 0,
                "top_subreddit": None, "subreddit_concentration": None}
    subs = [p.get("subreddit", "").lower() for p in posts if p.get("subreddit")]
    if not subs:
        return {"meme_post_count": 0, "subreddit_diversity": 0,
                "top_subreddit": None, "subreddit_concentration": None}
    counts = Counter(subs)
    meme_posts = sum(c for s, c in counts.items() if s in MEME_SUBREDDITS)
    diversity = len(counts)
    top_sub, top_count = counts.most_common(1)[0]
    total = sum(counts.values())
    hhi = sum((c / total) ** 2 for c in counts.values())
    return {
        "meme_post_count": meme_posts,
        "subreddit_diversity": diversity,
        "top_subreddit": top_sub,
        "top_subreddit_post_count": top_count,
        "subreddit_concentration": hhi,
    }


# ============================================================
# Driver
# ============================================================

def main():
    in_path = os.path.join(DATA_DIR, "extended_api_data.json")
    with open(in_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    omdb_key = os.environ.get("OMDB_API_KEY")
    if not omdb_key:
        logger.warning("OMDB_API_KEY missing; awards block will be skipped")

    n_patched = 0
    for rec in records:
        title = rec.get("movie_title")
        if title not in TITLES_TO_FIX:
            continue
        year = rec.get("movie_year")
        clean = TITLES_TO_FIX[title]
        logger.info(f"Patching: {title} ({year}) -> using clean title '{clean}'")

        before_wq = (rec.get("metrics", {}).get("wikiquote_quotes", {}) or {}).get("wikiquote_count", 0)
        before_views = (rec.get("metrics", {}).get("wikipedia_pageviews", {}) or {}).get("total_views", 0)

        m = rec.setdefault("metrics", {})

        new_views = fetch_wiki_pageviews(clean, year)
        if new_views.get("status") == "success" and new_views.get("total_views", 0) > before_views:
            m["wikipedia_pageviews"] = new_views
            logger.info(f"  wiki views: {before_views} -> {new_views['total_views']}")

        new_langs = fetch_wiki_languages(clean, year)
        if new_langs.get("status") == "success":
            m.setdefault("wikipedia_languages", {})
            m["wikipedia_languages"].update({
                "status": "success",
                "language_editions": new_langs["language_editions"],
                "wiki_title_used": new_langs["wiki_title_used"],
            })
            logger.info(f"  languages: {new_langs['language_editions']}")

        new_wq = scrape_wikiquote(clean, year)
        if new_wq.get("status") == "success":
            m["wikiquote_quotes"] = new_wq
            logger.info(f"  wikiquote: {before_wq} -> {new_wq['wikiquote_count']} dl blocks")

        new_om = fetch_omdb(clean, year, omdb_key)
        if new_om.get("status") == "success":
            m["omdb_awards"] = new_om
            logger.info(f"  omdb wins: {new_om.get('total_wins',0)}, "
                        f"noms: {new_om.get('total_nominations',0)}, "
                        f"imdb_rating: {new_om.get('imdb_rating')}")

        # Re-derive reddit community features (cheap, no API)
        red = m.get("reddit_mentions", {})
        m["reddit_derived"] = derive_reddit_features(red)
        n_patched += 1

    with open(in_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    logger.info(f"Patched {n_patched} films and rewrote {in_path}")


if __name__ == "__main__":
    main()
