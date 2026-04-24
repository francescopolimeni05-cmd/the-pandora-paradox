"""
Phase 4.1 - Build REAL Cultural Footprint Index from live-collected data.

Inputs:
  data/top200_movies.csv           - real box office metadata
  data/live_api_data.json          - real Wikipedia / Reddit / TMDB / Trends / IMSDb
  data/extended_api_data.json      - OPTIONAL, from 06_1_extended_collectors.py
                                     adds OMDb awards, IMDb quotes count, and
                                     derived meme/community features.
                                     If present, the extended CFI is used.
  data/subtitle_features.csv       - real subtitle-derived NLP features

Outputs:
  data/cultural_footprint_real.csv    - per-film CFI component metrics
  data/pandora_full_dataset_real.csv  - full merged dataset for modeling

CFI weighting (basic, when extended data absent; sums to 1.0):
  30%  Wikipedia monthly pageviews  (log-normalised)
  15%  Wikipedia language editions   (global reach proxy)
  25%  Reddit engagement             (log of upvotes + comments)
  15%  TMDB vote count               (broad audience, log-normalised)
  15%  Google Trends average         (search interest)

CFI weighting (extended, when awards/quotes/memes are available; sums to 1.0):
  20%  Wikipedia monthly pageviews
  10%  Wikipedia language editions
  20%  Reddit engagement
  10%  TMDB vote count
  10%  Google Trends average
  10%  IMDb quotes count             (realised verbal quotability)
  10%  Awards (wins + nominations)   (industry recognition)
  10%  Meme post count               (humour/meme penetration)

Unlike the original 04_build_index.py, this script does NOT include
hand-coded quotability / meme / merchandise / awards scores.
"""

import argparse
import json
import os
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import MinMaxScaler

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")


# ============================================================
# Flatten live_api_data.json -> DataFrame
# ============================================================

def _safe(d: Dict, key: str, default=np.nan):
    """Return d[key] only if d.status == 'success', else default."""
    if not isinstance(d, dict):
        return default
    if d.get("status") != "success":
        return default
    return d.get(key, default)


