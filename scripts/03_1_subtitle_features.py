"""
Phase 3.1 - Subtitle-based NLP feature extraction.

Pipeline:
  1. Load data/top200_movies.csv
  2. For each film:
     a. Look up IMDb ID via TMDB (free key required)
     b. Download English subtitle (.srt) from YIFY Subtitles
     c. Parse SRT into dialogue lines
     d. Compute traditional + peak-based NLP features
  3. Write data/subtitle_features.csv (row-per-film) and
     data/subtitle_raw.json (raw dialogue for audit).

Usage:
  python scripts/03_1_subtitle_features.py --api-key $TMDB_API_KEY
  python scripts/03_1_subtitle_features.py --api-key $TMDB_API_KEY --limit 5
"""

import argparse
import csv
import io
import json
import logging
import os
import re
import statistics
import time
import zipfile
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup


# ============================================================
# Config
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")

HEADERS = {
    "User-Agent": "PandoraParadoxCapstone/1.0 (Academic Research)",
    "Accept-Language": "en-US,en;q=0.9",
}

YIFY_BASE = "https://yifysubtitles.ch"
RATE_LIMITS = {"tmdb": 0.3, "yify": 1.5}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_DIR, "subtitle_collection.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ============================================================
# Lexicons (kept inline so the script is dependency-light)
# ============================================================

POSITIVE_WORDS = {
    "good","great","love","happy","beautiful","wonderful","amazing","excellent",
    "best","brilliant","awesome","fantastic","glad","nice","perfect","kind",
    "thank","thanks","welcome","enjoy","lovely","success","proud","smile",
    "laugh","joy","hope","peace","safe","win","won","victory","brave","strong",
    "free","alive","friend","family","home","bless","grace","please","yes",
}

NEGATIVE_WORDS = {
    "bad","hate","sad","angry","kill","killed","die","dead","death","pain",
    "hurt","scared","afraid","fear","terrible","awful","horrible","wrong",
    "lie","liar","stupid","fool","damn","ugly","evil","cruel","lose","lost",
    "fail","failed","fight","war","blood","enemy","threat","danger","broken",
    "cry","tears","alone","lonely","stop","never","no","nothing","worse","worst",
}

PROFANITY_WORDS = {
    "damn","hell","shit","fuck","fucking","bastard","bitch","ass","asshole",
    "crap","piss","dick","cock","bullshit","goddamn","motherfucker","screwed",
}

HUMOR_MARKERS = {
    "haha","hehe","hahaha","lol","funny","joke","joking","kidding","laugh",
    "laughing","ridiculous","hilarious","comedy","silly",
}

ROMANCE_MARKERS = {
    "love","kiss","kissed","darling","honey","sweetheart","baby","romantic",
    "heart","hearts","beloved","embrace","tender","forever","together",
    "marry","married","wedding","beautiful",
}

VIOLENCE_MARKERS = {
    "kill","killed","shoot","shot","blood","bloody","gun","gunfire","knife",
    "stab","punch","fight","fighting","attack","attacking","war","battle",
    "weapon","bomb","explosion","destroy","wound","injured","dead","murder",
}

STOPWORDS = {
    "a","an","the","and","or","but","of","in","on","at","to","for","with",
    "is","are","was","were","be","been","being","have","has","had","do",
    "does","did","will","would","could","should","may","might","can","i",
    "you","he","she","it","we","they","me","him","her","us","them","my",
    "your","his","its","our","their","this","that","these","those","if",
    "so","than","then","too","very","just","as","by","from","up","out",
    "about","into","over","after","before","not","no","yes","oh","uh","um",
}


# ============================================================
# Step 1: TMDB -> IMDb ID
# ============================================================

def get_imdb_id(title: str, year: int, api_key: str) -> Optional[str]:
    """Look up TMDB movie id and fetch external_ids.imdb_id."""
    try:
        time.sleep(RATE_LIMITS["tmdb"])
        search = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            headers=HEADERS,
            params={"api_key": api_key, "query": title, "year": year},
            timeout=30,
        )
        search.raise_for_status()
        results = search.json().get("results", [])
        if not results:
            return None
        tmdb_id = results[0]["id"]

        time.sleep(RATE_LIMITS["tmdb"])
        ext = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}/external_ids",
            headers=HEADERS,
            params={"api_key": api_key},
            timeout=30,
        )
        ext.raise_for_status()
        return ext.json().get("imdb_id")
    except requests.RequestException as e:
        logger.warning(f"TMDB lookup failed for {title}: {e}")
        return None


