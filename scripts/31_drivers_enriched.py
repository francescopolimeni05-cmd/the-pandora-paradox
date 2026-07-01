#!/usr/bin/env python3
"""
31_drivers_enriched.py — drivers model with the richer TMDB predictors
======================================================================
Runs AFTER 27_collect_extra_drivers.py. Tests whether star power, runtime,
adaptation/IP, language and release season add explanatory power for cultural
over-performance beyond the core set — and which of the assignment's named drivers
actually matter.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
import statsmodels.formula.api as smf

DATA = Path(__file__).resolve().parents[1] / "data"


def main():
    df = pd.read_csv(DATA / "final_model_dataset.csv")
    ex = DATA / "extra_drivers.csv"
    if not ex.exists():
        raise SystemExit("Run scripts/27_collect_extra_drivers.py first.")
    df = df.merge(pd.read_csv(ex), on=["title", "year"], how="left", suffixes=("", "_x"))

    df["log_gross"] = np.log1p(df["worldwide_gross"]); df["log_budget"] = np.log1p(df["budget"])
    df["has_franchise"] = df["in_franchise"].fillna(0).astype(int)
    df["is_sequel"] = (df["sequel_number"].fillna(0) > 0).astype(int)
    df["is_animated"] = df["is_animated_tmdb"].fillna(0).astype(int)
    df["log_star"] = np.log1p(pd.to_numeric(df["star_power"], errors="coerce"))
    df["is_english"] = (df["original_language"] == "en").astype(int)
    df["is_adaptation"] = pd.to_numeric(df["is_adaptation"], errors="coerce")
    df["runtime"] = pd.to_numeric(df["runtime"], errors="coerce")

    base_terms = ["imdb_rating", "has_franchise", "is_sequel", "is_animated",
                  "log_budget", "metascore", "SCI_z"]
    new_terms = ["log_star", "runtime", "is_adaptation", "is_english"]
    d = df.dropna(subset=["cultural_perf", "genre"] + base_terms + new_terms +
                  ["release_season"])

    base = smf.ols("cultural_perf ~ " + " + ".join(base_terms) + " + C(genre)", data=d).fit()
    full = smf.ols("cultural_perf ~ " + " + ".join(base_terms + new_terms) +
                   " + C(release_season) + C(genre)", data=d).fit(cov_type="HC3")

    print(f"n={int(full.nobs)}")
    print(f"R²  base (core drivers) = {base.rsquared:.3f}")
    print(f"R²  enriched            = {full.rsquared:.3f}   (Δ = {full.rsquared-base.rsquared:+.3f})")
    print("\n=== Enriched drivers of cultural over-performance ===")
    for v in base_terms + new_terms:
        b, p = full.params[v], full.pvalues[v]
        s = "***" if p < .01 else "**" if p < .05 else "*" if p < .1 else "ns"
        print(f"  {v:16} beta={b:+8.3f}  p={p:.4f}  {s}")
    print("  release season (F-test): see model; seasonal dummies included")

    # which directors over-deliver culturally? (descriptive)
    dd = df.dropna(subset=["cultural_perf", "director"])
    dd = dd[dd["director"].astype(str).str.len() > 0]
    g = dd.groupby("director")["cultural_perf"].agg(["mean", "count"])
    g = g[g["count"] >= 3].sort_values("mean", ascending=False)
    print("\nDirectors with >=3 films, by mean cultural over-performance:")
    print(" TOP:", ", ".join(f"{i} ({r['mean']:+.0f})" for i, r in g.head(5).iterrows()))
    print(" BOT:", ", ".join(f"{i} ({r['mean']:+.0f})" for i, r in g.tail(5).iterrows()))


if __name__ == "__main__":
    main()
