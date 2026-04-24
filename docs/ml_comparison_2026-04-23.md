# ML Results — 3-Way Comparison (2026-04-23)

Side-by-side comparison of the model results JSON (`data/model_results_real.json`) across three branch states:

| Column | What it is | Source |
|---|---|---|
| **main (before)** | `main` at commit `23df41a`, pre-integration | `git show 23df41a:data/model_results_real.json` |
| **midterm-submission** | `origin/midterm-submission`, commit `91afa6a` | `c:/tmp/pandora-midterm-submission/data/model_results_real.json` (worktree) |
| **main (after)** | `main` at commit `8c7898a`, post-integration | current `data/model_results_real.json` |

All three runs use n = 194 films. The **after** column is what is on `main` right now.

---

## 0. What changed between the three columns (reading order)

* **before → midterm-submission** — the `midterm-submission` branch was cut from an earlier state of the dataset, *before* the Round-2 / Round-3 data-quality audits landed on `main`. Same n = 194, but:
  * The branch is missing the Round-2 title renames (Horton / Sleeping Beauty / Pets 2) and the Round-3 wiki-redirect fix (60 films) that `main` applied. **Important: these audits were corrections to the original data that I had collected — the root cause is that my initial collection pass (`top200_movies.csv`, `live_api_data.json`) had several latent bugs (punctuation-breaking titles, a misrouting Wikipedia redirect on `Sleeping Beauty`, a mislabelled film row, and disambiguated URL traps that the pageviews API does not follow).** I only found and fixed those bugs on `main` over 2026-04-22/23. The `midterm-submission` branch was cut before the fixes landed, so it inherits the broken originals — that is on me, not on the branch.
  * Concrete symptom of the above: on `midterm-submission`, **wiki_views is degraded for ~60 films** (e.g. Inside Out 2 = 1 view, Jurassic Park = 1 view, Pulp Fiction = 5). Same root cause as above.
  * The branch has near-full Google Trends coverage via SerpAPI (188/190 shared, 99 %); `main` had 13/194 (7 %) from a rate-limited `pytrends` run.
  * YouTube schema is different: the branch has absolute `yt_top_views` / `yt_total_views_top3` / `yt_top_likes`; `main` has studio-decision `yt_trailer_count` / `yt_upload_lead_days` + Day-7/30 comments.
  * The branch drops `reddit_posts` and renames `wikiquote_count` → `wikiquote_page_size`.
* **before → after** — the `midterm-submission` branch's SerpAPI Trends data was merged into `main`'s `live_api_data.json` / `extended_api_data.json` (coverage 7 % → 98 %), the branch's YouTube-views collector was added as a new input to `04_1_build_index.py`, and the 4 new view-count columns added to `YOUTUBE_EARLY_FEATURES` in `05_1_ml_model.py`. `main`'s Round-2/3 wiki fixes and existing Day-7/30 columns were **preserved**.

---

## 1. IMPORTANT caveat before reading any number

**`n_positive` (overperformers) is different in every column**: 95 / 113 / 97. Why it matters:

The classification target is `is_overperformer = (cfi_residual > 0).astype(int)` where `cfi_residual = cfi_score − cfi_predicted_from_log_gross_log_budget`. The sign of `cfi_residual` depends entirely on the CFI components — Wikipedia views, Reddit, TMDB votes, Google Trends, awards, quotes, memes. When those inputs change (`midterm-submission` has broken wiki + real Trends; `main-after` has fixed wiki + real Trends), **`cfi_score` moves, `cfi_residual` moves, and which films cross zero moves**.

So a direct column-to-column AUC comparison is noisy: the models are solving slightly different binary problems. Use the CV AUC (more stable) and look at direction of movement, not absolute deltas.

---

## 2. Regression — predict `cfi_score` (0–100)

