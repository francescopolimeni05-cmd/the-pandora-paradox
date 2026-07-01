#!/usr/bin/env python3
"""
26_collect_franchise.py — UNIFORM franchise / sequel / animation for all 350 films
==================================================================================

The legacy `franchise` column is unusable (populated for every old film, empty for
every new one → perfectly confounded with the old/new split) and `is_sequel` was
hard-coded False for the new films. This re-derives all three from a single
authoritative, uniform source — TMDB — for EVERY film:

  in_franchise   1 if the film belongs to a TMDB collection (a real franchise), else 0
  sequel_number  0 = standalone OR first film in its collection; 1,2,... = later entry
                 (by release date within the collection) → a clean "is a sequel" measure
  is_animated    1 if 'Animation' is among the film's TMDB genres

Output: data/franchise_uniform.csv  (title, year, in_franchise, collection_name,
        sequel_number, n_in_collection, is_animated_tmdb)

  set -a; source .env; set +a
  python scripts/26_collect_franchise.py
"""
from __future__ import annotations
import os, time, csv
from pathlib import Path
import pandas as pd, requests

DATA = Path(__file__).resolve().parents[1] / "data"
KEY = os.environ.get("TMDB_API_KEY")
H = {"User-Agent": "PandoraParadox/1.0"}


def get(url, **params):
    params["api_key"] = KEY
    for a in range(4):
        try:
            time.sleep(0.28)
            r = requests.get(url, params=params, headers=H, timeout=30)
            if r.status_code in (429, 500, 502, 503):
                time.sleep(1.5 * (a + 1)); continue
            r.raise_for_status(); return r.json()
        except requests.RequestException:
            time.sleep(1.0 * (a + 1))
    return {}


def find_id(title, year):
    d = get("https://api.themoviedb.org/3/search/movie", query=title, year=int(year))
    res = d.get("results") or []
    return res[0]["id"] if res else None


def main():
    if not KEY:
        raise SystemExit("Set TMDB_API_KEY (env or .env).")
    df = pd.read_csv(DATA / "pandora_full_dataset_expanded.csv")
    rows = []
    for i, r in enumerate(df.itertuples(), 1):
        title, year = r.title, int(r.year)
        tmdb_id = getattr(r, "tmdb_id", None)
        if pd.isna(tmdb_id):
            tmdb_id = find_id(title, year)
        rec = {"title": title, "year": year, "in_franchise": 0, "collection_name": "",
               "sequel_number": 0, "n_in_collection": 0, "is_animated_tmdb": 0,
               "primary_genre": ""}
        if tmdb_id:
            det = get(f"https://api.themoviedb.org/3/movie/{int(tmdb_id)}")
            genres = [g["name"] for g in det.get("genres", [])]
            rec["is_animated_tmdb"] = int("Animation" in genres)
            rec["primary_genre"] = genres[0] if genres else ""  # uniform TMDB genre
            col = det.get("belongs_to_collection")
            if col:
                rec["in_franchise"] = 1
                rec["collection_name"] = col.get("name", "")
                cd = get(f"https://api.themoviedb.org/3/collection/{col['id']}")
                parts = [p for p in cd.get("parts", []) if p.get("release_date")]
                parts.sort(key=lambda p: p["release_date"])
                rec["n_in_collection"] = len(parts)
                ids = [p["id"] for p in parts]
                if int(tmdb_id) in ids:
                    rec["sequel_number"] = ids.index(int(tmdb_id))  # 0 = first/original
        rows.append(rec)
        print(f"[{i}/{len(df)}] {title[:34]:<34} franchise={rec['in_franchise']} "
              f"seq#={rec['sequel_number']} anim={rec['is_animated_tmdb']}")
        if i % 25 == 0:
            pd.DataFrame(rows).to_csv(DATA / "franchise_uniform.csv", index=False)
    pd.DataFrame(rows).to_csv(DATA / "franchise_uniform.csv", index=False)
    print(f"\nWrote data/franchise_uniform.csv ({len(rows)} films)")


if __name__ == "__main__":
    main()
