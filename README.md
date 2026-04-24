# The Pandora Paradox: Predicting Film Cultural Impact Through Data Integration

## Project Overview

**The Pandora Paradox** is a comprehensive data science project that investigates whether a film's **performance metrics** (box office revenue, budget, ratings) can reliably predict its **cultural impact** (Wikipedia pageviews, Reddit discussions, search trends, language editions).

The project challenges the assumption that box office success automatically translates to cultural relevance. Films like *The Room* (low budget, commercial failure) have achieved cult status and sustained cultural discussion, while some blockbusters fade from public memory despite massive revenue. This project quantifies and models these paradoxes.

### Key Research Questions

1. **Do blockbusters dominate cultural conversation?** - Compare Wikipedia pageviews and Reddit mentions for high vs. low-grossing films
2. **What drives sustained cultural interest?** - Identify which metrics best predict long-term Wikipedia engagement
3. **Can we predict a film's cultural impact?** - Build ML models using production data to forecast cultural metrics
4. **How does cultural impact correlate with critical reception?** - Analyze TMDB ratings vs. Wikipedia activity
5. **How does script complexity affect cultural reach?** - Correlate NLP features from scripts with cultural metrics

> **Recent additions (2026-04 onwards):** see [docs/PROGRESS.md](docs/PROGRESS.md) ([JA](docs/PROGRESS.ja.md)) for the live-API pipeline change log, and [docs/](docs/) for the team meeting brief and bilingual feature inventory. Original project docs are preserved under [docs/original_docs/](docs/original_docs/).

---

## Project Structure

```
Capstone/
├── data/
│   ├── top200_movies.csv              # Top 200 films by worldwide box office
│   ├── cultural_footprint.csv         # Wikipedia, Reddit, Trends metrics
│   ├── script_features.csv            # NLP features from movie scripts
│   ├── pandora_full_dataset.csv       # Integrated dataset (all metrics)
│   ├── live_api_data.json             # Raw API responses (generated)
│   └── model_predictions.csv          # ML model outputs
│
├── scripts/
│   ├── 01_collect_movies.py           # Phase 1: Scrape top 200 films
│   ├── 02_cultural_footprint.py       # Phase 2: Collect cultural metrics (legacy)
│   ├── 03_movie_scripts.py            # Phase 3: Scrape & analyze scripts
│   ├── 04_build_index.py              # Phase 4: Integrate all datasets
│   ├── 05_ml_model.py                 # Phase 5: Build predictive models
│   └── 06_live_data_collectors.py     # Phase 6: Live API collectors (new)
│
├── notebooks/
│   ├── 01_exploratory_analysis.ipynb  # Data exploration & visualization
│   ├── 02_cultural_paradoxes.ipynb    # Analysis of paradoxical cases
│   ├── 03_modeling.ipynb              # ML model development & evaluation
│   └── README.md                      # Notebook documentation
│
├── requirements.txt                    # Python dependencies
└── README.md                          # This file
```

---

## Data Sources

### 1. Box Office Data (Script 01)
- **Source**: Wikipedia list of highest-grossing films
- **Metrics**: Worldwide gross, domestic gross, budget, year, genre, franchise status
- **Coverage**: 200 films (1997-2024)

### 2. Wikipedia Activity (Script 06 - New)
- **Source**: Wikimedia REST API (no authentication required)
- **Endpoint**: `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/`
- **Metrics**:
  - Monthly pageviews (last 3 years)
  - Total views, average views, peak views
  - Language edition count
- **Rate Limit**: ~2 requests/second (1000 requests/hour)
- **Cost**: Free

### 3. Reddit Discussion (Script 06 - New)
- **Source**: Reddit search API (no authentication required)
- **Endpoint**: `https://www.reddit.com/search.json`
- **Metrics**:
  - Number of posts/discussions
  - Total comments and upvotes
  - Engagement metrics per post
- **Rate Limit**: 60 requests/minute
- **Cost**: Free

### 4. TMDB Movie Data (Script 06 - New)
- **Source**: The Movie Database API
- **Endpoint**: `https://api.themoviedb.org/3/search/movie`
- **Metrics**:
  - Budget and revenue (double-check against Wikipedia)
  - Popularity score
  - Vote average and count
  - Runtime, genres, production companies
- **Rate Limit**: 40 requests/10 seconds (free tier)
- **Cost**: Free (requires registration and API key)
- **API Key**: Get at https://www.themoviedb.org/settings/api

### 5. Google Trends (Script 06 - New)
- **Source**: Google Trends via `pytrends` library
- **Metrics**:
  - Search interest over time
  - Peak search interest date
  - Sustained vs. spike interest
- **Rate Limit**: ~1 request/second (with delays)
- **Cost**: Free
- **Note**: Uses web scraping, may break if Google changes page structure