| Model | Metric | main (before) | midterm-submission | main (after) |
|---|---|---:|---:|---:|
| A (pre-release) | test R² | −0.133 | −0.552 | **−0.302** |
| A (pre-release) | test RMSE | 18.78 | 19.51 | 20.94 |
| A (pre-release) | CV R² | −0.932 ± 0.521 | **−0.319 ± 0.131** | −0.872 ± 0.813 |
| B (+ early reception) | test R² | **+0.101** | −0.323 | −0.218 |
| B (+ early reception) | test RMSE | 16.72 | 18.01 | 20.26 |
| B (+ early reception) | CV R² | −0.193 ± 0.477 | **−0.037 ± 0.113** | −0.182 ± 0.440 |

**Read-out**: Regression R² on `cfi_score` remains negative-to-near-zero across all three columns — the Pandora-Paradox finding that production-side features don't predict CFI magnitude is **robust to the data changes**. The `midterm-submission` CV R² looks less negative, but that's partly because the broken Wiki signal (inherited from the pre-audit state of my original data collection) collapses the CFI variance on that branch — smaller residual-variance denominator ⇒ R² less punitive of a mean-predictor.

---

## 3. Classification — `is_overperformer ∈ {0,1}`

### Model A (strict pre-release)

| Algorithm | Metric | main (before) | midterm-submission | main (after) |
|---|---|---:|---:|---:|
| XGBoost | test AUC | 0.424 | 0.568 | 0.497 |
| XGBoost | CV AUC | 0.326 ± 0.050 | 0.545 ± 0.073 | 0.341 ± 0.050 |
| RandomForest | test AUC | 0.418 | 0.698 | 0.576 |
| RandomForest | CV AUC | 0.374 ± 0.077 | **0.625 ± 0.038** | 0.390 ± 0.037 |
| LogReg | test AUC | 0.595 | 0.641 | **0.742** |
| LogReg | CV AUC | 0.498 ± 0.065 | 0.594 ± 0.076 | 0.503 ± 0.070 |
| Best model (by test AUC) | — | LogReg | RandomForest | LogReg |

### Model B (pre-release + early reception)

| Algorithm | Metric | main (before) | midterm-submission | main (after) |
|---|---|---:|---:|---:|
| XGBoost | test AUC | 0.684 | 0.622 | **0.821** |
| XGBoost | CV AUC | 0.554 ± 0.075 | 0.661 ± 0.074 | 0.580 ± 0.053 |
| RandomForest | test AUC | 0.700 | 0.720 | 0.795 |
| RandomForest | CV AUC | 0.603 ± 0.039 | **0.737 ± 0.033** | 0.631 ± 0.055 |
| LogReg | test AUC | 0.766 | 0.630 | 0.745 |
| LogReg | CV AUC | 0.637 ± 0.043 | 0.641 ± 0.083 | **0.668 ± 0.050** |
| Best model (by test AUC) | — | LogReg | RandomForest | XGBoost |

**Read-out**:
- **Model A**: `main-after` is the only column where LogReg test AUC clears 0.70 (0.742). CV AUC only moves +0.005 vs. before — most of the test-AUC gain is variance from the 80/20 split with a slightly different target. The `midterm-submission` RandomForest CV (0.625) beats `main-after`'s RF CV (0.390), but that's target-dependent — its `n_positive` is 113 (58 % of n), a more-balanced problem than `main-after`'s 97 (50 % of n), which makes RF's bagging easier to hit. The `n_positive = 113` itself is an artefact of the broken Wiki data (from the pre-audit version of my original collection) compressing `cfi_score` toward a skewed residual distribution.
- **Model B**: `main-after` improves the LogReg CV AUC to 0.668 ± 0.050 (vs. 0.637 before), which is the cleanest apples-to-apples move — same algorithm, only the feature set and target changed. `main-after`'s XGBoost test AUC hits 0.821 (new best), though CV drops to 0.580 (variance warning). The `midterm-submission` RF CV AUC of 0.737 is the headline number on that branch, but its `cfi_score` is being computed against the **pre-audit version of the data I had originally collected** (broken Wikipedia redirects + unfixed title typos), so the target itself is distorted — *this number is not comparable like-for-like with the other two columns*.

