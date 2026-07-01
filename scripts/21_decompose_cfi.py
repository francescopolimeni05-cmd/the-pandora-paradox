#!/usr/bin/env python3
"""
21_decompose_cfi.py — Decompose the Cultural Footprint Index into 4 dimensions
==============================================================================

Per the supervisor: stop treating cultural footprint as one number. Separate it
into four conceptual dimensions and test the symbolic-compressibility mechanism
(SCI) against each — expecting it to matter for SYMBOLIC REUSE and ENGAGEMENT,
not for institutional LEGITIMATION.

  1. Attention persistence   — Wikipedia views/languages, Google Trends
  2. Participatory engagement — Reddit discussion volume (SerpAPI), meme signal
  3. Institutional legitimation — awards, critic scores
  4. Symbolic reuse          — realized quotability (Wikiquote), meme reuse

Approach (both, per supervisor):
  (A) Theoretical 4 indices  — z-score & average the signals in each dimension.
  (B) Exploratory factor analysis — let the factors emerge from the data.
Then regress each dimension on SCI controlling for exposure (log box office).

NOTE: Wikipedia views are still affected by the disambiguation under-count for
~52 films until fix_wiki_views_bulk.py is run; the ATTENTION dimension will
sharpen after that. The symbolic-reuse / engagement tests do not depend on it.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
import statsmodels.formula.api as smf
from factor_analyzer import FactorAnalyzer

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def z(s):
    s = pd.to_numeric(s, errors="coerce")
    return (s - s.mean()) / s.std(ddof=0)


def zlog(s):
    return z(np.log1p(pd.to_numeric(s, errors="coerce").clip(lower=0)))


def main():
    df = pd.read_csv(DATA / "analysis_dataset.csv")

    # NOTE on data consistency (QA): meme_post_count & subreddit_diversity were
    # derived from the OLD Reddit-API post lists and are structurally 0 for the
    # 156 new films (which used SerpAPI). To keep dimensions comparable across the
    # whole sample we use ONLY signals collected uniformly for all 350 films, and
    # we WINSORIZE the SerpAPI Reddit volume (generic one-word titles like "Avatar"
    # over-count site:reddit.com hits).
    serp = df.get("reddit_serp_log")
    if serp is not None:
        lo, hi = serp.quantile(0.02), serp.quantile(0.98)
        df["reddit_serp_w"] = serp.clip(lo, hi)
        engagement_signal = z(df["reddit_serp_w"])
    else:
        engagement_signal = zlog(df["reddit_upvotes"])

    # ---- (A) Theoretical four indices (uniform signals only) -------------
    # wiki_languages dropped: it is 0 for ~74 refetched films (the title fix updated
    # views but not language counts) → not uniformly measured.
    df["DIM_attention"] = np.nanmean(np.vstack([
        zlog(df["wiki_total_views"]), z(df["gtrends_avg_interest"])]), axis=0)
    df["DIM_engagement"] = engagement_signal                       # Reddit discussion volume
    df["DIM_legitimation"] = np.nanmean(np.vstack([
        zlog(df["omdb_total_wins"]), zlog(df["omdb_total_nominations"]),
        z(df["metascore"]), z(df["imdb_rating"])]), axis=0)
    df["DIM_symbolic_reuse"] = zlog(df["wikiquote_count"])          # realized quotability

    dims = ["DIM_attention", "DIM_engagement", "DIM_legitimation", "DIM_symbolic_reuse"]
    print("=== (A) Theoretical dimensions — correlation matrix ===")
    print(df[dims].corr().round(2).to_string())

    # ---- (B) Exploratory factor analysis on the raw signals --------------
    signals = {
        "wiki_views": zlog(df["wiki_total_views"]), "wiki_langs": z(df["wiki_languages"]),
        "gtrends": z(df["gtrends_avg_interest"]),
        "reddit_vol": df.get("reddit_serp_log", zlog(df["reddit_upvotes"])),
        "memes": zlog(df["meme_post_count"]), "subreddit_div": z(df["subreddit_diversity"]),
        "awards_wins": zlog(df["omdb_total_wins"]), "awards_noms": zlog(df["omdb_total_nominations"]),
        "metascore": z(df["metascore"]), "imdb_rating": z(df["imdb_rating"]),
        "quotes": zlog(df["wikiquote_count"]),
    }
    S = pd.DataFrame(signals).dropna()
    fa = FactorAnalyzer(n_factors=4, rotation="varimax")
    fa.fit(S)
    load = pd.DataFrame(fa.loadings_, index=S.columns,
                        columns=[f"F{i+1}" for i in range(4)])
    print(f"\n=== (B) EFA (varimax, 4 factors, n={len(S)}) — loadings (|.|>0.35 shown) ===")
    print(load.round(2).where(load.abs() > 0.35, "").to_string())
    ev = fa.get_factor_variance()
    print("variance explained by factor:", np.round(ev[1], 3))

    # ---- Test SCI against each dimension, controlling for exposure -------
    df["log_gross"] = zlog(df["worldwide_gross"])
    print("\n=== SCI vs each dimension (OLS, controlling for log box office) ===")
    print(f"{'dimension':22} {'SCI beta':>9} {'p-value':>9} {'partial r':>10}")
    for dim in dims:
        d = df.dropna(subset=["SCI_z", dim, "log_gross"])
        m = smf.ols(f"{dim} ~ SCI_z + log_gross", data=d).fit()
        beta = m.params["SCI_z"]; p = m.pvalues["SCI_z"]
        # partial correlation of SCI with dim given log_gross
        rx = smf.ols("SCI_z ~ log_gross", data=d).fit().resid
        ry = smf.ols(f"{dim} ~ log_gross", data=d).fit().resid
        pr = np.corrcoef(rx, ry)[0, 1]
        star = "***" if p < .01 else "**" if p < .05 else "*" if p < .1 else ""
        print(f"{dim:22} {beta:>9.3f} {p:>9.4f} {pr:>+10.3f} {star}")

    df.to_csv(DATA / "analysis_dataset.csv", index=False)
    print(f"\nSaved dimensions + SCI tests -> analysis_dataset.csv")


if __name__ == "__main__":
    main()
