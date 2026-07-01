# Sample Expansion, Run Guide

Adds ~150 cult / flop / low-budget / arthouse films to the existing 194, to create
the exposure↔persistence variation the supervisor asked for. Every value comes from
a real API response, nothing is invented. Films TMDB can't match are written to
`data/expansion_unmatched.csv` for manual review, never guessed.

> **Run this on your Mac**, not in the Claude session. The Claude sandbox is
> firewalled and cannot reach TMDB / OMDb / SerpAPI / YouTube / Reddit. Your
> existing pipeline already works locally, these steps reuse it.

## 0. One-time setup

```bash
cd capstone-pandora-paradox
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then paste your 4 keys into .env
set -a; source .env; set +a   # load keys into the shell
```

Keys needed (all reused from your current pipeline):
`TMDB_API_KEY`, `OMDB_API_KEY`, `SERPAPI_KEY`, `YOUTUBE_API_KEY`.

## 1. Review the candidate list (optional but recommended)

Open `data/expansion_candidates.csv` (157 films, tagged by category and expected
pattern). Add/remove rows as you like, the rest of the pipeline just reads this file.

## 2. Build the seed (TMDB → real budget/revenue/genre)

```bash
python scripts/10_build_expansion_seed.py
# smoke test first if you prefer:  python scripts/10_build_expansion_seed.py --limit 5
```

Produces `data/expansion_movies.csv`, `data/all_movies.csv`, and (if any) a
`data/expansion_unmatched.csv` to eyeball.

## 3. Collect for the NEW films only

```bash
# base metrics (Wikipedia, Reddit, TMDB, Trends-stub, IMSDb)
python scripts/06_live_data_collectors.py \
  --movies data/expansion_movies.csv \
  --output data/expansion_live_api_data.json \
  --api-key "$TMDB_API_KEY"

# awards (OMDb) + quotability (Wikiquote) + reddit-derived meme features
python scripts/06_1_extended_collectors.py \
  --input  data/expansion_live_api_data.json \
  --output data/expansion_extended_api_data.json

# subtitle NLP features (short_punchy_density, sentiment_peak, rare_proper_noun_count, ...)
python scripts/03_1_subtitle_features.py \
  --api-key "$TMDB_API_KEY" \
  --input   data/expansion_movies.csv \
  --csv-out data/expansion_subtitle_features.csv \
  --json-out data/expansion_subtitle_raw.json
```

## 4. Fold the new films into the canonical files

```bash
python scripts/12_merge_and_build.py combine
```

This merges the expansion outputs into `live_api_data.json`,
`extended_api_data.json`, and `subtitle_features.csv` (originals backed up to
`*.preexpansion`). Trends/YouTube must run **after** this, because they read the
canonical files and inject their blocks via `--merge`.

## 5. Trends + YouTube (existing films are skipped via checkpoints)

```bash
python scripts/07_google_trends_serpapi.py            # processes only the new films
python scripts/07_google_trends_serpapi.py --merge    # injects trends into live + extended

python scripts/09_youtube_trailer_views.py
python scripts/09_youtube_trailer_views.py --merge

python scripts/07_youtube_trailer_collector.py \
  --input data/live_api_data.json \
  --output data/youtube_data.json --resume
```

## 6. Build the expanded modelling dataset

```bash
python scripts/12_merge_and_build.py build
```

Produces **`data/pandora_full_dataset_expanded.csv`** (same 104-column schema as
`pandora_full_dataset.csv`, now ~340 films). That file is the input for the next
phase: SCI, the 4-component CFI, and the causal models.

---

### Notes & cost
- **SerpAPI** is the only paid key; ~1 search per new film (~150 calls).
- **OMDb** free tier is 1,000/day, fine for one run.
- Re-running any step is safe: collectors checkpoint/`--resume`, and `combine`
  dedupes by `(title, year)`.
- If a step dies midway, just re-run it; it picks up where it left off.