### 6. Movie Scripts (Script 03 & 06)
- **Source**: IMSDb (Internet Movie Script Database)
- **URL**: `https://www.imsdb.com/scripts/`
- **Metrics**:
  - Script length (lines, characters)
  - Dialogue vs. action ratio
  - NLP features (sentiment, complexity, etc.)
- **Rate Limit**: ~1 request/second
- **Cost**: Free
- **Coverage**: ~30% of films have publicly available scripts

---

## Installation & Setup

### 1. Clone/Download Project
```bash
cd ~/Capstone
```

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 3. Get TMDB API Key (Optional)
- Visit: https://www.themoviedb.org/settings/api
- Register for free account
- Copy API key to use with `--api-key` flag

### 4. (Optional) Install Spacy Language Model
```bash
python -m spacy download en_core_web_sm
```

---

## Running the Scripts

### Phase 1: Collect Top 200 Films (Already Done)
```bash
cd scripts/
python 01_collect_movies.py
```
Outputs: `data/top200_movies.csv`

### Phase 2: Legacy Cultural Footprint Collection
```bash
python 02_cultural_footprint.py
```
Note: This script may have API issues; use Phase 6 instead.

### Phase 3: Scrape & Analyze Scripts
```bash
python 03_movie_scripts.py
```
Outputs: `data/script_features.csv`

### Phase 4: Integrate All Datasets
```bash
python 04_build_index.py
```
Outputs: `data/pandora_full_dataset.csv`

### Phase 5: Train ML Models
```bash
python 05_ml_model.py
```
Outputs: Trained models and predictions

### **Phase 6: Live Data Collection (NEW)**

#### Collect All Metrics (All Collectors)
```bash
python 06_live_data_collectors.py --api-key YOUR_TMDB_API_KEY
```

#### Collect Specific Metrics
```bash
# Wikipedia pageviews only
python 06_live_data_collectors.py --collector wikipedia_pageviews

# Reddit mentions
python 06_live_data_collectors.py --collector reddit_mentions

# TMDB data (requires API key)
python 06_live_data_collectors.py --collector tmdb_data --api-key YOUR_KEY

# Google Trends
python 06_live_data_collectors.py --collector google_trends

# IMSDb scripts
python 06_live_data_collectors.py --collector imsdb_script
```

#### Collect with Date Range
```bash
python 06_live_data_collectors.py \
  --collector wikipedia_pageviews \
  --start 2023-01-01 \
  --end 2026-01-01
```

#### Limit Number of Films
```bash
# Process first 10 films only (for testing)
python 06_live_data_collectors.py --limit 10
```

#### Full Example with All Options
```bash
python 06_live_data_collectors.py \
  --collector all \
  --api-key YOUR_TMDB_KEY \
  --start 2022-01-01 \
  --end 2026-01-01 \
  --output data/live_api_data.json \
  --limit 50
```

### Command-Line Reference for Script 06

| Option | Default | Description |
|--------|---------|-------------|
| `--collector` | `all` | Which collector(s) to run |
| `--start` | 3 years ago | Start date (YYYY-MM-DD) for time-series data |
| `--end` | Today | End date (YYYY-MM-DD) for time-series data |
| `--api-key` | None | TMDB API key (required for TMDB data) |
| `--output` | `data/live_api_data.json` | Output file path |
| `--limit` | None | Max films to process |

---

## Running Analysis Notebooks

### 1. Exploratory Analysis
```bash
jupyter notebook notebooks/01_exploratory_analysis.ipynb
```
Explore distributions, correlations, and basic statistics.

### 2. Cultural Paradoxes
```bash
jupyter notebook notebooks/02_cultural_paradoxes.ipynb
```
Analyze films that defy expectations (high box office, low cultural impact, etc.)

### 3. Predictive Modeling
```bash
jupyter notebook notebooks/03_modeling.ipynb
```
Build and evaluate ML models predicting cultural impact from production metrics.

---

## Key Findings (Preliminary)

### The Paradox Effect
- **High Box Office ≠ High Cultural Impact**: Some blockbusters (e.g., *Avatar*, *Avengers: Endgame*) dominate both metrics, but many high-grossing films have low Wikipedia engagement
- **Cult Classics**: Films like *The Room*, *Plan 9 from Outer Space* achieve sustained cultural discussion despite poor commercial performance
- **Language Edition Proxy**: Wikipedia language count correlates with both box office AND cultural engagement (r > 0.7)

### Wikipedia as Cultural Barometer
- Wikipedia pageviews show **seasonal spikes** (around anniversaries, sequels, awards)
- Peak pageviews don't correlate with peak popularity scores—different audiences
- Average monthly views (normalized by time since release) better predicts sustained impact than peak views

### Reddit as Demographic Filter
- Reddit discussions overrepresent **sci-fi and animation** genres
- Film franchises show **lower per-post engagement** than standalone films
- Top posts mention themes/memes rather than plot (indicates cultural penetration)

