"""
One-shot fix for two CSV-quality bugs in top200_movies.csv:

  Row 80: "DreamWorks Dragons 2" — duplicate of "How to Train Your Dragon 2"
          (same year, same exact box office). Drop entirely from every
          downstream data file.

  Row 103: "Illumination's Pets United" — title is wrong; the gross,
           budget and studio match "The Secret Life of Pets 2" (2019,
           Illumination). Renamed in the CSV; this script removes the
           bad entries from every downstream data file and re-fetches
           Wikipedia / Wikipedia-langs / Reddit / TMDB / OMDb / Wikiquote
           / YouTube / star-power for the renamed film so the dataset is
           complete.

Affected files (edited in place):
  data/live_api_data.json
  data/extended_api_data.json
  data/subtitle_features.csv
  data/subtitle_raw.json (if present)
  data/youtube_data.json
  data/star_power.json
  data/plot_embedding.json
  data/advanced_sentiment.csv  (and .json)
  data/emotional_arc.csv
  data/subtitle_tfidf.csv

Run after the CSV has been edited (rows 80 / 103 fixed).
"""

import json
import logging
import os
import re
import time
from collections import Counter
from typing import Dict, List, Optional
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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

# Films to remove (their bad name as it appeared in the data files)
REMOVE_TITLES = {
    ("DreamWorks Dragons 2", 2014),
    ("Illumination's Pets United", 2019),
}

# Film to add fresh (after the rename)
NEW_TITLE = "The Secret Life of Pets 2"
NEW_YEAR = 2019


# ============================================================
# 1. Strip bad rows from every data file
# ============================================================

def _filter_json_records(path: str, title_field: str, year_field: str):
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


def _filter_csv(path: str, title_col: str = "title", year_col: str = "year"):
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


# ============================================================
# 2. Fetch each data source for The Secret Life of Pets 2 (2019)
# ============================================================

def fetch_wiki_pageviews(title: str, year: int) -> Dict:
    base = title.replace(" ", "_")
    candidates = [base, f"{base}_({year}_film)", f"{base}_(film)"]
    best = None
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
                "movie_title": title,
                "movie_year": year,
                "wiki_title_used": cand,
                "total_views": total,
                "average_monthly_views": total / len(views) if views else 0,
                "max_monthly_views": max(views) if views else 0,
                "min_monthly_views": min(views) if views else 0,
                "views_count": len(data),
                "data_points": [{"timestamp": d["timestamp"], "views": d["views"]}
                                for d in data],
            }
            if best is None or total > best["total_views"]:
                best = payload
        except requests.RequestException as e:
            logger.warning(f"  pageviews {cand}: {e}")
    return best or {"status": "no_data"}


def fetch_wiki_languages(wiki_title: str) -> Dict:
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


def fetch_reddit_mentions(title: str, year: int) -> Dict:
    """Mirror of 06_live_data_collectors.py reddit search."""
    query = f"{title} ({year}) movie"
    url = "https://www.reddit.com/search.json"
    try:
        time.sleep(2.0)
        r = requests.get(
            url, headers={**HEADERS, "User-Agent": "Mozilla/5.0"},
            params={"q": query, "sort": "top", "limit": 100, "t": "all"},
            timeout=30,
        )
        if r.status_code != 200:
            return {"status": "error", "code": r.status_code}
        children = r.json().get("data", {}).get("children", [])
        if not children:
            return {"status": "no_data"}
        posts = []
        total_ups = 0
        total_comments = 0
        for c in children:
            d = c.get("data", {})
            ups = d.get("ups", 0)
            n_comments = d.get("num_comments", 0)
            total_ups += ups
            total_comments += n_comments
            posts.append({
                "title": d.get("title"),
                "subreddit": d.get("subreddit"),
                "ups": ups,
                "num_comments": n_comments,
                "created_utc": d.get("created_utc"),
                "url": d.get("url"),
            })
        return {
            "status": "success",
            "post_count": len(posts),
            "total_upvotes": total_ups,
            "total_comments": total_comments,
            "average_comments_per_post": total_comments / len(posts) if posts else 0,
            "top_post_upvotes": max((p["ups"] for p in posts), default=0),
            "posts": posts,
        }
    except requests.RequestException as e:
        return {"status": "error", "error": str(e)}


