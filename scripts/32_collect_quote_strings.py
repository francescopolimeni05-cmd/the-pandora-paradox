#!/usr/bin/env python3
"""
32_collect_quote_strings.py — candidate "quotes that travel" per film
=====================================================================

The symbolic-reuse dimension so far uses only wikiquote_count (how many entries a
film has on Wikiquote). That is a *curated* proxy, not a measure of quotes actually
circulating online. To measure real circulation we first need the actual quote
STRINGS; this script fetches them from Wikiquote (free Wikimedia API, no key), then
33_collect_quote_circulation.py measures how much each string travels.

For each film:
  1. find its Wikiquote page (search API, disambiguation-aware),
  2. pull the page wikitext,
  3. extract clean quote lines (strip markup, drop speaker labels / stage directions),
  4. filter to distinctive, searchable lines (min/max word count) and dedupe,
  5. keep the top-K.

Output: data/quote_candidates.json — list of
  {title, year, wikiquote_page, n_found, quotes:[...], status}

Checkpoint/resume: successful films are skipped on re-run; misses are retried.

Usage
-----
  python scripts/32_collect_quote_strings.py \
      --input data/final_model_dataset.csv \
      --output data/quote_candidates.json --topk 8
  # smoke test:
  python scripts/32_collect_quote_strings.py --input data/final_model_dataset.csv \
      --output data/quote_candidates_test.json --limit 5
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WQ_API = "https://en.wikiquote.org/w/api.php"
UA = "PandoraParadox-capstone/1.0 (research; contact via repo)"

MIN_WORDS = 3     # 3 keeps iconic short quotes ("Why so serious?"); Wikiquote curation limits noise
MAX_WORDS = 18    # drop long passages that won't match as a single exact phrase


def load_films(path: str) -> list[dict]:
    import csv
    p = Path(path)
    with p.open() as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        if not r.get("title"):
            continue
        try:
            yr = int(float(r["year"]))
        except Exception:
            yr = None
        out.append({"title": r["title"], "year": yr})
    return out


def _get(params: dict, retries: int = 3) -> dict | None:
    params = {**params, "format": "json"}
    for a in range(retries):
        try:
            r = requests.get(WQ_API, params=params, timeout=45,
                             headers={"User-Agent": UA})
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 * (a + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException:
            time.sleep(2 * (a + 1))
    return None


def find_page(title: str, year: int | None) -> str | None:
    """Best Wikiquote page title for the film — ONE search call (fast).
    Picks, among the top hits: an exact title match, else a '... (film)' page,
    else the first hit."""
    d = _get({"action": "query", "list": "search",
              "srsearch": f'{title} film', "srlimit": 6, "srnamespace": 0})
    hits = (d or {}).get("query", {}).get("search", [])
    if not hits:
        return None
    norm = re.sub(r"[^a-z0-9]", "", title.lower())
    exact = film_match = None
    for h in hits:
        ht = h["title"]
        hn = re.sub(r"[^a-z0-9]", "", ht.lower())
        if hn == norm and exact is None:
            exact = ht
        if "film" in ht.lower() and norm in hn and film_match is None:
            film_match = ht
    return exact or film_match or hits[0]["title"]


def get_wikitext(page: str) -> str | None:
    d = _get({"action": "parse", "page": page, "prop": "wikitext",
              "redirects": 1})
    if not d or "parse" not in d:
        return None
    return d["parse"]["wikitext"]["*"]


_STRIP_PATTERNS = [
    (re.compile(r"<ref[^>]*>.*?</ref>", re.S), ""),
    (re.compile(r"<ref[^>]*/>"), ""),
    (re.compile(r"<[^>]+>"), ""),
    (re.compile(r"\{\{[^{}]*\}\}"), ""),
    (re.compile(r"\[\[[^\]|]*\|([^\]]*)\]\]"), r"\1"),   # [[a|b]] -> b
    (re.compile(r"\[\[([^\]]*)\]\]"), r"\1"),            # [[a]]   -> a
    (re.compile(r"'''''|'''|''"), ""),                    # bold/italic
    (re.compile(r"&nbsp;"), " "),
]
_SPEAKER = re.compile(r"^\s*[A-Z][A-Za-z0-9 .'\-]{0,30}:\s*")   # "JOKER: ..." / "Batman: ..."


def clean_line(raw: str) -> str:
    s = raw
    for pat, rep in _STRIP_PATTERNS:
        s = pat.sub(rep, s)
    s = _SPEAKER.sub("", s)                 # drop leading speaker label
    s = re.sub(r"\s+", " ", s).strip(" \t*—-–:")
    return s


def extract_quotes(wikitext: str, topk: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ln in wikitext.splitlines():
        m = re.match(r"^\*+\s*(.+)$", ln)     # bullet lines are the quotes
        if not m:
            continue
        s = clean_line(m.group(1))
        if not s or s.startswith(("[", "{", "|")):
            continue
        # must be mostly letters, sentence-like, and searchable as an exact phrase
        letters = sum(c.isalpha() for c in s)
        if letters < 0.6 * len(s):
            continue
        w = s.split()
        if not (MIN_WORDS <= len(w) <= MAX_WORDS):
            continue
        if s.isupper():                       # stage direction / heading
            continue
        key = re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= topk:
            break
    return out


def collect_one(title: str, year: int | None, topk: int) -> dict:
    try:
        page = find_page(title, year)
        if not page:
            return {"title": title, "year": year, "status": "no_page",
                    "n_found": 0, "quotes": []}
        wt = get_wikitext(page)
        if not wt:
            return {"title": title, "year": year, "wikiquote_page": page,
                    "status": "no_wikitext", "n_found": 0, "quotes": []}
        quotes = extract_quotes(wt, topk)
        return {"title": title, "year": year, "wikiquote_page": page,
                "status": "success" if quotes else "no_quotes",
                "n_found": len(quotes), "quotes": quotes}
    except Exception as e:
        return {"title": title, "year": year, "status": "error",
                "error": str(e), "n_found": 0, "quotes": []}


def main() -> None:
    global MIN_WORDS
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=str(DATA / "final_model_dataset.csv"))
    ap.add_argument("--output", default=str(DATA / "quote_candidates.json"))
    ap.add_argument("--topk", type=int, default=8)
    ap.add_argument("--min-words", type=int, default=None,
                    help=f"override minimum quote length (default {MIN_WORDS})")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=0.4)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.min_words is not None:
        MIN_WORDS = args.min_words

    films = load_films(args.input)
    if args.limit:
        films = films[: args.limit]
    out = Path(args.output)

    done: dict[tuple, dict] = {}
    if out.exists() and not args.force:
        for r in json.load(out.open()):
            if r.get("status") in ("success", "no_quotes", "no_page"):
                done[(r.get("title"), r.get("year"))] = r

    rows = list(done.values())
    for i, f in enumerate(films, 1):
        key = (f["title"], f["year"])
        if key in done:
            print(f"[{i}/{len(films)}] skip (done): {f['title']}")
            continue
        print(f"[{i}/{len(films)}] Wikiquote: {f['title']} ({f['year']})")
        time.sleep(args.sleep)
        block = collect_one(f["title"], f["year"], args.topk)
        print(f"      -> {block['status']} | {block['n_found']} quotes")
        rows.append(block)
        if i % 10 == 0:
            json.dump(rows, out.open("w"), indent=2, ensure_ascii=False)
    json.dump(rows, out.open("w"), indent=2, ensure_ascii=False)
    ok = sum(1 for r in rows if r.get("status") == "success")
    nq = sum(r.get("n_found", 0) for r in rows)
    print(f"\nWrote {len(rows)} films -> {out}  ({ok} with quotes, {nq} quote strings total)")


if __name__ == "__main__":
    main()
