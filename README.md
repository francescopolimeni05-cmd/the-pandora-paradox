# The Pandora Paradox: Predicting Film Cultural Impact Through Data Integration

> Capstone research project — **ESADE MIBA**
> Authors: **Francesco Polimeni**, **Hiroaki Nakano**
> Supervisor: **Carlos Carrasco-Farré, Ph.D.** (ESADE Business School)
> Repository: <https://github.com/francescopolimeni05-cmd/the-pandora-paradox>

---

## Project Overview

**The Pandora Paradox** is a data science project that investigates whether a film's **performance metrics** (box office revenue, budget, ratings) can reliably predict its **cultural impact** (Wikipedia pageviews, Reddit discussions, Google Trends interest, YouTube trailer attention, memorable quotes, awards, subtitle-derived narrative features).

The project challenges the assumption that box office success automatically translates to cultural relevance. Films like *Avatar* (2009) dominate revenue but underperform on cultural engagement per dollar earned, while cult films sustain discussion long after release despite commercial failure. This project quantifies that gap and builds a predictive model for it.

### Key Research Questions

1. **Do blockbusters dominate cultural conversation?** — Compare Wikipedia pageviews and Reddit engagement for high- vs. low-grossing films.
2. **What drives sustained cultural interest?** — Identify which metrics best predict long-term Wikipedia engagement.
3. **Can we predict a film's cultural impact from production signals alone?** — Build ML models that use pre-release and early-reception features.
4. **How does cultural impact correlate with critical reception?** — Compare TMDB ratings against Wikipedia, Reddit, and YouTube activity.
5. **How does script/subtitle complexity affect cultural reach?** — Correlate dialogue density, lexical diversity, and peak-intensity features with cultural metrics.

---

## Project Structure

```
capstone-pandora-paradox/
├── data/
│   ├── top200_movies.csv              # Seed list of top-grossing films (197 after disambiguation)
│   ├── cultural_footprint.csv         # Per-film Cultural Footprint Index (CFI) components
│   ├── script_features.csv            # NLP features from IMSDb scripts (limited coverage)
│   ├── subtitle_features.csv          # NLP features from official English subtitles (full coverage)
│   ├── live_api_data.json             # Wikipedia / Reddit / TMDB / Trends / IMSDb raw responses
│   ├── extended_api_data.json         # Live data + OMDb awards + Wikiquote + meme signal
│   ├── google_trends_serpapi.json     # Google Trends (via SerpAPI, replaces pytrends)
│   ├── youtube_data.json              # YouTube trailer metadata (pre/post-release split)
│   ├── youtube_trailer_data.json      # YouTube trailer absolute view counts
│   ├── pandora_full_dataset.csv       # Integrated, modeling-ready dataset
│   └── figures/                       # Exported plots (CFI distribution, paradox scatter, ...)
│
├── scripts/
│   ├── 01_collect_movies.py           # Scrape Wikipedia "highest-grossing films"
│   ├── 02_cultural_footprint.py       # Legacy cultural metrics pass (kept for reference)
│   ├── 03_movie_scripts.py            # IMSDb scripts + initial NLP features
│   ├── 03_1_subtitle_features.py      # Subtitle-based NLP (TMDB lookup → YIFY .srt → features)
│   ├── 04_build_index.py              # Legacy index build (kept for reference)
│   ├── 04_1_build_index.py            # Build REAL CFI + full modeling dataset
│   ├── 06_live_data_collectors.py     # Wikipedia / Reddit / TMDB / Trends / IMSDb live collectors
│   ├── 06_1_extended_collectors.py    # OMDb awards, Wikiquote quotes, meme signal
│   ├── 07_google_trends_serpapi.py    # Google Trends via SerpAPI (replaces rate-limited pytrends)
│   ├── 07_youtube_trailer_collector.py# YouTube trailer features (leakage-aware Model A / B split)
│   ├── 09_youtube_trailer_views.py    # YouTube trailer absolute view counts
│   └── (helpers)                      # audit_low_wiki_views, fix_csv_errors_*, fix_wiki_views_bulk,
│                                      # fix_disambiguation_titles, collect_real_data, export_summary_xlsx
│
├── notebooks/
│   ├── pandora_paradox_analysis.ipynb # EDA, CFI construction, paradox analysis, modeling
│   ├── INDEX.txt                      # Cell-level index
│   └── README.md                      # Notebook documentation
│
├── requirements.txt                   # Python dependencies
├── .gitignore
└── README.md                          # This file
```

---

## Data Sources

