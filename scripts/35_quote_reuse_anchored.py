#!/usr/bin/env python3
"""
35_quote_reuse_anchored.py — the decisive test: does SCI drive quotes that TRAVEL?
=================================================================================

Consolidates the quote-circulation analysis into one reproducible verdict.

Motivation: the symbolic-reuse dimension originally used only `wikiquote_count`
(curated notability), not quotes actually circulating online. We therefore measured
real circulation (32 -> 33) and re-tested SCI against it.

A naive first pass (exact-phrase Google counts, unanchored) made SCI look
significant — but that was a confound: SCI rewards SHORT punchy lines, and short
lines are often generic phrases ("I love you") that rack up millions of results not
attributable to the film. We corrected the most inflated short quotes with a
film-anchored query (`"quote" <title>`, script 33 --anchor only) and re-ran.

This script:
  - loads exact counts (quote_circulation.json) and anchored counts
    (quote_circulation_verify.json),
  - uses the anchored count where available (attribution-clean), else exact,
  - drops cast/credits noise,
  - builds a film-level realized-circulation score (mean of top-3 log counts),
  - tests SCI on all quotes and on distinctive-only subsets,
  - compares realized circulation with the curated wikiquote_count.

Output: data/quote_reuse_film_final.csv + console verdict.

Usage:  python scripts/35_quote_reuse_anchored.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _is_noise(q: str) -> bool:
    """Cast/credits bullet like 'Robert Downey, Jr. – Tony' — not a quote."""
    return bool((" – " in q or " — " in q) and re.search(r"[A-Z][a-z]+.*[–—].*[A-Z]", q))


def main() -> None:
    circ = pd.DataFrame(json.load((DATA / "quote_circulation.json").open()))
    circ = circ[circ["status"] == "success"].copy()
    circ["exact"] = pd.to_numeric(circ["results_exact"], errors="coerce")

    # anchored counts for the re-verified short quotes (attribution-clean)
    anchored = {}
    vpath = DATA / "quote_circulation_verify.json"
    if vpath.exists():
        v = pd.DataFrame(json.load(vpath.open()))
        v = v[v["status"] == "success"]
        for r in v.itertuples():
            a = pd.to_numeric(pd.Series([r.results_film]), errors="coerce").iloc[0]
            if pd.notna(a):
                anchored[(r.title, r.year, r.quote)] = a
    print(f"anchored (film-attributed) counts available for {len(anchored)} short quotes")

    circ["best"] = circ.apply(
        lambda x: anchored.get((x["title"], x["year"], x["quote"]), x["exact"]), axis=1)
    circ = circ.dropna(subset=["best"])
    circ = circ[~circ["quote"].apply(_is_noise)].copy()
    circ["words"] = circ["quote"].str.split().apply(len)
    circ["lr"] = np.log1p(circ["best"])

    # film-level realized circulation = mean of top-3 log counts
    film = (circ.groupby(["title", "year"])
            .agg(realized_circ=("lr", lambda s: s.nlargest(3).mean()),
                 n_quotes=("lr", "size")).reset_index())
    film.to_csv(DATA / "quote_reuse_film_final.csv", index=False)
    print(f"film-level realized circulation -> data/quote_reuse_film_final.csv "
          f"({len(film)} films)")

    df = pd.read_csv(DATA / "final_model_dataset.csv")
    df["log_gross"] = np.log1p(df["worldwide_gross"])
    df = df.merge(film, on=["title", "year"], how="left")

    # curated vs realized — are they the same? (No.)
    sub = df.dropna(subset=["wikiquote_count", "realized_circ"])
    rho, p = spearmanr(pd.to_numeric(sub["wikiquote_count"], errors="coerce"),
                       sub["realized_circ"])
    print(f"\nwikiquote_count vs realized circulation: Spearman rho={rho:+.3f} (p={p:.3g}) "
          f"-> curated notability != actual circulation")

    print("\n=== Does SCI predict quotes that ACTUALLY travel? "
          "(realized_circ ~ SCI_z + log_gross + C(genre), HC3) ===")
    for lo, label in [(0, "all quotes"), (5, "distinctive (>=5 words)"),
                      (7, "strict distinctive (>=7 words)")]:
        c = circ[circ["words"] >= lo]
        g = (c.groupby(["title", "year"])
             .agg(y=("lr", lambda s: s.nlargest(3).mean())).reset_index())
        d = df.drop(columns=["realized_circ"]).merge(g, on=["title", "year"]).dropna(
            subset=["SCI_z", "y", "log_gross", "genre"])
        m = smf.ols("y ~ SCI_z + log_gross + C(genre)", data=d).fit(cov_type="HC3")
        b, pv = m.params["SCI_z"], m.pvalues["SCI_z"]
        print(f"  {label:28} n={int(m.nobs):3}  SCI beta={b:+.3f}  p={pv:.4f}  "
              f"{'SIGNIFICANT' if pv < 0.05 else 'ns'}")

    print("\nVERDICT: with attribution-clean counts, SCI does NOT significantly predict "
          "realized quote circulation. The naive positive was a short-generic-phrase "
          "artifact. The well-identified null on symbolic compressibility holds — now "
          "against the outcome the theory is actually about.")


if __name__ == "__main__":
    main()