def flatten_live_api(json_path: str) -> pd.DataFrame:
    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    rows: List[Dict] = []
    for rec in records:
        m = rec.get("metrics", {})
        wp = m.get("wikipedia_pageviews", {})
        wl = m.get("wikipedia_languages", {})
        red = m.get("reddit_mentions", {})
        tm = m.get("tmdb_data", {})
        gt = m.get("google_trends", {})
        im = m.get("imsdb_script", {})
        # Extended (present only when 06_1_extended_collectors.py has been run)
        om = m.get("omdb_awards", {})
        wq = m.get("wikiquote_quotes", {})
        rd = m.get("reddit_derived", {})

        rows.append({
            "title": rec.get("movie_title"),
            "year": rec.get("movie_year"),
            # Wikipedia pageviews
            "wiki_total_views": _safe(wp, "total_views", 0),
            "wiki_avg_monthly_views": _safe(wp, "average_monthly_views", 0),
            "wiki_max_monthly_views": _safe(wp, "max_monthly_views", 0),
            "wiki_pageviews_found": wp.get("status") == "success",
            # Wikipedia languages
            "wiki_languages": _safe(wl, "language_editions", 0),
            # Reddit
            "reddit_posts": _safe(red, "post_count", 0),
            "reddit_comments": _safe(red, "total_comments", 0),
            "reddit_upvotes": _safe(red, "total_upvotes", 0),
            "reddit_avg_comments_per_post": _safe(red, "average_comments_per_post", 0),
            "reddit_top_post_upvotes": _safe(red, "top_post_upvotes", 0),
            # TMDB
            "tmdb_id": _safe(tm, "tmdb_id"),
            "tmdb_popularity": _safe(tm, "popularity"),
            "tmdb_vote_average": _safe(tm, "vote_average"),
            "tmdb_vote_count": _safe(tm, "vote_count", 0),
            "tmdb_runtime": _safe(tm, "runtime"),
            # Google Trends
            "gtrends_avg_interest": _safe(gt, "average_interest", 0),
            "gtrends_max_interest": _safe(gt, "max_interest", 0),
            # IMSDb (sparse; ~30% coverage expected)
            "imsdb_found": im.get("status") == "success",
            "imsdb_dialogue_percentage": _safe(im, "dialogue_percentage"),
            "imsdb_total_lines": _safe(im, "total_lines", 0),
            "imsdb_script_length_chars": _safe(im, "script_length_chars", 0),
            # Extended: OMDb awards (zeros when absent so downstream math is safe)
            "omdb_oscar_wins": _safe(om, "oscar_wins", 0) if om else 0,
            "omdb_oscar_nominations": _safe(om, "oscar_nominations", 0) if om else 0,
            "omdb_total_wins": _safe(om, "total_wins", 0) if om else 0,
            "omdb_total_nominations": _safe(om, "total_nominations", 0) if om else 0,
            "imdb_rating": _safe(om, "imdb_rating") if om else np.nan,
            "imdb_votes": _safe(om, "imdb_votes", 0) if om else 0,
            "metascore": _safe(om, "metascore") if om else np.nan,
            "imdb_id_from_omdb": _safe(om, "imdb_id") if om else None,
            # Extended: realized quotability via Wikiquote
            "wikiquote_count": _safe(wq, "wikiquote_count", 0) if wq else 0,
            "wikiquote_dl_count": _safe(wq, "wikiquote_dl_count", 0) if wq else 0,
            "wikiquote_li_count": _safe(wq, "wikiquote_li_count", 0) if wq else 0,
            "wikiquote_found": wq.get("status") == "success" if wq else False,
            # Extended: reddit-derived community features
            "meme_post_count": rd.get("meme_post_count", 0) if rd else 0,
            "subreddit_diversity": rd.get("subreddit_diversity", 0) if rd else 0,
            "top_subreddit": rd.get("top_subreddit") if rd else None,
            "subreddit_concentration": rd.get("subreddit_concentration") if rd else None,
        })

    df = pd.DataFrame(rows)
    # Numeric coercion for columns that might come in as object dtype
    keep_as_str = {"title", "tmdb_id", "wiki_pageviews_found", "imsdb_found",
                   "wikiquote_found", "imdb_id_from_omdb", "top_subreddit"}
    for col in df.columns:
        if col not in keep_as_str:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _has_extended(df: pd.DataFrame) -> bool:
    """True if any film carries extended signals (awards / quotes / memes)."""
    if "omdb_total_wins" not in df.columns:
        return False
    return bool(
        (df["omdb_total_wins"].fillna(0).sum() > 0)
        or (df.get("wikiquote_count", pd.Series([0])).fillna(0).sum() > 0)
        or (df["meme_post_count"].fillna(0).sum() > 0)
    )


