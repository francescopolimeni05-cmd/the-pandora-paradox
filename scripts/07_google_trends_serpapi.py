#!/usr/bin/env python3
"""
07_google_trends_serpapi.py — Google Trends collector via SerpAPI.

Why this exists:
    The original `06_live_data_collectors.py` Trends collector uses `pytrends`,
    which scrapes Google directly. Google ratelimited the original run and
    returned 429 on 184/197 films (only 13 succeeded). SerpAPI proxies the
    Trends endpoint server-side, so from our point of view it is a normal
    HTTP API with no per-IP rate limiting.

Signup / key:
    https://serpapi.com/users/sign_up
    https://serpapi.com/manage-api-key

Pricing note (check current plans on their site — pricing changes):
    Free tier has a small monthly search budget. 197 calls probably exceeds it,
    so a paid plan is likely needed for a single full run. Each film costs
    exactly 1 search.

Output schema (matches the existing `google_trends` block in live_api_data.json):
    {
      "movie_title": "...",
      "movie_year": 2009,
      "query": "Avatar movie",
      "timeframe": "today 3-y",
      "max_interest": 100,
      "min_interest": 2,
      "average_interest": 12.6,
      "peak_date": "2026-04-12",
      "data_points_count": 53,
      "status": "success",
      "source": "serpapi"
    }

Usage:
    # 1. Put key in env (or pass via --api-key)
    export SERPAPI_KEY=...

    # 2. Quick sanity run on 3 films
    python 07_google_trends_serpapi.py --limit 3

    # 3. Full run on all 197 films (takes ~5-10 min)
    python 07_google_trends_serpapi.py

    # 4. Merge the new Trends data into live_api_data.json
    python 07_google_trends_serpapi.py --merge
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests


def per_film_timeframe(release_year: Optional[int]) -> str:
    """Per-film window = max(release_year - 1, 2004)-01-01 to today.

    This gives every film a fair, release-aligned window:
      * 1 year of pre-release buzz is captured
      * Avoids padding newer films with ~15 years of pre-release zeros
        (which happens with the 'all' preset)
      * Google Trends has no data before 2004, so earlier films just get
        their full available history.

    If release_year is None we fall back to 'all' (no info to trim the window).
    """
    if release_year is None:
        return "all"
    try:
        start_year = max(int(release_year) - 1, 2004)
    except (TypeError, ValueError):
        return "all"
    end = datetime.now(timezone.utc).date()
    return f"{start_year}-01-01 {end.isoformat()}"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LIVE_FILE = DATA_DIR / "live_api_data.json"
EXTENDED_FILE = DATA_DIR / "extended_api_data.json"
OUTPUT_FILE = DATA_DIR / "google_trends_serpapi.json"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("trends_serpapi")

SERPAPI_ENDPOINT = "https://serpapi.com/search"


# ---------------------------------------------------------------------------
# Core collector
# ---------------------------------------------------------------------------
def fetch_trends(
    title: str,
    year: int,
    api_key: str,
    timeframe: Optional[str] = None,
    timeout: int = 60,
    max_retries: int = 3,
) -> Dict:
    if timeframe is None:
        # Per-film window: release_year - 1 → today. Makes average_interest
        # comparable across films of different ages, and avoids the bias that
        # a global 'all' window introduces (newer films get dragged down by
        # pre-release zero months).
        timeframe = per_film_timeframe(year)
    """Single SerpAPI call → normalised dict matching the pytrends schema."""
    query = f"{title} movie"
    params = {
        "engine": "google_trends",
        "q": query,
        "data_type": "TIMESERIES",
        "date": timeframe,
        "tz": "360",
        "api_key": api_key,
    }

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(SERPAPI_ENDPOINT, params=params, timeout=timeout)
        except requests.RequestException as e:
            last_error = f"network: {e}"
            time.sleep(2 * attempt)
            continue

        if resp.status_code == 429:
            last_error = f"http 429 — SerpAPI rate limit (unusual)"
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

        if body.get("error"):
            return {
                "movie_title": title,
                "movie_year": year,
                "status": "error",
                "error": body["error"],
            }

        timeline = (body.get("interest_over_time") or {}).get("timeline_data") or []
        if not timeline:
            return {
                "movie_title": title,
                "movie_year": year,
                "query": query,
                "timeframe": timeframe,
                "status": "no_data",
                "source": "serpapi",
            }

        values: List[int] = []
        peak_entry = None
        for entry in timeline:
            vals = entry.get("values") or []
            if not vals:
                continue
            raw = vals[0].get("extracted_value")
            if raw is None:
                sval = str(vals[0].get("value", "0")).replace("<", "").strip()
                try:
                    raw = int(sval)
                except ValueError:
                    continue
            values.append(int(raw))
            if peak_entry is None or raw > peak_entry[1]:
                peak_entry = (entry.get("date"), raw)

        if not values:
            return {
                "movie_title": title,
                "movie_year": year,
                "query": query,
                "timeframe": timeframe,
                "status": "no_data",
                "source": "serpapi",
            }

        peak_date = _parse_peak_date(peak_entry[0]) if peak_entry else None

        return {
            "movie_title": title,
            "movie_year": year,
            "query": query,
            "timeframe": timeframe,
            "max_interest": max(values),
            "min_interest": min(values),
            "average_interest": sum(values) / len(values),
            "peak_date": peak_date,
            "data_points_count": len(values),
            "status": "success",
            "source": "serpapi",
        }

    return {
        "movie_title": title,
        "movie_year": year,
        "status": "error",
        "error": last_error or "unknown (retries exhausted)",
    }


def _parse_peak_date(raw: Optional[str]) -> Optional[str]:
    """SerpAPI returns e.g. 'Apr 12 – 18, 2026' (weekly bins) or 'Apr 12, 2026'
    (daily bins). We pull out the first month+day and the trailing year, then
    combine them. Returns ISO YYYY-MM-DD, or the raw string on failure."""
    if not raw:
        return None

    # Year is always the trailing 4-digit number.
    year_match = re.search(r"(\d{4})\s*$", raw)
    # First "Mon DD" at the start of the string.
    md_match = re.match(r"^\s*([A-Za-z]+)\s+(\d+)", raw)
    if not (year_match and md_match):
        return raw

    month_name, day, year = md_match.group(1), md_match.group(2), year_match.group(1)
    try:
        return datetime.strptime(
            f"{month_name} {day} {year}", "%b %d %Y"
        ).strftime("%Y-%m-%d")
    except ValueError:
        return raw


# ---------------------------------------------------------------------------
# Film list / checkpoint I/O
# ---------------------------------------------------------------------------
def load_films() -> List[Dict]:
    """Use the same 197-film list already collected in live_api_data.json."""
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
    timeframe: str,
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
        f"{len(remaining)} to collect"
    )

    for i, f in enumerate(remaining, 1):
        title = f["movie_title"]
        year = f["movie_year"]
        logger.info(f"[{i}/{len(remaining)}] {title} ({year})")

        row = fetch_trends(title, year, api_key, timeframe=timeframe)

        # Drop any existing non-success row for this key, then append the new one
        rows = [
            r for r in rows
            if (r.get("movie_title"), r.get("movie_year"))
            != (row["movie_title"], row["movie_year"])
        ]
        rows.append(row)
        save_checkpoint(rows)

        if row["status"] == "success":
            logger.info(
                f"  ok — avg={row['average_interest']:.1f}, "
                f"max={row['max_interest']}, peak={row['peak_date']}"
            )
        else:
            logger.warning(
                f"  {row['status']}: "
                f"{row.get('error') or row.get('reason') or '-'}"
            )

        if i < len(remaining):
            time.sleep(sleep_between)

    status_counts: Dict[str, int] = {}
    for r in rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    logger.info(f"DONE — {status_counts}")
    logger.info(f"Results saved to {OUTPUT_FILE}")


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
    """Replace the `google_trends` block in live_api_data.json AND in
    extended_api_data.json (if present) for every film where SerpAPI produced
    a success. Unsuccessful films are left untouched.
    """
    if not OUTPUT_FILE.exists():
        sys.exit(f"ERROR: {OUTPUT_FILE} does not exist — run collection first.")

    with OUTPUT_FILE.open() as f:
        serp = json.load(f)

    by_key = {
        (d["movie_title"], d.get("movie_year")): d
        for d in serp
        if d.get("status") == "success"
    }

    for target in (LIVE_FILE, EXTENDED_FILE):
        if not target.exists():
            logger.info(f"Skipping {target.name} (does not exist)")
            continue
        updated = _merge_block_into(target, by_key, "google_trends")
        logger.info(
            f"Merged {updated} rows into {target.name} "
            f"(backup at {target.with_suffix('.backup.json').name})"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--api-key",
        default=os.environ.get("SERPAPI_KEY"),
        help="SerpAPI key (or set SERPAPI_KEY env var)",
    )
    p.add_argument("--limit", type=int, default=None, help="Only process first N films (testing)")
    p.add_argument("--sleep", type=float, default=1.0, help="Seconds between requests (default 1.0)")
    p.add_argument(
        "--timeframe",
        default=None,
        help=(
            "SerpAPI date param. Default = per-film window "
            "(release_year - 1 to today), fair comparison across films of "
            "different ages. Valid overrides: 'all' (2004-today), "
            "'today 12-m', 'today 5-y', or custom 'YYYY-MM-DD YYYY-MM-DD'. "
            "If set, the same window is used for every film."
        ),
    )
    p.add_argument("--force", action="store_true", help="Re-collect even films already marked success")
    p.add_argument("--merge", action="store_true", help="Merge existing output into live_api_data.json and exit")
    args = p.parse_args()

    if args.merge:
        merge_into_live()
        return

    if not args.api_key:
        sys.exit(
            "ERROR: provide --api-key or set SERPAPI_KEY env var.\n"
            "Get a key at https://serpapi.com/manage-api-key"
        )

    collect(
        api_key=args.api_key,
        limit=args.limit,
        sleep_between=args.sleep,
        timeframe=args.timeframe,
        force=args.force,
    )


if __name__ == "__main__":
    main()
