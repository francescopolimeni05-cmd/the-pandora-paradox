#!/usr/bin/env python3
"""
09_youtube_trailer_views.py — Absolute cultural attention via YouTube trailer views.

Why this exists:
    Google Trends (SerpAPI) gives us relative curiosity shapes (0-100
    normalised per query). For a TRUE absolute signal — real numbers,
    comparable across films — we hit YouTube Data API v3 and pull the
    view counts of each film's official trailer (plus likes / comments).

    Unlike Trends values, these are:
      * Actual integers (views, likes, comments)
      * Cross-film comparable by construction
      * A direct measure of "how many people cared enough to watch"

    Pre-2005 films (YouTube launched Feb 2005) had their trailers uploaded
    post-hoc — the `yt_pre_youtube_era` flag controls for this artefact
    the same way `gtrends_pre2004` controls for Trends' 2004 start date.

Auth:
    Uses a simple Google Cloud API key (no OAuth2 needed).
    Enable "YouTube Data API v3" in Google Cloud Console for your project.

Quota budget:
    - search.list       = 100 units per call
    - videos.list       =   1 unit  per call (regardless of batch size)
    - Per film          = 101 units
    - 197 films         = 19,897 units → ~2 days of the free 10,000/day
    - Collector is checkpoint-based, so quota-exhaust just means "resume
      tomorrow" — we pick up where we left off.
    - Ask Google for a quota bump if you want to finish in one day:
      https://support.google.com/youtube/contact/yt_api_form

Output schema (data/youtube_trailer_data.json, checkpointed):
    {
      "movie_title": "Avatar",
      "movie_year": 2009,
      "query": "\"Avatar\" 2009 official trailer",
      "candidates_returned": 3,
      "top_video_id": "5PSNL1qE6VY",
      "top_video_title": "Avatar | Official Trailer (HD)",
      "top_video_channel": "20th Century Studios",
      "top_video_published": "2009-08-20T16:58:03Z",
      "top_video_views": 85000000,
      "top_video_likes": 350000,
      "top_video_comments": 12000,
      "total_views_top3": 165000000,
      "quota_used_estimate": 101,
      "status": "success",
      "source": "youtube_data_v3"
    }

Usage:
    export YOUTUBE_API_KEY=AIza...           # your Cloud API key
    python 09_youtube_trailer_views.py --limit 3    # sanity check
    python 09_youtube_trailer_views.py              # full run
    python 09_youtube_trailer_views.py --merge      # merge into live_api_data.json
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LIVE_FILE = DATA_DIR / "live_api_data.json"
EXTENDED_FILE = DATA_DIR / "extended_api_data.json"
OUTPUT_FILE = DATA_DIR / "youtube_trailer_data.json"

SEARCH_ENDPOINT = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_ENDPOINT = "https://www.googleapis.com/youtube/v3/videos"

QUOTA_SEARCH = 100
QUOTA_VIDEOS = 1
QUOTA_PER_FILM = QUOTA_SEARCH + QUOTA_VIDEOS


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("youtube_trailer")


# ---------------------------------------------------------------------------
# Core collector
# ---------------------------------------------------------------------------
def build_query(title: str, year: Optional[int]) -> str:
    """Disambiguation query.

    - Quoting the title prevents partial-word matching (e.g. "Up" ≠ "pickup")
    - Including the release year handles remakes (two different "Dune")
    - "official trailer" tokens filter out reactions / fan edits
    """
    if year:
        return f'"{title}" {int(year)} official trailer'
    return f'"{title}" official trailer'


def fetch_trailer(
    title: str,
    year: Optional[int],
    api_key: str,
    max_candidates: int = 3,
    timeout: int = 60,
    max_retries: int = 3,
) -> Dict:
    """Search → get top candidates → fetch their stats → return summary."""
    query = build_query(title, year)

    # ---- Step 1: search
    search_params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_candidates,
        "order": "relevance",
        "key": api_key,
    }

    video_ids: List[str] = []
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(SEARCH_ENDPOINT, params=search_params, timeout=timeout)
        except requests.RequestException as e:
            last_error = f"network: {e}"
            time.sleep(2 * attempt)
            continue

        if resp.status_code == 403:
            try:
                body = resp.json()
            except ValueError:
                body = {}
            errs = (body.get("error") or {}).get("errors") or [{}]
            reason = errs[0].get("reason", "")
            if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
                return {
                    "movie_title": title,
                    "movie_year": year,
                    "status": "quota_exceeded",
                    "error": "YouTube quota exceeded — resume tomorrow",
                }
            # Permanent configuration problems: no point continuing the batch.
            # Bubble up a sentinel the driver will use to stop the loop.
            if reason in (
                "accessNotConfigured",   # API not enabled on this project
                "keyInvalid",            # malformed / wrong key
                "keyExpired",
                "ipRefererBlocked",      # key restricted to wrong origin
                "forbidden",
            ):
                return {
                    "movie_title": title,
                    "movie_year": year,
                    "status": "config_error",
                    "error": f"http 403 ({reason}): {resp.text[:300]}",
                }
            return {
                "movie_title": title,
                "movie_year": year,
                "status": "error",
                "error": f"http 403 ({reason}): {resp.text[:200]}",
            }

        if resp.status_code == 429:
            last_error = "http 429 — rate limit"
            time.sleep(5 * attempt)
            continue

        if resp.status_code != 200:
            return {
                "movie_title": title,
                "movie_year": year,
                "status": "error",
                "error": f"http {resp.status_code}: {resp.text[:200]}",
            }

        try:
            body = resp.json()
        except ValueError:
            last_error = "non-json response"
            time.sleep(2 * attempt)
            continue

        items = body.get("items") or []
        video_ids = [
            it.get("id", {}).get("videoId")
            for it in items
            if it.get("id", {}).get("videoId")
        ]
        break
    else:
        return {
            "movie_title": title,
            "movie_year": year,
            "status": "error",
            "error": last_error or "search retries exhausted",
        }

    if not video_ids:
        return {
            "movie_title": title,
            "movie_year": year,
            "query": query,
            "status": "no_data",
            "source": "youtube_data_v3",
        }

    # ---- Step 2: fetch statistics for candidates (one batched call)
    v_params = {
        "part": "statistics,snippet",
        "id": ",".join(video_ids),
        "key": api_key,
    }
    try:
        v_resp = requests.get(VIDEOS_ENDPOINT, params=v_params, timeout=timeout)
    except requests.RequestException as e:
        return {
            "movie_title": title,
            "movie_year": year,
            "query": query,
            "status": "error",
            "error": f"videos call network: {e}",
        }

    if v_resp.status_code != 200:
        return {
            "movie_title": title,
            "movie_year": year,
            "query": query,
            "status": "error",
            "error": f"videos http {v_resp.status_code}: {v_resp.text[:200]}",
        }

    try:
        v_body = v_resp.json()
    except ValueError:
        return {
            "movie_title": title,
            "movie_year": year,
            "query": query,
            "status": "error",
            "error": "videos non-json response",
        }

    v_items = v_body.get("items") or []
    if not v_items:
        return {
            "movie_title": title,
            "movie_year": year,
            "query": query,
            "status": "no_data",
            "source": "youtube_data_v3",
        }

    parsed: List[Dict] = []
    for it in v_items:
        stats = it.get("statistics") or {}
        snippet = it.get("snippet") or {}
        parsed.append({
            "video_id": it.get("id"),
            "title": snippet.get("title"),
            "channel": snippet.get("channelTitle"),
            "published": snippet.get("publishedAt"),
            "views": int(stats.get("viewCount") or 0),
            "likes": int(stats.get("likeCount")) if stats.get("likeCount") else None,
            "comments": int(stats.get("commentCount")) if stats.get("commentCount") else None,
        })

    # Sort candidates by view count DESC.
    # Most-viewed among the top search results is almost always the real
    # official trailer (studio channels outpace fan uploads by orders of
    # magnitude). If needed we could filter by channel whitelists, but view-
    # count ranking is a robust, channel-agnostic proxy.
    parsed.sort(key=lambda v: v["views"], reverse=True)
    top = parsed[0]
    total_views = sum(v["views"] for v in parsed)

    return {
        "movie_title": title,
        "movie_year": year,
        "query": query,
        "candidates_returned": len(parsed),
        "top_video_id": top["video_id"],
        "top_video_title": top["title"],
        "top_video_channel": top["channel"],
        "top_video_published": top["published"],
        "top_video_views": top["views"],
        "top_video_likes": top["likes"],
        "top_video_comments": top["comments"],
        "total_views_top3": total_views,
        "quota_used_estimate": QUOTA_PER_FILM,
        "status": "success",
        "source": "youtube_data_v3",
    }


# ---------------------------------------------------------------------------
# Film list / checkpoint I/O
# ---------------------------------------------------------------------------
def load_films() -> List[Dict]:
    """Reuse the 197-film list already collected in live_api_data.json."""
    with LIVE_FILE.open() as f:
        data = json.load(f)
    return [
        {"movie_title": d.get("movie_title"), "movie_year": d.get("movie_year")}
        for d in data
        if d.get("movie_title")
    ]


def load_checkpoint() -> List[Dict]:
    if OUTPUT_FILE.exists():
        with OUTPUT_FILE.open() as f:
            return json.load(f)
    return []


def save_checkpoint(rows: List[Dict]) -> None:
    tmp = OUTPUT_FILE.with_suffix(".tmp.json")
    with tmp.open("w") as f:
        json.dump(rows, f, indent=2)
    tmp.replace(OUTPUT_FILE)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def collect(
    api_key: str,
    limit: Optional[int],
    sleep_between: float,
    max_candidates: int,
    force: bool,
) -> None:
    films = load_films()
    if limit:
        films = films[:limit]

    done_rows = [] if force else load_checkpoint()
    done_keys = {
        (d["movie_title"], d.get("movie_year"))
        for d in done_rows
        if d.get("status") == "success"
    }
    rows = list(done_rows)

    remaining = [
        f for f in films
        if (f["movie_title"], f["movie_year"]) not in done_keys
    ]

    logger.info(
        f"{len(films)} films total | "
        f"{len(done_keys)} already successful | "
        f"{len(remaining)} to collect | "
        f"estimated quota: {len(remaining) * QUOTA_PER_FILM} units "
        f"(free tier: 10,000/day)"
    )

    quota_used = 0
    stopped_for_quota = False

    for i, f in enumerate(remaining, 1):
        title = f["movie_title"]
        year = f["movie_year"]
        logger.info(f"[{i}/{len(remaining)}] {title} ({year})")

        row = fetch_trailer(
            title, year, api_key,
            max_candidates=max_candidates,
        )

        if row["status"] not in ("quota_exceeded", "config_error"):
            quota_used += QUOTA_PER_FILM

        # Drop any existing row for this key, then append the new one
        rows = [
            r for r in rows
            if (r.get("movie_title"), r.get("movie_year"))
            != (row["movie_title"], row["movie_year"])
        ]
        rows.append(row)
        save_checkpoint(rows)

        if row["status"] == "success":
            logger.info(
                f"  ok — top views={row['top_video_views']:,} on "
                f"{row['top_video_channel']!r}, total_top3={row['total_views_top3']:,}"
            )
        elif row["status"] == "quota_exceeded":
            logger.error("  QUOTA EXCEEDED — stopping. Re-run tomorrow to resume.")
            stopped_for_quota = True
            break
        elif row["status"] == "config_error":
            logger.error(f"  CONFIG ERROR — stopping immediately.\n{row['error']}")
            logger.error(
                "  Fix the API configuration and re-run; "
                "all error rows so far will be retried automatically."
            )
            break
        elif row["status"] == "no_data":
            logger.warning(f"  no_data — no usable candidates for query {row.get('query')!r}")
        else:
            logger.warning(f"  {row['status']}: {row.get('error') or '-'}")

        if i < len(remaining):
            time.sleep(sleep_between)

    status_counts: Dict[str, int] = {}
    for r in rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    logger.info(f"DONE — {status_counts}")
    logger.info(f"Estimated quota used this run: {quota_used} units")
    logger.info(f"Results saved to {OUTPUT_FILE}")
    if stopped_for_quota:
        logger.info(
            "Quota budget hit — re-run this script tomorrow; "
            "already-successful films will be skipped."
        )


# ---------------------------------------------------------------------------
# Merge into live_api_data.json
# ---------------------------------------------------------------------------
def _merge_block_into(path: Path, by_key: dict, block_name: str) -> int:
    """Merge `by_key` into the metrics block of every matching film in `path`.
    Returns number of rows updated. Leaves a .backup.json sibling."""
    if not path.exists():
        return 0
    with path.open() as f:
        data = json.load(f)
    updated = 0
    for entry in data:
        key = (entry.get("movie_title"), entry.get("movie_year"))
        if key in by_key:
            entry.setdefault("metrics", {})[block_name] = by_key[key]
            updated += 1
    backup = path.with_suffix(".backup.json")
    if backup.exists():
        backup.unlink()
    path.rename(backup)
    with path.open("w") as f:
        json.dump(data, f, indent=2)
    return updated


def merge_into_live() -> None:
    """Add a `youtube_trailer` block under each film's `metrics` in both
    live_api_data.json AND extended_api_data.json (if present). Only
    successful rows are merged."""
    if not OUTPUT_FILE.exists():
        sys.exit(f"ERROR: {OUTPUT_FILE} does not exist — run collection first.")

    with OUTPUT_FILE.open() as f:
        yt = json.load(f)

    by_key = {
        (d["movie_title"], d.get("movie_year")): d
        for d in yt
        if d.get("status") == "success"
    }

    for target in (LIVE_FILE, EXTENDED_FILE):
        if not target.exists():
            logger.info(f"Skipping {target.name} (does not exist)")
            continue
        updated = _merge_block_into(target, by_key, "youtube_trailer")
        logger.info(
            f"Merged {updated} rows into {target.name} "
            f"(backup at {target.with_suffix('.backup.json').name})"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--api-key",
        default=os.environ.get("YOUTUBE_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
        help="YouTube Data API v3 key (or set YOUTUBE_API_KEY / GOOGLE_API_KEY env var)",
    )
    p.add_argument("--limit", type=int, default=None,
                   help="Only process first N films (testing)")
    p.add_argument("--sleep", type=float, default=0.3,
                   help="Seconds between requests (default 0.3)")
    p.add_argument("--candidates", type=int, default=3,
                   help="How many top search results to pull stats for (default 3)")
    p.add_argument("--force", action="store_true",
                   help="Re-collect even films already marked success")
    p.add_argument("--merge", action="store_true",
                   help="Merge existing output into live_api_data.json and exit")
    args = p.parse_args()

    if args.merge:
        merge_into_live()
        return

    if not args.api_key:
        sys.exit(
            "ERROR: provide --api-key or set YOUTUBE_API_KEY (or GOOGLE_API_KEY) env var.\n"
            "Enable 'YouTube Data API v3' for your project at console.cloud.google.com"
        )

    collect(
        api_key=args.api_key,
        limit=args.limit,
        sleep_between=args.sleep,
        max_candidates=args.candidates,
        force=args.force,
    )


if __name__ == "__main__":
    main()
