#!/usr/bin/env python3
"""
27_collect_extra_drivers.py — richer, uniform predictors from TMDB (all films)
==============================================================================

Adds the drivers the assignment names but the model lacked, measured the same way
for every film:

  star_power       mean TMDB popularity of the top-3 billed cast (fame of the leads)
  director         director name (for director fixed effects / track record)
  runtime          minutes
  original_language e.g. en, fr, ko (English vs foreign)
  release_month / release_season  (seasonality of release)
  is_adaptation    1 if TMDB keywords mark it as based on a novel/comic/true story/
                   video game/play (IP/adaptation vs original screenplay)

Output: data/extra_drivers.csv

  set -a; source .env; set +a
  python scripts/27_collect_extra_drivers.py
"""
from __future__ import annotations
import os, time
from pathlib import Path
import pandas as pd, requests

DATA = Path(__file__).resolve().parents[1] / "data"
KEY = os.environ.get("TMDB_API_KEY")
H = {"User-Agent": "PandoraParadox/1.0"}
ADAPT_KW = ("based on novel", "based on comic", "based on true story", "based on a true story",
            "based on video game", "based on play", "based on short story", "based on book",
            "based on graphic novel", "based on memoir", "adaptation", "based on tv")
SEASON = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
          6: "Summer", 7: "Summer", 8: "Summer", 9: "Fall", 10: "Fall", 11: "Fall"}


def get(url, **p):
    p["api_key"] = KEY
    for a in range(4):
        try:
            time.sleep(0.27)
            r = requests.get(url, params=p, headers=H, timeout=30)
            if r.status_code in (429, 500, 502, 503):
                time.sleep(1.5 * (a + 1)); continue
            r.raise_for_status(); return r.json()
        except requests.RequestException:
            time.sleep(1.0 * (a + 1))
    return {}


def find_id(t, y):
    d = get("https://api.themoviedb.org/3/search/movie", query=t, year=int(y))
    res = d.get("results") or []
    return res[0]["id"] if res else None


def main():
    if not KEY:
        raise SystemExit("Set TMDB_API_KEY.")
    df = pd.read_csv(DATA / "pandora_full_dataset_expanded.csv")
    rows = []
    for i, r in enumerate(df.itertuples(), 1):
        title, year = r.title, int(r.year)
        tid = getattr(r, "tmdb_id", None)
        if pd.isna(tid):
            tid = find_id(title, year)
        rec = {"title": title, "year": year, "star_power": None, "director": "",
               "runtime": None, "original_language": "", "release_month": None,
               "release_season": "", "is_adaptation": 0, "n_cast": 0}
        if tid:
            det = get(f"https://api.themoviedb.org/3/movie/{int(tid)}")
            rec["runtime"] = det.get("runtime")
            rec["original_language"] = det.get("original_language", "")
            rd = det.get("release_date") or ""
            if len(rd) >= 7:
                mth = int(rd[5:7]); rec["release_month"] = mth; rec["release_season"] = SEASON.get(mth, "")
            cr = get(f"https://api.themoviedb.org/3/movie/{int(tid)}/credits")
            cast = sorted(cr.get("cast", []), key=lambda c: c.get("order", 99))
            rec["n_cast"] = len(cast)
            top = [c.get("popularity", 0) or 0 for c in cast[:3]]
            rec["star_power"] = sum(top) / len(top) if top else 0
            crew = cr.get("crew", [])
            dirs = [c["name"] for c in crew if c.get("job") == "Director"]
            rec["director"] = dirs[0] if dirs else ""
            kw = get(f"https://api.themoviedb.org/3/movie/{int(tid)}/keywords")
            names = " ".join(k.get("name", "").lower() for k in kw.get("keywords", []))
            rec["is_adaptation"] = int(any(a in names for a in ADAPT_KW))
        rows.append(rec)
        print(f"[{i}/{len(df)}] {title[:30]:<30} star={rec['star_power'] or 0:6.1f} "
              f"runtime={rec['runtime']} adapt={rec['is_adaptation']} dir={rec['director'][:18]}")
        if i % 25 == 0:
            pd.DataFrame(rows).to_csv(DATA / "extra_drivers.csv", index=False)
    pd.DataFrame(rows).to_csv(DATA / "extra_drivers.csv", index=False)
    print(f"\nWrote data/extra_drivers.csv ({len(rows)} films)")


if __name__ == "__main__":
    main()
