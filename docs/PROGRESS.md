# Progress Log — Pandora Paradox
**Author:** Hiroaki
**Last updated:** 2026-04-23

This document records the work I have done on top of the project as described in [README.md](../README.md). All original files have been kept intact; everything below is additive.

---

## 1. Starting point

As described in [README.md](../README.md), the project targets the question

> "Can a film's performance metrics predict its cultural impact?"

The repository defined a 6-phase pipeline:

| Phase | Script | Role |
| --- | --- | --- |
| 1 | `01_collect_movies.py` | Scrape top-200 films from Wikipedia |
| 2 | `02_cultural_footprint.py` | Collect Wikipedia / Reddit / Trends metrics |
| 3 | `03_movie_scripts.py` | Scrape and analyse film scripts |
| 4 | `04_build_index.py` | Integrate everything into a Cultural Footprint Index |
| 5 | `05_ml_model.py` | Train regression + classification models on the CFI |
| 6 | `06_live_data_collectors.py` | Real API collectors for Wikipedia / Reddit / TMDB / Trends / IMSDb |

The included `data/model_results.json` reported **R² = 0.10 / AUC = 0.55** — both close to random.

---

## 2. Initial audit of the existing codebase

Before touching anything I read through the scripts and found that the pipeline was running on randomly-generated sample data rather than real data:

- **`02_cultural_footprint.py`**: a hand-authored dictionary holds values for ~30 famous films; for the remaining 170 titles, genre-based `np.random.normal()` calls fabricate cultural metrics.
- **`03_movie_scripts.py`**: the same pattern — hardcoded NLP feature values for a handful of films, then genre-conditioned random draws for everything else. No actual script text is parsed.
- **`06_live_data_collectors.py`**: fully implemented real-API code (Wikipedia pageviews + language editions, Reddit search, TMDB, Google Trends, IMSDb scraping) — but never actually run by the existing pipeline.
- **Consequence**: the R² / AUC numbers in `model_results.json` reflect that sample data, not real data.

---

## 3. Bug fixes to `06_live_data_collectors.py`

Two latent bugs prevented the existing live collectors from working correctly:

### 3.1 Wikipedia pageviews — title candidate fallback
- The URL builder always appended the disambiguation suffix `_(YYYY_film)`. This works for *Avatar_(2009_film)* but fails for *Avengers:_Endgame* (which does not use disambiguation).
- Fix: now tries multiple candidate titles in order — `Title_(YYYY_film)` → `Title` → `Title_(film)` — and uses the first one that returns 200 OK.
- Also properly URL-encodes spaces to underscores.

### 3.2 IMSDb scraper — URL pattern matching
- Was constructing `/scripts/title-YYYY.html` (lowercase + year). Actual IMSDb URLs do not include the year and often use PascalCase or the "Title, The" convention.
- Fix: tries several variants (`Title-Name`, `Title-Name,-The`, `TitleName`, `title-name`) and picks the first 200 OK that isn't a "not found" page.

---

## 4. New scripts added

The original files were left unchanged. Four new scripts and one helper sit alongside them:

| New file | What it does |
| --- | --- |
| `scripts/03_1_subtitle_features.py` | Scrapes YIFY subtitles by IMDb ID (via TMDB `external_ids`), parses SRTs, computes dialogue-level NLP features |
| `scripts/04_1_build_index.py` | Flattens `live_api_data.json` + `extended_api_data.json` + subtitle features into a real-data Cultural Footprint Index |
| `scripts/05_1_ml_model.py` | Trains Model A ("strict pre-release") and Model B ("+ early reception"); reports R², AUC, and feature importance |
| `scripts/06_1_extended_collectors.py` | Adds OMDb awards, Wikiquote realised quotability, and Reddit-derived meme signals |
| `scripts/export_summary_xlsx.py` | Generates `pandora_database_summary.xlsx` (two-tab bilingual summary) |

---

## 5. Data sources integrated