---

## 4. `n_positive` and target schema

| | main (before) | midterm-submission | main (after) |
|---|---:|---:|---:|
| `n_total` | 194 | 194 | 194 |
| `n_positive` (overperformers) | 95 (49 %) | **113 (58 %)** | 97 (50 %) |
| CFI weighting | extended | extended | extended |
| `cultural_category` — Strong Overperformer | 37 | 25 | 42 |
| `cultural_category` — Overperformer | 38 | 61 | 35 |
| `cultural_category` — As Expected | 43 | 48 | 35 |
| `cultural_category` — Underperformer | 39 | 30 | 38 |
| `cultural_category` — Strong Underperformer | 37 | 30 | 44 |

The `midterm-submission` distribution is skewed toward the middle two buckets (86 Over + As Expected) vs. `main`'s more bimodal split. Direct cause: broken Wiki signal (inherited from my original pre-audit collection) ⇒ compressed `cfi_score` range ⇒ more films clustered near the residual boundary.

---

## 5. Feature set per model (what's actually in X)

| Feature group | before | midterm-submission | after | Notes |
|---|:-:|:-:|:-:|---|
| Metadata (7) | ✅ | ✅ | ✅ | `budget`, `is_sequel`, `is_animated`, `has_franchise`, `genre_encoded`, `year`, `years_since_release` |
| Subtitle NLP (19) | ✅ | ✅ | ✅ | same across |
| `yt_trailer_count`, `yt_upload_lead_days` (Model A) | ✅ | ❌ | ✅ | `midterm-submission` has no studio-side YT |
| `yt_comments_day_7/30/velocity` (Model B) | ✅ | ❌ | ✅ | `midterm-submission` has no Day-7/30 |
| `yt_top_views`, `yt_total_views_top3`, `yt_top_likes`, `yt_top_comments_total` (Model B) | ❌ | ✅ (diff names) | ✅ | `midterm-submission` uses: `yt_top_views`, `yt_total_views_top3`, `yt_top_likes`, `yt_top_comments` |
| `tmdb_vote_average`, `tmdb_popularity`, `imdb_rating`, `metascore` (Model B) | ✅ | ✅ | ✅ | same across |
| **Features used — Model A** | 28 | 27 | 28 | |
| **Features used — Model B** | 35 | 36 | **39** | `main-after` = superset (both YT approaches) |

---

## 6. Coverage deltas of key CFI inputs

| Feature | main (before) | midterm-submission | main (after) |
|---|---:|---:|---:|
| `gtrends_avg_interest` | 13/194 (7 %) | **188/190 (99 %)** on shared | **190/194 (98 %)** |
| `yt_trailer_count` | 161/194 (83 %) | — | 161/194 (83 %) |
| `yt_comments_day_7/30` | 42/194 (22 %) | — | 30/194 (15 %) — dup-removed |
| `yt_top_views` | — | 190/190 (100 %) on shared | **192/194 (99 %)** |
| `yt_top_likes` | — | 188/190 (99 %) on shared | 190/194 (98 %) |
| Wiki views (≥ canonical value) | 194/194 (100 %) | **≤ 50 views for ~60 films** (broken) | 194/194 (100 %) |
| `wiki_languages` (non-zero) | 194/194 | 119/194 (missing 75 films) | 194/194 |

The "broken" Wiki numbers on the `midterm-submission` column are **inherited from my original data collection** (done before the Round-2/3 audits). They are not a consequence of how the `midterm-submission` branch was built; that branch simply inherited the data I had collected.

---

## 7. Top-5 features (regression importance)