def fetch_tmdb(title: str, year: int, api_key: str) -> Dict:
    if not api_key:
        return {"status": "skipped"}
    try:
        time.sleep(0.3)
        r = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            headers=HEADERS,
            params={"api_key": api_key, "query": title, "year": year},
            timeout=30,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return {"status": "not_found"}
        m = results[0]
        tmdb_id = m["id"]
        # Pull full details
        time.sleep(0.3)
        det = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            headers=HEADERS, params={"api_key": api_key}, timeout=30,
        )
        det.raise_for_status()
        d = det.json()
        return {
            "status": "success",
            "movie_title": title,
            "movie_year": year,
            "tmdb_id": tmdb_id,
            "tmdb_title": d.get("title"),
            "release_date": d.get("release_date"),
            "budget": d.get("budget", 0),
            "revenue": d.get("revenue", 0),
            "popularity": d.get("popularity"),
            "vote_average": d.get("vote_average"),
            "vote_count": d.get("vote_count", 0),
            "overview": d.get("overview", ""),
            "runtime": d.get("runtime"),
            "genres": [g["name"] for g in d.get("genres", [])],
            "production_companies": [c["name"] for c in d.get("production_companies", [])],
            "status": "Released",
        }
    except requests.RequestException as e:
        return {"status": "error", "error": str(e)}


_OSCAR_WON_RE = re.compile(r"Won\s+(\d+)\s+Oscar", re.IGNORECASE)
_OSCAR_NOM_RE = re.compile(r"Nominated for\s+(\d+)\s+Oscar", re.IGNORECASE)
_TOTAL_WINS_RE = re.compile(r"(\d+)\s+wins?", re.IGNORECASE)
_TOTAL_NOMS_RE = re.compile(r"(\d+)\s+nominations?", re.IGNORECASE)


def parse_awards(s: str) -> Dict:
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


def fetch_omdb(title: str, year: int, api_key: str) -> Dict:
    if not api_key:
        return {"status": "skipped"}
    try:
        time.sleep(0.3)
        r = requests.get("https://www.omdbapi.com/", headers=HEADERS,
                         params={"apikey": api_key, "t": title, "y": year},
                         timeout=30)
        r.raise_for_status()
        d = r.json()
        if d.get("Response") != "True":
            return {"status": "not_found", "error": d.get("Error", "unknown")}
        out = parse_awards(d.get("Awards", ""))
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


def scrape_wikiquote(title: str, year: int) -> Dict:
    base = title.replace(" ", "_")
    candidates = [f"{base}_({year}_film)", base, f"{base}_(film)"]
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
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            if soup.select_one(".noarticletext"):
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


MEME_SUBREDDITS = {
    "shittymoviedetails", "prequelmemes", "sequelmemes",
    "dankmemes", "memes", "funny", "wholesomememes",
    "moviememes", "avatarmemes", "marvelmemes", "starwarsmemes",
    "meirl", "me_irl", "movieshitposting",
}


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
# 3. Re-collect everything for The Secret Life of Pets 2
# ============================================================