| Source | Purpose | API key needed | Coverage |
| --- | --- | --- | --- |
| Wikipedia pageviews (Wikimedia REST) | Long-term reference interest | no | 98 % |
| Wikipedia language editions | Global reach | no | 100 % |
| Reddit public search | Discussion volume / engagement | no | 99 % |
| TMDB | Budget / revenue / popularity / rating | yes (free) | 98 % |
| Google Trends (pytrends) | Search interest | no | **7 %** — rate-limited |
| IMSDb | Script structure (supplementary) | no | 22 % |
| **YIFY Subtitles** (new) | Dialogue NLP — replaces IMSDb as primary script source | no | **95 %** |
| **OMDb API** (new) | Awards, IMDb rating / votes, Metascore | yes (free) | 96 % |
| **Wikiquote** (new) | Realised quotability — replaces blocked IMDb quotes | no | 93 % |
| **Reddit-derived** (new) | Meme penetration, subreddit diversity | computed | 100 % |

IMDb direct scraping was attempted but returns HTTP 202 + empty body (anti-bot). Wikiquote + OMDb together cover the same research need.

---

## 6. New features designed

### 6.1 Meme-prediction predictors (X-side, subtitle-derived)
- **`short_punchy_count`** — lines of 2-6 words ending in `.` / `!` with no `?` (structural quotability potential)
- **`short_punchy_density`** — the above, normalised by total dialogue lines
- **`rare_proper_noun_count`** — mid-sentence capitalised tokens appearing ≤ 2 times (invented names like Pandora, Thanos)
- **`sentiment_spike`** — largest absolute sentiment change between consecutive lines
- **`sentiment_peak`** — maximum absolute line-level sentiment

### 6.2 Cultural-impact outcomes (Y-side)
- **`wikiquote_count`** — realised quotability from Wikiquote
- **`meme_post_count`** — posts in meme-specific subreddits (derived from Reddit data already collected)
- **`subreddit_diversity`** — number of distinct subreddits discussing the film
- **`subreddit_concentration`** — Herfindahl index of subreddit distribution

---

## 7. Pipeline executed on all 197 films

Both collectors ran in parallel in the background. Final coverage:

| Collector | Success rate |
| --- | --- |
| Wikipedia pageviews | 193 / 197 (98 %) |
| Wikipedia language editions | 197 / 197 (100 %) |
| Reddit mentions | 196 / 197 (99 %) |
| TMDB metadata | 194 / 197 (98 %) |
| YIFY subtitles | 187 / 197 (95 %) |
| IMSDb scripts | 43 / 197 (22 %) |
| Google Trends | 13 / 197 (7 %) |
| OMDb awards | 190 / 197 (96 %) |
| Wikiquote | 183 / 197 (93 %) |
| Reddit-derived | 197 / 197 (100 %) |

---

## 8. CFI rebuilt on real data

The original CFI weighted seven components, of which four (`quotability_score`, `meme_score`, `merchandise_index`, `awards`) were hand-coded sample values. The new CFI uses eight **all-observable** components:

| Component | Weight | Real source |
| --- | --- | --- |
| Wikipedia views | 20 % | Wikimedia API |
| Wikipedia languages | 10 % | Wikimedia API |
| Reddit engagement | 20 % | Reddit API |
| TMDB vote count | 10 % | TMDB API |
| Google Trends | 10 % | pytrends (7 % populated) |
| Wikiquote count | 10 % | Wikiquote scrape |
| Awards (wins + noms) | 10 % | OMDb |
| Meme-subreddit posts | 10 % | Derived from Reddit |

`cfi_score` (0-100) and `cfi_residual` (residual from `log(gross)` + `log(budget)` regression) are stored per film.

---

## 9. First real-data ML results

**Model A — strict pre-release (metadata + subtitle NLP only)**
- Regression: test R² = +0.026, CV R² = −0.236 ± 0.13
- Classification (overperformer vs underperformer): best CV AUC 0.636 (Random Forest)

**Model B — + early reception (tmdb_popularity, imdb_rating, metascore)**
- Regression: test R² = +0.102, CV R² = +0.070 ± 0.18
- Classification: best CV AUC 0.725 (Random Forest)

