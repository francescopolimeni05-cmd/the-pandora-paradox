#!/usr/bin/env python3
"""
=============================================================================
THE PANDORA PARADOX — Real Data Collection Script
=============================================================================
Raccoglie dati REALI da API pubbliche per il capstone project.

USO:
    1. Installa dipendenze:
       pip install requests beautifulsoup4 pandas tqdm pytrends

    2. Ottieni una API key TMDB gratuita:
       https://www.themoviedb.org/settings/api

    3. Esegui:
       python collect_real_data.py --tmdb-key LA_TUA_API_KEY

    4. (Opzionale) Esegui solo un collector specifico:
       python collect_real_data.py --tmdb-key KEY --only tmdb
       python collect_real_data.py --only wikipedia
       python collect_real_data.py --only reddit
       python collect_real_data.py --only scripts

    5. (Opzionale) Testa con pochi film:
       python collect_real_data.py --tmdb-key KEY --limit 5

FONTI DATI:
    - TMDB API:           budget, revenue, ratings, popularity
    - Wikipedia REST API: pageviews mensili, numero lingue
    - Reddit JSON API:    menzioni, upvotes, commenti
    - IMSDB scraping:     script completi dei film

OUTPUT:
    data/real_tmdb_data.csv
    data/real_wikipedia_data.csv
    data/real_reddit_data.csv
    data/real_scripts_data.csv
    data/real_full_dataset.csv  (tutti i dati merged)
=============================================================================
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "PandoraParadoxCapstone/1.0 (Academic Research; Python/requests)"
}

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def save_progress(df, filename):
    """Salva il progresso corrente su disco (sovrascrive)."""
    path = os.path.join(DATA_DIR, filename)
    df.to_csv(path, index=False)


def load_progress(filename):
    """Carica progresso precedente se esiste."""
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        return pd.read_csv(path)
    return None


def wiki_title(movie_title, year):
    """Converte titolo film in titolo articolo Wikipedia."""
    # Mapping manuale per titoli ambigui
    manual = {
        "Avatar": "Avatar_(2009_film)",
        "Frozen": "Frozen_(2013_film)",
        "Frozen II": "Frozen_II",
        "Titanic": "Titanic_(1997_film)",
        "The Lion King": "The_Lion_King_(2019_film)",
        "The Lion King (1994)": "The_Lion_King",
        "Beauty and the Beast": "Beauty_and_the_Beast_(2017_film)",
        "Beauty and the Beast (1991)": "Beauty_and_the_Beast_(1991_film)",
        "It": "It_(2017_film)",
        "Up": "Up_(2009_film)",
        "Minions": "Minions_(film)",
        "Home": "Home_(2015_film)",
        "Brave": "Brave_(2012_film)",
        "Sing": "Sing_(2016_film)",
        "Coco": "Coco_(2017_film)",
        "Moana": "Moana_(2016_film)",
    }
    if movie_title in manual:
        return manual[movie_title]

    # Default: Title_(YEAR_film)
    safe = movie_title.replace(" ", "_")
    return f"{safe}_({year}_film)"


# ===========================================================================
# 1. TMDB COLLECTOR
# ===========================================================================

def collect_tmdb(movies_df, api_key, limit=None):
    """
    Raccoglie dati da TMDB API per ogni film.
    Restituisce: budget, revenue, vote_average, vote_count, popularity, genres, runtime, etc.
    """
    print("\n" + "="*60)
    print("  TMDB DATA COLLECTION")
    print("="*60)

    base_url = "https://api.themoviedb.org/3"
    results = []

    # Carica progresso precedente
    prev = load_progress("real_tmdb_data.csv")
    done_titles = set(prev["title"].tolist()) if prev is not None else set()

    films = movies_df.head(limit) if limit else movies_df

    for _, row in tqdm(films.iterrows(), total=len(films), desc="TMDB"):
        title = row["title"]
        year = int(row["year"])

        if title in done_titles:
            continue

        try:
            # Step 1: Search
            search = requests.get(
                f"{base_url}/search/movie",
                params={"api_key": api_key, "query": title, "year": year},
                headers=HEADERS, timeout=15
            )
            search.raise_for_status()
            search_results = search.json().get("results", [])

            if not search_results:
                # Retry senza anno
                search = requests.get(
                    f"{base_url}/search/movie",
                    params={"api_key": api_key, "query": title},
                    headers=HEADERS, timeout=15
                )
                search_results = search.json().get("results", [])

            if not search_results:
                print(f"  [!] Non trovato su TMDB: {title}")
                results.append({"title": title, "tmdb_found": False})
                time.sleep(0.3)
                continue

            movie_id = search_results[0]["id"]

            # Step 2: Dettagli
            details = requests.get(
                f"{base_url}/movie/{movie_id}",
                params={"api_key": api_key},
                headers=HEADERS, timeout=15
            ).json()

            results.append({
                "title": title,
                "tmdb_found": True,
                "tmdb_id": movie_id,
                "tmdb_budget": details.get("budget", 0),
                "tmdb_revenue": details.get("revenue", 0),
                "tmdb_vote_avg": details.get("vote_average", 0),
                "tmdb_vote_count": details.get("vote_count", 0),
                "tmdb_popularity": details.get("popularity", 0),
                "tmdb_runtime": details.get("runtime", 0),
                "tmdb_genres": "|".join(g["name"] for g in details.get("genres", [])),
                "tmdb_tagline": details.get("tagline", ""),
                "tmdb_original_language": details.get("original_language", ""),
                "tmdb_release_date": details.get("release_date", ""),
            })

        except Exception as e:
            print(f"  [!] Errore TMDB per {title}: {e}")
            results.append({"title": title, "tmdb_found": False, "tmdb_error": str(e)})

        time.sleep(0.3)  # Rate limit: ~3 req/sec

    df_new = pd.DataFrame(results)
    if prev is not None:
        df_new = pd.concat([prev, df_new], ignore_index=True).drop_duplicates(subset="title", keep="last")

    save_progress(df_new, "real_tmdb_data.csv")
    found = df_new["tmdb_found"].sum() if "tmdb_found" in df_new.columns else 0
    print(f"\n  Completato: {found}/{len(df_new)} film trovati su TMDB")
    return df_new


# ===========================================================================
# 2. WIKIPEDIA COLLECTOR
# ===========================================================================

def collect_wikipedia(movies_df, limit=None):
    """
    Raccoglie da Wikipedia:
    - Pageviews mensili (ultimi 3 anni)
    - Numero di edizioni linguistiche
    """
    print("\n" + "="*60)
    print("  WIKIPEDIA DATA COLLECTION")
    print("="*60)

    results = []
    prev = load_progress("real_wikipedia_data.csv")
    done_titles = set(prev["title"].tolist()) if prev is not None else set()

    films = movies_df.head(limit) if limit else movies_df

    # Date range: ultimi 3 anni
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=365*3)).strftime("%Y%m%d")

    for _, row in tqdm(films.iterrows(), total=len(films), desc="Wikipedia"):
        title = row["title"]
        year = int(row["year"])

        if title in done_titles:
            continue

        wiki_article = wiki_title(title, year)

        try:
            # --- Pageviews ---
            pv_url = (
                f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
                f"en.wikipedia/all-access/all-agents/{wiki_article}/monthly/{start_date}/{end_date}"
            )
            pv_resp = requests.get(pv_url, headers=HEADERS, timeout=15)

            if pv_resp.status_code == 200:
                pv_data = pv_resp.json().get("items", [])
                views = [item["views"] for item in pv_data]
                total_views = sum(views)
                avg_monthly = total_views / max(len(views), 1)
                peak_monthly = max(views) if views else 0
                recent_monthly = views[-1] if views else 0
            else:
                # Riprova con titolo semplice
                wiki_simple = title.replace(" ", "_")
                pv_url2 = (
                    f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
                    f"en.wikipedia/all-access/all-agents/{wiki_simple}/monthly/{start_date}/{end_date}"
                )
                pv_resp2 = requests.get(pv_url2, headers=HEADERS, timeout=15)
                if pv_resp2.status_code == 200:
                    pv_data = pv_resp2.json().get("items", [])
                    views = [item["views"] for item in pv_data]
                    total_views = sum(views)
                    avg_monthly = total_views / max(len(views), 1)
                    peak_monthly = max(views) if views else 0
                    recent_monthly = views[-1] if views else 0
                else:
                    total_views = avg_monthly = peak_monthly = recent_monthly = None
                    print(f"  [!] Pageviews non trovate per: {title} ({wiki_article})")

            # --- Language editions ---
            lang_url = "https://en.wikipedia.org/w/api.php"
            lang_params = {
                "action": "query",
                "titles": wiki_article.replace("_", " "),
                "prop": "langlinks",
                "lllimit": "500",
                "format": "json"
            }
            lang_resp = requests.get(lang_url, params=lang_params, headers=HEADERS, timeout=15)
            if lang_resp.status_code == 200:
                pages = lang_resp.json().get("query", {}).get("pages", {})
                page = list(pages.values())[0]
                lang_links = page.get("langlinks", [])
                n_languages = len(lang_links) + 1  # +1 per l'inglese
            else:
                n_languages = None

            results.append({
                "title": title,
                "wiki_article": wiki_article,
                "wiki_total_views_3y": total_views,
                "wiki_avg_monthly_views": round(avg_monthly) if avg_monthly else None,
                "wiki_peak_monthly_views": peak_monthly,
                "wiki_recent_monthly_views": recent_monthly,
                "wiki_n_languages": n_languages,
            })

        except Exception as e:
            print(f"  [!] Errore Wikipedia per {title}: {e}")
            results.append({"title": title, "wiki_error": str(e)})

        time.sleep(0.5)  # Rispetta i rate limits di Wikimedia

    df_new = pd.DataFrame(results)
    if prev is not None:
        df_new = pd.concat([prev, df_new], ignore_index=True).drop_duplicates(subset="title", keep="last")

    save_progress(df_new, "real_wikipedia_data.csv")
    ok = df_new["wiki_avg_monthly_views"].notna().sum() if "wiki_avg_monthly_views" in df_new.columns else 0
    print(f"\n  Completato: {ok}/{len(df_new)} film con pageviews")
    return df_new


# ===========================================================================
# 3. REDDIT COLLECTOR
# ===========================================================================

def collect_reddit(movies_df, limit=None):
    """
    Raccoglie menzioni e discussioni da Reddit (JSON API, no auth needed).
    Cerca il titolo del film su r/movies e search globale.
    """
    print("\n" + "="*60)
    print("  REDDIT DATA COLLECTION")
    print("="*60)

    results = []
    prev = load_progress("real_reddit_data.csv")
    done_titles = set(prev["title"].tolist()) if prev is not None else set()

    films = movies_df.head(limit) if limit else movies_df

    reddit_headers = {
        "User-Agent": "PandoraParadox:v1.0 (by /u/capstone_research)"
    }

    for _, row in tqdm(films.iterrows(), total=len(films), desc="Reddit"):
        title = row["title"]

        if title in done_titles:
            continue

        try:
            # Search Reddit per questo film
            search_query = f'"{title}" movie'
            search_url = "https://www.reddit.com/search.json"
            params = {
                "q": search_query,
                "limit": 100,
                "sort": "relevance",
                "t": "all"
            }

            resp = requests.get(search_url, params=params,
                              headers=reddit_headers, timeout=15)

            if resp.status_code == 200:
                data = resp.json().get("data", {})
                posts = data.get("children", [])

                total_posts = len(posts)
                total_upvotes = sum(p["data"].get("ups", 0) for p in posts)
                total_comments = sum(p["data"].get("num_comments", 0) for p in posts)
                avg_upvotes = total_upvotes / max(total_posts, 1)

                # Cerca anche su r/movies specificamente
                rmovies_url = "https://www.reddit.com/r/movies/search.json"
                rmovies_params = {
                    "q": title,
                    "restrict_sr": "on",
                    "limit": 100,
                    "sort": "relevance",
                    "t": "all"
                }
                rmovies_resp = requests.get(rmovies_url, params=rmovies_params,
                                           headers=reddit_headers, timeout=15)

                if rmovies_resp.status_code == 200:
                    rm_data = rmovies_resp.json().get("data", {})
                    rm_posts = rm_data.get("children", [])
                    rmovies_posts = len(rm_posts)
                    rmovies_upvotes = sum(p["data"].get("ups", 0) for p in rm_posts)
                else:
                    rmovies_posts = rmovies_upvotes = 0

                results.append({
                    "title": title,
                    "reddit_total_posts": total_posts,
                    "reddit_total_upvotes": total_upvotes,
                    "reddit_total_comments": total_comments,
                    "reddit_avg_upvotes": round(avg_upvotes, 1),
                    "reddit_rmovies_posts": rmovies_posts,
                    "reddit_rmovies_upvotes": rmovies_upvotes,
                })
            elif resp.status_code == 429:
                print(f"  [!] Reddit rate limit — aspetto 60 secondi...")
                time.sleep(60)
                continue
            else:
                print(f"  [!] Reddit errore {resp.status_code} per: {title}")
                results.append({"title": title, "reddit_error": f"HTTP {resp.status_code}"})

        except Exception as e:
            print(f"  [!] Errore Reddit per {title}: {e}")
            results.append({"title": title, "reddit_error": str(e)})

        time.sleep(2.0)  # Reddit è molto sensibile — 1 req/2sec

    df_new = pd.DataFrame(results)
    if prev is not None:
        df_new = pd.concat([prev, df_new], ignore_index=True).drop_duplicates(subset="title", keep="last")

    save_progress(df_new, "real_reddit_data.csv")
    ok = df_new["reddit_total_posts"].notna().sum() if "reddit_total_posts" in df_new.columns else 0
    print(f"\n  Completato: {ok}/{len(df_new)} film con dati Reddit")
    return df_new


# ===========================================================================
# 4. IMSDB SCRIPT SCRAPER
# ===========================================================================

def collect_scripts(movies_df, limit=None):
    """
    Scarica script dei film da IMSDB e calcola feature NLP.
    """
    print("\n" + "="*60)
    print("  IMSDB SCRIPT COLLECTION")
    print("="*60)

    results = []
    prev = load_progress("real_scripts_data.csv")
    done_titles = set(prev["title"].tolist()) if prev is not None else set()

    films = movies_df.head(limit) if limit else movies_df

    for _, row in tqdm(films.iterrows(), total=len(films), desc="IMSDB Scripts"):
        title = row["title"]

        if title in done_titles:
            continue

        try:
            # IMSDB URL format: https://imsdb.com/scripts/TITLE.html
            # I titoli su IMSDB usano trattini e formati particolari
            safe_title = title.replace(":", "").replace("'", "").replace(",", "")
            safe_title = safe_title.replace("  ", " ").replace(" ", "-")
            script_url = f"https://imsdb.com/scripts/{safe_title}.html"

            resp = requests.get(script_url, headers=HEADERS, timeout=15)

            if resp.status_code == 200 and len(resp.text) > 5000:
                soup = BeautifulSoup(resp.text, "html.parser")

                # Il testo dello script è dentro <pre> o nella classe "scrtext"
                script_pre = soup.find("pre")
                if not script_pre:
                    script_pre = soup.find("td", class_="scrtext")

                if script_pre:
                    script_text = script_pre.get_text()
                    features = analyze_script_text(script_text, title)
                    results.append(features)
                else:
                    print(f"  [!] Script trovato ma non parsabile: {title}")
                    results.append({"title": title, "script_found": False})
            else:
                # Prova con un URL alternativo
                alt_url = f"https://imsdb.com/scripts/{title.replace(' ', '-')}.html"
                resp2 = requests.get(alt_url, headers=HEADERS, timeout=15)
                if resp2.status_code == 200 and len(resp2.text) > 5000:
                    soup = BeautifulSoup(resp2.text, "html.parser")
                    script_pre = soup.find("pre") or soup.find("td", class_="scrtext")
                    if script_pre:
                        features = analyze_script_text(script_pre.get_text(), title)
                        results.append(features)
                    else:
                        results.append({"title": title, "script_found": False})
                else:
                    results.append({"title": title, "script_found": False})

        except Exception as e:
            print(f"  [!] Errore IMSDB per {title}: {e}")
            results.append({"title": title, "script_found": False, "script_error": str(e)})

        time.sleep(1.0)

    df_new = pd.DataFrame(results)
    if prev is not None:
        df_new = pd.concat([prev, df_new], ignore_index=True).drop_duplicates(subset="title", keep="last")

    save_progress(df_new, "real_scripts_data.csv")
    found = df_new["script_found"].sum() if "script_found" in df_new.columns else 0
    print(f"\n  Completato: {found}/{len(df_new)} script trovati")
    return df_new


def analyze_script_text(text, title):
    """
    Analizza il testo di uno script e restituisce feature NLP.
    """
    lines = text.strip().split("\n")
    lines = [l for l in lines if l.strip()]  # Rimuovi righe vuote

    total_words = len(text.split())

    # Identifica righe di dialogo vs azione/descrizione
    # In uno script: righe MAIUSCOLE sono nomi personaggi,
    # righe indentate dopo un nome sono dialogo,
    # righe non indentate senza nome sono descrizione/azione
    dialogue_lines = []
    action_lines = []
    character_names = set()
    current_is_dialogue = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Riga tutta maiuscola e corta -> probabilmente nome personaggio
        if stripped.isupper() and len(stripped.split()) <= 4 and not stripped.startswith("("):
            character_names.add(stripped)
            current_is_dialogue = True
            continue

        # Se la riga è centrata/indentata e siamo dopo un personaggio -> dialogo
        if current_is_dialogue and (line.startswith("    ") or line.startswith("\t")):
            dialogue_lines.append(stripped)
        else:
            action_lines.append(stripped)
            current_is_dialogue = False

    dialogue_text = " ".join(dialogue_lines)
    action_text = " ".join(action_lines)

    dialogue_words = len(dialogue_text.split())
    action_words = len(action_text.split())

    dialogue_pct = (dialogue_words / max(total_words, 1)) * 100
    action_pct = (action_words / max(total_words, 1)) * 100

    # Sentiment semplice (senza librerie pesanti)
    positive_words = set(["love", "happy", "great", "beautiful", "wonderful", "hope",
                          "amazing", "good", "best", "joy", "brave", "hero", "save",
                          "friend", "thank", "peace", "dream", "win", "free", "light"])
    negative_words = set(["kill", "die", "death", "hate", "war", "destroy", "fear",
                          "pain", "dark", "evil", "wrong", "lost", "never", "hell",
                          "blood", "fight", "enemy", "suffer", "broken", "dead"])

    words_lower = text.lower().split()
    pos_count = sum(1 for w in words_lower if w in positive_words)
    neg_count = sum(1 for w in words_lower if w in negative_words)
    sentiment = (pos_count - neg_count) / max(total_words, 1) * 100

    # Conteggi utili
    exclamations = sum(1 for l in dialogue_lines if "!" in l)
    questions = sum(1 for l in dialogue_lines if "?" in l)
    total_dial_lines = max(len(dialogue_lines), 1)

    # Vocabulary richness (type-token ratio)
    unique_words = len(set(words_lower))
    vocab_richness = unique_words / max(len(words_lower), 1)

    # Scene count (cerca "INT." e "EXT.")
    scene_count = sum(1 for l in lines if l.strip().startswith(("INT.", "EXT.", "INT ", "EXT ")))

    return {
        "title": title,
        "script_found": True,
        "script_word_count": total_words,
        "script_dialogue_pct": round(dialogue_pct, 1),
        "script_action_pct": round(action_pct, 1),
        "script_n_characters": len(character_names),
        "script_n_dialogue_lines": len(dialogue_lines),
        "script_n_action_lines": len(action_lines),
        "script_avg_dialogue_len": round(dialogue_words / max(len(dialogue_lines), 1), 1),
        "script_exclamation_ratio": round(exclamations / total_dial_lines, 3),
        "script_question_ratio": round(questions / total_dial_lines, 3),
        "script_vocab_richness": round(vocab_richness, 4),
        "script_sentiment_score": round(sentiment, 3),
        "script_scene_count": scene_count,
    }


# ===========================================================================
# 5. MERGE EVERYTHING
# ===========================================================================

def merge_all_data(movies_df):
    """Merge tutti i dataset raccolti in un unico CSV."""
    print("\n" + "="*60)
    print("  MERGING ALL DATA")
    print("="*60)

    df = movies_df.copy()

    for filename, label in [
        ("real_tmdb_data.csv", "TMDB"),
        ("real_wikipedia_data.csv", "Wikipedia"),
        ("real_reddit_data.csv", "Reddit"),
        ("real_scripts_data.csv", "Scripts"),
    ]:
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            extra = pd.read_csv(path)
            n_before = len(df.columns)
            df = df.merge(extra, on="title", how="left")
            print(f"  + {label}: {len(df.columns) - n_before} nuove colonne")
        else:
            print(f"  [!] {label}: file non trovato ({filename})")

    output_path = os.path.join(DATA_DIR, "real_full_dataset.csv")
    df.to_csv(output_path, index=False)
    print(f"\n  Dataset finale: {df.shape[0]} film x {df.shape[1]} colonne")
    print(f"  Salvato in: {output_path}")
    return df


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="The Pandora Paradox — Raccolta dati reali",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python collect_real_data.py --tmdb-key abc123          # Tutti i collector
  python collect_real_data.py --only wikipedia           # Solo Wikipedia (no key needed)
  python collect_real_data.py --only reddit              # Solo Reddit (no key needed)
  python collect_real_data.py --tmdb-key abc123 --limit 5  # Test con 5 film
        """
    )
    parser.add_argument("--tmdb-key", type=str, default=None,
                       help="API key di TMDB (gratuita, vedi themoviedb.org/settings/api)")
    parser.add_argument("--only", type=str, default=None,
                       choices=["tmdb", "wikipedia", "reddit", "scripts", "merge"],
                       help="Esegui solo un collector specifico")
    parser.add_argument("--limit", type=int, default=None,
                       help="Limita a N film (utile per test)")

    args = parser.parse_args()

    # Carica lista film
    movies_path = os.path.join(DATA_DIR, "top200_movies.csv")
    if not os.path.exists(movies_path):
        print(f"ERRORE: Non trovo {movies_path}")
        print("Assicurati di aver generato prima il file top200_movies.csv")
        sys.exit(1)

    movies = pd.read_csv(movies_path)
    movies = movies.drop_duplicates(subset="title", keep="first")
    print(f"\nCaricati {len(movies)} film da {movies_path}")

    collectors = {
        "tmdb": lambda: collect_tmdb(movies, args.tmdb_key, args.limit) if args.tmdb_key else print(
            "\n[!] TMDB saltato — fornisci --tmdb-key per raccogliere budget/revenue/ratings"),
        "wikipedia": lambda: collect_wikipedia(movies, args.limit),
        "reddit": lambda: collect_reddit(movies, args.limit),
        "scripts": lambda: collect_scripts(movies, args.limit),
        "merge": lambda: merge_all_data(movies),
    }

    if args.only:
        if args.only == "tmdb" and not args.tmdb_key:
            print("ERRORE: Il collector TMDB richiede --tmdb-key")
            sys.exit(1)
        collectors[args.only]()
    else:
        # Esegui tutti
        for name, fn in collectors.items():
            fn()

    print("\n" + "="*60)
    print("  COMPLETATO!")
    print("="*60)
    print(f"\n  I file sono in: {DATA_DIR}/")
    print("  Puoi ora eseguire il notebook di analisi con i dati reali.")


if __name__ == "__main__":
    main()