### 1. Box Office Data (Script 01)
- **Source**: Wikipedia list of highest-grossing films.
- **Metrics**: Worldwide gross, domestic gross, budget, release year, genre, franchise flag.
- **Coverage**: **197 films** (1997–2024). 3 titles were dropped from the original top 200 during disambiguation cleaning (see `fix_disambiguation_titles.py`).

### 2. Wikipedia Activity (Script 06)
- **Source**: Wikimedia REST API (no authentication required).
- **Endpoint**: `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/`
- **Metrics**:
  - Monthly pageviews (rolling 3-year window)
  - Total views, average monthly views, peak views
  - Language edition count (cross-wiki reach proxy)
- **Rate Limit**: ~2 requests/second (≈1,000 req/hour).
- **Cost**: Free.

### 3. Reddit Discussion (Script 06)
- **Source**: Reddit public search API (no authentication required).
- **Endpoint**: `https://www.reddit.com/search.json`
- **Metrics**:
  - Post count, total comments, total upvotes
  - Average engagement per post
  - Subreddit diversity and top subreddit (extracted in `06_1_extended_collectors.py`)
- **Rate Limit**: 60 req/min (script adds delays).
- **Cost**: Free.

### 4. TMDB Movie Data (Script 06)
- **Source**: The Movie Database API.
- **Endpoint**: `https://api.themoviedb.org/3/search/movie`
- **Metrics**: Budget, revenue, popularity, vote average, vote count, runtime, genres, production companies.
- **Rate Limit**: 40 req / 10s (free tier).
- **Cost**: Free (registration + API key required).
- **API key**: <https://www.themoviedb.org/settings/api>

### 5. Google Trends (Script 07 — SerpAPI)
- **Source**: Google Trends via **SerpAPI** (`07_google_trends_serpapi.py`).
- **Why not pytrends?** Direct scraping rate-limited us to 13/197 films with 429 responses. SerpAPI proxies the Trends endpoint server-side, removing the per-IP limit.
- **Metrics**: 3-year interest time series, max / min / average interest, peak date, `gtrends_pre2004` flag for titles older than the Trends record.
- **Cost**: Paid tier likely needed for a full 197-film run (1 search per film). Free tier covers smoke testing.
- **API key**: <https://serpapi.com/manage-api-key>

### 6. Awards, Quotes, Meme Signal (Script 06.1)
- **Awards** — OMDb API: `awards_wins`, `awards_nominations`, `oscar_wins` parsed from the plain-text `Awards` field.
- **Quotability** — Wikiquote: `wikiquote_count` (number of `<dl>` dialogue blocks on `https://en.wikiquote.org/wiki/<Title>`). IMDb's `/quotes` is blocked by anti-bot; Wikiquote is the open-licensed fallback.
- **Meme signal** — derived from Reddit posts already collected: `meme_post_count`, `subreddit_diversity`, `top_subreddit`.

### 7. YouTube Trailers (Scripts 07 & 09)
- **Source**: YouTube Data API v3 (simple API key, no OAuth).
- **`07_youtube_trailer_collector.py`** — trailer-level features, split to avoid data leakage:
  - **Model A (safe, pre-release)**: `yt_trailer_count`, `yt_upload_lead_days`.
  - **Model B (early-reception)**: `yt_comments_day_7`, `yt_comments_day_30`, `yt_comments_velocity`.
- **`09_youtube_trailer_views.py`** — absolute view / like / comment counts per trailer, checkpoint-based to survive daily quota limits.
- **Pre-2005 films** flagged with `yt_pre_youtube_era` — YouTube launched Feb 2005, so earlier "trailers" are post-hoc uploads and produce noisy signals.

### 8. Movie Scripts & Subtitles (Scripts 03 & 03.1)
- **Scripts** — IMSDb (`03_movie_scripts.py`): line count, dialogue/action ratio, basic NLP. Coverage ≈30% (many films have no public script).
- **Subtitles** — YIFY via TMDB lookup (`03_1_subtitle_features.py`): parses official English `.srt`, computes traditional NLP features **plus peak-based features** (most-intense 10% of runtime, lexical burstiness). Coverage is much higher than IMSDb scripts and does not rely on screenplay availability.

---

## The Cultural Footprint Index (CFI)

The CFI is an 8-component composite, MinMax-normalised to 0–100. `04_1_build_index.py` builds two variants:

**Basic CFI** (when only `live_api_data.json` is present):

| Weight | Component                          |
|--------|------------------------------------|
| 30%    | Wikipedia monthly pageviews (log)  |
| 15%    | Wikipedia language editions        |
| 25%    | Reddit engagement (log of upvotes + comments) |
| 15%    | TMDB vote count (log)              |
| 15%    | Google Trends average interest     |

