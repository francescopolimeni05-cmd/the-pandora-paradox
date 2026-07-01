"""
Phase 7 - YouTube trailer collector (data-leakage aware).

Reads data/extended_api_data.json and augments each post-2005 film with
official-trailer features pulled from YouTube Data API v3.

Why only post-2005: YouTube launched Feb 2005. Pre-2005 films have no
contemporary trailer upload, so any "trailer" we find is actually a
re-upload years later — noise, not signal. Those films get yt_* = NaN.

Why we split the features across Model A / Model B:
  "Cultural Footprint Index" measures buzz. If we also feed the model
  YouTube views/likes/comments (which are themselves buzz), we are
  predicting buzz from buzz — circular. So:

    MODEL A SAFE (pure studio decisions, measurable pre-release)
      - yt_trailer_count        how many official trailers they uploaded
      - yt_upload_lead_days     how early they started the campaign

    MODEL B ONLY (early-reception, post-release but still "initial")
      - yt_comments_day_7       comments posted within 7 days of trailer upload
      - yt_comments_day_30      comments posted within 30 days
      - yt_comments_velocity    comments_day_7 / max(1, comments_day_30)

Why no Social Blade / no view-count history:
  Verified during smoke test: socialblade.com/youtube/video/<id> is gated
  behind login for per-video daily history. No free source provides
  reliable Day-7 views/likes at scale. Wayback Machine is the only
  remaining free fallback but coverage is 30-50% and implementation cost
  is high — deferred to post-deadline work.

Why commentThreads has partial coverage:
  YouTube API does not support order="oldest". commentThreads.list with
  order="time" returns NEWEST comments first. For a trailer uploaded in
  2009 with 100k+ comments, the original Day-7 comments are buried under
  years of recent activity and unreachable within any reasonable quota.
  We therefore only attempt comment scanning on trailers with total
  comment_count <= MAX_COMMENTS_FOR_WINDOW. Films above that limit get
  yt_comments_* = NaN.

Quota plan (free tier = 10,000 units/day):
  search.list         = 100 units per call
  videos.list         = 1 unit per call
  commentThreads.list = 1 unit per page (100 comments)
  ≈ 130 units / film for small trailers, 101 units for big trailers (skip).
  ~80 films per day  →  2-day run for 164 films.
  Re-run with --resume to pick up where we stopped.

Output:
  data/youtube_data.json  - raw YouTube records (one per film)
"""

import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")

