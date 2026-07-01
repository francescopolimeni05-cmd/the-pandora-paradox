# Data consistency audit, old (194) vs new (155) films

Goal: every variable used in the model must be measured the SAME way for all 349
films. We audited each column for old-vs-new coverage and harmonised everything that
was collected differently.

## Inconsistencies found and how they are resolved
| Variable | Problem (old vs new) | Resolution |
|---|---|---|
| `franchise` | populated for **every** old film (even standalones), **empty** for every new film → perfectly confounded with the old/new split | **Re-derived** from TMDB `belongs_to_collection` → `in_franchise` (uniform) |
| `is_sequel` | hard-coded **False** for all new films (Blade Runner 2049 = "not a sequel") | **Re-derived** from TMDB collection release-order → `sequel_number` |
| `is_animated` | old from Wikipedia, new from TMDB | **Re-derived** uniformly from TMDB genres |
| `genre` | label mismatch: old "Sci-Fi" vs new "Science Fiction" (same thing, two taxonomies) → broke every `C(genre)` control | **Re-derived** from TMDB primary genre (uniform) |
| `wiki_languages` | 0 for ~74 refetched films (the title fix updated views but not language counts) | **Dropped** from the attention dimension |
| `reddit_posts/upvotes/comments`, `meme_post_count`, `subreddit_diversity` | from the old Reddit API → ~0 for all new films | **Dropped**; replaced by `reddit_serp_volume` (SerpAPI, uniform, winsorised) |
| `yt_*` trailer features | YouTube quota → present for 83% old, 23% new | used only in the secondary trailer-timing test; backfilled after the quota reset, now complete |
| `domestic_gross` | TMDB has none → missing for new | not used in the model (we use worldwide gross) |

## Duplicate / matching checks
- **1 true duplicate removed:** the 2019 film entered twice, as "X-Men: Dark Phoenix"
  (top-200) and "Dark Phoenix" (expansion), same TMDB id 320288. Dropped the expansion
  copy; the dataset is now **349 unique films**. Re-running the model without it left all
  results unchanged (robustness confirmed).
- *Beauty and the Beast* (1991/2017) and *The Lion King* (1994/2019) are kept, they are
  genuinely different films (remakes), not duplicates.
- **Known minor error:** *How to Train Your Dragon 3* (2019) was matched to the TMDB id
  of *HTTYD 2* (82702), so its box-office/financials are the sequel's. Affects one film;
  flagged for a targeted re-fetch.

## Variables confirmed UNIFORM (no action needed)
`worldwide_gross`, `budget`, `imdb_rating`, `metascore`, `omdb_total_wins/nominations`,
`tmdb_vote_count`, `wiki_total_views` (after the redirect fix), `gtrends_avg_interest`,
`reddit_serp_volume`, `wikiquote_count`, and all subtitle/SCI inputs
(`short_punchy_density`, `sentiment_spike`, `rare_proper_noun_count`,
`estimated_word_count`). Their medians differ between old and new films, but that is
**real** (new films are smaller, less-awarded, more niche, the variation we added on
purpose), not a measurement artifact: coverage (non-null %) is the same.

## Action required (Francesco, ~5 min, TMDB only)
```
python scripts/26_collect_franchise.py      # uniform franchise/sequel/animation/genre
```
Then Claude re-runs 20 → 21 → 25. NOTE: because `franchise` was confounded with the
old/new split, the previously-reported "franchise +6.7" driver will be re-estimated on
clean data, its value may change materially. That correction is the whole point.