**Top Model A features (regression)**
1. `rare_proper_noun_count` 0.120 ← newly designed
2. `short_punchy_count` 0.093 ← newly designed
3. `humor_indicator` 0.067
4. `vocabulary_richness` 0.064
5. `short_punchy_density` 0.057

The two peak-based features I designed top the list, ahead of budget, sequel flag, or franchise flag. This directly validates the hypothesis that extractable units matter more than averages for meme prediction.

### 9.1 `years_since_release` experiment — null result

After the first run I added `years_since_release` (current year − release year) as a metadata feature, on the hypothesis that older films should accumulate more Wiki views / Reddit posts / etc.

Re-running 04_1 → 05_1 with the feature included:

| Metric | Before | After | Change |
| --- | --- | --- | --- |
| Model A regression test R² | +0.026 | −0.016 | slight ↓ |
| Model A regression CV R² | −0.236 | −0.308 | ↓ |
| Model A best classifier CV AUC | 0.636 | 0.657 | +0.02 |
| Model B regression test R² | +0.102 | +0.208 | ↑ |
| Model B regression CV R² | +0.070 | −0.042 | ↓ |
| Model B best classifier CV AUC | 0.725 | 0.729 | flat |

`years_since_release` did **not** appear in the top-10 feature importances of either model. The likely reason is that the new CFI is structurally time-controlled: Wikipedia pageviews use a rolling 3-year window, Reddit returns "current" hot posts, Wikiquote counts are editor-curated rather than time-accumulated, and award counts are mostly fixed at release. So there was little time-bias left to absorb. The feature was retained in the codebase as a recorded experiment.

CV variance was high (σ ≈ 0.21–0.30) — the test-R² swings between runs are largely noise from a small (n = 197) sample, not real signal.

---

## 10. Output files

### Data
- `data/live_api_data.json` — raw live-API results for 197 films
- `data/extended_api_data.json` — live data + OMDb + Wikiquote + Reddit-derived
- `data/subtitle_features.csv` — NLP features from real subtitles
- `data/cultural_footprint_real.csv` — CFI components
- `data/pandora_full_dataset_real.csv` — full merged dataset (87 columns)
- `data/model_results_real.json` — Model A / B metrics and feature importance

### Deliverables / documents
- `pandora_database_summary.xlsx` — two-tab summary (JA / EN)
- `meeting_brief_2026-04-22.md` / `.pdf` — English meeting brief
- `meeting_brief_2026-04-22.ja.md` / `.ja.pdf` — Japanese meeting brief
- `PROGRESS.md` / `.ja.md` — this log

---

## 11. What is scheduled next

For the 2026-04-26 intermediate deadline (dataset only):
- 4/23 — add `years_since_release`, fix OMDb year-mismatch edge cases, write and run YouTube trailer collector
- 4/24 — run visual-distinctiveness feature extractor on posters, final CFI re-run
- 4/25 — data integration + presentation-video recording
- 4/26 — buffer day and intermediate submission

Post-deadline:
- Analysis notebook refresh on real data
- Paradox case studies (top residuals)
- Feature-importance visualisation
- CFI-weight sensitivity analysis
- Final report and slides

---

## 12. 2026-04-22 addition — YouTube trailer collector

`scripts/07_youtube_trailer_collector.py` was added to `main` on 2026-04-22. It collects official-trailer data via YouTube Data API v3 with a **data-leakage-aware split**:

- **Model A safe**: `yt_trailer_count`, `yt_upload_lead_days` (marketing decisions, known pre-release)
- **Model B only**: `yt_comments_day_7`, `yt_comments_day_30`, `yt_comments_velocity` (early-reception signals, post-release)

Documented limitations: pre-2005 films are skipped; trailers with >5,000 total comments cannot reach Day-7 comments within free quota and get NaN; ~50 % of major-studio trailers have comments disabled.

### Broader scope explored on the `hiroaki` branch

On 2026-04-22 a further set of extensions was explored, but kept **off `main`** and isolated to `origin/hiroaki` for team review before any merge. Contents in one sentence: seven additional feature families (star power, release context, plot embedding, subtitle TF-IDF SVD, transformer sentiment, 7-emotion classification, Vonnegut emotional arc) plus a three-way Y-variable experiment (`balanced` / `pure_culture` / `buzz`).