# ============================================================
# Step 2: YIFY subtitle download
# ============================================================

def fetch_yify_subtitle(imdb_id: str, language: str = "english") -> Optional[str]:
    """Return SRT text for the best-rated English subtitle, or None."""
    try:
        time.sleep(RATE_LIMITS["yify"])
        movie_url = f"{YIFY_BASE}/movie-imdb/{imdb_id}"
        resp = requests.get(movie_url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        # Each subtitle row lives in <tr> with a language <span> and a
        # download link pointing at /subtitles/<id>.
        best_link = None
        best_rating = -999
        for row in soup.select("tr"):
            lang_cell = row.find(class_="sub-lang")
            if not lang_cell or lang_cell.get_text(strip=True).lower() != language:
                continue
            link = row.find("a", href=re.compile(r"/subtitles/"))
            if not link:
                continue
            rating_cell = row.find(class_="rating-cell")
            try:
                rating = int(rating_cell.get_text(strip=True)) if rating_cell else 0
            except ValueError:
                rating = 0
            if rating > best_rating:
                best_rating = rating
                best_link = link.get("href")

        if not best_link:
            return None

        # The /subtitles/<id> page hosts a download button pointing to a ZIP.
        detail_url = YIFY_BASE + best_link if best_link.startswith("/") else best_link
        time.sleep(RATE_LIMITS["yify"])
        detail = requests.get(detail_url, headers=HEADERS, timeout=30)
        if detail.status_code != 200:
            return None
        detail_soup = BeautifulSoup(detail.text, "html.parser")
        dl = detail_soup.find("a", class_="download-subtitle")
        if not dl or not dl.get("href"):
            # Fallback: any <a> whose href points to /subtitle/...zip
            dl = detail_soup.find("a", href=re.compile(r"/subtitle/.*\.zip$"))
        if not dl or not dl.get("href"):
            return None
        zip_url = dl["href"]
        if zip_url.startswith("/"):
            zip_url = YIFY_BASE + zip_url

        time.sleep(RATE_LIMITS["yify"])
        # YIFY blocks hotlinked ZIP downloads; the Referer must point to the
        # subtitle detail page.
        zip_headers = dict(HEADERS)
        zip_headers["Referer"] = detail_url
        zip_resp = requests.get(zip_url, headers=zip_headers, timeout=60)
        if zip_resp.status_code != 200:
            return None

        with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
            srt_names = [n for n in zf.namelist() if n.lower().endswith(".srt")]
            if not srt_names:
                return None
            with zf.open(srt_names[0]) as f:
                raw = f.read()
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="ignore")
    except requests.RequestException as e:
        logger.warning(f"YIFY fetch failed for {imdb_id}: {e}")
        return None


# ============================================================
# Step 3: SRT parsing
# ============================================================

SRT_INDEX_RE = re.compile(r"^\d+$")
SRT_TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}")
TAG_RE = re.compile(r"<[^>]+>")
MUSIC_RE = re.compile(r"[♪♫].*?[♪♫]")
BRACKET_RE = re.compile(r"[\[\(][^\]\)]*[\]\)]")  # [MUSIC], (SIGHS), etc.


def parse_srt(srt_text: str) -> List[str]:
    """Return list of cleaned dialogue lines from an SRT string."""
    lines = []
    buffer = []
    for raw in srt_text.splitlines():
        line = raw.strip()
        if not line:
            if buffer:
                lines.append(" ".join(buffer))
                buffer = []
            continue
        if SRT_INDEX_RE.match(line) or SRT_TIME_RE.match(line):
            continue
        line = TAG_RE.sub("", line)
        line = MUSIC_RE.sub("", line)
        line = BRACKET_RE.sub("", line)
        line = line.replace("\u200b", "").strip()
        if line:
            buffer.append(line)
    if buffer:
        lines.append(" ".join(buffer))
    # Drop empties, deduplicate runs of identical lines (common in SRT noise)
    return [l for l in lines if l]


# ============================================================
# Step 4: Feature extraction
# ============================================================

