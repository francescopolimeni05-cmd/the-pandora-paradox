"""
Phase 2 - Build Cultural Footprint Index
Merge all datasets, normalize signals, create composite index.
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import os
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

def load_and_merge():
    """Load all 3 datasets and merge on title."""
    movies = pd.read_csv(os.path.join(DATA_DIR, "top200_movies.csv"))
    cultural = pd.read_csv(os.path.join(DATA_DIR, "cultural_footprint.csv"))
    scripts = pd.read_csv(os.path.join(DATA_DIR, "script_features.csv"))

    # Merge
    df = movies.merge(cultural, on="title", how="inner")
    df = df.merge(scripts, on="title", how="inner")

    print(f"Merged dataset: {df.shape[0]} films x {df.shape[1]} features")
    return df


def build_cultural_footprint_index(df):
    """
    Build a composite Cultural Footprint Index (CFI) from multiple signals.

    Components (weighted):
    1. Wikipedia presence (pageviews + languages): 20%
    2. Community engagement (Reddit + IMDb votes): 20%
    3. Long-term search interest (Google Trends sustained): 15%
    4. Fan ecosystem (Fandom wiki): 15%
    5. Quotability & memeability: 15%
    6. Merchandise/brand strength: 10%
    7. Awards recognition: 5%
    """
    scaler = MinMaxScaler()

    # Component 1: Wikipedia Presence (20%)
    df['wiki_presence_norm'] = scaler.fit_transform(
        np.log1p(df[['wikipedia_monthly_views']]))
    df['wiki_languages_norm'] = scaler.fit_transform(df[['wikipedia_languages']])
    df['comp_wikipedia'] = 0.6 * df['wiki_presence_norm'] + 0.4 * df['wiki_languages_norm']

    # Component 2: Community Engagement (20%)
    df['reddit_norm'] = scaler.fit_transform(
        np.log1p(df[['reddit_mentions_estimate']]))
    df['imdb_votes_norm'] = scaler.fit_transform(
        np.log1p(df[['imdb_votes']]))
    df['comp_community'] = 0.5 * df['reddit_norm'] + 0.5 * df['imdb_votes_norm']

    # Component 3: Long-term Search Interest (15%)
    df['comp_search'] = scaler.fit_transform(df[['google_trends_sustained']])

    # Component 4: Fan Ecosystem (15%)
    df['fandom_norm'] = scaler.fit_transform(
        np.log1p(df[['fandom_wiki_pages']]))
    df['comp_fandom'] = df['fandom_norm']

    # Component 5: Quotability & Memeability (15%)
    df['quot_norm'] = scaler.fit_transform(df[['quotability_score']])
    df['meme_norm'] = scaler.fit_transform(df[['meme_score']])
    df['comp_cultural_sticky'] = 0.5 * df['quot_norm'] + 0.5 * df['meme_norm']

    # Component 6: Merchandise (10%)
    df['comp_merch'] = scaler.fit_transform(df[['merchandise_index']])

    # Component 7: Awards (5%)
    df['awards_total'] = df['awards_nominations'] + df['awards_wins']
    df['comp_awards'] = scaler.fit_transform(
        np.log1p(df[['awards_total']]))

    # === COMPOSITE INDEX ===
    df['cultural_footprint_index'] = (
        0.20 * df['comp_wikipedia'] +
        0.20 * df['comp_community'] +
        0.15 * df['comp_search'] +
        0.15 * df['comp_fandom'] +
        0.15 * df['comp_cultural_sticky'] +
        0.10 * df['comp_merch'] +
        0.05 * df['comp_awards']
    )

    # Scale CFI to 0-100 for interpretability
    df['cfi_score'] = scaler.fit_transform(df[['cultural_footprint_index']]) * 100

    return df


def compute_box_office_efficiency(df):
    """
    Compute cultural impact relative to box office performance.
    This is the key metric for the Pandora Paradox.
    """
    # Normalize box office
    scaler = MinMaxScaler()
    df['box_office_norm'] = scaler.fit_transform(
        np.log1p(df[['worldwide_gross']]))

    # Cultural Efficiency = CFI / Box Office (normalized)
    # > 1 means overperforms culturally, < 1 means underperforms
    df['cultural_efficiency'] = df['cfi_score'] / (df['box_office_norm'] * 100 + 1)

    # Residual approach: OLS regression of CFI on box office, then residuals
    from sklearn.linear_model import LinearRegression
    X = df[['worldwide_gross', 'budget']].values
    X_log = np.log1p(X)
    y = df['cfi_score'].values

    reg = LinearRegression().fit(X_log, y)
    df['cfi_predicted'] = reg.predict(X_log)
    df['cfi_residual'] = df['cfi_score'] - df['cfi_predicted']

    # Positive residual = cultural overperformer
    # Negative residual = cultural underperformer (the "Pandora Paradox")
    df['cultural_category'] = pd.cut(
        df['cfi_residual'],
        bins=[-np.inf, -15, -5, 5, 15, np.inf],
        labels=['Strong Underperformer', 'Underperformer', 'As Expected',
                'Overperformer', 'Strong Overperformer']
    )

    return df


def main():
    # Load and merge
    df = load_and_merge()

    # Build CFI
    df = build_cultural_footprint_index(df)

    # Compute efficiency metrics
    df = compute_box_office_efficiency(df)

    # Save full dataset
    output_path = os.path.join(DATA_DIR, "pandora_full_dataset.csv")
    df.to_csv(output_path, index=False)

    # Print key findings
    print("\n" + "="*70)
    print("CULTURAL FOOTPRINT INDEX - KEY FINDINGS")
    print("="*70)

    print(f"\nDataset: {df.shape[0]} films, {df.shape[1]} features")
    print(f"CFI Score range: {df['cfi_score'].min():.1f} - {df['cfi_score'].max():.1f}")
    print(f"CFI Score mean: {df['cfi_score'].mean():.1f} (std: {df['cfi_score'].std():.1f})")

    print("\n--- TOP 10 by Cultural Footprint Index ---")
    top_cfi = df.nlargest(10, 'cfi_score')[['title', 'year', 'worldwide_gross', 'cfi_score', 'cfi_residual', 'cultural_category']]
    for _, row in top_cfi.iterrows():
        print(f"  {row['title']} ({row['year']}) - CFI: {row['cfi_score']:.1f}, "
              f"Box: ${row['worldwide_gross']/1e9:.2f}B, Residual: {row['cfi_residual']:+.1f} [{row['cultural_category']}]")

    print("\n--- TOP 10 CULTURAL OVERPERFORMERS (highest residual) ---")
    overperformers = df.nlargest(10, 'cfi_residual')[['title', 'year', 'worldwide_gross', 'cfi_score', 'cfi_residual']]
    for _, row in overperformers.iterrows():
        print(f"  {row['title']} ({row['year']}) - CFI: {row['cfi_score']:.1f}, "
              f"Box: ${row['worldwide_gross']/1e9:.2f}B, Residual: {row['cfi_residual']:+.1f}")

    print("\n--- TOP 10 CULTURAL UNDERPERFORMERS (lowest residual = Pandora Paradox) ---")
    underperformers = df.nsmallest(10, 'cfi_residual')[['title', 'year', 'worldwide_gross', 'cfi_score', 'cfi_residual']]
    for _, row in underperformers.iterrows():
        print(f"  {row['title']} ({row['year']}) - CFI: {row['cfi_score']:.1f}, "
              f"Box: ${row['worldwide_gross']/1e9:.2f}B, Residual: {row['cfi_residual']:+.1f}")

    # Avatar deep dive
    print("\n--- AVATAR DEEP DIVE ---")
    avatar = df[df['title'] == 'Avatar'].iloc[0]
    print(f"  Box Office: ${avatar['worldwide_gross']/1e9:.2f}B (Rank #{avatar['rank']:.0f})")
    print(f"  CFI Score: {avatar['cfi_score']:.1f} (Rank #{(df['cfi_score'] > avatar['cfi_score']).sum() + 1})")
    print(f"  CFI Residual: {avatar['cfi_residual']:+.1f}")
    print(f"  Category: {avatar['cultural_category']}")
    print(f"  Quotability: {avatar['quotability_score']}/10")
    print(f"  Meme Score: {avatar['meme_score']}/10")
    print(f"  Reddit Mentions: {avatar['reddit_mentions_estimate']:,.0f}")
    print(f"  Fandom Wiki Pages: {avatar['fandom_wiki_pages']:,.0f}")

    print(f"\nFull dataset saved to: {output_path}")

    return df


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(__file__)))
    df = main()
