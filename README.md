# Geopolitical Risk Dashboard

## Project Overview

The Geopolitical Risk Dashboard is a web application designed to display and analyze geopolitical risk factors based on various data sources. It aims to provide users with a visual understanding of global events and trends.

Key Features:
- **Daily Updates:** Data is fetched and processed daily to provide the latest insights.
- **GitHub Pages Hosting:** The dashboard is designed to be easily deployable via GitHub Pages.
- **Data Source:** Events come from the GDELT 2.0 event export. Other sources can be added in `etl.py`.

## Local Setup and Running

### Prerequisites

- Python (3.8+ recommended)
- Node.js and npm (LTS version recommended)

### Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/geopolitical-risk-dashboard.git
    cd geopolitical-risk-dashboard
    ```

2.  **Set up Python virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Install Node.js dependencies:**
    ```bash
    npm install
    ```

5.  **Run the ETL script:**
    This script fetches and processes data. As per recent updates, it should save its primary output to `static/data/latest.json` for the frontend and potentially archival data to `data/YYYY-MM-DD.json`.
    ```bash
    python etl.py
    ```

6.  **Run the frontend development server:**
    This will start a local server, typically at `http://localhost:5173`.
    ```bash
    npm run dev
    ```

7.  **Build the frontend for production:**
    This command compiles the Svelte app into static files in the `build` directory (including a copy of `static/`), ready for deployment.
    ```bash
    npm run build
    ```

## Ticker: news and market indices

The bar under the header scrolls either the latest headlines or market index performance; the NEWS / MARKETS buttons switch between them. Both lists are set in `config.json` and refreshed by the daily ETL run:

- `news_feeds`: RSS or Atom feeds, each with a `name` and `url`. Written to `static/data/news.json`.
- `markets`: instruments to show, each with a display `name` and a Yahoo Finance `symbol` (for example `^GSPC`, `^TWII`, `GC=F`, `BTC-USD`, `2330.TW`). Written to `static/data/markets.json` with the latest daily price and the 1-day, 1-week and 1-month change.

Prices are as of the last ETL run, not live quotes: the close of each market's most recent session, or the price at fetch time for a market that was still trading. Market data comes from Yahoo Finance's unofficial chart endpoint, which has no service guarantee; when a source fails the previous file is kept.

## Event briefs

Hovering an entry in the target list or a marker on the map shows a brief: what happened (the CAMEO action for the event code, from `src/cameo.json`), where, who, when, tone and source. The target list shows one entry per source article and prefers events GDELT found in at least three articles, since thinly covered events are the ones most often miscoded. For the 20 highest-risk source articles the ETL also reads the page's title and description metadata and stores them as `headline` and `summary`.

## Adding New Data Sources

To add new data sources, you will primarily need to modify the `etl.py` script.
-   Focus on the sections related to data fetching and processing logic.
-   You'll likely need to implement new functions or classes to handle API interactions, data transformation, and integration with the existing data structure that `process_data` expects.

## Changing Schedule/Timezone

The daily data update is managed by a GitHub Actions workflow defined in `.github/workflows/daily.yml`.
-   The schedule is determined by the `cron` string within this file (e.g., `'30 0 * * *'` for 00:30 UTC).
-   **Important:** Cron schedules in GitHub Actions are in UTC by default. Adjust the cron string according to UTC to match your desired local time for the update. The `TZ: Asia/Taipei` environment variable in the workflow sets the timezone for the execution environment, which can be useful for scripts that rely on system time.

## Data Source Attribution and Licensing

-   **GDELT Project:** Data from the GDELT Project is available under an open data policy. Please refer to their website for specific terms and citation guidelines.
-   **Natural Earth:** The world outline is the public-domain Natural Earth 1:50m dataset, bundled through the `world-atlas` package.

## Project Structure

```
.
├── .github/workflows/
│   └── daily.yml        # GitHub Actions workflow for daily ETL, build, and deployment
├── data/                # Directory for archival data (e.g., daily JSON snapshots)
│   └── YYYY-MM-DD.json  # Example of a daily archived data file
├── static/              # Files served statically by the frontend
│   └── data/
│       └── latest.json  # The latest processed data, fetched by the frontend
│       └── history.json # 14-day average risk per day, built from data/ by the ETL
├── src/
│   ├── components/      # Svelte components (Map, Timeseries, Hotlist)
│   │   ├── Hotlist.svelte
│   │   ├── Map.svelte
│   │   └── Timeseries.svelte
│   ├── App.svelte       # Main Svelte application component
├── config.json          # News feeds and market symbols for the ticker
├── etl.py               # Python script for Extract, Transform, Load processes
├── package.json         # Node.js project metadata and dependencies
├── vite.config.js       # Vite configuration (serves static/ and builds into build/)
├── README.md            # This file: project overview and instructions
├── requirements.txt     # Python dependencies for the ETL script
└── test_etl.py          # Pytest unit tests for etl.py
```
*Further note on data paths: The `etl.py` script is responsible for generating `static/data/latest.json` (for the frontend) and potentially daily archive files like `data/YYYY-MM-DD.json`. The GitHub Actions workflow is configured to commit changes in both `static/data/` and `data/` directories.*

---

*Disclaimer: personal research/educational project. Not investment advice; no solicitation or recommendation of any security. Any figures are illustrative and hypothetical; past or backtested results do not indicate future performance.*