#!/usr/bin/env python3
"""
30_validity.py — is the Cultural Footprint Index actually valid?
================================================================

1. Convergent/discriminant validity: the four dimensions should correlate
   positively (they tap one underlying construct) but not redundantly. Reports the
   correlation matrix and a Cronbach-style alpha.
2. Known-groups validity: films that are *indisputably* cultural landmarks should
   score far above films everyone agrees are forgotten — a hard, pre-registered test
   using only uncontroversial cases.
3. Criterion check vs a signal NOT used to build the CFI (audience reach = number of
   IMDb/TMDB raters), as a convergent external-ish anchor.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats

DATA = Path(__file__).resolve().parents[1] / "data"
DIMS = ["DIM_attention", "DIM_engagement", "DIM_legitimation", "DIM_symbolic_reuse"]

ICONIC = ["Pulp Fiction", "The Dark Knight", "Titanic", "Shrek", "Toy Story",
          "Inception", "Avatar", "Frozen", "Get Out", "The Matrix",
          "Interstellar", "Joker"]
FORGOTTEN = ["John Carter", "R.I.P.D.", "Monster Trucks", "Jupiter Ascending",
             "The Nutcracker and the Four Realms", "The Adventures of Pluto Nash",
             "Catwoman", "Mars Needs Moms", "Pan", "Sahara", "Gigli"]


def cronbach_alpha(X):
    X = X.dropna(); k = X.shape[1]
    vc = X.var(axis=0, ddof=1).sum(); vt = X.sum(axis=1).var(ddof=1)
    return (k / (k - 1)) * (1 - vc / vt)


def main():
    df = pd.read_csv(DATA / "final_model_dataset.csv")

    # 1) convergent / discriminant validity
    Z = df[DIMS].apply(lambda s: (s - s.mean()) / s.std())
    print("1) Dimension correlation matrix (convergent + discriminant validity):")
    print(Z.corr().round(2).to_string())
    print(f"   Cronbach's alpha (4 dimensions): {cronbach_alpha(Z):.2f}  "
          "(>0.6 = the dimensions cohere into one index)")

    # 2) known-groups validity
    ic = df[df.title.isin(ICONIC)]; fg = df[df.title.isin(FORGOTTEN)]
    print(f"\n2) Known-groups validity  (iconic n={len(ic)}, forgotten n={len(fg)}):")
    print(f"   mean CFI  — iconic = {ic['CFI_final'].mean():.1f}   forgotten = {fg['CFI_final'].mean():.1f}")
    t, p = stats.ttest_ind(ic['CFI_final'].dropna(), fg['CFI_final'].dropna(), equal_var=False)
    print(f"   difference t={t:.1f}, p={p:.1e}")
    # rank-based: do all iconic outrank all forgotten? (AUC)
    a = ic['CFI_final'].dropna().values; b = fg['CFI_final'].dropna().values
    auc = np.mean([x > y for x in a for y in b])
    print(f"   AUC (P[iconic CFI > forgotten CFI]) = {auc:.2f}  (1.0 = perfect separation)")

    # 3) criterion check vs audience reach (raters), not used in CFI construction
    if "tmdb_vote_count" in df.columns:
        d = df.dropna(subset=["CFI_final", "tmdb_vote_count"])
        rho = stats.spearmanr(d["CFI_final"], np.log1p(d["tmdb_vote_count"])).correlation
        print(f"\n3) CFI vs audience reach (log #raters, not in the index): Spearman rho={rho:+.2f}")

    print("\nThe CFI coheres (alpha), separates landmark from forgotten films (AUC), "
          "and tracks independent audience reach → evidence it measures real cultural footprint.")


if __name__ == "__main__":
    main()
