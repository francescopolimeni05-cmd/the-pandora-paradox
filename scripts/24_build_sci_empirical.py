#!/usr/bin/env python3
"""
24_build_sci_empirical.py — a VALIDATED, data-driven Symbolic Compressibility Index
===================================================================================

Instead of assuming three a-priori features, we LEARN which script-intrinsic
features (all fixed at release) predict REALIZED quotability (Wikiquote dialogue
blocks). SCI_emp = the out-of-sample predicted quotability from script form alone.

Anti-circularity safeguards:
  - Cross-validated out-of-sample prediction (cross_val_predict): SCI for each film
    is predicted by a model trained on OTHER films, so it can't memorize.
  - SCI uses ONLY script features — no genre, no exposure.
  - The decisive validity test uses a DIFFERENT, held-out outcome (Reddit discussion
    volume; attention persistence) — not the quotability target used to build it —
    controlling for genre and box office.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNetCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import cross_val_predict, KFold
import statsmodels.formula.api as smf

DATA = Path(__file__).resolve().parents[1] / "data"

# Script-intrinsic features available at release (no exposure, no genre).
FEATURES = [
    "avg_dialogue_length", "longest_monologue_words", "unique_character_count",
    "sentiment_mean", "sentiment_std", "sentiment_spike",
    "exclamation_ratio", "question_ratio", "profanity_score",
    "vocabulary_richness", "avg_sentence_complexity", "humor_indicator",
    "romance_indicator", "violence_indicator", "short_punchy_density",
]


def zlog(s): return np.log1p(pd.to_numeric(s, errors="coerce").clip(lower=0))


def main():
    df = pd.read_csv(DATA / "analysis_dataset.csv")
    df["rare_pn_density"] = (pd.to_numeric(df["rare_proper_noun_count"], errors="coerce")
                             / pd.to_numeric(df["estimated_word_count"], errors="coerce") * 1000)
    feats = [f for f in FEATURES if f in df.columns] + ["rare_pn_density"]

    # build set: films with script features AND a realized-quotability target
    d = df.dropna(subset=feats + ["wikiquote_count"]).copy()
    # drop degenerate subtitle parses
    d = d[(pd.to_numeric(d["dialogue_line_count"], errors="coerce") >= 50)
          & (pd.to_numeric(d["estimated_word_count"], errors="coerce") >= 500)]
    X = d[feats].astype(float).values
    y = zlog(d["wikiquote_count"]).values
    print(f"Training set: {len(d)} films, {len(feats)} script features")

    model = make_pipeline(StandardScaler(), ElasticNetCV(l1_ratio=[.2, .5, .7, .9],
                                                         cv=5, max_iter=5000))
    cv = KFold(5, shuffle=True, random_state=0)
    sci_oos = cross_val_predict(model, X, y, cv=cv)            # OUT-OF-SAMPLE SCI
    r2 = 1 - np.sum((y - sci_oos) ** 2) / np.sum((y - y.mean()) ** 2)
    print(f"Out-of-sample R² (script form -> realized quotability): {r2:.3f}")

    # refit on all data to read which features define compressibility
    model.fit(X, y)
    coefs = model.named_steps["elasticnetcv"].coef_
    imp = pd.Series(coefs, index=feats).sort_values(key=abs, ascending=False)
    print("\nFeatures defining empirical compressibility (standardized weights):")
    print(imp[imp.abs() > 1e-6].round(3).to_string())

    d["SCI_emp"] = (sci_oos - sci_oos.mean()) / sci_oos.std()
    df = df.merge(d[["title", "year", "SCI_emp"]], on=["title", "year"], how="left")

    # face validity
    print("\n--- Highest SCI_emp (predicted most quotable from script form) ---")
    print(d.sort_values("SCI_emp", ascending=False)[["title", "year"]].head(10).to_string(index=False))
    print("--- Lowest ---")
    print(d.sort_values("SCI_emp")[["title", "year"]].head(6).to_string(index=False))

    # ---- DECISIVE non-circular validity test on HELD-OUT outcomes -------------
    df["log_gross"] = zlog(df["worldwide_gross"]); df["log_budget"] = zlog(df["budget"])
    print("\n=== SCI_emp vs HELD-OUT outcomes (not used to build it), controls: box office + genre ===")
    for out in ["reddit_serp_log", "DIM_attention", "DIM_engagement", "DIM_symbolic_reuse"]:
        dd = df.dropna(subset=["SCI_emp", out, "log_gross", "genre"])
        m = smf.ols(f"{out} ~ SCI_emp + log_gross + log_budget + C(genre)", data=dd).fit(cov_type="HC3")
        b, p = m.params["SCI_emp"], m.pvalues["SCI_emp"]
        tag = "(construction target — circular)" if out == "DIM_symbolic_reuse" else "(held-out)"
        star = "***" if p < .01 else "**" if p < .05 else "*" if p < .1 else ""
        print(f"  {out:20} beta={b:+.3f}  p={p:.4f} {star:3} {tag}")

    df.to_csv(DATA / "analysis_dataset.csv", index=False)
    print("\nSaved SCI_emp -> analysis_dataset.csv")


if __name__ == "__main__":
    main()
