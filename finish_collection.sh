#!/usr/bin/env bash
# ============================================================
# finish_collection.sh — completa la raccolta da DOVE si era fermata
# (step 6 Reddit -> 7 Trends/YouTube -> 8 build) in modo HANDS-OFF.
#
# - I collector SerpAPI (Reddit e Trends) si mettono in pausa da soli quando
#   toccano il limite di 200 ricerche/ora, e riprendono. Nessun errore ferma il
#   processo: ogni step e' tollerante e tutto e' loggato su collection_overnight.log.
# - Lanci la sera, vai a dormire, la mattina trovi pandora_full_dataset_expanded.csv.
#
#   bash finish_collection.sh
# ============================================================
cd "$(dirname "$0")"
[[ -f .env ]] || { echo "ERRORE: manca .env"; exit 1; }
set -a; source .env; set +a
export PYTHONUNBUFFERED=1          # mostra le stampe in tempo reale (niente buffering)
PY="${PYTHON:-python} -u"
LOG=collection_overnight.log
# tutto a schermo E su file di log
exec > >(tee -a "$LOG") 2>&1

say(){ printf "\n\033[1;36m==> %s  [%s]\033[0m\n" "$1" "$(date '+%Y-%m-%d %H:%M')"; }

# Riprova un comando fino a N volte (pausa 10 min) finche' non esce con successo.
# Rete di sicurezza: i collector si auto-gestiscono gia' il limite orario.
retry(){
  local n=$1; shift; local i=0
  until "$@"; do
    i=$((i+1))
    if [[ $i -ge $n ]]; then echo "   (rinuncio dopo $n tentativi: $*)"; return 1; fi
    echo "   ...errore/limite: riprovo tra 10 minuti ($i/$n)"; sleep 600
  done
}

say "INIZIO raccolta notturna"

say "STEP 6/8  Reddit discussion volume (SerpAPI — auto-pausa sul limite orario)"
retry 8 $PY scripts/08b_reddit_serpapi.py --input data/all_movies.csv \
    --output data/reddit_serpapi.json || echo "   WARN: Reddit incompleto (proseguo)."

say "STEP 7/8  Google Trends (SerpAPI — auto-pausa) + YouTube"
retry 8 $PY scripts/07_google_trends_serpapi.py || echo "   WARN: Trends incompleto (proseguo)."
$PY scripts/07_google_trends_serpapi.py --merge || echo "   WARN: Trends merge."
$PY scripts/09_youtube_trailer_views.py || echo "   WARN: YouTube views (quota?)."
$PY scripts/09_youtube_trailer_views.py --merge || echo "   WARN: YouTube views merge."
$PY scripts/07_youtube_trailer_collector.py --input data/live_api_data.json \
    --output data/youtube_data.json --resume || echo "   WARN: YouTube trailer (quota?)."

say "STEP 8/8  Build del dataset finale"
$PY scripts/12_merge_and_build.py build || echo "   WARN: build fallito — controlla il log."

say "FATTO"
echo "Output atteso: data/pandora_full_dataset_expanded.csv"
echo "Log completo: collection_overnight.log"