load_dotenv(os.path.join(PROJECT_DIR, ".env"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

YOUTUBE_CUTOFF_YEAR = 2005

# Only attempt Day-7/30 comment scanning on trailers with total comment count
# below this. Above it, the original Day-7 comments are buried under years
# of activity and unreachable via the API's newest-first ordering.
MAX_COMMENTS_FOR_WINDOW = 5000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_DIR, "youtube_collection.log"),
                            encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# Channels that upload genuinely-official trailers. Not exhaustive — a
# trailer from another channel is still acceptable if the title strongly
# matches, but these are ranked first when multiple candidates tie.
PREFERRED_CHANNELS = {
    "marvel entertainment", "warner bros. pictures", "warner bros.",
    "universal pictures", "sony pictures entertainment", "20th century studios",
    "20th century fox", "paramount pictures", "disney", "walt disney studios",
    "a24", "lionsgate movies", "focus features", "netflix",
    "netflix film club", "rotten tomatoes trailers", "imdb", "movieclips",
    "movieclips trailers", "apple tv", "dreamworks animation",
    "pixar", "illuminationent", "illumination",
}


# ============================================================
# Data-leakage-aware classification helper
# ============================================================

def looks_like_official_trailer(
    video_title: str,
    channel_title: str,
    film_title: str,
) -> Tuple[bool, int]:
    """
    Return (is_official, score). Higher score is a better candidate.

    We rank candidates — we do not hard-filter. If every result is garbage
    we still want to record *something* so the film isn't a silent skip.
    """
    vt = video_title.lower()
    ct = channel_title.lower()
    ft = film_title.lower()

    score = 0
    is_official = False

    if "official trailer" in vt:
        score += 10
        is_official = True
    elif "trailer" in vt:
        score += 5

    # Strong negatives — these are not the official trailer
    for bad in ("reaction", "breakdown", "analysis", "review", "easter egg",
                "explained", "fan made", "fan-made", "fanmade", "honest trailer",
                "parody", "behind the scenes"):
        if bad in vt:
            score -= 8

    # Film title appears in video title
    if ft in vt:
        score += 5

    # Preferred channel
    if ct in PREFERRED_CHANNELS:
        score += 6
    # Heuristic: channel name contains "pictures", "studios", "entertainment"
    elif any(w in ct for w in ("pictures", "studios", "entertainment",
                               "movies", "films")):
        score += 2

    return is_official, score


# ============================================================
# 1. YouTube API — find and fetch trailer metadata + comments
# ============================================================

def search_trailer(
    yt,
    title: str,
    year: int,
) -> Optional[Dict]:
    """Search YouTube for the film's official trailer and rank candidates."""
    query = f"{title} {year} official trailer"
    try:
        resp = yt.search().list(
            q=query,
            part="snippet",
            type="video",
            maxResults=10,
            order="relevance",
        ).execute()
    except HttpError as e:
        raise

    items = resp.get("items", [])
    if not items:
        return None

    scored: List[Tuple[int, Dict]] = []
    for it in items:
        sn = it["snippet"]
        vid = it["id"]["videoId"]
        vt = sn.get("title", "")
        ct = sn.get("channelTitle", "")
        _, score = looks_like_official_trailer(vt, ct, title)
        scored.append((score, {
            "video_id": vid,
            "video_title": vt,
            "channel_title": ct,
            "channel_id": sn.get("channelId"),
            "published_at": sn.get("publishedAt"),
            "score": score,
        }))

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1]
    best["candidates_considered"] = len(scored)
    best["total_trailers_seen"] = sum(1 for s, _ in scored if s >= 5)
    return best


def get_video_metadata(yt, video_id: str) -> Optional[Dict]:
    """videos.list - 1 quota unit."""
    try:
        resp = yt.videos().list(
            part="snippet,statistics,contentDetails",
            id=video_id,
        ).execute()
    except HttpError:
        raise
    items = resp.get("items", [])
    if not items:
        return None
    v = items[0]
    sn = v["snippet"]
    st = v.get("statistics", {})
    cd = v.get("contentDetails", {})
    return {
        "video_id": video_id,
        "title": sn.get("title"),
        "channel_title": sn.get("channelTitle"),
        "channel_id": sn.get("channelId"),
        "published_at": sn.get("publishedAt"),
        "description": (sn.get("description") or "")[:500],
        "duration_iso": cd.get("duration"),
        "view_count": int(st["viewCount"]) if "viewCount" in st else None,
        "like_count": int(st["likeCount"]) if "likeCount" in st else None,
        "comment_count": int(st["commentCount"]) if "commentCount" in st else None,
    }


def _parse_iso8601(s: str) -> Optional[datetime]:
    if not s:
        return None
    # YouTube returns e.g. '2009-08-20T18:23:42Z'
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None