| Rank | main (before) — Model A | midterm-submission — Model A | main (after) — Model A |
|:-:|---|---|---|
| 1 | `short_punchy_count` 0.167 | `genre_encoded` 0.089 | `short_punchy_count` 0.161 |
| 2 | `rare_proper_noun_count` 0.097 | `rare_proper_noun_count` 0.084 | `sentiment_spike` 0.088 |
| 3 | `humor_indicator` 0.068 | `violence_indicator` 0.074 | `rare_proper_noun_count` 0.075 |
| 4 | `vocabulary_richness` 0.055 | `exclamation_ratio` 0.072 | `short_punchy_density` 0.057 |
| 5 | `violence_indicator` 0.045 | `vocabulary_richness` 0.072 | `humor_indicator` 0.057 |

Main's Model A is dominated by the same meme-template / invented-name script proxies in both before and after. The `midterm-submission` Model A has flatter importance — no single feature clears 0.09 — consistent with the broken Wiki signal (from my original pre-audit collection) compressing the Y variance.

| Rank | main (before) — Model B | midterm-submission — Model B | main (after) — Model B |
|:-:|---|---|---|
| 1 | `tmdb_popularity` 0.206 | `imdb_rating` 0.187 | `tmdb_popularity` **0.273** |
| 2 | `imdb_rating` 0.143 | `tmdb_popularity` 0.106 | `metascore` 0.063 |
| 3 | `tmdb_vote_average` 0.086 | `yt_top_comments` 0.083 | `imdb_rating` 0.061 |
| 4 | `rare_proper_noun_count` 0.047 | `metascore` 0.073 | **`yt_comments_day_7` 0.060** |
| 5 | `vocabulary_richness` 0.047 | `rare_proper_noun_count` 0.057 | `tmdb_vote_average` 0.057 |

`main-after`'s Model B: `tmdb_popularity` concentrates further (0.206 → 0.273 — more leverage because the target is cleaner?), and **`yt_comments_day_7`** (main's Day-7 count signal) enters the top 5 — despite only 30/194 coverage, the signal among the 30 is strong enough for the tree-based regressor to reach for it. The `midterm-submission` equivalent `yt_top_comments` (view-side total) is top-3 on that branch, confirming YouTube comment volume carries signal regardless of which aggregation you pick.

---

## 8. Bottom line

1. **The `midterm-submission` branch's SerpAPI Trends collector is the single most valuable addition.** Adopting it lifts Trends coverage 7 % → 98 % on `main`. It improves the Y-side (it's a CFI component) rather than giving the X-side a new feature, so the visible impact is more subtle than an AUC jump — but the CFI residual target is now computed from signal that's actually there, not from a 7 %-sparse column.
2. **The branch's YouTube-views collector adds to Model B's early-reception side** — near-complete coverage where the existing Day-7/30 columns were only 22 % reachable. Model B LogReg CV AUC moves **0.637 → 0.668** on this input change.
3. **The `midterm-submission` classification numbers (e.g. RF CV AUC 0.737) are NOT directly usable as a benchmark for `main`** — *not because of anything that branch did wrong*. It was cut off the pre-audit version of the dataset that I had originally collected, and that collection had ~60 films with broken Wikipedia signal (misrouting redirects, punctuation-breaking titles, a mislabelled film row). Those bugs are on me, and they were only fixed on `main` during the 2026-04-22/23 audits, after the `midterm-submission` branch had already been cut. So the `cfi_score` / `cfi_residual` / `is_overperformer` on that branch are computed against a degraded Y. The Y-construction on `main` (post Round-2/3 fix + SerpAPI Trends) is the correct one to report against.
4. **Model A stays at ≈ chance on CV AUC** in every column. The Pandora-Paradox core finding — production-side data does not pre-determine cultural footprint — survives every data-quality permutation we've tried.
5. Residual-as-target probe (see §4.5 of the 2026-04-23 meeting brief) is a cleaner way to report the research result than `cfi_score`-as-target; worth re-running on `main-after` before the paper.
