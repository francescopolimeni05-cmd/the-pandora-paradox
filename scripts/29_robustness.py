#!/usr/bin/env python3
"""
29_robustness.py — does the model survive stress tests?
=======================================================

1. Out-of-sample cross-validation of the drivers model (5-fold R²).
2. Alternative CFI construction: PCA-weighted instead of equal-weight dimensions —
   do the drivers hold?
3. Outlier-robust regression (Huber) for the drivers.
4. 95% confidence intervals on the key coefficients.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
import statsmodels.api as sm
from sklearn.model_selection import cross_val_score, KFold
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

DATA = Path(__file__).resolve().parents[1] / "data"
DIMS = ["DIM_attention", "DIM_engagement", "DIM_legitimation", "DIM_symbolic_reuse"]
DRV = ["imdb_rating", "has_franchise", "is_sequel", "is_animated", "log_budget",
       "metascore", "SCI_z"]


def main():
    df = pd.read_csv(DATA / "final_model_dataset.csv")
    df["log_gross"] = np.log1p(df["worldwide_gross"]); df["log_budget"] = np.log1p(df["budget"])
    df["has_franchise"] = df["in_franchise"].fillna(0).astype(int)
    df["is_sequel"] = (df["sequel_number"].fillna(0) > 0).astype(int)
    df["is_animated"] = df["is_animated_tmdb"].fillna(0).astype(int)

    d = df.dropna(subset=["cultural_perf"] + DRV + ["genre"]).copy()
    X = pd.get_dummies(d[DRV + ["genre"]], columns=["genre"], drop_first=True).astype(float)
    y = d["cultural_perf"].values

    # 1) cross-validated out-of-sample R²
    cv = KFold(5, shuffle=True, random_state=0)
    r2 = cross_val_score(LinearRegression(), X, y, cv=cv, scoring="r2")
    print(f"1) Drivers model 5-fold OUT-OF-SAMPLE R² = {r2.mean():.3f} (±{r2.std():.3f})")

    # 2) PCA-weighted CFI → does it change the drivers?
    Z = StandardScaler().fit_transform(df[DIMS].fillna(df[DIMS].mean()))
    pc = PCA(1).fit(Z); w = np.abs(pc.components_[0]); w = w / w.sum()
    df["CFI_pca"] = 100 * (Z @ w - (Z @ w).min()) / ((Z @ w).max() - (Z @ w).min())
    base = smf.ols("CFI_pca ~ log_gross + years_since_release", data=df).fit()
    df["cultural_perf_pca"] = df["CFI_pca"] - base.predict(df)
    print(f"   PCA dimension weights: " +
          ", ".join(f"{n}={wi:.2f}" for n, wi in zip(DIMS, w)))
    dp = df.dropna(subset=["cultural_perf_pca"] + DRV + ["genre"])
    m2 = smf.ols("cultural_perf_pca ~ " + " + ".join(DRV) + " + C(genre)", data=dp).fit(cov_type="HC3")
    print("2) Drivers under PCA-weighted CFI (key coefs):")
    for v in ["imdb_rating", "is_sequel", "has_franchise", "SCI_z"]:
        print(f"     {v:14} beta={m2.params[v]:+.3f}  p={m2.pvalues[v]:.4f}")

    # 3) outlier-robust (Huber) regression on the main spec
    Xc = sm.add_constant(X)
    rlm = sm.RLM(y, Xc, M=sm.robust.norms.HuberT()).fit()
    print("3) Outlier-robust (Huber) drivers:")
    for v in ["imdb_rating", "is_sequel", "has_franchise", "SCI_z"]:
        if v in rlm.params:
            print(f"     {v:14} beta={rlm.params[v]:+.3f}  p={rlm.pvalues[v]:.4f}")

    # 4) 95% CIs on the headline OLS spec
    m = smf.ols("cultural_perf ~ " + " + ".join(DRV) + " + C(genre)", data=d).fit(cov_type="HC3")
    ci = m.conf_int().loc[["imdb_rating", "is_sequel", "has_franchise", "SCI_z"]]
    print("4) 95% confidence intervals (headline spec):")
    for v in ci.index:
        print(f"     {v:14} {m.params[v]:+.3f}  [{ci.loc[v,0]:+.3f}, {ci.loc[v,1]:+.3f}]")
    print("\nConclusion stable if IMDb stays +/significant and SCI's CI spans 0 across all.")


if __name__ == "__main__":
    main()
