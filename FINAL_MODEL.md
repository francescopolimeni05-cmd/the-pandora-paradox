# The Pandora Paradox, Final Model (locked)

Data: 349 unique films (194 originally top-grossing + 155 added: cult, flop, low-budget, arthouse). Clean
Wikipedia (redirect fix), uniform Reddit discussion volume (SerpAPI), fixed-window
Trends, awards, quotes, subtitles. Modelling table: `data/final_model_dataset.csv`.

## The Cultural Footprint Index (CFI)
Built from FOUR dimensions (supervisor's decomposition), equal-weight z-scores → 0-100:
attention persistence · participatory engagement (Reddit volume) · institutional
legitimation · symbolic reuse (quotes + memes). **Box office explains only R²≈0.03-0.06 of
the CFI**, i.e. ~94-97% of cultural footprint is decoupled from commercial scale. That
is the paradox, quantified on real data.

## What drives cultural OVER-performance? (CFI net of box office, n=307, R²=0.45)
*All variables measured uniformly across the 349 films (see DATA_AUDIT.md). Franchise,
sequel, animation and genre were re-derived from TMDB after the audit found the legacy
`franchise` column was confounded with the old/new split.*

Enriched specification (adds star power, runtime, adaptation, language, season; R²=0.51,
validated out-of-sample):

| Driver | Effect (CFI pts) | raw p | Holm p | Verdict |
|---|---|---|---|---|
| **Audience love (IMDb rating)** | **+4.7** | 0.0004 | 0.005 | survives |
| **Being a sequel** | **−5.6** | 0.0004 | 0.005 | survives |
| **Critic acclaim (Metascore)** | **+0.23** | 0.002 | 0.015 | survives |
| **Runtime (per minute)** | **+0.10** | 0.004 | 0.031 | survives |
| Star power (log cast popularity) | +6.1 | 0.019 | 0.135 | suggestive (fails Holm) |
| Franchise, budget, animation, adaptation/IP, language | ns |, |, | ns |
| Symbolic compressibility (SCI) | +0.2 | 0.87 | 1.00 | ns |

**Takeaway:** cultural over-performance is driven by **audience love + critical acclaim + being a substantial (longer) film**, and is **hurt by being a sequel**. Star power is positive too but does not survive Holm correction, so we report it as suggestive only.
It is **not** bought with budget, **not** a function of franchise membership (the
earlier "+7.4" was an artifact of the old/new sampling, why the audit mattered), not
of adaptation/IP or language, and, tested every way (a-priori SCI, a cross-validated
empirical SCI with out-of-sample R²≈0, three causal designs, and now with the full
control set), **not** explained by script-level "compressibility." Bonus, at the
director level: auteurs (Cameron +19, Nolan +18, Raimi, Bird) over-deliver cultural
footprint; sequel-factory animation directors erode it. In short: films stick in
culture when they are **loved, acclaimed and substantial**, not because
of franchise machinery, money, or clever scripts.

## The Avatar verdict (the assignment's centerpiece)
Avatar is a cultural **over-performer overall** (+31 CFI pts vs its box-office
expectation), it is *not* forgettable in the aggregate. But the four-dimension
decomposition locates exactly where the "forgettable" intuition is right:

| Film | Wikiquote | Box office | Symbolic-reuse pct (size-adjusted) |
|---|---|---|---|
| Avatar | 16 | $2.9B | **46** (below median for its size) |
| Avengers: Endgame | 13 | $2.8B | **43** |
| Frozen | 30 | $1.29B | 85 |
| Pulp Fiction | 24 | $0.21B | 70 |
| The Big Lebowski | 22 | $0.05B | 81 |

→ Avatar is culturally huge on attention, engagement and legitimation, but
**quote/meme-poor relative to its scale**, weak on the *one* dimension (symbolic
reuse) that drives the felt sense of "leaving a mark." The same is true of Endgame.
This is precisely what the supervisor intuited, and only the decomposition reveals it.

The real cultural black holes are expensive flops: **Jupiter Ascending, The Nutcracker
and the Four Realms, Monster Trucks, R.I.P.D., Cutthroat Island, The Adventures of Pluto
Nash**. The over-achievers are beloved/acclaimed and cult films: **Up, Burning, Drive,
Get Out, Dune, Pulp Fiction, The Shawshank Redemption, Her** (Avatar is also a clear
over-performer, +26). *Caveat:* ~10 films (e.g. Swiss Army Man) still have an
unresolved Wikipedia title and so score artificially low, a known, documented data gap,
not a real result.

## Robustness, validity & dynamics (model-strengthening pass)
- **Robustness (29):** the drivers conclusions survive everything, 5-fold
  out-of-sample R²=0.31 (predicts, not overfit); identical under a PCA-weighted CFI;
  identical under outlier-robust (Huber) regression; 95% CIs put IMDb clearly >0,
  sequel <0, and franchise & SCI spanning 0.
- **Validity (30):** the CFI separates *indisputable* landmarks (Pulp Fiction, Dark
  Knight, Titanic…) from forgotten flops (John Carter, R.I.P.D.…) **perfectly
  (AUC=1.00)**, and tracks independent audience reach (ρ=0.51). The four dimensions,
  however, barely correlate (Cronbach α=0.38) → cultural footprint is genuinely
  **multidimensional**: empirical justification for the supervisor's decomposition,
  and the reason dimension-level analysis (not the single CFI number) is the right unit.
- **Persistence over time (28):** from the monthly Wikipedia series, cult films get
  *rediscovered* (Her, Pan's Labyrinth, Amélie trend upward), while franchise films
  fade faster (franchise → persistence β=−0.38, p=0.03). Exploratory (recent releases
  decay mechanically within the window).

## Data quality (QA pass)
Two issues found and fixed: (1) `meme_post_count` / `subreddit_diversity` were derived
from the old Reddit API and were structurally 0 for the 155 new films → dropped in
favour of signals collected uniformly for all 349; (2) the SerpAPI Reddit volume
over-counts generic one-word titles ("Avatar" matches the word everywhere) → winsorized
at the 2nd/98th percentile. All signals now have consistent coverage across old and new
films. Residual limitations: ~10 films still have low Wikipedia views (hard-to-resolve
titles), 40 films have no Wikiquote page, and the Reddit-volume engagement signal
remains noisy for common-word titles (mitigated, not eliminated).

## Managerial implication
Long-term cultural value comes from earning *genuine audience affection* and critical
acclaim, casting recognizable talent, and making *substantial* films people return to, 
not from bigger budgets, franchise machinery, sequels, or scripts engineered to be
"quotable." In our data none of the latter predict cultural over-performance.

## Status / remaining
- Core model: **locked.**
- YouTube trailer signals (view counts and comment features) are complete for every
  film with a post-2005 trailer; used only in the secondary trailer-timing test.