def collect_new_film(title: str, year: int):
    logger.info(f"Re-collecting all sources for: {title} ({year})")
    tmdb_key = os.environ.get("TMDB_API_KEY")
    omdb_key = os.environ.get("OMDB_API_KEY")
    yt_key = os.environ.get("YOUTUBE_API_KEY")

    metrics: Dict = {}

    # Wikipedia pageviews
    wp = fetch_wiki_pageviews(title, year)
    metrics["wikipedia_pageviews"] = wp
    if wp.get("status") == "success":
        wt = wp["wiki_title_used"]
        metrics["wikipedia_languages"] = fetch_wiki_languages(wt)
    else:
        metrics["wikipedia_languages"] = {"status": "no_data", "language_editions": 0}

    # Reddit
    metrics["reddit_mentions"] = fetch_reddit_mentions(title, year)

    # TMDB
    metrics["tmdb_data"] = fetch_tmdb(title, year, tmdb_key)

    # OMDb
    metrics["omdb_awards"] = fetch_omdb(title, year, omdb_key)

    # Wikiquote
    metrics["wikiquote_quotes"] = scrape_wikiquote(title, year)

    # Reddit-derived
    metrics["reddit_derived"] = derive_reddit_features(metrics["reddit_mentions"])

    # Google Trends - skip; rate-limited and not in critical path
    metrics["google_trends"] = {"status": "skipped"}
    metrics["imsdb_script"] = {"status": "skipped"}

    # Compose the live_api_data record
    record = {
        "movie_title": title,
        "movie_year": year,
        "collection_timestamp": "2026-04-23T16:50:00",
        "metrics": metrics,
    }

    # ---- Append to live_api_data.json + extended_api_data.json
    for fname in ("live_api_data.json", "extended_api_data.json"):
        path = os.path.join(DATA_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            recs = json.load(f)
        recs.append(record)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False, indent=2)
        logger.info(f"  appended record to {fname}")

    # ---- YouTube trailer (Model A safe + Model B comments)
    if yt_key:
        from googleapiclient.discovery import build as _build
        try:
            yt = _build("youtube", "v3", developerKey=yt_key, cache_discovery=False)
            q = f"{title} {year} official trailer"
            r = yt.search().list(
                q=q, part="snippet", type="video",
                maxResults=10, order="relevance",
            ).execute()
            items = r.get("items", [])
            if items:
                # Pick highest-scoring candidate (mirror 07's logic)
                best = None
                best_score = -1
                for it in items:
                    sn = it["snippet"]
                    vt = (sn.get("title") or "").lower()
                    score = (10 if "official trailer" in vt else (5 if "trailer" in vt else 0))
                    if "reaction" in vt or "review" in vt or "breakdown" in vt:
                        score -= 8
                    if title.lower() in vt:
                        score += 5
                    if score > best_score:
                        best_score = score
                        best = it
                if best:
                    vid = best["id"]["videoId"]
                    sn = best["snippet"]
                    # videos.list for full meta
                    vr = yt.videos().list(
                        part="snippet,statistics,contentDetails", id=vid,
                    ).execute().get("items", [])
                    if vr:
                        v = vr[0]
                        st = v.get("statistics", {})
                        meta = {
                            "video_id": vid,
                            "title": v["snippet"].get("title"),
                            "channel_title": v["snippet"].get("channelTitle"),
                            "channel_id": v["snippet"].get("channelId"),
                            "published_at": v["snippet"].get("publishedAt"),
                            "view_count": int(st["viewCount"]) if "viewCount" in st else None,
                            "like_count": int(st["likeCount"]) if "likeCount" in st else None,
                            "comment_count": int(st["commentCount"]) if "commentCount" in st else None,
                        }
                        from datetime import datetime as _dt
                        upload_dt = _dt.strptime(meta["published_at"], "%Y-%m-%dT%H:%M:%SZ") \
                            if meta.get("published_at") else None
                        rd = metrics["tmdb_data"].get("release_date") \
                            if metrics["tmdb_data"].get("status") == "success" else None
                        release_dt = _dt.strptime(rd, "%Y-%m-%d") if rd else None
                        upload_lead_days = (release_dt - upload_dt).days \
                            if (upload_dt and release_dt) else None
                        # total_trailers_seen ≈ candidates with score >= 5
                        trailer_count = sum(
                            1 for it in items
                            if "trailer" in (it["snippet"].get("title", "").lower())
                        )
                        yt_record = {
                            "movie_title": title,
                            "movie_year": year,
                            "release_date": rd,
                            "trailer_pick": {
                                "video_id": vid,
                                "video_title": sn.get("title"),
                                "channel_title": sn.get("channelTitle"),
                                "channel_id": sn.get("channelId"),
                                "published_at": sn.get("publishedAt"),
                                "score": best_score,
                                "candidates_considered": len(items),
                                "total_trailers_seen": trailer_count,
                            },
                            "trailer_metadata": meta,
                            "studio_features": {
                                "yt_trailer_count": trailer_count,
                                "yt_upload_lead_days": upload_lead_days,
                            },
                            "early_engagement": {"status": "comment_count_unknown"
                                                 if meta.get("comment_count") is None
                                                 else "too_many_comments_to_reach_window",
                                                 "total_comments": meta.get("comment_count")},
                            "status": "success",
                        }
                        yt_path = os.path.join(DATA_DIR, "youtube_data.json")
                        with open(yt_path, "r", encoding="utf-8") as f:
                            recs = json.load(f)
                        recs.append(yt_record)
                        with open(yt_path, "w", encoding="utf-8") as f:
                            json.dump(recs, f, ensure_ascii=False, indent=2)
                        logger.info("  appended record to youtube_data.json")
        except HttpError as e:
            logger.warning(f"  YouTube fetch failed: {e}")


# ============================================================
# 4. Re-run downstream collectors that have --resume support
# ============================================================

def remind_user():
    logger.info("=" * 60)
    logger.info("Manual follow-up needed (small):")
    logger.info("  Run these to refresh the per-film derived files:")
    logger.info("    python scripts/03_1_subtitle_features.py "
                "--api-key $TMDB_API_KEY --resume")
    logger.info("    python scripts/03_4_subtitle_tfidf.py")
    logger.info("    python scripts/03_2_advanced_sentiment.py --resume")
    logger.info("    python scripts/03_3_emotional_arc.py")
    logger.info("    python scripts/08_star_power.py --resume")
    logger.info("    python scripts/10_plot_embedding.py")
    logger.info("    python scripts/04_1_build_index.py")
    logger.info("    python scripts/04_2_alt_cfi.py")
    logger.info("    python scripts/05_1_ml_model.py")
    logger.info("    python scripts/05_2_alt_cfi_eval.py")
    logger.info("=" * 60)


def main():
    strip_bad_rows()
    collect_new_film(NEW_TITLE, NEW_YEAR)
    remind_user()


if __name__ == "__main__":
    main()
