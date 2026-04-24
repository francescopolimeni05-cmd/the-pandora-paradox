"""
Audit films with low wiki_views to detect Wikipedia redirect/disambiguation
traps similar to the Sleeping Beauty (1959) -> Tchaikovsky-ballet redirect bug.

Reads data/extended_api_data.json, lists every film with
total_views <= THRESHOLD, and prints whatever URL the collector ended up using
so the human can spot suspicious redirects (e.g. ballets, stage musicals, or
unrelated franchises hijacking the article).
"""
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")

THRESHOLD = 10_000


def main():
    path = os.path.join(DATA_DIR, "extended_api_data.json")
    with open(path, "r", encoding="utf-8") as f:
        recs = json.load(f)

    suspects = []
    for r in recs:
        m = r.get("metrics", {})
        wiki = m.get("wikipedia_pageviews", {})
        views = wiki.get("total_views")
        if views is None:
            continue
        if views <= THRESHOLD:
            suspects.append({
                "title": r.get("movie_title"),
                "year": r.get("movie_year"),
                "views": views,
                "wiki_title_used": wiki.get("wiki_title_used"),
                "wiki_langs": m.get("wikipedia_languages", {}).get("language_editions"),
                "status": wiki.get("status"),
            })

    suspects.sort(key=lambda x: x["views"])
    out_path = os.path.join(DATA_DIR, "audit_low_wiki_views.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"Films with wiki_views <= {THRESHOLD}: {len(suspects)}\n\n")
        for s in suspects:
            f.write(f"  views={s['views']:>8}  langs={s['wiki_langs']!s:>4}  "
                    f"{s['title']!r} ({s['year']})  -> "
                    f"wiki_title_used={s['wiki_title_used']!r}  "
                    f"status={s['status']}\n")
    print(f"Wrote {len(suspects)} entries to {out_path}")


if __name__ == "__main__":
    main()