WORD_RE = re.compile(r"[A-Za-z']+")
SENTENCE_END_RE = re.compile(r"[.!?]+")


def _tokenize(text: str) -> List[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


def _simple_sentiment(tokens: List[str]) -> float:
    if not tokens:
        return 0.0
    pos = sum(1 for t in tokens if t in POSITIVE_WORDS)
    neg = sum(1 for t in tokens if t in NEGATIVE_WORDS)
    total = len(tokens)
    return (pos - neg) / total


def compute_subtitle_features(lines: List[str]) -> Dict:
    """Compute traditional and peak-based features from dialogue lines."""
    if not lines:
        return {"subtitle_available": False}

    full_text = " ".join(lines)
    all_tokens = _tokenize(full_text)
    total_words = len(all_tokens)
    content_tokens = [t for t in all_tokens if t not in STOPWORDS]

    # --- Traditional features (compatible with script_features.csv where possible)
    word_count = total_words
    line_count = len(lines)
    avg_line_words = word_count / line_count if line_count else 0.0

    # Sentence-level split (approximate from punctuation)
    sentences = [s.strip() for s in SENTENCE_END_RE.split(full_text) if s.strip()]
    avg_sentence_complexity = (
        sum(len(_tokenize(s)) for s in sentences) / len(sentences) if sentences else 0.0
    )

    # Vocabulary richness (type-token ratio on content words)
    vocab_richness = (
        len(set(content_tokens)) / len(content_tokens) if content_tokens else 0.0
    )

    # Per-line sentiment — peak / variability matter for meme potential
    per_line_sentiment = [_simple_sentiment(_tokenize(l)) for l in lines]
    sentiment_mean = statistics.mean(per_line_sentiment) if per_line_sentiment else 0.0
    sentiment_std = (
        statistics.pstdev(per_line_sentiment) if len(per_line_sentiment) > 1 else 0.0
    )
    sentiment_peak = max(abs(s) for s in per_line_sentiment) if per_line_sentiment else 0.0

    # Exclamation / question ratios (per line)
    exclamation_ratio = sum(1 for l in lines if "!" in l) / line_count
    question_ratio = sum(1 for l in lines if "?" in l) / line_count

    # Content-topic indicators (proportion of content tokens falling in each lexicon)
    def _marker_rate(marker_set):
        if not content_tokens:
            return 0.0
        return sum(1 for t in content_tokens if t in marker_set) / len(content_tokens)

    humor_indicator = _marker_rate(HUMOR_MARKERS) * 1000   # scaled for readability
    romance_indicator = _marker_rate(ROMANCE_MARKERS) * 1000
    violence_indicator = _marker_rate(VIOLENCE_MARKERS) * 1000
    profanity_score = _marker_rate(PROFANITY_WORDS) * 1000

    # --- Peak-based features (the ones we actually care about for meme prediction)
    # Short punchy declaratives: <= 6 words, no question mark, ends with . or !
    short_punchy_lines = [
        l for l in lines
        if 2 <= len(_tokenize(l)) <= 6
        and "?" not in l
        and (l.rstrip().endswith(".") or l.rstrip().endswith("!"))
    ]
    short_punchy_count = len(short_punchy_lines)
    short_punchy_density = short_punchy_count / line_count

    # Rare proper-noun candidates: capitalised tokens in mid-sentence that appear
    # fewer than 3 times in the entire script (approximates invented names).
    proper_noun_candidates = re.findall(r"(?<=[a-z\s,])([A-Z][a-zA-Z]{2,})", full_text)
    noun_counts = Counter(proper_noun_candidates)
    rare_proper_nouns = [n for n, c in noun_counts.items() if c <= 2]
    rare_proper_noun_count = len(rare_proper_nouns)

    # Sentiment spike: largest absolute change between consecutive lines
    sentiment_spike = 0.0
    if len(per_line_sentiment) > 1:
        sentiment_spike = max(
            abs(b - a) for a, b in zip(per_line_sentiment, per_line_sentiment[1:])
        )

    # Longest contiguous monologue in words (approx: sum words between blank rows)
    longest_monologue_words = max((len(_tokenize(l)) for l in lines), default=0)

    # Rough character-count proxy: unique all-caps tokens of length >= 3 in
    # standalone lines (SRT often marks speaker names in caps).
    speaker_like = set()
    for l in lines:
        stripped = l.strip()
        if stripped.isupper() and 3 <= len(stripped) <= 30 and " " not in stripped[:20]:
            speaker_like.add(stripped)
    unique_character_count = len(speaker_like)

    return {
        "subtitle_available": True,
        "estimated_word_count": word_count,
        "dialogue_line_count": line_count,
        "avg_dialogue_length": avg_line_words,
        "longest_monologue_words": longest_monologue_words,
        "unique_character_count": unique_character_count,
        "sentiment_mean": sentiment_mean,
        "sentiment_std": sentiment_std,
        "sentiment_peak": sentiment_peak,
        "exclamation_ratio": exclamation_ratio,
        "question_ratio": question_ratio,
        "profanity_score": profanity_score,
        "vocabulary_richness": vocab_richness,
        "avg_sentence_complexity": avg_sentence_complexity,
        "humor_indicator": humor_indicator,
        "romance_indicator": romance_indicator,
        "violence_indicator": violence_indicator,
        # Peak / meme-potential features
        "short_punchy_count": short_punchy_count,
        "short_punchy_density": short_punchy_density,
        "rare_proper_noun_count": rare_proper_noun_count,
        "sentiment_spike": sentiment_spike,
    }


# ============================================================
# Orchestration
# ============================================================

def process_film(title: str, year: int, api_key: str) -> Dict:
    result = {"title": title, "year": year, "status": "pending"}
    imdb_id = get_imdb_id(title, year, api_key)
    result["imdb_id"] = imdb_id
    if not imdb_id:
        result["status"] = "no_imdb_id"
        return {**result, **compute_subtitle_features([])}

    srt_text = fetch_yify_subtitle(imdb_id)
    if not srt_text:
        result["status"] = "no_subtitle"
        return {**result, **compute_subtitle_features([])}

    lines = parse_srt(srt_text)
    features = compute_subtitle_features(lines)
    result["status"] = "success" if features.get("subtitle_available") else "empty_srt"
    return {**result, **features, "_raw_line_sample": lines[:10]}


def save_incremental(record: Dict, json_path: str):
    try:
        data = []
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        data.append(record)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save incremental record: {e}")


def write_csv(records: List[Dict], csv_path: str):
    """Flatten records (drop _raw_line_sample) and write CSV."""
    if not records:
        return
    rows = []
    for r in records:
        row = {k: v for k, v in r.items() if not k.startswith("_")}
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False, encoding="utf-8")
    logger.info(f"Wrote {len(df)} rows -> {csv_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True, help="TMDB API key")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N films (for testing)")
    parser.add_argument("--input", default=os.path.join(DATA_DIR, "top200_movies.csv"))
    parser.add_argument("--csv-out", default=os.path.join(DATA_DIR, "subtitle_features.csv"))
    parser.add_argument("--json-out", default=os.path.join(DATA_DIR, "subtitle_raw.json"))
    parser.add_argument("--resume", action="store_true",
                        help="Skip films already present in json-out")
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    if args.limit:
        df = df.head(args.limit)

    processed_titles = set()
    if args.resume and os.path.exists(args.json_out):
        with open(args.json_out, "r", encoding="utf-8") as f:
            for r in json.load(f):
                processed_titles.add((r.get("title"), r.get("year")))
        logger.info(f"Resuming: {len(processed_titles)} films already processed")
    elif not args.resume and os.path.exists(args.json_out):
        os.remove(args.json_out)

    total = len(df)
    success = 0
    records: List[Dict] = []

    for idx, row in df.iterrows():
        title = row["title"]
        year = int(row["year"])
        key = (title, year)
        if key in processed_titles:
            continue

        logger.info(f"[{idx+1}/{total}] {title} ({year})")
        record = process_film(title, year, args.api_key)
        save_incremental(record, args.json_out)
        records.append(record)
        if record.get("status") == "success":
            success += 1

    # Rebuild CSV from the full JSON log so resumed runs include prior records
    if os.path.exists(args.json_out):
        with open(args.json_out, "r", encoding="utf-8") as f:
            all_records = json.load(f)
        write_csv(all_records, args.csv_out)

    logger.info(f"Done. Success: {success}/{total} new films processed.")


if __name__ == "__main__":
    main()
