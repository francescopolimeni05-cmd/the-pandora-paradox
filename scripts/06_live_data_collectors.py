"""
Phase 1 - Step 6: Live Data Collectors for Real APIs
Collects REAL data from live APIs when run on a user's local machine.

This script provides functions to collect data from multiple APIs:
1. Wikipedia Pageviews - Monthly pageview metrics
2. Wikipedia Language Editions - Count of language versions
3. Reddit Mentions - Social media discussion metrics
4. TMDB Movie Data - Budget, revenue, popularity scores
5. Google Trends - Search interest over time
6. IMSDB Script Scraper - Movie script analysis

USAGE:
    # Collect all data for all films
    python 06_live_data_collectors.py --api-key YOUR_TMDB_KEY

    # Collect specific metric for a date range
    python 06_live_data_collectors.py --collector wikipedia_pageviews --start 2023-01-01 --end 2026-01-01

    # Collect Reddit data only
    python 06_live_data_collectors.py --collector reddit_mentions

REQUIREMENTS:
    - requests
    - pandas
    - beautifulsoup4
    - pytrends
    - praw (for Reddit, optional)
    - tmdb API key (free from https://www.themoviedb.org/settings/api)

NOTES:
    - Some APIs have rate limits; script includes delays between requests
    - Results are saved incrementally to avoid data loss on interruption
    - Errors are logged but don't stop the collection process
    - Reddit API allows 60 requests/minute without authentication
    - TMDB allows 40 requests/10 seconds with free tier
"""

import requests
import pandas as pd
import os
import json
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
import logging
from typing import Dict, List, Optional, Tuple
import re
import csv
from urllib.parse import quote

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data_collection.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Base directories
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Default headers for API requests
DEFAULT_HEADERS = {
    "User-Agent": "PandoraParadoxCapstone/1.0 (Academic Research)"
}

# Rate limiting (seconds between requests)
RATE_LIMITS = {
    "wikipedia": 0.5,
    "reddit": 0.5,
    "tmdb": 0.3,
    "imsdb": 1.0,
}


# ============================================================
# 1. WIKIPEDIA PAGEVIEWS COLLECTOR
# ============================================================