### Script Features
- **Dialogue percentage** correlates with Reddit engagement (high-dialogue films more discussable)
- **Script length** weakly correlates with box office but not with cultural impact
- **Complex vocabulary** (using NLP analysis) shows slight positive correlation with Wikipedia activity

---

## Data Processing Pipeline

```
Raw Data → Collectors → API Responses → Cleaning → Feature Engineering → Models
   ↓            ↓              ↓            ↓             ↓              ↓
Movies CSV  live_api_data   JSON files   CSV files    Full dataset   Predictions
```

### Output File Formats

**live_api_data.json** (Script 06 output):
```json
[
  {
    "movie_title": "Avatar",
    "movie_year": 2009,
    "collection_timestamp": "2026-03-27T12:34:56...",
    "metrics": {
      "wikipedia_pageviews": {
        "total_views": 15234567,
        "average_monthly_views": 423460,
        ...
      },
      "reddit_mentions": {
        "post_count": 1523,
        "total_comments": 45230,
        ...
      },
      ...
    }
  }
]
```

---

## Troubleshooting

### TMDB API Key Error
**Error**: `401 Unauthorized`
- **Solution**: Get free API key at https://www.themoviedb.org/settings/api and pass with `--api-key`

### Reddit 429 Too Many Requests
**Error**: Rate limit exceeded
- **Solution**: Script includes delays; reduce with `--limit` flag to test first

### Wikipedia Pageviews No Data
**Error**: Empty results for some films
- **Solution**: Some films may not have Wikipedia articles; this is normal. Check wiki_title formatting

### IMSDb Script Not Found
**Info**: Not all scripts available online
- **Solution**: Script returns gracefully; 30-40% coverage is expected

### pytrends Connection Issues
**Error**: Google Trends scraper fails
- **Solution**: Google may block requests; try again later or skip with individual `--collector` flag

### Memory Issues with Full Dataset
**Solution**:
1. Use `--limit` to process smaller batches
2. Delete intermediate files after integration
3. Run on machine with 8GB+ RAM

---

## Contributing & Extending

### Adding a New Collector

1. Create a function in `scripts/06_live_data_collectors.py`:
```python
def collect_new_metric(movie_title: str, movie_year: int) -> Dict:
    """Your docstring here."""
    try:
        # Your collection logic
        result = {
            "movie_title": movie_title,
            "metric": value,
            "status": "success"
        }
        return result
    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "error"}
```

2. Register in `collect_all_metrics()` function

3. Update `main()` argparse choices

4. Update this README with new source info

### Running on Cloud (AWS, GCP, Azure)

For large-scale collection:
1. Deploy script to cloud VM
2. Use cloud scheduler for periodic runs (e.g., monthly)
3. Store results in cloud storage (S3, GCS, Azure Blob)
4. Use cloud databases for incremental updates

Example (AWS EC2):
```bash
# SSH to instance
ssh -i key.pem ec2-user@instance-ip

# Run collection with nohup (survives disconnection)
nohup python 06_live_data_collectors.py --api-key YOUR_KEY > collection.log 2>&1 &
```

---

## Project Timeline

- **Phase 1** (Done): Collect top 200 films from Wikipedia
- **Phase 2** (Done): Legacy cultural metrics collection
- **Phase 3** (Done): Script scraping and NLP feature extraction
- **Phase 4** (Done): Dataset integration and cleaning
- **Phase 5** (Done): ML model development (regression, classification)
- **Phase 6** (New): Live API data collectors with error handling and incremental saves

---

## Team & Attribution

**Project**: The Pandora Paradox - Capstone Research
**Focus**: Data-driven cultural impact prediction
**Methods**: Web scraping, API integration, NLP, machine learning
**Tools**: Python, Pandas, Scikit-learn, TensorFlow

---

## References & Resources

- [Wikimedia REST API Docs](https://www.mediawiki.org/wiki/APIs)
- [TMDB API Documentation](https://developer.themoviedb.org/)
- [Reddit API Documentation](https://www.reddit.com/dev/api/)
- [IMSDb Database](https://www.imsdb.com/)
- [pytrends GitHub](https://github.com/GeneralMills/pytrends)
- [Beautiful Soup Documentation](https://www.crummy.com/software/BeautifulSoup/)

---

## License & Data Usage

- **Box office data**: Wikipedia (CC-BY-SA)
- **Wikipedia metrics**: Wikimedia (CC-BY-SA)
- **TMDB data**: TMDB Terms of Use (attribution required)
- **Reddit data**: Reddit Terms of Service
- **Scripts**: Copyright holders (fair use for research)

For any commercial use, review individual API terms of service.

---

**Last Updated**: March 27, 2026
**Status**: Active development
