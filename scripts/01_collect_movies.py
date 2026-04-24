"""
Phase 1 - Step 1: Collect Top 200 Films by Worldwide Box Office
Sources: Wikipedia list of highest-grossing films
"""

import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
import json
import time
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ============================================================
# 1. Scrape Wikipedia's list of highest-grossing films
# ============================================================

def get_top_grossing_films():
    """Scrape Wikipedia for top highest-grossing films worldwide."""
    url = "https://en.wikipedia.org/wiki/List_of_highest-grossing_films"
    headers = {"User-Agent": "PandoraParadoxCapstone/1.0 (Academic Research)"}

    resp = requests.get(url, headers=headers, timeout=30)
    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the main table (first wikitable with box office data)
    tables = soup.find_all("table", class_="wikitable")

    films = []
    for table in tables:
        rows = table.find_all("tr")
        headers_row = rows[0] if rows else None
        if not headers_row:
            continue

        ths = [th.get_text(strip=True).lower() for th in headers_row.find_all(["th", "td"])]

        # Check if this table has the right columns
        has_gross = any("gross" in h or "box" in h or "worldwide" in h for h in ths)
        has_title = any("title" in h or "film" in h for h in ths)

        if not (has_gross and has_title):
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue

            # Extract data based on column headers
            row_data = {}
            for i, cell in enumerate(cells):
                if i < len(ths):
                    text = cell.get_text(strip=True)
                    # Get link for title
                    link = cell.find("a")
                    if link and "title" in ths[i] or "film" in ths[i]:
                        row_data["wiki_link"] = link.get("href", "")
                    row_data[ths[i]] = text

            films.append(row_data)

        if len(films) >= 50:
            break

    return films


def parse_box_office_table(html_text):
    """More robust parsing of the Wikipedia box office table."""
    soup = BeautifulSoup(html_text, "html.parser")

    # The first sortable wikitable is usually the main one
    tables = soup.find_all("table", class_="wikitable sortable")
    if not tables:
        tables = soup.find_all("table", class_="wikitable")

    films = []

    for table in tables[:2]:  # Check first 2 tables
        rows = table.find_all("tr")
        if len(rows) < 10:
            continue

        # Parse header
        header_cells = rows[0].find_all(["th"])
        headers = [h.get_text(strip=True) for h in header_cells]

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            film = {}
            for i, cell in enumerate(cells):
                if i >= len(headers):
                    break
                text = cell.get_text(strip=True)
                header_name = headers[i] if i < len(headers) else f"col_{i}"
                film[header_name] = text

                # Get Wikipedia link
                link = cell.find("a")
                if link and link.get("href", "").startswith("/wiki/"):
                    if "title" not in film.get("_wiki_link", ""):
                        film["_wiki_link"] = "https://en.wikipedia.org" + link["href"]
                        film["_wiki_title"] = link.get("title", "")

            if film:
                films.append(film)

        if len(films) >= 50:
            break

    return films


def clean_money(value):
    """Parse money strings like '$2,923,706,026' or '$2.9 billion'."""
    if pd.isna(value) or not isinstance(value, str):
        return None
    value = value.replace(",", "").replace("$", "").strip()

    # Handle billion
    match = re.search(r"([\d.]+)\s*billion", value, re.IGNORECASE)
    if match:
        return float(match.group(1)) * 1_000_000_000

    # Handle million
    match = re.search(r"([\d.]+)\s*million", value, re.IGNORECASE)
    if match:
        return float(match.group(1)) * 1_000_000

    # Handle raw number
    match = re.search(r"[\d,]+", value.replace(",", ""))
    if match:
        try:
            return float(match.group().replace(",", ""))
        except ValueError:
            return None
    return None


def build_movie_database():
    """Build the initial movie database from Wikipedia."""
    print("Fetching top grossing films from Wikipedia...")
    url = "https://en.wikipedia.org/wiki/List_of_highest-grossing_films"
    headers = {"User-Agent": "PandoraParadoxCapstone/1.0 (Academic Research)"}

    resp = requests.get(url, headers=headers, timeout=30)
    films_raw = parse_box_office_table(resp.text)

    print(f"  Found {len(films_raw)} films in table")

    # Also get the budget information from a separate page
    budget_url = "https://en.wikipedia.org/wiki/List_of_most_expensive_films"
    budget_resp = requests.get(budget_url, headers=headers, timeout=30)
    budget_films = parse_box_office_table(budget_resp.text)
    print(f"  Found {len(budget_films)} films in budget table")

    return films_raw, budget_films


if __name__ == "__main__":
    grossing_raw, budget_raw = build_movie_database()

    # Save raw data
    pd.DataFrame(grossing_raw).to_csv(os.path.join(DATA_DIR, "raw_grossing.csv"), index=False)
    pd.DataFrame(budget_raw).to_csv(os.path.join(DATA_DIR, "raw_budget.csv"), index=False)

    print(f"\nSaved {len(grossing_raw)} grossing films and {len(budget_raw)} budget films")
    print("Files saved to data/raw_grossing.csv and data/raw_budget.csv")
