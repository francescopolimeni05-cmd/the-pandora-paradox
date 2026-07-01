# Measuring "quotes that actually travel online"

Goal: replace the curated `wikiquote_count` proxy with a **real circulation** outcome, 
how much each film's lines actually circulate on the web, and re-test whether Symbolic
Compressibility (SCI) predicts it. Runs on your Mac (needs internet + `SERPAPI_KEY` in
`.env`, same key you already use). The sandbox has no external network, so collection
must run locally.

## Step 1, get the candidate quote strings (free, ~10 min)
Wikiquote via the Wikimedia API (no key, no quota):
```
python scripts/32_collect_quote_strings.py \
    --input data/final_model_dataset.csv \
    --output data/quote_candidates.json --topk 4
```
Produces `data/quote_candidates.json` (up to 4 distinctive quotes per film). Resumable.

## Step 2, measure how much each quote circulates (SerpAPI)
Exact-phrase Google result count per quote:
```
python scripts/33_collect_quote_circulation.py \
    --input data/quote_candidates.json \
    --output data/quote_circulation.json --anchor off --sleep 0.3
```
- With ~309 films × 4 quotes that's **~1,200 SerpAPI searches ≈ 1.2 h on a 1000/hour
  plan** (`--sleep 0.3` keeps requests moving; the script still parks and resumes if it
  ever hits the hourly cap). On a 200/hour plan the same run is ~6 h, hands-off.
- `--anchor off` = 1 query per quote. `--anchor on` adds a `"quote" + title` query
  (better attribution) but doubles the searches, use later on a subset if needed.
- Fully resumable: re-run the same command to continue after any interruption.
- The key is read automatically from `.env` (`SERPAPI_KEY`).

## Step 3, build the outcome and re-test the mechanism (offline, back in the session)
Once `data/quote_circulation.json` exists, I run:
```
python scripts/34_build_quote_reuse.py
```
This aggregates to a film-level realized-circulation score, shows how different it is
from `wikiquote_count`, and re-tests `realized_circulation ~ SCI_z + log_gross + genre`.

## How to read the result
- **If SCI now predicts realized circulation** → the earlier SCI null was partly a
  measurement artifact (Wikiquote too coarse). That would *revive* the mechanism, a
  big deal for the paper.
- **If SCI is still null against real circulation** → the well-identified null stands,
  and is now *stronger*, because the outcome finally matches the theory the supervisor
  proposed.

Either way it directly answers "we never studied the quotes that actually travel."
