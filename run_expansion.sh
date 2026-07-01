#!/usr/bin/env bash
# ============================================================
# run_expansion.sh — one-command sample expansion (run on your Mac)
#
#   1. cp .env.example .env   &&   paste your 4 keys into .env
#   2. ./run_expansion.sh
#
# Re-runnable: every collector checkpoints, so if a step dies just
# launch the script again — it resumes where it left off.
# Keys are read ONLY from .env (gitignored); nothing is printed.
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

# --- load keys from .env -------------------------------------------------
if [[ ! -f .env ]]; then
  echo "ERROR: .env not found. Run:  cp .env.example .env  then paste your keys."
  exit 1
fi
set -a; source .env; set +a

# --- sanity-check required keys (without printing them) ------------------
missing=()
[[ -z "${TMDB_API_KEY:-}"   ]] && missing+=("TMDB_API_KEY")
[[ -z "${OMDB_API_KEY:-}"   ]] && missing+=("OMDB_API_KEY")
[[ -z "${SERPAPI_KEY:-}"    ]] && missing+=("SERPAPI_KEY")
[[ -z "${YOUTUBE_API_KEY:-}${GOOGLE_API_KEY:-}" ]] && missing+=("YOUTUBE_API_KEY")
if (( ${#missing[@]} )); then
  echo "ERROR: missing keys in .env: ${missing[*]}"
  exit 1
fi

PY=${PYTHON:-python}
say() { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }

say "1/8  Build expansion seed from TMDB"
$PY scripts/10_build_expansion_seed.py

say "2/8  Base metrics (Wikipedia / Reddit / TMDB / IMSDb) — new films"
$PY scripts/06_live_data_collectors.py \
    --movies data/expansion_movies.csv \
    --output data/expansion_live_api_data.json \
    --api-key "$TMDB_API_KEY"

say "3/8  Awards (OMDb) + Wikiquote + reddit-derived — new films"
$PY scripts/06_1_extended_collectors.py \
    --input  data/expansion_live_api_data.json \
    --output data/expansion_extended_api_data.json

say "4/8  Subtitle NLP features — new films"
$PY scripts/03_1_subtitle_features.py \
    --api-key "$TMDB_API_KEY" \
    --input   data/expansion_movies.csv \
    --csv-out data/expansion_subtitle_features.csv \
    --json-out data/expansion_subtitle_raw.json

say "5/8  Fold new films into canonical data files"
$PY scripts/12_merge_and_build.py combine

say "6/8  Reddit discussion volume — ALL films (via SerpAPI)"
$PY scripts/08b_reddit_serpapi.py --input data/all_movies.csv \
    --output data/reddit_serpapi.json || echo "  WARN: SerpAPI Reddit issue (continuing; resumes from checkpoint)."

say "7/8  Google Trends + YouTube (existing films skipped via checkpoints)"
# Tolerant: a single API hiccup must not throw away a long run. The build step
# handles any of these being missing/partial.
$PY scripts/07_google_trends_serpapi.py            || echo "  WARN: Trends collect issue (continuing)."
$PY scripts/07_google_trends_serpapi.py --merge    || echo "  WARN: Trends merge issue (continuing)."
$PY scripts/09_youtube_trailer_views.py            || echo "  WARN: YouTube views issue (continuing)."
$PY scripts/09_youtube_trailer_views.py --merge    || echo "  WARN: YouTube views merge issue (continuing)."
$PY scripts/07_youtube_trailer_collector.py \
    --input data/live_api_data.json \
    --output data/youtube_data.json --resume       || echo "  WARN: YouTube trailer issue (continuing)."

say "8/8  Build expanded modelling dataset"
$PY scripts/12_merge_and_build.py build

echo
echo "DONE -> data/pandora_full_dataset_expanded.csv"