See **[docs/HIROAKI_BRANCH_SUMMARY.md](HIROAKI_BRANCH_SUMMARY.md)** (or [.ja.md](HIROAKI_BRANCH_SUMMARY.ja.md)) for a full summary of that branch's work, including predictive-performance results and headline findings.

---

## 13. 2026-04-22/23 additions — data-quality audits + `midterm-submission` integration

Three streams of work landed on `main` between 2026-04-22 and 2026-04-23:

### 13.1 CSV / Wikipedia data-quality audits (Round-1 / 2 / 3)

My original `top200_movies.csv` + `live_api_data.json` collection had several latent bugs that I only discovered after the first live run. Three rounds of audits fixed them:

- **Row deletions (3)**: "DreamWorks Dragons 2" (row 80; CSV-scraping duplicate of How to Train Your Dragon 2), "Frozen 2" (row 74; same film as Frozen II), "Incredibles" (row 23; same film as The Incredibles). Sample size moved 197 → **194**.
- **Title renames (3)**: punctuation / disambiguation bugs that had broken downstream API calls were corrected:
  - `Dr. Seuss' Horton Hears a Who!` → `Horton Hears a Who!` — the apostrophe + `!` killed Wikipedia, Wikiquote and OMDb queries
  - `The Sleeping Beauty` → `Sleeping Beauty` — the leading "The" made the Wikipedia API redirect to **Tchaikovsky's ballet** (wiki_views = 2,683 = ballet article's traffic; post-fix = 1,836,599)
  - `Illumination's Pets United` → `The Secret Life of Pets 2` — "Pets United" is a separate German Netflix release; box office / year / studio all matched Secret Life 2
- **Round-3 Wikipedia redirect audit (60 films)**: the original collector built disambiguated URLs like `Title_(YYYY_film)`, which are **redirects** to the canonical article. The pageviews API does NOT follow redirects, so the disambiguator's near-zero traffic was being attributed instead of the real article traffic. A dedicated audit script (`scripts/audit_low_wiki_views.py`) + two auto-fix scripts (`scripts/fix_csv_errors_round3.py`, `scripts/fix_csv_errors_round3b.py`) used the MediaWiki `?redirects=true` query to re-fetch pageviews + langlinks for 60 films. Sample effects: Toy Story 895 → 4.2M views, Frozen II 814 → 1.1M, Oppenheimer 15K → 51.5M, Lion King (1994) 47K → 5.9M views + `wiki_langs` 1 → 114.
- Full audit log in **[docs/CSV_CORRECTIONS.md](CSV_CORRECTIONS.md)** (Japanese: [.ja.md](CSV_CORRECTIONS.ja.md)).

### 13.2 YouTube trailer collector integrated (2026-04-22)

- `scripts/07_youtube_trailer_collector.py` and `data/youtube_data.json` (collected 4-22) were integrated into `scripts/04_1_build_index.py` via a new `flatten_youtube()` function. Six YouTube columns land in `pandora_full_dataset_real.csv`:
  - Model-A-safe (studio decisions, known pre-release): `yt_trailer_count`, `yt_upload_lead_days`
  - Model-B-only (audience reception, post-release): `yt_comments_day_7`, `yt_comments_day_30`, `yt_comments_velocity`
- `scripts/05_1_ml_model.py` now lists these under `YOUTUBE_STUDIO_FEATURES` (Model A) and `YOUTUBE_EARLY_FEATURES` (Model B).
- Commit: `36451ff`.

### 13.3 `midterm-submission` branch integration (2026-04-23)

A teammate pushed `origin/midterm-submission` on 2026-04-23. The branch carried two valuable additions that I pulled into `main`, plus several data-layer differences that I resolved by cherry-picking rather than merging.