**Extended CFI** (used when `extended_api_data.json` is present — default):

| Weight | Component                          |
|--------|------------------------------------|
| 20%    | Wikipedia monthly pageviews (log)  |
| 10%    | Wikipedia language editions        |
| 20%    | Reddit engagement                  |
| 10%    | TMDB vote count                    |
| 10%    | Google Trends average interest     |
| 10%    | IMDb/Wikiquote quote count         |
| 10%    | OMDb awards (wins + nominations)   |
| 10%    | Meme signal (subreddit diversity)  |

**Residual-based classification**: films are labelled Strong Underperformer, Underperformer, As Expected, Overperformer, or Strong Overperformer based on the residual between observed CFI and CFI predicted from box-office + budget + rating alone.

---

## Installation & Setup

### 1. Clone
```bash
git clone https://github.com/francescopolimeni05-cmd/the-pandora-paradox.git
cd the-pandora-paradox
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. API keys (store as environment variables)
- **TMDB** — <https://www.themoviedb.org/settings/api>
- **OMDb** — <http://www.omdbapi.com/apikey.aspx>
- **SerpAPI** (for Google Trends) — <https://serpapi.com/manage-api-key>
- **YouTube Data API v3** — Google Cloud Console, enable *YouTube Data API v3*, create an API key.

### 4. (Optional) SpaCy language model for extended NLP
```bash
python -m spacy download en_core_web_sm
```

---

## Running the Pipeline

All scripts run from the repo root.

### Phase 1 — Collect the seed list
```bash
python scripts/01_collect_movies.py
# → data/top200_movies.csv
```

### Phase 3 — Script & subtitle features
```bash
# Legacy script-based pass (limited coverage)
python scripts/03_movie_scripts.py
# → data/script_features.csv

# Subtitle-based pass (recommended, full coverage)
python scripts/03_1_subtitle_features.py --api-key "$TMDB_API_KEY"
# → data/subtitle_features.csv
```

### Phase 6 — Live API collectors
```bash
# All collectors
python scripts/06_live_data_collectors.py --api-key "$TMDB_API_KEY"
# → data/live_api_data.json

# A single collector
python scripts/06_live_data_collectors.py --collector wikipedia_pageviews
python scripts/06_live_data_collectors.py --collector reddit_mentions
python scripts/06_live_data_collectors.py --collector tmdb_data --api-key "$TMDB_API_KEY"

# Extended collectors (awards, quotes, meme signal)
python scripts/06_1_extended_collectors.py --omdb-key "$OMDB_API_KEY"
# → data/extended_api_data.json
```

### Phase 7 — Google Trends (SerpAPI) and YouTube trailers
```bash
python scripts/07_google_trends_serpapi.py --api-key "$SERPAPI_KEY"
# → data/google_trends_serpapi.json

python scripts/07_youtube_trailer_collector.py --api-key "$YOUTUBE_API_KEY"
# → data/youtube_data.json
```

### Phase 9 — YouTube trailer absolute views
```bash
python scripts/09_youtube_trailer_views.py --api-key "$YOUTUBE_API_KEY"
# → data/youtube_trailer_data.json
```

### Phase 4.1 — Build the index and full dataset
```bash
python scripts/04_1_build_index.py
# → data/cultural_footprint.csv
# → data/pandora_full_dataset.csv
```

---

## Analysis Notebook

A single consolidated notebook covers EDA, CFI construction, paradox analysis, and modeling:

```bash
jupyter notebook notebooks/pandora_paradox_analysis.ipynb
```

See `notebooks/INDEX.txt` for a cell-level map.

---

## Key Findings (Preliminary)

### The Paradox Effect
- **High box office ≠ high cultural impact.** Some blockbusters dominate both (e.g. *Avengers: Endgame*), but many high-grossing titles have weak Wikipedia / Reddit / search signals relative to their revenue.
- **Cult sustained engagement**: lower-budget films can reach Wikipedia language-edition counts comparable to mid-tier blockbusters.
- **Language-edition proxy**: Wikipedia language count correlates with both box office **and** cultural engagement (r > 0.7), making it one of the single strongest individual signals.

### Wikipedia as cultural barometer
- Pageviews show **seasonal spikes** aligned with anniversaries, sequels, and awards cycles.
- Peak pageviews and average-monthly pageviews measure different audiences — average better predicts sustained impact.

### Reddit as a demographic filter
- Sci-fi and animation genres are over-represented.
- Franchises show **lower per-post engagement** than standalone films — more posts but shorter discussions.

### Script & subtitle features
- **Dialogue density** (subtitles) correlates positively with Reddit engagement.
- **Peak-intensity features** (most-intense 10% of runtime) capture narrative climaxes better than whole-film averages.
- Script/subtitle **lexical diversity** shows a mild positive correlation with Wikipedia activity.

### YouTube trailers
- `yt_comments_velocity` (day-7 / day-30 comments) is a leading indicator of early buzz.
- Pre-2005 trailers are noisy by construction and handled with `yt_pre_youtube_era` flag rather than imputed.

---

## Data Processing Pipeline

```
Raw data  →  Collectors  →  JSON/CSV  →  Feature engineering  →  CFI + residuals  →  Models
   ↓             ↓              ↓                ↓                      ↓              ↓
