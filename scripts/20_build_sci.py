#!/usr/bin/env python3
"""
20_build_sci.py — Symbolic Compressibility Index (SCI)
======================================================

Formalizes the supervisor's mechanism: cultural persistence is driven not by raw
exposure but by whether a film yields small, emotionally salient, recombinable
symbolic units (quotes/phrases/fragments) that travel. SCI operationalizes that
"compressibility" from three script/subtitle signals already in the data:

    short_punchy_density   — share of short, punchy lines (quotable cadence)
    sentiment_spike        — abrupt emotional jumps (salient, clippable moments)
    rare_proper_noun_count — distinctive names/coinages (memetic handles)

Two constructions (report one as main, the other as robustness):
  SCI_z   = mean of z-scored components (transparent, equal-weight)
  SCI_pca = first principal component (data-driven weights)

Also folds in the SerpAPI Reddit discussion-volume signal collected for all films.
Outputs data/analysis_dataset.csv (the modelling table for the next steps).
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Scale-free compressibility signals. We use a length-normalized proper-noun
# DENSITY (not the raw count, which just tracks script length / blockbuster
# scale) and sentiment_spike (sentiment_peak is degenerate ~1.0 for everyone).
SCI_COMPONENTS = ["short_punchy_density", "sentiment_spike", "rare_pn_density"]


def main():
    df = pd.read_csv(DATA / "pandora_full_dataset_expanded.csv")

    # --- de-duplicate: a film that slipped in under two title strings (e.g.
    #     "X-Men: Dark Phoenix" vs "Dark Phoenix") = same TMDB id AND same year.
    #     Keep the lower-rank (original top-200) entry. Films that merely share an
    #     erroneous tmdb_id but differ in year (HTTYD2 2014 vs HTTYD3 2019) are NOT
    #     duplicates and are kept.
    if "tmdb_id" in df.columns:
        df = df.sort_values("rank")
        dup = df.duplicated(subset=["tmdb_id", "year"], keep="first") & df["tmdb_id"].notna()
        if dup.any():
            print("Removed duplicate film(s):", df.loc[dup, "title"].tolist())
            df = df[~dup].reset_index(drop=True)

    # --- harmonize the variables that were collected differently for old vs new
    #     films, using the uniform TMDB pass (26_collect_franchise.py). This makes
    #     genre, franchise, sequel and animation consistent across all 350 films.
    fu = DATA / "franchise_uniform.csv"
    if fu.exists():
        f = pd.read_csv(fu)
        df = df.merge(f, on=["title", "year"], how="left", suffixes=("", "_u"))
        df["genre"] = df["primary_genre"].where(
            df["primary_genre"].notna() & (df["primary_genre"].astype(str).str.strip() != ""),
            df["genre"])                       # uniform TMDB genre (fallback to legacy)
        df["has_franchise"] = df["in_franchise"].fillna(0).astype(int)
        df["is_sequel"] = (df["sequel_number"].fillna(0) > 0).astype(int)
        df["is_animated"] = df["is_animated_tmdb"].fillna(0).astype(int)
        print("Harmonized genre/franchise/sequel/animation from franchise_uniform.csv")
    else:
        print("NOTE: franchise_uniform.csv not found — genre/franchise still legacy "
              "(inconsistent old vs new). Run scripts/26_collect_franchise.py.")

    # Length-normalized proper-noun density (per 1,000 words): removes the
    # blockbuster-length confound that contaminated the raw count.
    wc = pd.to_numeric(df.get("estimated_word_count"), errors="coerce")
    df["rare_pn_density"] = pd.to_numeric(df["rare_proper_noun_count"], errors="coerce") / wc * 1000.0

    # Drop films whose subtitles failed to parse (degenerate all-zero rows, or
    # absurd word/line counts) — these are MISSING, not low-compressibility.
    bad = (
        (pd.to_numeric(df["dialogue_line_count"], errors="coerce") < 50)
        | (wc < 500)
        | ((df["short_punchy_density"].fillna(0) == 0)
           & (df["sentiment_spike"].fillna(0) == 0)
           & (df["rare_proper_noun_count"].fillna(0) == 0))
    )
    for c in SCI_COMPONENTS:
        df.loc[bad, c] = np.nan
    print(f"Excluded {int(bad.sum())} films with failed/degenerate subtitle parsing from SCI")

    # --- fold in Reddit discussion volume (SerpAPI), the uniform engagement signal
    serp_path = DATA / "reddit_serpapi.json"
    if serp_path.exists():
        serp = {(r["movie_title"], r.get("movie_year")): r.get("reddit_serp_results")
                for r in json.load(serp_path.open()) if r.get("status") == "success"}
        df["reddit_serp_volume"] = [
            serp.get((t, y)) for t, y in zip(df["title"], df["year"])
        ]
        df["reddit_serp_log"] = np.log1p(pd.to_numeric(df["reddit_serp_volume"], errors="coerce"))
        print(f"Reddit SerpAPI volume joined for {df['reddit_serp_volume'].notna().sum()}/{len(df)} films")

    # --- SCI on films with subtitle-derived features
    sub = df.dropna(subset=SCI_COMPONENTS).copy()
    X = sub[SCI_COMPONENTS].astype(float).values
    Xz = StandardScaler().fit_transform(X)

    # SCI_z : equal-weight mean of z-scores
    sub["SCI_z"] = Xz.mean(axis=1)

    # SCI_pca : first principal component (sign-aligned so higher = more compressible)
    pca = PCA(n_components=1)
    pc1 = pca.fit_transform(Xz)[:, 0]
    # orient so it correlates positively with short_punchy_density
    if np.corrcoef(pc1, Xz[:, 0])[0, 1] < 0:
        pc1 = -pc1
    sub["SCI_pca"] = pc1

    print("\n--- PCA on SCI components ---")
    print("explained variance ratio (PC1):", round(float(pca.explained_variance_ratio_[0]), 3))
    print("loadings (PC1):")
    for c, l in zip(SCI_COMPONENTS, pca.components_[0]):
        print(f"   {c:24} {l:+.3f}")
    print("corr(SCI_z, SCI_pca):", round(float(np.corrcoef(sub['SCI_z'], sub['SCI_pca'])[0, 1]), 3))

    # merge SCI back
    df = df.merge(sub[["title", "year", "SCI_z", "SCI_pca"]], on=["title", "year"], how="left")

    # --- quick face-validity: who scores highest / lowest on SCI?
    print("\n--- Highest SCI (most 'compressible' / quotable) ---")
    print(sub.sort_values("SCI_z", ascending=False)
          [["title", "year"] + SCI_COMPONENTS + ["SCI_z"]].head(12).to_string(index=False))
    print("\n--- Lowest SCI ---")
    print(sub.sort_values("SCI_z")
          [["title", "year", "SCI_z"]].head(8).to_string(index=False))

    # --- does SCI relate to cultural footprint? (descriptive, pre-causal)
    print("\n--- Correlations of SCI_z with cultural outcomes (Spearman) ---")
    for col in ["cultural_footprint_index", "cfi_score", "reddit_serp_log",
                "wikiquote_count", "reddit_engagement", "wiki_total_views",
                "worldwide_gross"]:
        if col in df.columns:
            s = df[["SCI_z", col]].apply(pd.to_numeric, errors="coerce").dropna()
            if len(s) > 10:
                rho = s.corr(method="spearman").iloc[0, 1]
                print(f"   SCI_z vs {col:28} rho = {rho:+.3f}  (n={len(s)})")

    out = DATA / "analysis_dataset.csv"
    df.to_csv(out, index=False)
    print(f"\nWrote modelling table ({df.shape[0]} films, {df.shape[1]} cols) -> {out.name}")


if __name__ == "__main__":
    main()