def flatten_youtube(json_path: str) -> pd.DataFrame:
    """
    One row per film with YouTube trailer features. Pre-2005 films are
    skipped by the collector and arrive here as NaN across the model
    columns; the median imputer in 05_1_ml_model handles them.

    Model A safe (studio decisions, pre-release):
      - yt_trailer_count       number of official trailers uploaded
      - yt_upload_lead_days    days between first trailer and release
    Model B only (early engagement, populated only when the trailer's
    total comments are small enough to page through to Day-30):
      - yt_comments_day_7      top-level comments in the first 7 days
      - yt_comments_day_30     top-level comments in the first 30 days
      - yt_comments_velocity   day_7 / day_30 ratio
    """
    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    rows: List[Dict] = []
    for rec in records:
        title = rec.get("movie_title")
        year = rec.get("movie_year")
        status = rec.get("status", "unknown")

        studio = rec.get("studio_features") or {}
        early = rec.get("early_engagement") or {}
        meta = rec.get("trailer_metadata") or {}

        # Day-7/30 are only meaningful when early_engagement.status == "success".
        # "comments_disabled" returns 0 from the collector but that is "channel
        # turned comments off", not real zero engagement -> NaN.
        early_ok = early.get("status") == "success"
        yt_d7 = early.get("yt_comments_day_7") if early_ok else np.nan
        yt_d30 = early.get("yt_comments_day_30") if early_ok else np.nan
        yt_vel = early.get("yt_comments_velocity") if early_ok else np.nan

        rows.append({
            "title": title,
            "year": year,
            "yt_status": status,
            "yt_video_id": meta.get("video_id"),
            "yt_channel_title": meta.get("channel_title"),
            "yt_trailer_count": studio.get("yt_trailer_count"),
            "yt_upload_lead_days": studio.get("yt_upload_lead_days"),
            "yt_total_comments": early.get("total_comments"),
            "yt_comments_day_7": yt_d7,
            "yt_comments_day_30": yt_d30,
            "yt_comments_velocity": yt_vel,
            "yt_early_status": early.get("status"),
        })

    df = pd.DataFrame(rows)
    numeric_cols = [
        "yt_trailer_count", "yt_upload_lead_days",
        "yt_total_comments", "yt_comments_day_7", "yt_comments_day_30",
        "yt_comments_velocity",
    ]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def flatten_youtube_trailer_views(json_path: str) -> pd.DataFrame:
    """
    YouTube trailer VIEW-count features (from scripts/09_youtube_trailer_views.py).

    Complementary to flatten_youtube (Day-7/30 comments approach):
      - Day-7/30 is reachable only for small-comment trailers (~22 % coverage).
      - View counts are reachable for essentially every post-2005 trailer.
    Used as additional Model B early-reception signal.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    rows: List[Dict] = []
    for rec in records:
        ok = rec.get("status") == "success"
        rows.append({
            "title": rec.get("movie_title"),
            "year": rec.get("movie_year"),
            "yt_views_status": rec.get("status"),
            "yt_top_channel": rec.get("top_video_channel") if ok else None,
            "yt_top_views": rec.get("top_video_views") if ok else np.nan,
            "yt_top_likes": rec.get("top_video_likes") if ok else np.nan,
            "yt_top_comments_total": rec.get("top_video_comments") if ok else np.nan,
            "yt_total_views_top3": rec.get("total_views_top3") if ok else np.nan,
        })

    df = pd.DataFrame(rows)
    numeric_cols = [
        "yt_top_views", "yt_top_likes", "yt_top_comments_total",
        "yt_total_views_top3",
    ]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# ============================================================
# CFI construction
# ============================================================

def _normalise(series: pd.Series, log: bool = False) -> np.ndarray:
    vals = series.fillna(0).astype(float).values.reshape(-1, 1)
    if log:
        vals = np.log1p(np.clip(vals, 0, None))
    return MinMaxScaler().fit_transform(vals).flatten()


def compute_cfi(df: pd.DataFrame) -> pd.DataFrame:
    """Compute component norms and the composite cultural footprint index.

    Uses the extended weighting (with awards / quotes / memes) when those
    signals have been collected; otherwise falls back to the basic weighting.
    """
    df = df.copy()

    # Base component norms (always computed)
    df["cfi_comp_wiki_views"] = _normalise(df["wiki_total_views"], log=True)
    df["cfi_comp_wiki_langs"] = _normalise(df["wiki_languages"], log=False)
    df["reddit_engagement"] = (
        df["reddit_upvotes"].fillna(0) + df["reddit_comments"].fillna(0)
    )
    df["cfi_comp_reddit"] = _normalise(df["reddit_engagement"], log=True)
    df["cfi_comp_tmdb_votes"] = _normalise(df["tmdb_vote_count"], log=True)
    df["cfi_comp_gtrends"] = _normalise(df["gtrends_avg_interest"], log=False)

    extended = _has_extended(df)
    if extended:
        # Extended component norms
        df["awards_total"] = (
            df["omdb_total_wins"].fillna(0) + df["omdb_total_nominations"].fillna(0)
        )
        df["cfi_comp_awards"] = _normalise(df["awards_total"], log=True)
        df["cfi_comp_quotes"] = _normalise(df["wikiquote_count"], log=True)
        df["cfi_comp_memes"] = _normalise(df["meme_post_count"], log=True)

        df["cultural_footprint_index"] = (
            0.20 * df["cfi_comp_wiki_views"]
            + 0.10 * df["cfi_comp_wiki_langs"]
            + 0.20 * df["cfi_comp_reddit"]
            + 0.10 * df["cfi_comp_tmdb_votes"]
            + 0.10 * df["cfi_comp_gtrends"]
            + 0.10 * df["cfi_comp_quotes"]
            + 0.10 * df["cfi_comp_awards"]
            + 0.10 * df["cfi_comp_memes"]
        )
        df.attrs["cfi_weighting"] = "extended"
    else:
        df["cultural_footprint_index"] = (
            0.30 * df["cfi_comp_wiki_views"]
            + 0.15 * df["cfi_comp_wiki_langs"]
            + 0.25 * df["cfi_comp_reddit"]
            + 0.15 * df["cfi_comp_tmdb_votes"]
            + 0.15 * df["cfi_comp_gtrends"]
        )
        df.attrs["cfi_weighting"] = "basic"

    # Scale to 0-100 for interpretability
    df["cfi_score"] = (
        MinMaxScaler().fit_transform(df[["cultural_footprint_index"]]) * 100
    ).flatten()

    return df


def compute_cfi_residual(df: pd.DataFrame) -> pd.DataFrame:
    """Residual of CFI from a log(box_office) + log(budget) regression."""
    df = df.copy()
    mask = (
        (df["worldwide_gross"].fillna(0) > 0)
        & df["cfi_score"].notna()
    )
    if mask.sum() < 5:
        df["cfi_predicted"] = np.nan
        df["cfi_residual"] = np.nan
        df["cultural_category"] = pd.NA
        return df

    X = np.log1p(df.loc[mask, ["worldwide_gross", "budget"]].fillna(0).values)
    y = df.loc[mask, "cfi_score"].values
    reg = LinearRegression().fit(X, y)

    df["cfi_predicted"] = np.nan
    df.loc[mask, "cfi_predicted"] = reg.predict(X)
    df["cfi_residual"] = df["cfi_score"] - df["cfi_predicted"]

    # Descriptive category from residual
    df["cultural_category"] = pd.cut(
        df["cfi_residual"],
        bins=[-np.inf, -15, -5, 5, 15, np.inf],
        labels=[
            "Strong Underperformer", "Underperformer",
            "As Expected", "Overperformer", "Strong Overperformer",
        ],
    )
    return df


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--movies", default=os.path.join(DATA_DIR, "top200_movies.csv"))
    parser.add_argument("--live-api", default=os.path.join(DATA_DIR, "live_api_data.json"))
    parser.add_argument("--extended", default=os.path.join(DATA_DIR, "extended_api_data.json"),
                        help="If this file exists it supersedes --live-api")
    parser.add_argument("--subtitles", default=os.path.join(DATA_DIR, "subtitle_features.csv"))
    parser.add_argument("--youtube", default=os.path.join(DATA_DIR, "youtube_data.json"),
                        help="Optional; produced by 07_youtube_trailer_collector.py")
    parser.add_argument("--youtube-trailer-views",
                        default=os.path.join(DATA_DIR, "youtube_trailer_data.json"),
                        help="Optional; produced by 09_youtube_trailer_views.py "
                             "(absolute trailer view/like counts; Model B signal)")
    parser.add_argument("--cfi-out", default=os.path.join(DATA_DIR, "cultural_footprint_real.csv"))
    parser.add_argument("--full-out", default=os.path.join(DATA_DIR, "pandora_full_dataset_real.csv"))
    args = parser.parse_args()

    movies = pd.read_csv(args.movies)
    print(f"Loaded {len(movies)} movies metadata")

    # Prefer the extended file if available (it is a superset of live_api_data)
    live_source = args.extended if os.path.exists(args.extended) else args.live_api
    live = flatten_live_api(live_source)
    print(f"Loaded {len(live)} films from {os.path.basename(live_source)}")

    subs = pd.read_csv(args.subtitles)
    # Avoid collisions on merge: rename status and keep imdb_id
    subs = subs.rename(columns={"status": "subtitle_status"})
    print(f"Loaded {len(subs)} films from subtitle_features.csv")

    # Merge (left join on movies so every top200 film is present)
    df = movies.merge(live, on=["title", "year"], how="left")
    df = df.merge(subs, on=["title", "year"], how="left")
    df["subtitle_available"] = df["subtitle_available"].fillna(False)

    # Optional YouTube trailer features (Model A + Model B predictors,
    # never enter CFI -- they are X-side features, not Y-side).
    if os.path.exists(args.youtube):
        yt = flatten_youtube(args.youtube)
        print(f"Loaded {len(yt)} films from {os.path.basename(args.youtube)}")
        df = df.merge(yt, on=["title", "year"], how="left")
    else:
        print(f"YouTube data not found at {args.youtube} (skipping YouTube features)")

    # Optional YouTube trailer VIEW counts (complementary to Day-7/30 comments;
    # near-full coverage for post-2005 films -> Model B early-reception signal).
    if os.path.exists(args.youtube_trailer_views):
        ytv = flatten_youtube_trailer_views(args.youtube_trailer_views)
        print(f"Loaded {len(ytv)} films from {os.path.basename(args.youtube_trailer_views)}")
        df = df.merge(ytv, on=["title", "year"], how="left")
    else:
        print(f"YouTube trailer views not found at {args.youtube_trailer_views} (skipping)")

    # Time-since-release feature controls the accumulation effect:
    # older films had more years to accrue Wiki views / Reddit posts / etc.
    from datetime import datetime
    current_year = datetime.now().year
    df["years_since_release"] = (current_year - df["year"]).clip(lower=0)

    # Coerce any object columns that should be numeric
    numeric_candidates = [
        "wiki_total_views", "wiki_languages", "reddit_upvotes", "reddit_comments",
        "tmdb_vote_count", "gtrends_avg_interest", "worldwide_gross", "budget",
    ]
    for col in numeric_candidates:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Compute CFI + residual
    df = compute_cfi(df)
    df = compute_cfi_residual(df)

    # ----- Outputs -----
    cfi_cols = [
        "title", "year", "worldwide_gross", "budget",
        "wiki_total_views", "wiki_languages",
        "reddit_upvotes", "reddit_comments", "reddit_engagement",
        "tmdb_vote_count", "tmdb_vote_average", "tmdb_popularity",
        "gtrends_avg_interest",
        # Extended metrics (zeroes when not collected)
        "omdb_total_wins", "omdb_total_nominations", "omdb_oscar_wins",
        "wikiquote_count", "meme_post_count", "subreddit_diversity",
        # Normalised CFI components
        "cfi_comp_wiki_views", "cfi_comp_wiki_langs", "cfi_comp_reddit",
        "cfi_comp_tmdb_votes", "cfi_comp_gtrends",
        "cfi_comp_awards", "cfi_comp_quotes", "cfi_comp_memes",
        "cultural_footprint_index", "cfi_score",
        "cfi_predicted", "cfi_residual", "cultural_category",
    ]
    cfi_cols = [c for c in cfi_cols if c in df.columns]
    df[cfi_cols].to_csv(args.cfi_out, index=False)
    print(f"\nWrote CFI components -> {args.cfi_out}")

    df.to_csv(args.full_out, index=False)
    print(f"Wrote full dataset ({df.shape[1]} cols) -> {args.full_out}")

    # Summary
    print("\n" + "=" * 60)
    print("DATA QUALITY SUMMARY")
    print("=" * 60)
    print(f"CFI weighting used: {df.attrs.get('cfi_weighting', 'unknown')}")
    print(f"Total films: {len(df)}")
    print(f"Wikipedia pageviews found: {int(df['wiki_pageviews_found'].sum())}")
    print(f"IMSDb script found:        {int(df['imsdb_found'].sum())}")
    print(f"Subtitles extracted:       {int(df['subtitle_available'].sum())}")
    if "wikiquote_count" in df.columns:
        print(f"Wikiquote pages found:     {int((df['wikiquote_count'] > 0).sum())}")
    if "omdb_total_wins" in df.columns:
        print(f"OMDb awards collected:     {int((df['omdb_total_wins'] + df['omdb_total_nominations'] > 0).sum())}")
    if df["cfi_score"].notna().any():
        print(f"\nCFI score  min / median / max: "
              f"{df['cfi_score'].min():.1f} / "
              f"{df['cfi_score'].median():.1f} / "
              f"{df['cfi_score'].max():.1f}")
    if df["cfi_residual"].notna().any():
        print(f"CFI residual distribution:")
        print(df["cultural_category"].value_counts().to_string())


if __name__ == "__main__":
    main()
