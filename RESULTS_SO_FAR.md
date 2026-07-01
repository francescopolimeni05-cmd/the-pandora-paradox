# Pandora Paradox, analysis progress (offline phase)

## Dataset
`data/pandora_full_dataset_expanded.csv`, **350 films** (194 originals + 156 cult /
flop / low-budget / arthouse). Reddit discussion volume (SerpAPI) joined for 350/350.
Modelling table with all derived variables: `data/analysis_dataset.csv`.

## 1. Symbolic Compressibility Index (SCI), built
From three *pre-release, script-intrinsic* signals, made scale-free:
`short_punchy_density`, `sentiment_spike`, and **proper-noun density per 1,000 words**
(the raw count was contaminated by script length / blockbuster scale, fixed).
- Two versions: `SCI_z` (equal-weight z-scores) and `SCI_pca` (PC1, 48% variance).
  They correlate 0.99 → robust to construction choice.
- 27 films with failed/degenerate subtitle parsing excluded (treated as missing,
  not as low-compressibility).

## 2. CFI decomposed into 4 dimensions, done
Attention persistence · Participatory engagement · Institutional legitimation ·
Symbolic reuse. Built both ways (theoretical z-score indices + exploratory factor
analysis). EFA recovers a sensible 4-factor structure (awards+critics together;
Reddit volume alone; Wikipedia/memes/quotes cluster).

## 3. Headline finding
Testing SCI against the **aggregate** CFI → null (β≈0, p≈0.36). But the supervisor
predicted SCI should hit specific dimensions. Decomposing and testing SCI against
each dimension, **controlling for log box office**:

| Dimension | SCI β | p |
|---|---|---|
| **Symbolic reuse** | **+0.126** | **0.030** |
| Participatory engagement | +0.027 | 0.69 |
| Attention persistence | +0.041 | 0.39 |
| Institutional legitimation | −0.140 | 0.055 |

→ Symbolic compressibility **selectively** drives symbolic reuse and is, if anything,
*negatively* associated with institutional recognition, the dimension-specific
pattern the mechanism implies. This is the core result to build the paper around.

## Caveats / open items
- **Wikipedia attention is still under-counted for ~52 films** (the "(YYYY film)"
  redirect bug, affects Inception, Interstellar, etc.). The attention dimension
  will sharpen after `fix_wiki_views_bulk.py --threshold 200000` is run. Symbolic-
  reuse result does not depend on it.
- Results so far are **partial correlations** (controlling for box office), i.e.
  associational. The causal step is next.

## 4. Causal identification (scripts/23_causal.py), done, and HONEST
Outcome = symbolic reuse. All three strategies run:
- **Temporal** (SCI fixed at release; pre-release controls + genre FE): SCI β=+0.075,
  p=0.23. Persistence test (late- vs early-window Wikipedia): null (p=0.56).
- **IV / 2SLS** (instrument = leave-one-out genre means of dialogue structure):
  first-stage F≈12.9 (acceptable instrument), but 2SLS SCI β=+0.355, p=0.23, right
  sign, too imprecise to conclude.
- **Trailer-timing** (SCI × low early exposure): interaction not significant (p=0.62).

**Interpretation (important).** The simple SCI→symbolic-reuse result (p=0.03) does
NOT survive genre fixed effects or the causal designs. A large share of the apparent
effect is **genre composition** (action/sci-fi films have both high SCI and high
meme/quote reuse). With the current SCI we cannot make a strong causal claim. This
is a valid result, and the most likely fix is the construct, not the design: SCI as
built partly measures action/spectacle, not quotability.

## 5. Empirical (validated) SCI, the decisive test (scripts/24_build_sci_empirical.py)
We let the data choose: cross-validated models predicting *realized* quotability
(Wikiquote) and meme reuse from 16 script-intrinsic features (out-of-sample, so no
circularity). Result, robust across model classes:

| Model | predict realized quotability | predict meme reuse |
|---|---|---|
| ElasticNet (linear) | OOS R² = −0.02 |, |
| Random Forest | −0.03 | +0.08 |
| Gradient Boosting | −0.21 | +0.04 |

→ **Script-text features carry essentially no out-of-sample signal about which films
become quotable / memetic.** The "most compressible" films the model picks are
animated kids' films (Ice Age, Minions); famously quotable ones (Big Lebowski,
Trainspotting) rank lowest. On held-out outcomes (Reddit volume, attention), SCI_emp
is null-to-negative. For comparison, exposure + genre alone explain R²=0.16 of
quotability, i.e., box office and genre predict it better than anything in the script.

## CONCLUSION (honest, robust)
Symbolic compressibility, **as measurable from script/subtitle text**, does NOT
explain cultural persistence. Tested three ways, a-priori SCI, validated empirical
SCI, and three causal designs, the mechanism does not survive controls for genre and
exposure. The box-office ↔ cultural-footprint divergence is **real descriptively** but
is **not driven by script-level compressibility**. What makes films culturally
persistent likely lies beyond the text, performance/delivery, specific iconic
audiovisual moments, casting, cultural timing, fandom dynamics, none of which are
captured by dialogue-structure metrics.

This is a well-identified null and a legitimate capstone contribution: a rich 350-film
dataset across the full success spectrum, a formalized mechanism + 4-dimension CFI, and
a rigorous test that the mechanism, given its best empirical shot, is not supported.

**Recommended: discuss this finding with Carlos before writing.** Options: (a) report
the null rigorously and reframe the contribution around the paradox + the negative
result; (b) pivot the mechanism toward non-text signals (e.g., audiovisual "iconic
moment" features, casting/star power, release-timing) if feasible.