top200_movies  06 / 06.1    live_api_data   pandora_full_dataset   cultural_footprint  notebook
                07gt / 07yt                                                             outputs
                09 / 03.1
```

### Output schema (`live_api_data.json`, truncated)
```json
[
  {
    "movie_title": "Avatar",
    "movie_year": 2009,
    "collection_timestamp": "2026-03-27T12:34:56Z",
    "metrics": {
      "wikipedia_pageviews": { "total_views": 15234567, "average_monthly_views": 423460 },
      "reddit_mentions":     { "post_count": 1523, "total_comments": 45230 },
      "tmdb_data":           { "vote_count": 27340, "vote_average": 7.6 },
      "google_trends":       { "average_interest": 12.6 }
    }
  }
]
```

---

## Troubleshooting

- **TMDB `401 Unauthorized`** — pass a valid key via `--api-key`.
- **Reddit `429`** — reduce `--limit`, or wait. The script already throttles.
- **Wikipedia pageviews empty** — title may need disambiguation; see `fix_disambiguation_titles.py`.
- **IMSDb script missing** — ~30% coverage is expected; the subtitle pipeline (`03_1`) is the recommended alternative.
- **pytrends 429** — do not use `pytrends` for full runs; switch to `07_google_trends_serpapi.py`.
- **YouTube quota exceeded** — `09_youtube_trailer_views.py` is checkpoint-based; rerun the next day and it resumes.

---

## Project Timeline

- **Phase 1** (Done): Seed list from Wikipedia — 200 → 197 after disambiguation.
- **Phase 2** (Done): Legacy cultural metrics.
- **Phase 3** (Done): IMSDb script NLP.
- **Phase 3.1** (Done): Subtitle-based NLP (full-coverage replacement for 3).
- **Phase 4** (Done): Dataset integration.
- **Phase 4.1** (Done): Real-value CFI construction + residual classification.
- **Phase 6** (Done): Live API collectors (Wikipedia, Reddit, TMDB, Trends, IMSDb).
- **Phase 6.1** (Done): Extended collectors (OMDb awards, Wikiquote, meme signal).
- **Phase 7 (Trends)** (Done): SerpAPI replacement for rate-limited pytrends.
- **Phase 7 (YouTube)** (Done): Trailer features with Model A / Model B leakage split.
- **Phase 9** (Done): YouTube trailer absolute view counts.

---

## Team & Attribution

- **Authors**: Francesco Polimeni, Hiroaki Nakano (ESADE MIBA)
- **Supervisor**: Carlos Carrasco-Farré, Ph.D. — ESADE Business School
- **Focus**: Data-driven cultural impact prediction
- **Methods**: Web scraping, API integration, NLP (spaCy / custom), regression & classification
- **Tools**: Python, Pandas, Scikit-learn, spaCy, Matplotlib / Seaborn

---

## References & Resources

- [Wikimedia REST API docs](https://www.mediawiki.org/wiki/APIs)
- [TMDB API](https://developer.themoviedb.org/)
- [OMDb API](http://www.omdbapi.com/)
- [SerpAPI — Google Trends](https://serpapi.com/google-trends-api)
- [YouTube Data API v3](https://developers.google.com/youtube/v3)
- [Reddit API](https://www.reddit.com/dev/api/)
- [IMSDb](https://www.imsdb.com/)
- [Wikiquote](https://en.wikiquote.org/)

---

## License & Data Usage

- **Box office & Wikipedia metrics**: CC-BY-SA.
- **TMDB data**: TMDB Terms of Use (attribution required).
- **OMDb / SerpAPI / YouTube**: respective provider terms of service.
- **Reddit data**: Reddit Terms of Service.
- **Scripts & subtitles**: rights belong to their holders (fair-use, research only).

For any commercial use, review each provider's terms directly.

---

**Last Updated**: April 2026
**Status**: Midterm checkpoint — active development