**Pulled into `main` (commit `8c7898a`):**
- `scripts/07_google_trends_serpapi.py` + `data/google_trends_serpapi.json` — SerpAPI-based Google Trends collector. The `--merge` path drops the new `google_trends` block into both `live_api_data.json` and `extended_api_data.json`, so `scripts/04_1_build_index.py` picks it up with no further change on the Y-side. **Trends coverage jumped 13/194 (7 %) → 190/194 (98 %)**, closing the `pytrends` rate-limit gap.
- `scripts/09_youtube_trailer_views.py` + `data/youtube_trailer_data.json` — absolute YouTube trailer views / likes / comments collector. A new `flatten_youtube_trailer_views()` function in `04_1_build_index.py` surfaces `yt_top_views`, `yt_total_views_top3`, `yt_top_likes`, `yt_top_comments_total` (coverage 192/194 for views). `05_1_ml_model.py` adds these four columns to `YOUTUBE_EARLY_FEATURES` (Model B only — they are post-release signal).

**Deliberately NOT merged:**
- The `midterm-submission` branch was cut before the Round-2/3 audits landed, so its copies of `top200_movies.csv`, `pandora_full_dataset_real.csv`, and `live_api_data.json` still carry the pre-audit Wikipedia bugs — merging those would have regressed the dataset by ~60 films. Only the two new collectors + their data outputs were pulled.
- The branch also renamed `wikiquote_count` → `wikiquote_page_size` and dropped `reddit_posts`; both were left as-is on `main` pending team discussion.
- Title-rename reconciliation: two safe renames applied to the `midterm-submission` JSONs before merging (`Incredibles` → `The Incredibles`, `Dr. Seuss' Horton Hears a Who!` → `Horton Hears a Who!`); two dropped rather than remapped (`Illumination's Pets United` was a different film; `The Sleeping Beauty` queries land on the ballet on Trends).

### 13.4 Model results after integration

`data/cultural_footprint_real.csv`, `data/pandora_full_dataset_real.csv`, `data/model_results_real.json` rebuilt on `main`. n = 194, extended CFI weighting.

| Model | Metric | main (pre-integration) | main (post-integration) |
|---|---|---:|---:|
| A (strict pre-release) | LogReg test AUC | 0.595 | **0.742** |
| A | LogReg CV AUC | 0.498 ± 0.065 | 0.503 ± 0.070 |
| B (+ early reception) | LogReg CV AUC | 0.637 ± 0.043 | **0.668 ± 0.050** |
| B | best test AUC | 0.766 (LogReg) | **0.821 (XGBoost)** |

**Caveat identified in the 2026-04-23 debrief**: Model B's AUC lift is at least partly a **construct-overlap artefact** — the X-side now contains multiple "cumulative cultural attention" proxies (`tmdb_popularity`, `imdb_rating`, `metascore`, `yt_top_views`, `yt_top_likes`, `yt_top_comments_total`), while the CFI target (Y) is also built from cumulative-attention components (Wikipedia views, Reddit engagement, TMDB vote count, Trends, Wikiquote). The classical Pandora-Paradox test is therefore **`cfi_residual` as target** (Model B on residual — see §4.5 of the 2026-04-23 meeting brief), which collapses Model B back to ≈ Model A. Re-running the residual-target probe on the post-integration dataset is the cleanest next step before the paper.

Full 3-way comparison in **[docs/ml_comparison_2026-04-23.md](ml_comparison_2026-04-23.md)** (Japanese: [.ja.md](ml_comparison_2026-04-23.ja.md)).

### 13.5 Output files added

- `data/google_trends_serpapi.json` — SerpAPI Trends (190/194 success)
- `data/youtube_trailer_data.json` — YouTube trailer views / likes / comments (192/194 success)
- `data/youtube_data.json` — main's YouTube trailer collector output (trailer count + Day-7/30 comments)
- `scripts/07_google_trends_serpapi.py`, `scripts/09_youtube_trailer_views.py`
- `docs/ml_comparison_2026-04-23.md` / `.ja.md`
- `docs/CSV_CORRECTIONS.md` / `.ja.md` — audit log of the 2026-04-22/23 CSV fixes
- `docs/meeting_brief_2026-04-22.md` / `.ja.md`, `docs/meeting_brief_2026-04-23.md` / `.ja.md`
