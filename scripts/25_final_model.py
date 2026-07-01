#!/usr/bin/env python3
"""
25_final_model.py — the consolidated final model
=================================================

Brings everything onto clean, uniform signals:
  - Cultural Footprint Index rebuilt from the FOUR dimensions (attention,
    engagement [Reddit SerpAPI volume], legitimation, symbolic reuse) — not the
    legacy composite whose Reddit component was ~0 for the 156 new films.
  - Over/under-performance = CFI net of box office (+ film age).
  - Explanatory model: what drives cultural over-performance? (franchise, audience
    love, sequel, budget, genre) — with the SCI null reported alongside as a
    rigorous "it's not the script" contrast.

Run AFTER 20_build_sci.py and 21_decompose_cfi.py (which create the dimensions on
the fixed-Wikipedia / SerpAPI-Reddit data).
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
import statsmodels.formula.api as smf

DATA = Path(__file__).resolve().parents[1] / "data"
DIMS = ["DIM_attention", "DIM_engagement", "DIM_legitimation", "DIM_symbolic_reuse"]


def z(s): s = pd.to_numeric(s, errors="coerce"); return (s - s.mean()) / s.std(ddof=0)


def main():
    df = pd.read_csv(DATA / "analysis_dataset.csv")

    # ---- final CFI from the 4 dimensions (equal-weight z-scores → 0-100) ----
    Z = pd.DataFrame({d: z(df[d]) for d in DIMS})
    df["CFI_final_z"] = Z.mean(axis=1)
    r = df["CFI_final_z"]
    df["CFI_final"] = 100 * (r - r.min()) / (r.max() - r.min())

    df["log_gross"] = np.log1p(df["worldwide_gross"]); df["log_budget"] = np.log1p(df["budget"])

    # franchise / sequel / animation come UNIFORM from 20_build_sci.py's harmonization
    # (TMDB, via 26_collect_franchise.py). Fall back to legacy only if not present.
    if "in_franchise" in df.columns:
        df["has_franchise"] = df["in_franchise"].fillna(0).astype(int)
        df["is_sequel"] = (df["sequel_number"].fillna(0) > 0).astype(int)
        df["is_animated"] = df["is_animated_tmdb"].fillna(0).astype(int)
        print("Using UNIFORM franchise/sequel/animation (TMDB).")
    else:
        print("WARNING: uniform franchise vars missing — run 26_collect_franchise.py "
              "then re-run 20/21. Using legacy (confounded) columns for now.")
        df["has_franchise"] = (df["franchise"].notna() &
                               (df["franchise"].astype(str).str.strip() != "")).astype(int)
        for c in ["is_sequel", "is_animated"]:
            df[c] = df[c].astype(str).str.lower().isin(["true", "1"]).astype(int)

    # ---- cultural over/under-performance: CFI net of box office + age ----
    base = smf.ols("CFI_final ~ log_gross + years_since_release", data=df).fit()
    df["cultural_perf"] = df["CFI_final"] - base.predict(df)
    print(f"CFI_final built from 4 dimensions. Box office explains "
          f"R²={base.rsquared:.2f} of CFI (the rest is the 'paradox' residual).")

    # ---- explanatory drivers model ----
    d = df.dropna(subset=["cultural_perf", "imdb_rating", "metascore", "SCI_z"])
    m = smf.ols("cultural_perf ~ has_franchise + is_sequel + is_animated + log_budget "
                "+ imdb_rating + metascore + SCI_z + C(genre)", data=d).fit(cov_type="HC3")
    print(f"\n=== DRIVERS of cultural over-performance (n={int(m.nobs)}, R²={m.rsquared:.2f}) ===")
    for v in ["has_franchise", "imdb_rating", "is_sequel", "is_animated",
              "log_budget", "metascore", "SCI_z"]:
        b, p = m.params[v], m.pvalues[v]
        s = "***" if p < .01 else "**" if p < .05 else "*" if p < .1 else "ns"
        print(f"  {v:15} beta={b:+7.3f}  p={p:.4f}  {s}")

    # ---- exposure-adjusted PER-DIMENSION scores (does a film over/under-perform
    #      on THIS dimension relative to its reach?) — the Avatar test ----
    for d in DIMS:
        dd = df.dropna(subset=[d, "log_gross"])
        b = smf.ols(f"{d} ~ log_gross + years_since_release", data=dd).fit()
        df.loc[dd.index, d + "_adj"] = dd[d] - b.predict(dd)
    adj = [d + "_adj" for d in DIMS]
    for a in adj:
        df[a + "_pct"] = df[a].rank(pct=True) * 100

    print("\n=== Exposure-ADJUSTED dimension profile (percentile; <50 = below "
          "expected for its box office) ===")
    print(f"{'film':24} {'attention':>9} {'engage':>7} {'legit':>6} {'sym_reuse':>10}")
    for t in ["Avatar", "Avatar: The Way of Water", "Avengers: Endgame", "Titanic",
              "The Dark Knight", "Frozen", "Pulp Fiction", "Mean Girls"]:
        r = df[df.title == t]
        if len(r):
            r = r.iloc[0]
            print(f"  {t:22} {r['DIM_attention_adj_pct']:9.0f} {r['DIM_engagement_adj_pct']:7.0f} "
                  f"{r['DIM_legitimation_adj_pct']:6.0f} {r['DIM_symbolic_reuse_adj_pct']:10.0f}")

    print("\n=== AVATAR & reference films ===")
    for t in ["Avatar", "Avatar: The Way of Water", "Titanic", "Avengers: Endgame",
              "The Dark Knight", "Frozen", "John Carter"]:
        rr = df[df.title == t]
        if len(rr):
            rr = rr.iloc[0]
            print(f"  {t:26} CFI={rr['CFI_final']:5.1f}  ${rr['worldwide_gross']/1e9:4.2f}B  "
                  f"perf={rr['cultural_perf']:+5.1f}")

    print("\n=== Cultural OVER-achievers (top 10) ===")
    print(df.nlargest(10, "cultural_perf")[["title", "year", "CFI_final", "cultural_perf"]]
          .round(1).to_string(index=False))
    print("\n=== Cultural UNDER-achievers (bottom 10) ===")
    print(df.nsmallest(10, "cultural_perf")[["title", "year", "CFI_final", "cultural_perf"]]
          .round(1).to_string(index=False))

    df.to_csv(DATA / "final_model_dataset.csv", index=False)
    print(f"\nWrote final model table -> final_model_dataset.csv ({len(df)} films)")


if __name__ == "__main__":
    main()
