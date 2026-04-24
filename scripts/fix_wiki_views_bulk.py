"""
Bulk-patch wiki views / Wikiquote / OMDb / Wikipedia languages for any
film whose existing wiki_views is implausibly low (<= 100). The original
collector picked the FIRST title candidate that returned 200, but for
many films the disambiguated `_(YYYY_film)` page is a near-empty redirect
while the canonical page lives at the bare title.

Strategy:
  For each suspicious film, re-query each candidate title and pick the
  one whose monthly pageviews are HIGHEST (not just the first 200-OK
  response). Update Wikipedia pageviews, Wikipedia language editions,
  Wikiquote dialogue blocks, and OMDb awards accordingly — reuse helpers
  from fix_disambiguation_titles.py where possible.

Films fixed:
  - Anything whose current total_views <= 100 (~18 titles in our data)
  - This includes Apollo 13, Pulp Fiction, Avengers: Infinity War,
    Jurassic Park, Star Wars: The Last Jedi, etc.

Usage:
  python scripts/fix_wiki_views_bulk.py
"""

import json
import logging
import os
import re
import time
from collections import Counter
from typing import Dict, List, Optional
from urllib.parse import quote

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
SUSPICION_THRESHOLD = 100   # if wiki_views <= this, refetch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _strip_year_paren(title: str) -> str:
    """'The Lion King (1994)' -> 'The Lion King'."""
    return re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()


def fetch_wiki_pageviews_best(clean_title: str, year: int) -> Dict:
    """
    Try multiple title candidates and return the one with HIGHEST views,
    not just the first 200-OK. This fixes the case where the disambig
    page is a near-empty redirect.
    """
    base = clean_title.replace(" ", "_")
    candidates = [base, f"{base}_({year}_film)", f"{base}_(film)"]

    best: Optional[Dict] = None
    for cand in candidates:
        try:
            encoded = quote(cand, safe="_():,!")
            url = (
                "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
                f"en.wikipedia/all-access/all-agents/{encoded}/monthly/"
                "2023040100/2026040100"
            )
            time.sleep(0.4)
            r = requests.get(url, headers=HEADERS, timeout=45)
            if r.status_code != 200:
                continue
            data = r.json().get("items", [])
            if not data:
                continue
            views = [d.get("views", 0) for d in data]
            total = sum(views)
            payload = {
                "status": "success",
                "movie_title": clean_title,
                "movie_year": year,
                "wiki_title_used": cand,
                "total_views": total,
                "average_monthly_views": total / len(views) if views else 0,
                "max_monthly_views": max(views) if views else 0,
                "min_monthly_views": min(views) if views else 0,
                "views_count": len(data),
            }
            if best is None or total > best["total_views"]:
                best = payload
        except requests.RequestException as e:
            logger.warning(f"  pageviews {cand}: {e}")
    return best or {"status": "no_data"}


def fetch_wiki_languages(wiki_title: str) -> Dict:
    """Use a confirmed wiki_title (from pageviews lookup) for language lookup."""
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "prop": "langlinks",
                "lllimit": "max", "format": "json", "titles": wiki_title,
            },
            headers=HEADERS, timeout=30,
        )
        time.sleep(0.3)
        if r.status_code != 200:
            return {"status": "error"}
        pages = r.json().get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            if page_id == "-1":
                continue
            ll = page.get("langlinks", []) or []
            return {
                "status": "success",
                "language_editions": len(ll) + 1,
                "wiki_title_used": wiki_title,
            }
        return {"status": "no_data"}
    except requests.RequestException as e:
        return {"status": "error", "error": str(e)}


_WIKIQUOTE_TITLE_SUFFIXES = ["_({year}_film)", "", "_(film)"]


def scrape_wikiquote(clean_title: str, year: int) -> Dict:
    base = clean_title.replace(" ", "_")
    candidates = [f"{base}{suffix.format(year=year)}" for suffix in _WIKIQUOTE_TITLE_SUFFIXES]
    last_error = None
    for cand in candidates:
        try:
            url = f"https://en.wikiquote.org/wiki/{cand}"
            time.sleep(0.4)
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
        return {"status": "skipped"}
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


def main():
    in_path = os.path.join(DATA_DIR, "extended_api_data.json")
    with open(in_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    omdb_key = os.environ.get("OMDB_API_KEY")

    # Find suspicious films
    suspects: List[Dict] = []
    for rec in records:
        wp = (rec.get("metrics", {}) or {}).get("wikipedia_pageviews", {}) or {}
        if (wp.get("total_views", 0) or 0) <= SUSPICION_THRESHOLD:
            suspects.append(rec)
    logger.info(f"Found {len(suspects)} films with wiki_views <= {SUSPICION_THRESHOLD}; refetching")

    n_pageviews_fixed = 0
    n_wikiquote_fixed = 0
    n_omdb_fixed = 0
    n_languages_fixed = 0

    for rec in suspects:
        title = rec.get("movie_title", "")
        year = rec.get("movie_year")
        clean = _strip_year_paren(title)
        m = rec.setdefault("metrics", {})

        before_views = (m.get("wikipedia_pageviews", {}) or {}).get("total_views", 0) or 0
        before_wq = (m.get("wikiquote_quotes", {}) or {}).get("wikiquote_count", 0) or 0
        before_om = (m.get("omdb_awards", {}) or {}).get("total_wins", 0) or 0
        before_lang = (m.get("wikipedia_languages", {}) or {}).get("language_editions", 0) or 0

        new_views = fetch_wiki_pageviews_best(clean, year)
        if new_views.get("status") == "success" and new_views["total_views"] > before_views:
            m["wikipedia_pageviews"] = new_views
            n_pageviews_fixed += 1
            wiki_title = new_views["wiki_title_used"]
            new_lang = fetch_wiki_languages(wiki_title)
            if new_lang.get("status") == "success" and new_lang["language_editions"] > before_lang:
                m.setdefault("wikipedia_languages", {})
                m["wikipedia_languages"].update({
                    "status": "success",
                    "language_editions": new_lang["language_editions"],
                    "wiki_title_used": wiki_title,
                })
                n_languages_fixed += 1

        new_wq = scrape_wikiquote(clean, year)
        if new_wq.get("status") == "success" and new_wq["wikiquote_count"] > before_wq:
            m["wikiquote_quotes"] = new_wq
            n_wikiquote_fixed += 1

        if omdb_key and before_om == 0:
            new_om = fetch_omdb(clean, year, omdb_key)
            if new_om.get("status") == "success" and new_om.get("total_wins", 0) > 0:
                m["omdb_awards"] = new_om
                n_omdb_fixed += 1

        new_v = (m.get("wikipedia_pageviews", {}) or {}).get("total_views", 0)
        new_q = (m.get("wikiquote_quotes", {}) or {}).get("wikiquote_count", 0)
        logger.info(f"  {title[:50]:<50} views {before_views:>7} -> {new_v:>7}, wq {before_wq:>3} -> {new_q:>3}")

    with open(in_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    logger.info(f"Fixed: pageviews={n_pageviews_fixed}, wikiquote={n_wikiquote_fixed}, "
                f"languages={n_languages_fixed}, omdb={n_omdb_fixed}")


if __name__ == "__main__":
    main()