def count_early_comments(
    yt,
    video_id: str,
    reference_dt: datetime,
    max_pages: int = 50,
) -> Dict:
    """
    Paginate commentThreads.list. Count how many top-level comments were
    posted within Day 7 / Day 30 of the reference datetime (= trailer upload).

    max_pages caps quota burn: 50 pages * 100 comments = 5000 comments max.
    Trailers with fewer comments stop paginating naturally via nextPageToken.
    """
    day7_cutoff = reference_dt + timedelta(days=7)
    day30_cutoff = reference_dt + timedelta(days=30)

    day7_count = 0
    day30_count = 0
    total_scanned = 0
    disabled = False
    pages_used = 0
    next_token = None

    try:
        for _ in range(max_pages):
            req_args = dict(
                part="snippet",
                videoId=video_id,
                maxResults=100,
                order="time",       # newest first; we still must scan all
                textFormat="plainText",
            )
            if next_token:
                req_args["pageToken"] = next_token
            resp = yt.commentThreads().list(**req_args).execute()
            pages_used += 1

            for item in resp.get("items", []):
                total_scanned += 1
                sn = item["snippet"]["topLevelComment"]["snippet"]
                ts = _parse_iso8601(sn.get("publishedAt", ""))
                if ts is None:
                    continue
                if ts <= day30_cutoff:
                    day30_count += 1
                if ts <= day7_cutoff:
                    day7_count += 1

            next_token = resp.get("nextPageToken")
            if not next_token:
                break
    except HttpError as e:
        # Comments may be disabled -> 403 commentsDisabled
        err_text = str(e)
        if "commentsDisabled" in err_text or "disabled comments" in err_text:
            disabled = True
        else:
            raise

    velocity = day7_count / max(1, day30_count)
    return {
        "comments_day_7": day7_count,
        "comments_day_30": day30_count,
        "comments_velocity": velocity,
        "comments_scanned_total": total_scanned,
        "comments_pages_used": pages_used,
        "comments_disabled": disabled,
    }


# ============================================================
# 2. Main film-level processor
# ============================================================