def collect_wikipedia_pageviews(
    movie_title: str,
    movie_year: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict:
    """
    Collect monthly pageview data for a Wikipedia article.

    Args:
        movie_title: Film title (e.g., "Avatar")
        movie_year: Release year (e.g., 2009)
        start_date: Start date as YYYY-MM-01 format (default: 3 years ago)
        end_date: End date as YYYY-MM-01 format (default: today)

    Returns:
        Dictionary with pageview metrics
    """
    try:
        # Format dates
        if end_date is None:
            end_date = datetime.now()
        else:
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        if start_date is None:
            start_date = end_date - timedelta(days=365*3)
        else:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")

        # Format dates for API (YYYYMMDD)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        # Try multiple Wikipedia title candidates — Wikipedia disambiguation is
        # inconsistent: some films need "_(YYYY_film)", others use the bare title.
        base = movie_title.replace(" ", "_")
        title_candidates = [
            f"{base}_({movie_year}_film)",   # Avatar_(2009_film)
            base,                             # Avengers:_Endgame
            f"{base}_(film)",                 # fallback disambiguation
        ]

        logger.info(f"Fetching Wikipedia pageviews for {movie_title}...")
        time.sleep(RATE_LIMITS["wikipedia"])

        data = None
        resolved_title = None
        last_error = None
        for candidate in title_candidates:
            encoded = quote(candidate, safe='')
            url = (
                f"https://wikimedia.org/api/rest_v1/metrics/pageviews/"
                f"per-article/en.wikipedia/all-access/all-agents/"
                f"{encoded}/monthly/{start_str}/{end_str}"
            )
            try:
                response = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    resolved_title = candidate
                    break
                last_error = f"{response.status_code} for '{candidate}'"
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                continue

        if data is None:
            logger.warning(f"No Wikipedia article matched for {movie_title}: {last_error}")
            return {
                "movie_title": movie_title,
                "movie_year": movie_year,
                "total_views": 0,
                "average_monthly_views": 0,
                "max_monthly_views": 0,
                "min_monthly_views": 0,
                "views_count": 0,
                "data_points": [],
                "status": "no_data",
                "error": last_error,
            }

        # Extract metrics
        if "items" not in data or len(data["items"]) == 0:
            logger.warning(f"No pageview data found for {resolved_title}")
            return {
                "movie_title": movie_title,
                "movie_year": movie_year,
                "total_views": 0,
                "average_monthly_views": 0,
                "max_monthly_views": 0,
                "min_monthly_views": 0,
                "views_count": 0,
                "data_points": [],
                "status": "no_data"
            }

        # Calculate statistics
        views = [item["views"] for item in data["items"]]

        result = {
            "movie_title": movie_title,
            "movie_year": movie_year,
            "wiki_title_used": resolved_title,
            "total_views": sum(views),
            "average_monthly_views": sum(views) / len(views) if views else 0,
            "max_monthly_views": max(views) if views else 0,
            "min_monthly_views": min(views) if views else 0,
            "views_count": len(views),
            "data_points": [
                {
                    "timestamp": item["timestamp"],
                    "views": item["views"]
                } for item in data["items"]
            ],
            "status": "success"
        }

        logger.info(f"Successfully collected pageviews for {movie_title} "
                   f"(wiki='{resolved_title}'): {result['total_views']:,} total views")
        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching pageviews for {movie_title}: {e}")
        return {
            "movie_title": movie_title,
            "movie_year": movie_year,
            "status": "error",
            "error": str(e)
        }


# ============================================================
# 2. WIKIPEDIA LANGUAGE EDITIONS COLLECTOR
# ============================================================

def collect_wikipedia_language_editions(
    movie_title: str,
    movie_year: int
) -> Dict:
    """
    Collect count of Wikipedia language editions for a film.

    Args:
        movie_title: Film title
        movie_year: Release year

    Returns:
        Dictionary with language edition count
    """
    try:
        wiki_title = f"{movie_title}_{movie_year}_film"

        # Wikipedia API endpoint
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "titles": movie_title,
            "prop": "langlinks",
            "lllimit": "500",
            "format": "json"
        }

        logger.info(f"Fetching language editions for {movie_title}...")
        time.sleep(RATE_LIMITS["wikipedia"])

        response = requests.get(url, headers=DEFAULT_HEADERS, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Extract language count
        pages = data.get("query", {}).get("pages", {})
        if not pages:
            return {
                "movie_title": movie_title,
                "movie_year": movie_year,
                "language_editions": 0,
                "status": "no_data"
            }

        page = next(iter(pages.values()))
        langlinks = page.get("langlinks", [])

        result = {
            "movie_title": movie_title,
            "movie_year": movie_year,
            "language_editions": len(langlinks),
            "languages": [lang["lang"] for lang in langlinks],
            "status": "success"
        }

        logger.info(f"Found {len(langlinks)} language editions for {movie_title}")
        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching language editions for {movie_title}: {e}")
        return {
            "movie_title": movie_title,
            "movie_year": movie_year,
            "status": "error",
            "error": str(e)
        }


# ============================================================
# 3. REDDIT MENTIONS COLLECTOR
# ============================================================

def collect_reddit_mentions(
    movie_title: str,
    movie_year: int,
    limit: int = 100
) -> Dict:
    """
    Collect Reddit mentions and discussion metrics for a film.
    Note: Uses Reddit's public search API (no authentication required).

    Args:
        movie_title: Film title
        movie_year: Release year
        limit: Max results per request (default 100)

    Returns:
        Dictionary with Reddit metrics
    """
    try:
        # Format search query
        search_query = f"{movie_title} {movie_year} movie"

        url = "https://www.reddit.com/search.json"
        params = {
            "q": search_query,
            "limit": limit,
            "sort": "relevance",
            "t": "all"
        }

        logger.info(f"Fetching Reddit mentions for {movie_title}...")
        time.sleep(RATE_LIMITS["reddit"])

        response = requests.get(
            url,
            headers=DEFAULT_HEADERS,
            params=params,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()

        # Extract posts
        posts = data.get("data", {}).get("children", [])

        if not posts:
            return {
                "movie_title": movie_title,
                "movie_year": movie_year,
                "post_count": 0,
                "total_comments": 0,
                "total_upvotes": 0,
                "status": "no_data"
            }

        # Aggregate metrics
        total_comments = sum(post["data"].get("num_comments", 0) for post in posts)
        total_upvotes = sum(post["data"].get("ups", 0) for post in posts)

        result = {
            "movie_title": movie_title,
            "movie_year": movie_year,
            "post_count": len(posts),
            "total_comments": total_comments,
            "total_upvotes": total_upvotes,
            "average_comments_per_post": total_comments / len(posts) if posts else 0,
            "average_upvotes_per_post": total_upvotes / len(posts) if posts else 0,
            "top_post_upvotes": max([p["data"].get("ups", 0) for p in posts]) if posts else 0,
            "posts": [
                {
                    "title": post["data"].get("title"),
                    "subreddit": post["data"].get("subreddit"),
                    "upvotes": post["data"].get("ups"),
                    "comments": post["data"].get("num_comments"),
                    "url": post["data"].get("url")
                } for post in posts[:10]  # Top 10 posts
            ],
            "status": "success"
        }

        logger.info(f"Found {len(posts)} Reddit posts for {movie_title}")
        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Reddit data for {movie_title}: {e}")
        return {
            "movie_title": movie_title,
            "movie_year": movie_year,
            "status": "error",
            "error": str(e)
        }


# ============================================================
# 4. TMDB MOVIE DATA COLLECTOR
# ============================================================

def collect_tmdb_movie_data(
    movie_title: str,
    movie_year: int,
    api_key: str
) -> Dict:
    """
    Collect movie data from The Movie Database (TMDB).
    Requires free API key from https://www.themoviedb.org/settings/api

    Args:
        movie_title: Film title
        movie_year: Release year
        api_key: TMDB API key

    Returns:
        Dictionary with TMDB metrics
    """
    try:
        if not api_key:
            logger.warning("TMDB API key not provided, skipping TMDB collection")
            return {
                "movie_title": movie_title,
                "movie_year": movie_year,
                "status": "skipped",
                "reason": "No API key provided"
            }

        url = "https://api.themoviedb.org/3/search/movie"
        params = {
            "api_key": api_key,
            "query": movie_title,
            "year": movie_year,
            "page": 1
        }

        logger.info(f"Fetching TMDB data for {movie_title}...")
        time.sleep(RATE_LIMITS["tmdb"])

        response = requests.get(url, headers=DEFAULT_HEADERS, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        results = data.get("results", [])

        if not results:
            logger.warning(f"No TMDB results found for {movie_title} ({movie_year})")
            return {
                "movie_title": movie_title,
                "movie_year": movie_year,
                "status": "no_data"
            }

        # Use first result (best match)
        movie = results[0]
        movie_id = movie["id"]

        # Fetch detailed information
        details_url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        details_params = {"api_key": api_key}

        time.sleep(RATE_LIMITS["tmdb"])
        details_response = requests.get(
            details_url,
            headers=DEFAULT_HEADERS,
            params=details_params,
            timeout=30
        )
        details_response.raise_for_status()
        details = details_response.json()

        result = {
            "movie_title": movie_title,
            "movie_year": movie_year,
            "tmdb_id": movie_id,
            "tmdb_title": movie.get("title"),
            "release_date": movie.get("release_date"),
            "budget": details.get("budget", 0),
            "revenue": details.get("revenue", 0),
            "popularity": movie.get("popularity", 0),
            "vote_average": movie.get("vote_average", 0),
            "vote_count": movie.get("vote_count", 0),
            "overview": movie.get("overview", ""),
            "runtime": details.get("runtime", 0),
            "genres": [g["name"] for g in details.get("genres", [])],
            "production_companies": [c["name"] for c in details.get("production_companies", [])],
            "status": "success"
        }

        logger.info(f"Successfully collected TMDB data for {movie_title}: "
                   f"Budget: ${result['budget']:,}, Revenue: ${result['revenue']:,}")
        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching TMDB data for {movie_title}: {e}")
        return {
            "movie_title": movie_title,
            "movie_year": movie_year,
            "status": "error",
            "error": str(e)
        }


# ============================================================
# 5. GOOGLE TRENDS COLLECTOR
# ============================================================

def collect_google_trends(
    movie_title: str,
    movie_year: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict:
    """
    Collect Google Trends data for a film using pytrends library.
    This requires the pytrends package (pip install pytrends).

    Args:
        movie_title: Film title
        movie_year: Release year
        start_date: Start date as YYYY-MM-DD (default: 1 year ago)
        end_date: End date as YYYY-MM-DD (default: today)

    Returns:
        Dictionary with Google Trends metrics
    """
    try:
        # Try to import pytrends
        try:
            from pytrends.request import TrendReq
        except ImportError:
            logger.warning("pytrends not installed. Install with: pip install pytrends")
            return {
                "movie_title": movie_title,
                "movie_year": movie_year,
                "status": "skipped",
                "reason": "pytrends not installed"
            }

        # Format dates
        if end_date is None:
            end_date = datetime.now()
        else:
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        if start_date is None:
            start_date = end_date - timedelta(days=365)
        else:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")

        timeframe = f"{start_date.strftime('%Y-%m-%d')} {end_date.strftime('%Y-%m-%d')}"

        logger.info(f"Fetching Google Trends for {movie_title}...")

        # Create pytrends request
        pytrends = TrendReq(hl='en-US', tz=360)

        # Build payload and get interest over time
        search_term = f"{movie_title} movie"
        pytrends.build_payload([search_term], timeframe=timeframe)

        time.sleep(RATE_LIMITS["wikipedia"])
        interest_df = pytrends.interest_over_time()

        if interest_df.empty:
            return {
                "movie_title": movie_title,
                "movie_year": movie_year,
                "status": "no_data"
            }

        # Extract metrics
        values = interest_df[search_term].tolist()

        result = {
            "movie_title": movie_title,
            "movie_year": movie_year,
            "max_interest": max(values) if values else 0,
            "min_interest": min(values) if values else 0,
            "average_interest": sum(values) / len(values) if values else 0,
            "peak_date": interest_df[search_term].idxmax().strftime("%Y-%m-%d") if values else None,
            "data_points_count": len(values),
            "status": "success"
        }

        logger.info(f"Successfully collected Google Trends for {movie_title}")
        return result

    except Exception as e:
        logger.error(f"Error fetching Google Trends for {movie_title}: {e}")
        return {
            "movie_title": movie_title,
            "movie_year": movie_year,
            "status": "error",
            "error": str(e)
        }


# ============================================================
# 6. IMSDB SCRIPT SCRAPER
# ============================================================

def scrape_imsdb_script(movie_title: str, movie_year: int) -> Dict:
    """
    Scrape movie script from IMSDb (Internet Movie Script Database).
    Parses script into dialogue vs action lines for NLP analysis.

    Args:
        movie_title: Film title
        movie_year: Release year

    Returns:
        Dictionary with script analysis metrics
    """
    try:
        logger.info(f"Scraping script for {movie_title}...")

        # IMSDb URL patterns are inconsistent. Real examples:
        #   Avatar                 -> /scripts/Avatar.html
        #   Titanic                -> /scripts/Titanic.html
        #   The Dark Knight        -> /scripts/Dark-Knight,-The.html
        #   Inception              -> /scripts/Inception.html
        # Year is NOT in IMSDb URLs. Try several pattern variants.
        cleaned = re.sub(r"[^\w\s\-]", "", movie_title).strip()
        candidates = []

        # PascalCase with hyphens (most common)
        candidates.append(cleaned.replace(" ", "-"))
        # Handle "The X" -> "X,-The"
        if cleaned.lower().startswith("the "):
            rest = cleaned[4:]
            candidates.append(rest.replace(" ", "-") + ",-The")
        # PascalCase without separator
        candidates.append(cleaned.replace(" ", ""))
        # Lowercase with hyphens (legacy)
        candidates.append(cleaned.lower().replace(" ", "-"))

        # De-duplicate while preserving order
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                unique_candidates.append(c)

        response = None
        script_url = None
        for candidate in unique_candidates:
            trial_url = f"https://www.imsdb.com/scripts/{candidate}.html"
            time.sleep(RATE_LIMITS["imsdb"])
            try:
                r = requests.get(trial_url, headers=DEFAULT_HEADERS, timeout=30)
                if r.status_code == 200 and "not found" not in r.text.lower()[:500]:
                    response = r
                    script_url = trial_url
                    break
            except requests.exceptions.RequestException:
                continue

        if response is None:
            logger.warning(f"IMSDb script page not found for {movie_title}")
            return {
                "movie_title": movie_title,
                "movie_year": movie_year,
                "status": "not_found",
            }

        soup = BeautifulSoup(response.text, "html.parser")

        # Find script text (usually in <pre> or <div class="script">)
        script_text = None

        # Try multiple selectors
        script_div = soup.find("div", class_="script")
        if script_div:
            script_text = script_div.get_text()
        else:
            pre_tags = soup.find_all("pre")
            if pre_tags:
                script_text = "\n".join([p.get_text() for p in pre_tags])

        if not script_text:
            logger.warning(f"Could not find script text for {movie_title}")
            return {
                "movie_title": movie_title,
                "movie_year": movie_year,
                "status": "no_data"
            }

        # Analyze script
        lines = script_text.split("\n")

        # Simple heuristic: all-caps lines are likely dialogue/character names
        dialogue_lines = 0
        action_lines = 0

        for line in lines:
            if not line.strip():
                continue

            # All caps = likely dialogue/character
            if line.strip().isupper():
                dialogue_lines += 1
            else:
                action_lines += 1

        total_lines = dialogue_lines + action_lines

        result = {
            "movie_title": movie_title,
            "movie_year": movie_year,
            "script_url": script_url,
            "script_found": True,
            "total_lines": total_lines,
            "dialogue_lines": dialogue_lines,
            "action_lines": action_lines,
            "dialogue_percentage": (dialogue_lines / total_lines * 100) if total_lines > 0 else 0,
            "script_length_chars": len(script_text),
            "status": "success"
        }

        logger.info(f"Successfully scraped script for {movie_title}: "
                   f"{total_lines} lines, {dialogue_lines} dialogue")
        return result

    except requests.exceptions.RequestException as e:
        logger.warning(f"Script not found for {movie_title}: {e}")
        return {
            "movie_title": movie_title,
            "movie_year": movie_year,
            "status": "not_found",
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Error scraping script for {movie_title}: {e}")
        return {
            "movie_title": movie_title,
            "movie_year": movie_year,
            "status": "error",
            "error": str(e)
        }


# ============================================================
# MAIN DATA COLLECTION ORCHESTRATOR
# ============================================================

def collect_all_metrics(
    movie_title: str,
    movie_year: int,
    tmdb_api_key: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    collectors: Optional[List[str]] = None
) -> Dict:
    """
    Collect all available metrics for a single film.

    Args:
        movie_title: Film title
        movie_year: Release year
        tmdb_api_key: TMDB API key (optional)
        start_date: Start date for time-series data
        end_date: End date for time-series data
        collectors: List of collectors to run (None = all)

    Returns:
        Dictionary with all collected metrics
    """
    result = {
        "movie_title": movie_title,
        "movie_year": movie_year,
        "collection_timestamp": datetime.now().isoformat(),
        "metrics": {}
    }

    # Default to all collectors
    if collectors is None:
        collectors = [
            "wikipedia_pageviews",
            "wikipedia_languages",
            "reddit_mentions",
            "tmdb_data",
            "google_trends",
            "imsdb_script"
        ]

    # Run requested collectors
    if "wikipedia_pageviews" in collectors:
        result["metrics"]["wikipedia_pageviews"] = collect_wikipedia_pageviews(
            movie_title, movie_year, start_date, end_date
        )

    if "wikipedia_languages" in collectors:
        result["metrics"]["wikipedia_languages"] = collect_wikipedia_language_editions(
            movie_title, movie_year
        )

    if "reddit_mentions" in collectors:
        result["metrics"]["reddit_mentions"] = collect_reddit_mentions(
            movie_title, movie_year
        )

    if "tmdb_data" in collectors:
        result["metrics"]["tmdb_data"] = collect_tmdb_movie_data(
            movie_title, movie_year, tmdb_api_key
        )

    if "google_trends" in collectors:
        result["metrics"]["google_trends"] = collect_google_trends(
            movie_title, movie_year, start_date, end_date
        )

    if "imsdb_script" in collectors:
        result["metrics"]["imsdb_script"] = scrape_imsdb_script(
            movie_title, movie_year
        )

    return result


def save_results_incrementally(
    movie_data: Dict,
    output_file: str
) -> None:
    """
    Save results to file incrementally (append mode).
    This prevents data loss if collection is interrupted.

    Args:
        movie_data: Dictionary with collected metrics
        output_file: Path to output JSON file
    """
    try:
        # Load existing data if file exists
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                all_data = json.load(f)
        else:
            all_data = []

        # Append new data
        all_data.append(movie_data)

        # Save updated data
        with open(output_file, 'w') as f:
            json.dump(all_data, f, indent=2, default=str)

        logger.info(f"Saved results to {output_file}")

    except Exception as e:
        logger.error(f"Error saving results: {e}")


def main():
    """
    Main function: orchestrate live data collection from all APIs.
    Reads top200_movies.csv and collects metrics for each film.
    """
    parser = argparse.ArgumentParser(
        description="Collect live data from multiple APIs for movie analysis"
    )
    parser.add_argument(
        "--collector",
        type=str,
        choices=[
            "all",
            "wikipedia_pageviews",
            "wikipedia_languages",
            "reddit_mentions",
            "tmdb_data",
            "google_trends",
            "imsdb_script"
        ],
        default="all",
        help="Specific collector to run (default: all)"
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date for time-series data (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date for time-series data (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="TMDB API key (get from https://www.themoviedb.org/settings/api)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.path.join(DATA_DIR, "live_api_data.json"),
        help="Output file for collected data"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of films to process (default: all)"
    )

    args = parser.parse_args()

    # Determine which collectors to use
    if args.collector == "all":
        collectors = [
            "wikipedia_pageviews",
            "wikipedia_languages",
            "reddit_mentions",
            "tmdb_data",
            "google_trends",
            "imsdb_script"
        ]
    else:
        collectors = [args.collector]

    logger.info("=" * 70)
    logger.info("PANDORA PARADOX - LIVE DATA COLLECTION")
    logger.info("=" * 70)
    logger.info(f"Collectors: {', '.join(collectors)}")
    logger.info(f"Output file: {args.output}")
    logger.info(f"Start date: {args.start or 'Default (3 years ago)'}")
    logger.info(f"End date: {args.end or 'Default (today)'}")
    logger.info(f"TMDB API key: {'Provided' if args.api_key else 'Not provided'}")
    logger.info("=" * 70)

    # Load movies CSV
    movies_csv = os.path.join(DATA_DIR, "top200_movies.csv")
    if not os.path.exists(movies_csv):
        logger.error(f"Movies CSV not found: {movies_csv}")
        return

    df = pd.read_csv(movies_csv)

    # Apply limit if specified
    if args.limit:
        df = df.head(args.limit)

    logger.info(f"Found {len(df)} movies to process")

    # Collect data for each movie
    for idx, row in df.iterrows():
        movie_title = row['title']
        movie_year = int(row['year'])

        logger.info(f"\n[{idx+1}/{len(df)}] Processing: {movie_title} ({movie_year})")

        try:
            # Collect all metrics
            data = collect_all_metrics(
                movie_title,
                movie_year,
                tmdb_api_key=args.api_key,
                start_date=args.start,
                end_date=args.end,
                collectors=collectors
            )

            # Save immediately (incremental save)
            save_results_incrementally(data, args.output)

            # Small delay between movies to respect rate limits
            time.sleep(1)

        except Exception as e:
            logger.error(f"Fatal error processing {movie_title}: {e}")
            continue

    logger.info("\n" + "=" * 70)
    logger.info(f"Data collection complete! Results saved to: {args.output}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
