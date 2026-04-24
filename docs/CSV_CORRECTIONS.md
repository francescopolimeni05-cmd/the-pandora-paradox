# `top200_movies.csv` Correction Log
**Author:** Hiroaki | **Last updated:** 2026-04-23 (Round-3 audit added)

This log records the corrections applied to the original `top200_movies.csv` (initial commit). All edits address **data quality bugs only** — no business judgement calls were involved (though a few mislabelled fields were realigned to canonical sources like Box Office Mojo / IMDb when the rename made the truth obvious).

Sample size after all corrections: **n = 194** (down from the original 197: 3 duplicate rows removed, 3 rows renamed plus minor field corrections, plus a Round-3 wiki audit that fixed 60 films' Wikipedia data without further CSV changes).

---

## 1. Row deletions (3)

### 1.1 Row 80 deleted: "DreamWorks Dragons 2" (2014)
- **Reason:** complete duplicate of row 92 "How to Train Your Dragon 2" (2014). Identical down to the dollar in worldwide gross ($618,876,695). Same year, same director, same studio.
- "DreamWorks Dragons" is a Netflix TV series, not a theatrical film. Likely a CSV-scraping artefact.
- Commits: hiroaki `c00162e` / main `99eb503`

### 1.2 Row 23 deleted: "Incredibles" (2004) — Round-3
- **Reason:** complete duplicate of "The Incredibles" (2004, originally row 53). Identical worldwide gross ($633,026,024), same director (Brad Bird).
- "Incredibles" (no article) is the same Pixar film; the canonical title is "The Incredibles". This duplicate's Wikipedia query went to a redirect page (langs=0) while the canonical "The Incredibles" entry got the proper langlinks (langs=74).
- Found during the Round-3 wiki_views ≤ 10,000 audit.
- Commits: hiroaki `20730eb` / main `196d4fe`

### 1.3 Row 74 deleted: "Frozen 2" (2019)
- **Reason:** complete duplicate of row 13 "Frozen II" (2019). Identical worldwide gross ($1,450,026,015). Same director, same studio.
- "Frozen II" (Roman numeral) is the official title; "Frozen 2" (Arabic numeral) is the same film.
- Both rows could not coexist because their API queries returned different downstream data — keeping them would have broken CFI normalisation.
- Kept the row whose API queries returned the correct OMDb data (Frozen II → IMDb rating 6.8, the canonical value); the deleted row's OMDb query had hit a different film entirely (rating 3.9).
- Commits: hiroaki `9c7a716` / main `e7fa3f7`

---

## 2. Title renames (3)

### 2.1 Row 103 renamed: "Illumination's Pets United" → "The Secret Life of Pets 2"
- **Reason:** the original title did not exist in TMDB, but the gross ($458M), year (2019), and studio (Illumination) matched The Secret Life of Pets 2.
- "Pets United" is a separate German Netflix release with negligible theatrical box office; it does not belong in a Top-200 box-office list.
- Likely a placeholder CSV title from when the canonical name wasn't yet known.
- **Additional field corrections (made canonical at the same time):**
  - Worldwide gross: $458,168,898 → **$431,118,094** (Box Office Mojo)
  - Budget: $75M → **$80M** (Box Office Mojo)
  - Director: Eric Darnell → **Chris Renaud** (the actual director)
  - Studio: Illumination (already correct)
- Re-collected every data source for the renamed film.
- Commits: hiroaki `c00162e` / main `99eb503`

### 2.2 Row 105 renamed: "Dr. Seuss' Horton Hears a Who!" → "Horton Hears a Who!"
- **Reason:** the **apostrophe + exclamation mark** in the title broke Wikipedia / Wikiquote / OMDb queries:
  - wiki_views = 722 (true value ~1.26 million)
  - wiki_langs = 0 (true value 49)
  - omdb wins/noms = 0/0 (true value 1/4)
  - wikiquote = not_found (true value 23 dialogue blocks)
- The canonical Wikipedia article is "Horton Hears a Who! (film)" — without the "Dr. Seuss'" prefix.
- **Additional field corrections (made canonical at the same time):**
  - Director: Steve Carell → **Jimmy Hayward** (Steve Carell was the voice actor, not the director)
  - Studio: Illumination → **Blue Sky Studios** (the actual production company)
- Re-collected every data source for the renamed film (all six sources now return correct data).
- Commits: hiroaki `9c7a716` / main `e7fa3f7`

### 2.3 Row 68 renamed: "The Sleeping Beauty" → "Sleeping Beauty"
- **Reason:** the leading "The" caused the Wikipedia API to follow a redirect to **Tchaikovsky's ballet** of the same name:
  - wiki_views = 2,683 (this was the ballet article's traffic — not the 1959 Disney film)
  - wiki_langs = 0
  - omdb rating = 6.2 (a different film entirely — true rating is 7.2)
- The canonical Wikipedia article for the 1959 Disney film is "Sleeping Beauty (1959 film)" without the article.
- All other metadata (director Clyde Geronimi, studio Disney, gross $170M, budget $4M) were already correct values for the 1959 Disney film, so **only the title was corrected**.
- Re-collection results:
  - wiki_views: 2,683 → **1,836,599**
  - wiki_langs: 0 → **79**
  - omdb wins: 0 → **3**
  - wikiquote: 0 → **14**
- Commits: hiroaki `e84969b` / main `d787f00`

---

## 3. Related data fixes triggered by CSV bugs

CSV title errors propagated into broken API responses, so several scripts were developed to detect and fix the resulting downstream data corruption (all under `scripts/`, present on both branches):

| Script | Role | Films affected |
|---|---|---|
| `fix_disambiguation_titles.py` | Re-fetch wiki/wikiquote/omdb for the four films with `(year)` in their CSV title (Lion King 1994/2019, Beauty and the Beast 1991/2017) | 4 |
| `fix_wiki_views_bulk.py` | Generalised pass for any film with wiki_views ≤ 100 (the disambiguated `_(YYYY_film)` URL was a near-empty redirect for many titles) | 16 |
| `fix_csv_errors.py` | Drop row 80 + rename row 103 + re-fetch the renamed film | 2 |
| `fix_csv_errors_round2.py` | Drop row 74 + rename row 105 + re-fetch Horton | 2 |

**Total: 24 films had data corrections of some kind.** Pre-fix CFI was distorted by zero / near-zero values for these films; post-fix, the data is canonical.

---

## 4. Effect on rankings (top-10 underperformers)

### Before all corrections
1. DreamWorks Dragons 2 (later **deleted as duplicate**)
2. Illumination's Pets United (later **renamed**)
3. **The Lion King (1994)** ← removed by data fix
4. **The Lion King (2019)** ← removed by data fix
5. **Beauty and the Beast (2017)** ← removed by data fix
6. The Mummy: Tomb of the Dragon Emperor
7. Dr. Seuss' Horton Hears a Who! (later **renamed**)
8. How to Train Your Dragon 3
9. Ant-Man and the Wasp: Quantumania
10. Frozen 2 (later **deleted as duplicate**)

### After all corrections
1. How to Train Your Dragon 3 (2019)
2. Madagascar 3 (2012)
3. The Croods (2013)
4. Frozen II (2019) ← only Frozen 2 entry now
5. Madagascar 2 (2008)
6. Toy Story 4 (2019)
7. Thor: The Dark World (2013)
8. **Batman v Superman: Dawn of Justice** — a genuine cultural underperformer
9. The Lion King (1994) — now correctly mid-table
10. (next entry)

Pre-fix the underperformer list was contaminated by films whose data had simply failed to collect; post-fix the list reflects **genuine cultural underperformance** (sequel fatigue + the DC universe's critically-failed entries).

---

## 4b. Round-3 audit: wiki_views ≤ 10,000 sweep (2026-04-23)

The Round-1/2 fixes left a remaining risk noted in §5: many films had wiki_views in the 100–10,000 range because the original collector picked the disambiguated `Foo_(YYYY_film)` URL, which is a redirect to the canonical article. The pageviews API does NOT follow redirects, so the disambiguator's tiny direct-hit traffic was attributed instead of the real traffic on the canonical article.

A 46-film audit (`scripts/audit_low_wiki_views.py`) found 45 films at risk. Round-3 + 3b applied a **redirect-resolution** fix using the MediaWiki `?redirects=true` query: for each suspect film, follow Wikipedia's own redirect chain to find the canonical article, then refetch pageviews + langlinks from that title.

### Round-3 (`fix_csv_errors_round3.py`) — wiki_views ≤ 10,000
- Dropped duplicate row "Incredibles" (2004) from `top200_movies.csv` and all `data/*.json/*.csv` (kept "The Incredibles" as canonical).
- Re-fetched pageviews + langs for **43 films**; 2 skipped (Aladdin, Thor) because the canonical resolution would have regressed langlinks.

### Round-3b (`fix_csv_errors_round3b.py`) — wiki_langs ≤ 5
A second pass caught films above the views threshold that nonetheless had broken langlinks (langs ≤ 5 despite being well-known films). Same redirect-resolution logic, but only updates pageviews when the canonical title's views are within 50% of the existing value (so we don't trade good views for fewer views).
- Fixed **15 additional films**: Avengers (2012) langs 0→84, Snow White (1937) langs 0→113, Mulan (1998) langs 0→77, Lion King (1994) views 47K → 5.9M and langs 1→114, Lion King (2019) langs 1→56, Oppenheimer (2023) views 15K → 51.5M, Rogue One views 165K → 4.4M, etc.

### Round-3 manual patches
Two films needed manual canonical-title resolution because the automated fix would have made things worse:
- **Sing (2016)**: canonical resolution went to `Sing_(disambiguation)` instead of the actual film article. Patched to `Sing_(2016_American_film)` (views 4828 → 2,275,929; langs 0 → 54).
- **Trolls (2016)**: canonical resolution went to `Troll` (mythological creature) instead of the film. Patched to `Trolls_(film)` (views 31,742 → 2,037,555; langs 0 → 41).
- **Aladdin (1992)**: canonical resolution would have followed `Aladdin_(1992_film)` → `Aladdin_(disambiguation)` (langs 37, lower than the existing 61 — Round-3 correctly skipped this). Patched manually to `Aladdin_(1992_Disney_film)` (views 7758 → 2,698,063; langs 61 → 95).

### Round-3 effect on rankings (top 10 after all rounds)
**Underperformers** (post Round-3):
1. Batman v Superman: Dawn of Justice (2016)
2. How to Train Your Dragon 3 (2019)
3. The Croods: A New Age (2020)
4. Ice Age: Dawn of the Dinosaurs (2009)
5. Madagascar 2 (2008)
6. 101 Dalmatians (1961)
7. Transformers (2007)
8. Thor (2011)
9. Star Wars: The Force Awakens (2015)
10. Trolls (2016)

**Overperformers** (post Round-3):
1. Titanic (1997) — cfi=100
2. Pulp Fiction (1994)
3. **Oppenheimer (2023)** ← surfaced after fix (was hidden behind broken wiki data)
4. Dune (2021)
5. Madagascar (2005)
6. Toy Story (1995) — moved up after wiki views fix
7. Avengers: Age of Ultron (2015)
8. Inglourious Basterds (2009)
9. Batman Begins (2005)
10. The Incredibles (2004) — moved up after dedup + wiki views fix

ML model B (with early reception) on `buzz` CFI now achieves test AUC = 0.859, CV AUC = 0.718 ± 0.094 — meaningful improvement over pre-Round-3 levels.

---

## 5. Known remaining risks

The Round-3 audit closed the most material risk. Lingering possibilities:

- **Films with wiki_views ≤ 10,000** — addressed by Round-3 (was the main remaining risk).
- **Titles containing non-ASCII characters** (none in the current dataset, but worth flagging if expanded)
- **Films released 2024–2025** (low wiki_views may be normal due to article-creation lag rather than a data bug — exclude from naive thresholds)

---

## 6. Audit log — full list of correction commits

| Correction | hiroaki commit | main commit |
|---|---|---|
| Disambiguation 4 films | `99cf85c` (subset) | `0a3f89b` |
| Bulk wiki_views fix (16 films) | `56dc99a` | `85fdc41` |
| Row 80 deleted + row 103 renamed + Pets 2 fetched | `c00162e` | `99eb503` |
| Pets 2 Reddit refetch | `c71cb68` | `31bab79` |
| Row 74 deleted + row 105 renamed + Horton fetched | `9c7a716` | `e7fa3f7` |
| Row 68 renamed + Sleeping Beauty fetched | `e84969b` | `d787f00` |
| Round-3: drop Incredibles dup + 43 wiki redirect-resolves | `20730eb` | `196d4fe` |
| Round-3b: 15 langs ≤ 5 redirect-resolves | (same commit) | (same commit) |
| Round-3 manual: Sing / Trolls / Aladdin canonical patches | (same commit) | (same commit) |

Each commit message records the specific edits, before/after numbers, and downstream effects. Use `git log --oneline data/top200_movies.csv` to follow the history.
