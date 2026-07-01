#!/usr/bin/env python3
"""
28_persistence.py — cultural persistence over time (the dynamic side of the paradox)
====================================================================================

The Pandora Paradox is fundamentally temporal: a footprint is about *staying alive*.
From each film's monthly Wikipedia pageview series (recent 3-year window) we measure:

  persistence_slope  OLS slope of log(monthly views) on month index → is attention
                     currently trending up (>0, still gaining cultural relevance) or
                     fading (<0)? Scale-free (log) and comparable across films.
  persistence_ratio  mean(last 12 months) / mean(first 12 months) → >1 = growing.
  attention_cv       coefficient of variation → spiky (event-driven) vs steady.

Then: which films persist vs fade, and what predicts persistence net of box office?
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd
import statsmodels.formula.api as smf

DATA = Path(__file__).resolve().parents[1] / "data"


def series_features(dp):
    v = np.array([p.get("views", 0) for p in dp], float)
    if len(v) < 12 or v.sum() == 0:
        return None
    t = np.arange(len(v)) / max(len(v) - 1, 1)          # 0..1
    y = np.log1p(v)
    slope = np.polyfit(t, y, 1)[0]                        # log-views per full window
    h = len(v) // 3
    first, last = v[:12].mean(), v[-12:].mean()
    ratio = (last + 1) / (first + 1)
    cv = v.std() / (v.mean() + 1e-9)
    return slope, ratio, cv


def main():
    recs = json.load((DATA / "live_api_data.json").open())
    rows = []
    for r in recs:
        dp = (r.get("metrics", {}) or {}).get("wikipedia_pageviews", {}).get("data_points") or []
        f = series_features(dp)
        if f:
            rows.append({"title": r.get("movie_title"), "year": r.get("movie_year"),
                         "persistence_slope": f[0], "persistence_ratio": f[1],
                         "attention_cv": f[2]})
    pers = pd.DataFrame(rows)
    print(f"Persistence computed for {len(pers)} films (>=12 monthly points)")

    df = pd.read_csv(DATA / "final_model_dataset.csv").merge(pers, on=["title", "year"], how="left")
    df["log_gross"] = np.log1p(df["worldwide_gross"])

    print("\n--- STILL GAINING cultural relevance (top persistence_slope) ---")
    print(df.dropna(subset=["persistence_slope"]).nlargest(10, "persistence_slope")
          [["title", "year", "persistence_slope", "persistence_ratio"]].round(2).to_string(index=False))
    print("\n--- FADING fastest (bottom persistence_slope) ---")
    print(df.dropna(subset=["persistence_slope"]).nsmallest(10, "persistence_slope")
          [["title", "year", "persistence_slope"]].round(2).to_string(index=False))

    # does cultural over-performance go with persistence?
    d = df.dropna(subset=["persistence_slope", "cultural_perf"])
    print(f"\ncorr(persistence_slope, cultural over-performance): "
          f"{d[['persistence_slope','cultural_perf']].corr().iloc[0,1]:+.3f}  (n={len(d)})")

    # what predicts persistence, net of box office?
    d = df.dropna(subset=["persistence_slope", "imdb_rating", "log_gross"])
    d["has_franchise"] = d["in_franchise"].fillna(0)
    d["is_sequel"] = (d["sequel_number"].fillna(0) > 0).astype(int)
    m = smf.ols("persistence_slope ~ imdb_rating + has_franchise + is_sequel + log_gross "
                "+ years_since_release + metascore", data=d).fit(cov_type="HC3")
    print(f"\n=== What predicts cultural PERSISTENCE (n={int(m.nobs)}, R²={m.rsquared:.2f}) ===")
    for v in ["imdb_rating", "has_franchise", "is_sequel", "log_gross",
              "years_since_release", "metascore"]:
        b, p = m.params[v], m.pvalues[v]
        s = "***" if p < .01 else "**" if p < .05 else "*" if p < .1 else "ns"
        print(f"  {v:18} beta={b:+.4f}  p={p:.4f}  {s}")

    df.to_csv(DATA / "final_model_dataset.csv", index=False)
    print("\nAdded persistence_slope/ratio/cv -> final_model_dataset.csv")


if __name__ == "__main__":
    main()
