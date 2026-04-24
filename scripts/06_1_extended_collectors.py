"""
Phase 6.1 - Extended collectors (awards, realized quotability, meme signal).

Reads data/live_api_data.json (produced by 06_live_data_collectors.py) and
augments each film with three new metrics:

  1. awards_wins / awards_nominations / oscar_wins
       Source: OMDb API (http://www.omdbapi.com/)
       Parses the plain-text 'Awards' field into numbers.

  2. wikiquote_count
       Source: Wikiquote (https://en.wikiquote.org/wiki/<Movie_Title>)
       IMDb's /quotes page is blocked by anti-bot (HTTP 202 with empty body)
       so we use Wikiquote instead. A film having a Wikiquote page at all is
       itself a quotability signal — and the number of <dl> dialogue blocks
       gives a coarse count of memorable exchanges.

  3. meme_post_count / subreddit_diversity / top_subreddit
       Source: the 'reddit_mentions.posts' sub-array we already collected.
       No new API calls needed.

Output:
  data/extended_api_data.json  - augmented copy of live_api_data.json
"""

import argparse
import json
import logging
import os
import re
import time
from collections import Counter
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")

HEADERS = {
    "User-Agent": "PandoraParadoxCapstone/1.0 (Academic Research)",
    "Accept-Language": "en-US,en;q=0.9",
}
RATE_LIMITS = {"omdb": 0.3, "wikiquote": 0.5}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_DIR, "extended_collection.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# Subreddits considered primarily meme/humour oriented.
# Presence of a film's title in posts from these reflects meme activity.
MEME_SUBREDDITS = {
    "shittymoviedetails", "prequelmemes", "sequelmemes",
    "dankmemes", "memes", "funny", "wholesomememes",
    "moviememes", "avatarmemes", "marvelmemes", "starwarsmemes",
    "meirl", "me_irl", "movieshitposting",
}


# ============================================================
# 1. OMDb awards
# ============================================================

_OSCAR_WON_RE = re.compile(r"Won\s+(\d+)\s+Oscar", re.IGNORECASE)
_OSCAR_NOM_RE = re.compile(r"Nominated for\s+(\d+)\s+Oscar", re.IGNORECASE)
_TOTAL_WINS_RE = re.compile(r"(\d+)\s+wins?", re.IGNORECASE)
_TOTAL_NOMS_RE = re.compile(r"(\d+)\s+nominations?", re.IGNORECASE)


def parse_awards_string(awards_str: str) -> Dict:
    """Parse strings like 'Won 3 Oscars. 92 wins & 63 nominations total.'"""
    if not awards_str or awards_str.strip().lower() == "n/a":
        return {"oscar_wins": 0, "oscar_nominations": 0,
                "total_wins": 0, "total_nominations": 0,
                "awards_raw": awards_str or ""}

    oscar_wins = 0
    oscar_noms = 0
    m = _OSCAR_WON_RE.search(awards_str)
    if m:
        oscar_wins = int(m.group(1))
    m = _OSCAR_NOM_RE.search(awards_str)
    if m:
        oscar_noms = int(m.group(1))

    total_wins = 0
    total_noms = 0
    m = _TOTAL_WINS_RE.search(awards_str)
    if m:
        total_wins = int(m.group(1))
    m = _TOTAL_NOMS_RE.search(awards_str)
    if m:
        total_noms = int(m.group(1))

    # If only 'Won N Oscars' is given without a 'wins' summary, surface it.
    if oscar_wins and total_wins == 0:
        total_wins = oscar_wins
    if oscar_noms and total_noms == 0:
        total_noms = oscar_noms

    return {
        "oscar_wins": oscar_wins,
        "oscar_nominations": oscar_noms,
        "total_wins": total_wins,
        "total_nominations": total_noms,
        "awards_raw": awards_str,
    }


