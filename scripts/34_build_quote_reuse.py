#!/usr/bin/env python3
"""
34_build_quote_reuse.py — realized-circulation outcome + re-test of the mechanism
=================================================================================

Runs OFFLINE after 32 + 33. Aggregates per-quote circulation into a film-level
"realized circulation" score — a measure of quotes that ACTUALLY travel online —
and re-tests whether Symbolic Compressibility (SCI) predicts it. This is the
proper outcome for the supervisor's mechanism, replacing the curated wikiquote_count.

What it does
------------
  1. Aggregate quote_circulation.json to film level:
       circ_sum   = log1p(sum of per-quote result counts)
       circ_top3  = mean of the 3 largest log1p(result) per film
     Uses the film-anchored count (results_film) when present, else results_exact.
  2. Show how different this is from wikiquote_count (curated) — Spearman rho.
  3. Re-test the mechanism on the NEW outcome:
       realized_circulation ~ SCI_z + log_gross + C(genre)   (HC3)
     and rebuild DIM_symbolic_reuse from circulation, comparing to the old build.

Output: data/quote_reuse_film.csv (+ console report). Nothing is overwritten in the
main modelling table; merge deliberately after reviewing the numbers.

Usage
-----
  python scripts/34_build_quote_reuse.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def zlog(s: pd.Series) -> pd.Series:
    x = np.log1p(pd.to_numeric(s, errors="coerce"))
    return (x - x.mean()) / x.std(ddof=0)


def main() -> None:
    circ_path = DATA / "quote_circulation.json"
    if not circ_path.exists():
        raise SystemExit("Run 32 then 33 first (data/quote_circulation.json missing).")
    circ = pd.DataFrame(json.load(circ_path.open()))
    circ = circ[circ["status"] == "success"].copy()
    # prefer film-anchored count; fall back to raw exact-phrase count
    circ["r"] = pd.to_numeric(circ["results_film"], errors="coerce")
    circ["r"] = circ["r"].fillna(pd.to_numeric(circ["results_exact"], errors="coerce"))
    circ = circ.dropna(subset=["r"])
    circ["lr"] = np.log1p(circ["r"])

    def agg(g: pd.DataFrame) -> pd.Series:
        top3 = g["lr"].nlargest(3)
        return pd.Series({
            "n_quotes_measured": len(g),
            "circ_sum": np.log1p(g["r"].sum()),
            "circ_top3": top3.mean(),
            "circ_max": g["lr"].max(),
        })

    film = circ.groupby(["title", "year"]).apply(agg).reset_index()
    film.to_csv(DATA / "quote_reuse_film.csv", index=False)
    print(f"Aggregated {len(circ)} measured quotes -> {len(film)} films "
          f"-> data/quote_reuse_film.csv")

    df = pd.read_csv(DATA / "final_model_dataset.csv")
    df = df.merge(film, on=["title", "year"], how="left")
    have = df["circ_top3"].notna()
    print(f"\nFilms with a realized-circulation score: {have.sum()}/{len(df)}")

    # (1) curated count vs realized circulation — are they the same thing? (No.)
    sub = df.loc[have, ["wikiquote_count", "circ_top3", "circ_sum"]].apply(
        pd.to_numeric, errors="coerce").dropna()
    rho, p = spearmanr(sub["wikiquote_count"], sub["circ_top3"])
    print(f"\n(1) wikiquote_count  vs  realized circ_top3:  Spearman rho={rho:+.3f} (p={p:.3g})")
    print("    -> a low/moderate rho means 'has curated quotes' != 'quotes actually travel'.")

    # (2) does SCI predict quotes that REALLY travel?
    df["log_gross"] = np.log1p(df["worldwide_gross"])
    for outcome in ["circ_top3", "circ_sum"]:
        d = df.dropna(subset=["SCI_z", outcome, "log_gross", "genre"])
        m = smf.ols(f"{outcome} ~ SCI_z + log_gross + C(genre)", data=d).fit(cov_type="HC3")
        b, pv = m.params["SCI_z"], m.pvalues["SCI_z"]
        print(f"\n(2) {outcome} ~ SCI_z + log_gross + C(genre)  (n={int(m.nobs)}, R2={m.rsquared:.3f})")
        print(f"    SCI_z beta = {b:+.3f}  p={pv:.4f}  "
              f"{'SIGNIFICANT' if pv < 0.05 else 'ns'}")

    # (3) rebuild the symbolic-reuse dimension from circulation and compare
    df["DIM_reuse_circ"] = zlog(df["circ_top3"])
    comp = df.dropna(subset=["DIM_reuse_circ", "DIM_symbolic_reuse"])
    if len(comp) > 5:
        rho2, _ = spearmanr(comp["DIM_reuse_circ"], comp["DIM_symbolic_reuse"])
        print(f"\n(3) new DIM_reuse (circulation) vs old DIM_symbolic_reuse (wikiquote): "
              f"rho={rho2:+.3f} (n={len(comp)})")
    print("\nInterpretation: if SCI now predicts realized circulation, the earlier null "
          "was partly a measurement issue (wikiquote_count too coarse). If SCI is still "
          "null against real circulation, the well-identified null stands — and is "
          "*stronger*, because the outcome now matches the theory.")


if __name__ == "__main__":
    main()
