#!/usr/bin/env python3
"""
23_causal.py — three identification strategies for SCI -> cultural persistence
==============================================================================

Outcome of interest: DIM_symbolic_reuse (the dimension SCI moves; see 21). We push
from "SCI predicts" to "SCI plausibly causes", three complementary ways.

  (1) TEMPORAL precedence. SCI is fixed by the script at release; outcomes are
      measured in a recent (2023–26) window, years later. Regressing the outcome
      on SCI while controlling for *pre-release* factors (budget, gross, genre,
      age) rules out reverse causality (the outcome cannot have caused the script).
      Plus a persistence test on the monthly Wikipedia series: does SCI predict
      LATE-window attention controlling for EARLY-window attention?

  (2) INSTRUMENTAL VARIABLE. Genre writing conventions shape script structure
      (hence SCI) but, conditional on controls, should not affect long-run reuse
      except through that structure. Instrument SCI with the leave-one-out GENRE
      mean of dialogue-structure features. Report first-stage F (weak-iv check).

  (3) TRAILER-TIMING quasi-experiment. If compressibility compensates for lack of
      exposure, SCI should matter MORE when early exposure is LOW. Test the
      interaction SCI x (late/low trailer lead time) on the outcome.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from linearmodels.iv import IV2SLS

DATA = Path(__file__).resolve().parents[1] / "data"


def zlog(s):
    s = pd.to_numeric(s, errors="coerce"); return np.log1p(s.clip(lower=0))


def main():
    df = pd.read_csv(DATA / "analysis_dataset.csv")
    df["log_gross"] = zlog(df["worldwide_gross"])
    df["log_budget"] = zlog(df["budget"])
    Y = "DIM_symbolic_reuse"

    # ---------------------------------------------------------------- (1) TEMPORAL
    print("="*70, "\n(1) TEMPORAL PRECEDENCE  —  outcome:", Y)
    d = df.dropna(subset=["SCI_z", Y, "log_gross", "log_budget", "genre"]).copy()
    m = smf.ols(f"{Y} ~ SCI_z + log_gross + log_budget + years_since_release + C(genre)",
                data=d).fit(cov_type="HC3")
    print(f"  SCI fixed at release; controls are pre-release. n={int(m.nobs)}")
    print(f"  SCI_z beta = {m.params['SCI_z']:+.3f}  (p={m.pvalues['SCI_z']:.4f}, HC3)  R2={m.rsquared:.3f}")

    # persistence on the monthly Wikipedia series: late vs early window
    series = {}
    for rec in json.load((DATA / "live_api_data.json").open()):
        dp = (rec.get("metrics", {}) or {}).get("wikipedia_pageviews", {}).get("data_points") or []
        if len(dp) >= 12:
            v = [p.get("views", 0) for p in dp]
            half = len(v)//2
            series[(rec.get("movie_title"), rec.get("movie_year"))] = (sum(v[:half]), sum(v[half:]))
    df["wiki_early"] = [series.get((t, y), (np.nan, np.nan))[0] for t, y in zip(df.title, df.year)]
    df["wiki_late"]  = [series.get((t, y), (np.nan, np.nan))[1] for t, y in zip(df.title, df.year)]
    dp = df.dropna(subset=["SCI_z", "wiki_early", "wiki_late"]).copy()
    dp["log_late"], dp["log_early"] = zlog(dp.wiki_late), zlog(dp.wiki_early)
    mp = smf.ols("log_late ~ SCI_z + log_early + log_budget", data=dp).fit(cov_type="HC3")
    print(f"  persistence: late-window Wiki ~ SCI + early-window  (n={int(mp.nobs)}): "
          f"SCI beta={mp.params['SCI_z']:+.3f} (p={mp.pvalues['SCI_z']:.4f})")

    # ---------------------------------------------------------------- (2) IV / 2SLS
    print("="*70, "\n(2) INSTRUMENTAL VARIABLE (genre writing conventions)")
    iv = df.dropna(subset=["SCI_z", Y, "log_gross", "log_budget",
                           "avg_dialogue_length", "avg_sentence_complexity", "genre"]).copy()
    # leave-one-out genre mean of dialogue-structure features = the instrument
    for col in ["avg_dialogue_length", "avg_sentence_complexity", "vocabulary_richness"]:
        if col in iv.columns:
            g = iv.groupby("genre")[col]
            iv[f"z_{col}_genreLOO"] = (g.transform("sum") - iv[col]) / (g.transform("count") - 1)
    instr = [c for c in iv.columns if c.endswith("_genreLOO")]
    iv = iv.dropna(subset=instr)
    # first stage strength
    fs = smf.ols("SCI_z ~ " + " + ".join(instr) + " + log_gross + log_budget", data=iv).fit()
    fstat = fs.fvalue
    print(f"  instruments: {instr}")
    print(f"  first-stage R2={fs.rsquared:.3f}, overall F={fstat:.1f} (rule of thumb >10)")
    try:
        res = IV2SLS.from_formula(
            f"{Y} ~ 1 + log_gross + log_budget + [SCI_z ~ " + " + ".join(instr) + "]",
            data=iv).fit(cov_type="robust")
        b, p = res.params["SCI_z"], res.pvalues["SCI_z"]
        print(f"  2SLS SCI_z beta = {b:+.3f}  (p={p:.4f}, n={int(res.nobs)})")
    except Exception as e:
        print("  2SLS failed:", e)

    # ------------------------------------------------------- (3) TRAILER TIMING
    print("="*70, "\n(3) TRAILER-TIMING QUASI-EXPERIMENT (SCI x low early exposure)")
    t = df.dropna(subset=["SCI_z", Y, "yt_upload_lead_days", "log_gross"]).copy()
    # low early exposure = trailer dropped late (small lead). Median split + continuous.
    t["late_trailer"] = (t["yt_upload_lead_days"] <= t["yt_upload_lead_days"].median()).astype(int)
    mi = smf.ols(f"{Y} ~ SCI_z * late_trailer + log_gross + log_budget", data=t).fit(cov_type="HC3")
    print(f"  n={int(mi.nobs)}")
    print(f"  SCI_z (high-exposure films)        = {mi.params['SCI_z']:+.3f} (p={mi.pvalues['SCI_z']:.4f})")
    print(f"  SCI_z x late_trailer (extra effect)= {mi.params['SCI_z:late_trailer']:+.3f} "
          f"(p={mi.pvalues['SCI_z:late_trailer']:.4f})")
    tot = mi.params['SCI_z'] + mi.params['SCI_z:late_trailer']
    print(f"  => SCI effect when exposure is LOW = {tot:+.3f}  (compressibility compensates?)")
    print("="*70)


if __name__ == "__main__":
    main()