def collect_omdb_awards(
    title: str, year: int, api_key: str, imdb_id: Optional[str] = None
) -> Dict:
    """Fetch awards summary from OMDb by title+year (fallback to imdb_id)."""
    if not api_key:
        return {"status": "skipped", "reason": "no OMDb key"}
    try:
        params = {"apikey": api_key, "y": year}
        if imdb_id:
            params["i"] = imdb_id
        else:
            params["t"] = title
        time.sleep(RATE_LIMITS["omdb"])
        resp = requests.get("https://www.omdbapi.com/", headers=HEADERS,
                            params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("Response") != "True":
            return {"status": "not_found",
                    "error": data.get("Error", "unknown")}
        awards = parse_awards_string(data.get("Awards", ""))
        awards["status"] = "success"
        awards["imdb_id"] = data.get("imdbID")
        awards["imdb_rating"] = (
            float(data["imdbRating"]) if data.get("imdbRating", "N/A") != "N/A" else None
        )
        awards["metascore"] = (
            int(data["Metascore"]) if data.get("Metascore", "N/A") != "N/A" else None
        )
        # imdb_votes arrives as a string like "1,300,000" — strip commas before int()
        votes_raw = data.get("imdbVotes", "N/A")
        if votes_raw and votes_raw != "N/A":
            try:
                awards["imdb_votes"] = int(votes_raw.replace(",", ""))
            except (ValueError, AttributeError):
                awards["imdb_votes"] = None
        else:
            awards["imdb_votes"] = None
        return awards
    except requests.RequestException as e:
        logger.warning(f"OMDb failed for {title}: {e}")
        return {"status": "error", "error": str(e)}


# ============================================================
# 2. Wikiquote quote count
# ============================================================

_WIKIQUOTE_TITLE_SUFFIXES = ["_({year}_film)", "", "_(film)"]


def scrape_wikiquote_count(title: str, year: int) -> Dict:
    """
    Count dialogue-block quotes on the film's Wikiquote page.

    Strategy:
      - Try a few Wikiquote page-title variants (with/without year disambiguation)
      - If the page exists, count <dl> blocks in the main content (each <dl>
        typically represents one dialogue exchange)
      - If no page exists for any candidate, return 0 quotes.
    """
    base = title.replace(" ", "_")
    candidates = [
        f"{base}{suffix.format(year=year)}" for suffix in _WIKIQUOTE_TITLE_SUFFIXES
    ]

    last_error = None
    for candidate in candidates:
        try:
            url = f"https://en.wikiquote.org/wiki/{candidate}"
            time.sleep(RATE_LIMITS["wikiquote"])
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 404:
                last_error = "not_found"
                continue
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            # Wikipedia-family sites return an HTML page even for missing
            # articles; detect that via a .noarticletext marker.
            if soup.select_one(".noarticletext"):
                last_error = "noarticletext"
                continue

            content = soup.find(id="mw-content-text")
            if content is None:
                last_error = "no_content_div"
                continue

            dl_count = len(content.find_all("dl"))
            # Top-level <li> that aren't inside navigation: rough secondary count
            li_count = len(content.find_all("li"))

            return {
                "status": "success",
                "wikiquote_title": candidate,
                "wikiquote_url": url,
                "wikiquote_dl_count": dl_count,
                "wikiquote_li_count": li_count,
                # Primary quote count: dl blocks (dialogue) are the cleanest signal
                "wikiquote_count": dl_count,
            }
        except requests.RequestException as e:
            last_error = str(e)
            continue

    return {
        "status": "not_found",
        "wikiquote_count": 0,
        "error": last_error,
    }


# ============================================================
# 3. Derived meme & community breadth features (no API calls)
# ============================================================

def derive_reddit_community_features(reddit_block: Dict) -> Dict:
    """Compute meme_post_count, subreddit_diversity, top_subreddit, concentration."""
    posts = reddit_block.get("posts", []) if isinstance(reddit_block, dict) else []
    if not posts:
        return {
            "meme_post_count": 0,
            "subreddit_diversity": 0,
            "top_subreddit": None,
            "subreddit_concentration": None,
        }
    subs = [p.get("subreddit", "").lower() for p in posts if p.get("subreddit")]
    if not subs:
        return {
            "meme_post_count": 0,
            "subreddit_diversity": 0,
            "top_subreddit": None,
            "subreddit_concentration": None,
        }
    counts = Counter(subs)
    meme_posts = sum(c for s, c in counts.items() if s in MEME_SUBREDDITS)
    diversity = len(counts)
    top_sub, top_count = counts.most_common(1)[0]
    total = sum(counts.values())
    # Herfindahl index: sum of (share^2); 1.0 = one sub dominates, near 0 = diffuse
    hhi = sum((c / total) ** 2 for c in counts.values())
    return {
        "meme_post_count": meme_posts,
        "subreddit_diversity": diversity,
        "top_subreddit": top_sub,
        "top_subreddit_post_count": top_count,
        "subreddit_concentration": hhi,
    }


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=os.path.join(DATA_DIR, "live_api_data.json"))
    parser.add_argument("--output", default=os.path.join(DATA_DIR, "extended_api_data.json"))
    parser.add_argument("--omdb-key", default=os.environ.get("OMDB_API_KEY"))
    parser.add_argument("--skip-wikiquote", action="store_true",
                        help="Skip Wikiquote scraping (faster)")
    parser.add_argument("--skip-omdb", action="store_true",
                        help="Skip OMDb calls (faster)")
    parser.add_argument("--resume", action="store_true",
                        help="Keep records already present in the output file")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if not os.path.exists(args.input):
        raise SystemExit(f"Input not found: {args.input}")

    with open(args.input, "r", encoding="utf-8") as f:
        records = json.load(f)
    if args.limit:
        records = records[: args.limit]
    logger.info(f"Loaded {len(records)} records from {args.input}")

    already_done = {}
    if args.resume and os.path.exists(args.output):
        with open(args.output, "r", encoding="utf-8") as f:
            for r in json.load(f):
                already_done[(r.get("movie_title"), r.get("movie_year"))] = r
        logger.info(f"Resume: {len(already_done)} films already extended")

    out_records = list(already_done.values())

    for idx, rec in enumerate(records):
        title = rec.get("movie_title")
        year = rec.get("movie_year")
        key = (title, year)
        if key in already_done:
            continue

        logger.info(f"[{idx+1}/{len(records)}] {title} ({year})")

        metrics = dict(rec.get("metrics", {}))
        reddit_block = metrics.get("reddit_mentions", {})

        # --- Derived meme + community features (instant, no I/O)
        metrics["reddit_derived"] = derive_reddit_community_features(reddit_block)

        # --- OMDb awards
        if not args.skip_omdb and args.omdb_key:
            awards = collect_omdb_awards(title, year, args.omdb_key)
            metrics["omdb_awards"] = awards
        else:
            metrics["omdb_awards"] = {"status": "skipped"}

        # --- Wikiquote-based realized quotability (replaces IMDb which is blocked)
        if not args.skip_wikiquote:
            metrics["wikiquote_quotes"] = scrape_wikiquote_count(title, year)
        else:
            metrics["wikiquote_quotes"] = {"status": "skipped"}

        new_rec = dict(rec)
        new_rec["metrics"] = metrics
        out_records.append(new_rec)

        # Incremental save every 5 records
        if (idx + 1) % 5 == 0:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(out_records, f, ensure_ascii=False, indent=2)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out_records, f, ensure_ascii=False, indent=2)
    logger.info(f"Wrote {len(out_records)} records -> {args.output}")


if __name__ == "__main__":
    main()