def _film_release_dt(rec: Dict) -> Optional[datetime]:
    tmdb = rec.get("metrics", {}).get("tmdb_data", {}) or {}
    rd = tmdb.get("release_date")
    if not rd:
        return None
    try:
        return datetime.strptime(rd, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def process_film(yt, rec: Dict) -> Dict:
    title = rec["movie_title"]
    year = rec["movie_year"]
    release_dt = _film_release_dt(rec)

    out: Dict = {
        "movie_title": title,
        "movie_year": year,
        "release_date": release_dt.strftime("%Y-%m-%d") if release_dt else None,
    }

    if year < YOUTUBE_CUTOFF_YEAR:
        out["status"] = "skipped_pre_youtube_era"
        return out

    # --- 1. Search for trailer (100 units)
    pick = search_trailer(yt, title, year)
    if pick is None:
        out["status"] = "no_trailer_found"
        return out
    out["trailer_pick"] = pick

    # --- 2. Fetch video metadata (1 unit)
    meta = get_video_metadata(yt, pick["video_id"])
    if meta is None:
        out["status"] = "metadata_fetch_failed"
        return out
    out["trailer_metadata"] = meta

    # --- Pure studio-decision features (Model A safe, no data leakage)
    upload_dt = _parse_iso8601(meta.get("published_at", ""))
    if upload_dt and release_dt:
        upload_lead_days = (release_dt - upload_dt).days
    else:
        upload_lead_days = None
    out["studio_features"] = {
        "yt_trailer_count": pick.get("total_trailers_seen", 0),
        "yt_upload_lead_days": upload_lead_days,
    }

    # --- Early-engagement features (Model B only)
    # Only attempt if total comment count is low enough to page through.
    total_comments = meta.get("comment_count")
    early: Dict = {}
    if upload_dt is None:
        early["status"] = "no_upload_date"
    elif total_comments is None:
        early["status"] = "comment_count_unknown"
    elif total_comments > MAX_COMMENTS_FOR_WINDOW:
        early["status"] = "too_many_comments_to_reach_window"
        early["total_comments"] = total_comments
    else:
        comment_stats = count_early_comments(yt, pick["video_id"], upload_dt)
        early["status"] = (
            "comments_disabled" if comment_stats["comments_disabled"]
            else "success"
        )
        early["yt_comments_day_7"] = comment_stats["comments_day_7"]
        early["yt_comments_day_30"] = comment_stats["comments_day_30"]
        early["yt_comments_velocity"] = comment_stats["comments_velocity"]
        early["yt_comments_scanned_total"] = comment_stats["comments_scanned_total"]
        early["total_comments"] = total_comments
    out["early_engagement"] = early

    out["status"] = "success"
    return out


# ============================================================
# 4. Driver
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=os.path.join(DATA_DIR, "extended_api_data.json"),
    )
    parser.add_argument(
        "--output",
        default=os.path.join(DATA_DIR, "youtube_data.json"),
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("YOUTUBE_API_KEY"),
    )
    parser.add_argument("--resume", action="store_true",
                        help="Skip films already in the output file")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--stop-on-quota", action="store_true",
                        help="Stop cleanly instead of crashing when quota "
                             "is exhausted")
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("YOUTUBE_API_KEY not found in env or --api-key")

    if not os.path.exists(args.input):
        raise SystemExit(f"Input not found: {args.input}")
    with open(args.input, "r", encoding="utf-8") as f:
        records = json.load(f)
    if args.limit:
        records = records[: args.limit]
    logger.info(f"Loaded {len(records)} films from {args.input}")

    # Resume: load already-processed records. Treat api_error (e.g. quota
    # exhaustion) as NOT done, so a re-run after the daily quota resets retries them.
    already: Dict[Tuple[str, int], Dict] = {}
    carry: list = []
    if args.resume and os.path.exists(args.output):
        with open(args.output, "r", encoding="utf-8") as f:
            for r in json.load(f):
                if r.get("status") == "api_error":   # nested top-level 'status'
                    continue  # retry these
                already[(r.get("movie_title"), r.get("movie_year"))] = r
                carry.append(r)
        n_retry = sum(1 for r in json.load(open(args.output)) if r.get("status") == "api_error")
        logger.info(f"Resume: {len(already)} films kept; retrying {n_retry} api_error films")
    out_records = list(carry)

    yt = build("youtube", "v3", developerKey=args.api_key,
               cache_discovery=False)

    processed_this_run = 0
    for idx, rec in enumerate(records):
        title = rec.get("movie_title")
        year = rec.get("movie_year")
        key = (title, year)

        if key in already:
            continue
        if year < YOUTUBE_CUTOFF_YEAR:
            out_records.append({
                "movie_title": title,
                "movie_year": year,
                "status": "skipped_pre_youtube_era",
            })
            continue

        logger.info(f"[{idx+1}/{len(records)}] {title} ({year})")

        try:
            rec_out = process_film(yt, rec)
        except HttpError as e:
            reason = ""
            try:
                reason = e.error_details[0].get("reason", "")  # type: ignore[attr-defined]
            except Exception:
                reason = str(e)
            logger.warning(f"  HttpError ({reason}): {e}")
            if "quotaExceeded" in str(e) or reason == "quotaExceeded":
                logger.warning("Quota exhausted. Saving and stopping.")
                _save(out_records, args.output)
                if args.stop_on_quota:
                    return
                raise
            rec_out = {
                "movie_title": title,
                "movie_year": year,
                "status": "api_error",
                "error": reason or str(e),
            }
        except Exception as e:
            logger.exception(f"  Unexpected error: {e}")
            rec_out = {
                "movie_title": title,
                "movie_year": year,
                "status": "error",
                "error": str(e),
            }

        out_records.append(rec_out)
        processed_this_run += 1

        # Incremental save every 5 records
        if processed_this_run % 5 == 0:
            _save(out_records, args.output)
            logger.info(f"  [checkpoint] saved {len(out_records)} records")

    _save(out_records, args.output)
    logger.info(f"Wrote {len(out_records)} records -> {args.output}")

    # Quick summary
    statuses = {}
    for r in out_records:
        s = r.get("status", "unknown")
        statuses[s] = statuses.get(s, 0) + 1
    logger.info("Status breakdown:")
    for s, n in sorted(statuses.items(), key=lambda kv: -kv[1]):
        logger.info(f"  {s}: {n}")


def _save(records: List[Dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
