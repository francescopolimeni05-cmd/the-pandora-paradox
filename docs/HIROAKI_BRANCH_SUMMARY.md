# `hiroaki` Branch Work Summary
**Author:** Hiroaki | **Last updated:** 2026-04-22

This document, kept on `main`, summarises **the additional work done on the `hiroaki` branch**. The `main` branch itself only received the new YouTube collector script; everything else was isolated to `hiroaki` so the team can review before merging.

Target branch: [`origin/hiroaki`](https://github.com/HiroakiNakano1985/capstone-pandora-paradox/tree/hiroaki)

---

## 1. Overview

On top of the pipeline described in [docs/PROGRESS.md](PROGRESS.md), three parallel extensions were carried out:

1. **New X data sources** (8 categories, ~70 additional features total)
2. **Upgraded analysis methods** (Transformer sentiment / Vonnegut emotional arc / TF-IDF SVD / Sentence embeddings)
3. **Re-defined Y variable** (a three-way comparison between `balanced` / `pure_culture` / `buzz`)

Goal: lift the Model A regression test R² from its pre-session value of -0.010, and **build an analytical foundation closer to the "cultural footprint" research question suggested by the original P262 brief.**

---

## 2. New X data sources and features (8 categories)

### 2.1 YouTube trailer features — `scripts/07_youtube_trailer_collector.py`

Searches official trailers via YouTube Data API v3, with a **data-leakage-aware two-bucket split**:

- **Model A safe** (studio marketing decisions, known pre-release):
  - `yt_trailer_count`: how many official trailers the studio uploaded (marketing-investment proxy)
  - `yt_upload_lead_days`: days between first trailer and release (campaign length)
- **Model B only** (early audience reception, post-release):
  - `yt_comments_day_7`, `yt_comments_day_30`, `yt_comments_velocity`

**Implementation constraints** (documented in the script docstring):
- Pre-2005 films are skipped (YouTube didn't exist)
- Trailers with >5,000 total comments cannot reach Day-7 comments because the YouTube API has no `order=oldest`; those films get NaN
- ~50% of major-studio trailers have comments disabled entirely
- Social Blade is login-gated — no scrapeable per-video daily history

**Coverage:** Day 1 collected 109/197 films (87 success). Day 2 (after quota reset) will pick up the remaining 77 films.

### 2.2 Star power features — `scripts/08_star_power.py`

Uses TMDB `/movie/{id}/credits` + `/person/{id}/movie_credits` to aggregate **past films (release year < target year) of the director, lead actor, and top-3 cast**.

Important design choice: `/person/movie_credits` does not return revenue, so we use `vote_count` instead. Vote_count is an "engagement" proxy and arguably **more aligned with cultural footprint than revenue**.

| Feature | Meaning |
|---|---|
| `director_past_avg_popularity` | Director's avg TMDB popularity across past films |
| `director_past_max_vote_count` | Vote count of the director's peak past hit |
| `director_past_avg_rating` | Director's avg past rating |
| `lead_actor_past_*` | Same four metrics for the lead actor |
| `cast_top3_past_*` | Averaged versions for the top-3 cast |

Coverage: 194/197 films success.

### 2.3 Release-context derived features — derived inside `scripts/04_1_build_index.py`

No API call required. Derived purely from the TMDB `release_date` we already had:

- `release_month`, `release_quarter`, `release_decade`
- `release_is_summer`, `release_is_holiday_window`, `release_is_awards_window`

**→ These ended up being the strongest predictors in Model A** (see §4).

### 2.4 Plot embedding similarity — `scripts/10_plot_embedding.py`

Embeds the TMDB overview text with `sentence-transformers/all-MiniLM-L6-v2` and, using **leave-one-out**, computes cosine similarity to the mean embedding of the CFI top-10% and bottom-10% prototypes.

| Feature | Meaning |
|---|---|
| `plot_sim_to_top_decile` | Similarity to past cultural hits |
| `plot_sim_to_bottom_decile` | Similarity to past cultural flops |
| `plot_hit_vs_flop_gap` | Top minus bottom |

Empirical effect is weak. Likely cause: TMDB overviews are only 50–100 words, too short for embedding similarity to be discriminative. Improvement candidate: re-embed using full subtitle text.

### 2.5 Subtitle TF-IDF + SVD — `scripts/03_4_subtitle_tfidf.py`

Runs TF-IDF on the 187-film dialogue corpus, then `TruncatedSVD(K=20)` to extract **20 thematic axes**.

`min_df` is set to roughly 7% of films (=13), which prevents franchise character names (Jack Sparrow, Woody, Elsa) from dominating the principal components.

### 2.6 Advanced sentiment + 7-emotion classification — `scripts/03_2_advanced_sentiment.py`

Runs two transformer pipelines on up to 600 evenly-sampled dialogue lines per film:

1. **cardiffnlp/twitter-roberta-base-sentiment-latest** → pos/neu/neg probabilities
2. **j-hartmann/emotion-english-distilroberta-base** → 7-class emotion (anger/disgust/fear/joy/neutral/sadness/surprise)

Aggregated features (17 total):
- Sentiment: polarity mean/std/peak, strong-pos/strong-neg ratios
- 7 emotions: mean probabilities, top-class ratios, and **Shannon entropy** of the mean distribution (emotional diversity)

Superseding the word-list sentiment in `03_1` for contexts where negation, sarcasm and intensifiers matter (e.g. "not bad" is now correctly positive).

### 2.7 Vonnegut emotional-arc features — `scripts/03_3_emotional_arc.py`

Implements Reagan et al. (2016) "The emotional arcs of stories are dominated by six basic shapes":

1. Bucket the per-line polarity series (from 03_2) into 20 equal segments
2. Smooth with a window=3 moving average
3. Cosine-match against six idealised prototypes (rags_to_riches, tragedy, man_in_hole, icarus, cinderella, oedipus)
4. Extract trajectory stats (peak position, first-half/second-half slopes, volatility, range)

Dominant-arc distribution across 187 scored films:

| Shape | Count |
|---|---|
| man_in_hole | 81 |
| cinderella | 32 |
| rags_to_riches | 30 |
| tragedy | 17 |
| oedipus | 15 |
| icarus | 12 |

Matches Reagan et al.'s observation that man_in_hole dominates commercial narrative.

### 2.8 Additive changes to existing scripts

- `scripts/03_1_subtitle_features.py`: now persists `_dialogue_lines` (full SRT lines) so 03_2 / 03_3 / 03_4 can share the corpus
- `scripts/04_1_build_index.py`: merges all the new CSV/JSON sidecars and adds the release-context derived columns
- `scripts/05_1_ml_model.py`: expanded Model A / B feature groups

---

## 3. Y-variable re-definition experiment — three-way comparison

### 3.1 Motivation

The existing CFI on `main` (called `balanced`) is an 8-component composite in which **over 60% of weight comes from "general popularity / topicality"** (Wikipedia views, Reddit, TMDB votes, Google Trends). Only ~30% captures genuine cultural-memory signals (Wikiquote, language editions, meme posts).

Two concrete problems:
- The strongest predictors (`tmdb_popularity`, `imdb_rating`) are themselves popularity proxies → partial buzz-to-buzz circularity
- *Pulp Fiction* ($214M, high meme density) gets a modest score while *Avengers: Endgame* ($2.8B, low meme density) ranks at the top — out of sync with the "Pandora Paradox" intuition from the brief

### 3.2 Three CFI definitions — `scripts/04_2_alt_cfi.py`

Computes three Ys side-by-side from the same normalised components:

| CFI | Composition | Intent |
|---|---|---|
| **balanced** | 20% wiki_views + 10% wiki_langs + 20% reddit + 10% tmdb_votes + 10% gtrends + 10% wikiquote + 10% awards + 10% memes | Existing 8-component CFI, baseline |
| **pure_culture** | **40% memes + 30% wikiquote + 20% wiki_langs + 10% awards** | Pure cultural memory, strips all popularity proxies |
| **buzz** | 50% reddit + 30% wiki_views + 20% tmdb_votes | Unfiltered popularity — **negative control** |

### 3.3 Inter-CFI correlation

|  | balanced | pure_culture | buzz |
| --- | --- | --- | --- |
| balanced | 1.00 | 0.77 | 0.87 |
| pure_culture | 0.77 | 1.00 | 0.44 |
| buzz | 0.87 | 0.44 | 1.00 |

**The balanced CFI is pulled toward buzz (r=0.87).** This quantifies the diagnosis that the existing CFI is popularity-heavy. The low correlation between pure_culture and buzz (r=0.44) confirms the two are genuinely measuring different things.

### 3.4 Predictive performance comparison — `scripts/05_2_alt_cfi_eval.py`

All on n=197, evaluated under Model A (pre-release only) and Model B (+early reception):

| Y definition | Model | Reg test R² | Best test AUC |
|---|---|---|---|
| balanced | A | +0.095 | 0.714 |
| balanced | B | +0.175 | 0.742 |
| **pure_culture** | **A** | **+0.216** | **0.732** |
| **pure_culture** | **B** | **+0.279** | **0.817** |
| buzz | A | -0.042 | 0.586 |
| buzz | B | -0.130 | 0.641 |

---

## 4. Key findings and implications

### 4.1 Purifying Y does NOT sacrifice predictability

**Prior expectation**: pure_culture would be harder to predict because memes/wikiquote are zero-inflated → R² should drop.  
**Empirical result**: pure_culture R² is **2.3× higher** than balanced, AUC reaches 0.817.

### 4.2 buzz is the hardest Y to predict

Even Model B produces a negative R² on buzz. **Our features cannot predict buzz.**  
Paradoxically important: this is quantitative evidence that **the methodology is NOT buzz-from-buzz circular**, which strengthens the credibility of the pure_culture success.

### 4.3 Y definition matters more than feature engineering

In this session we added 70+ new features, but the predictive gain from simply switching Y from balanced to pure_culture was larger than the gain from any feature additions.

### 4.4 Feature-importance findings (Model A, balanced Y)

Category-level contribution to the top-30 features:

| Category | Sum of importance | Representative features |
|---|---|---|
| Release context | 0.189 | `release_quarter`, `release_month` |
| Emotional arc | 0.113 | `arc_sim_icarus`, `arc_volatility` |
| Advanced sentiment | 0.107 | `emotion_joy_top_ratio`, `emotion_diversity_entropy` |
| Star power | 0.101 | `director_past_avg_popularity` |
| Subtitle TF-IDF | 0.083 | `subtitle_tfidf_svd_01` |
| Plot embedding | 0.011 | `plot_sim_to_top_decile` |

**Key observations:**
- **Release timing (month/quarter)** is the single strongest predictor. Best interpreted as a proxy for studio confidence — studios place their high-expectation films in summer or holiday windows
- **Icarus-type emotional arc** (↗↘) ranks third in Model A. Reagan et al. found man_in_hole shapes dominant in *novels*; we find **Icarus more predictive for cultural footprint in films** — a potential independent finding for the paper
- **Emotional-diversity entropy** contributes meaningfully → films with a wide emotional range tend to stick in culture

### 4.5 Overfitting appeared

With 170 features over n=197, test R² improved but CV AUC dropped (Model A RF: 0.651 → 0.558). Mitigation candidate: mutual-information-based feature selection down to ~30 features.

---

## 5. Files changed on the `hiroaki` branch

### New scripts (8 files)
```
scripts/03_2_advanced_sentiment.py
scripts/03_3_emotional_arc.py
scripts/03_4_subtitle_tfidf.py
scripts/04_2_alt_cfi.py
scripts/05_2_alt_cfi_eval.py
scripts/07_youtube_trailer_collector.py    ← also added to main
scripts/08_star_power.py
scripts/10_plot_embedding.py
```

### Existing scripts modified (3 files, additive only)
```
scripts/03_1_subtitle_features.py          ← now persists _dialogue_lines
scripts/04_1_build_index.py                ← merges new sidecars + release-context features
scripts/05_1_ml_model.py                   ← expanded feature groups
```

### New data outputs
```
data/youtube_data.json                     ← 87/197 success (Day 1)
data/star_power.json                       ← 194/197 success
data/plot_embedding.json                   ← 194/197
data/subtitle_tfidf.csv (+terms.json)      ← 187 films
data/advanced_sentiment.csv (+json)        ← 187 films
data/emotional_arc.csv                     ← 187 films
data/pandora_full_dataset_real_alt_cfi.csv ← 197 × 194 columns (includes 3 CFIs)
data/alt_cfi_comparison.json               ← 3 CFI × Model A/B results
```

### Data quality fix (2026-04-23, lives on `main` already)

The day after the session, a routine inspection of the underperformer ranking revealed both *The Lion King (1994)* and *The Lion King (2019)* in the top 10 with `pure_culture` scores of 0 — clearly broken data. Investigation showed **20 films with silently failed Wikipedia / Wikiquote / OMDb lookups**, in two patterns:

1. Four films had a parenthetical year suffix in their CSV title (e.g. `"The Lion King (1994)"`) that broke every API search.
2. Sixteen films had `_(YYYY_film)` Wikipedia URLs that resolved to near-empty redirect pages, while the canonical article lived at the bare title — the original collector accepted the first 200-OK URL even when it returned 1 view per month.

Two fix scripts now live on `main`:
- `scripts/fix_disambiguation_titles.py` (4 films)
- `scripts/fix_wiki_views_bulk.py` (16 films, generalised — picks the candidate with the *highest* pageviews, not the first 200-OK)

Representative shifts after the fix:

| Film | wiki_views (before → after) | balanced score (before → after) |
|---|---|---|
| Pulp Fiction | 5 → 7,008,469 | 54.3 → **78.6** |
| Apollo 13 | 1 → 4,509,435 | — |
| Jurassic Park | 1 → 6,288,979 | — |
| The Lion King (1994) | 6 → 47,656 | 6.7 → **42.1** |
| Beauty and the Beast (1991) | 0 → 2,824,793 | 0 → **75.6** |

**New top-10 overperformers / underperformers after the fix** (CFI_balanced):
- **Pulp Fiction (1994) becomes the #1 overperformer** (residual +30.6) — the textbook Pandora Paradox case
- **Beauty and the Beast (1991) joins the top 10** at #4
- *Lion King 1994*, *Lion King 2019* and *Beauty and the Beast 2017* all drop off the underperformer list (the fix was the cause of their previous extreme negative residuals)
- New underperformers surface: *Batman v Superman: Dawn of Justice*, *Madagascar 2 / 3*, *The Croods* — illustrating a "sequel cultural decay" pattern (Madagascar 1 is #3 overperformer, Madagascar 2 and 3 are both underperformers)

**Caveat**: Pulp Fiction's #1 placement reflects its huge footprint in *Western* film culture. Our CFI is built entirely from English-language sources — strictly we measure "Western cultural footprint", not global penetration. For an ESADE (Spain) capstone targeting the Western blockbuster market this is intentional.

### Detailed documentation (on hiroaki branch)
```
docs/SESSION_2026-04-22.md / .ja.md        ← session-wide summary
docs/CFI_COMPARISON.md / .ja.md            ← 3-CFI experiment details
docs/DELIVERABLES.ja.md                    ← final-submission roadmap
```

---

## 6. Team discussion points

### 6.1 Should `hiroaki` be merged?

**Recommendation**: merge incrementally.

1. **Already merged to main**: `07_youtube_trailer_collector.py`
2. **Suggested for merge after review**: `08_star_power.py` (zero extra API cost, Model A safe, 194/197 success)
3. **Consider after review**: `03_2` / `03_3` / `03_4` (transformer-based, requires downloading ~500MB of models, real accuracy lift)
4. **Needs a team decision**: `04_2` / `05_2` and whether to promote `pure_culture` as the primary Y

### 6.2 Should we promote `pure_culture` to primary Y?

**Arguments for**:
- Closer to the "cultural footprint (not box office)" framing from the P262 brief
- Avoids the buzz-to-buzz circularity risk
- Matches our intuition about Avengers: Endgame vs Pulp Fiction (see §3)

**Concerns**:
- High CV variance (σ ≈ 0.4)
- Wikiquote / meme data carries editor-selection bias

### 6.3 Overfitting mitigation

Either keep all 170 features (and report it as a robustness check) or run feature selection to top 30 (recovers primary CV AUC). Team decision needed.

---

## 7. Next steps (what the team decides)

| # | Decision | Owners | Deadline |
|---|---|---|---|
| 1 | Phased merge plan for `hiroaki` | Whole team | Next meeting |
| 2 | Whether to promote `pure_culture` to primary Y | Francesco + Hiroaki | Same |
| 3 | Run feature selection? | Same | Same |
| 4 | Split of visualisation work (scatterplot / rankings / Avatar case) | Same | Same |

---

## 8. Notes

This summary is written for **a teammate reading `main` without checking out `hiroaki`**. For full details:
- Code: `git checkout hiroaki` or view on GitHub
- Session-wide findings: [hiroaki/docs/SESSION_2026-04-22.md](https://github.com/HiroakiNakano1985/capstone-pandora-paradox/blob/hiroaki/docs/SESSION_2026-04-22.md)
- CFI experiment details: [hiroaki/docs/CFI_COMPARISON.md](https://github.com/HiroakiNakano1985/capstone-pandora-paradox/blob/hiroaki/docs/CFI_COMPARISON.md)
- Final deliverables roadmap (JA): [hiroaki/docs/DELIVERABLES.ja.md](https://github.com/HiroakiNakano1985/capstone-pandora-paradox/blob/hiroaki/docs/DELIVERABLES.ja.md)
