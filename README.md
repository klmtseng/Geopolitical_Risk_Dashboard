# Geopolitical Risk Dashboard

## Project Overview

The Geopolitical Risk Dashboard shows where conflict-related activity is being reported around the world, ranked by how widely it is covered.

Key Features:
- **Hourly updates:** A scheduled workflow fetches every GDELT 2.0 event export published since its last run (one file per 15 minutes).
- **Hotspots, not single events:** Conflict events are grouped by place and kind of activity. A hotspot's rank depends on how many distinct news outlets reported it, because single GDELT events are often miscoded while widely reported ones rarely are.
- **Selectable time window:** 1 hour, 6 hours, 24 hours or 7 days, chosen in the page.
- **Surge indicator:** How a hotspot's coverage compares with earlier windows of the same length.
- **GitHub Pages hosting:** Built and deployed by the same workflow.

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

5. **Run the ETL script:**
    It keeps hourly state in `_state/state` and writes the files the frontend reads to `static/data` (both ignored by git). The first run fetches the last 24 hours of exports, later runs only what is new.
    ```bash
    python etl.py --state-dir _state/state --out-dir static/data
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

## Hotspot score

GDELT's machine coding is noisy: a single event row is frequently wrong about what happened. The dashboard therefore never ranks single events. Conflict events (CAMEO root codes 13–20: threats, protests, force posture, sanctions, coercion, assault, fighting, mass violence) are grouped into hotspots by country and root code (named after the place mentioned most), and each hotspot is scored 0–100 for the selected window:

`score = 100 × severity × coverage × actors`

- **severity**: mean Goldstein scale of the hotspot's events (0 to −10, as a fraction of 10).
- **coverage**: `1 − exp(−outlets / scale)`, where `outlets` is the number of distinct news domains reporting in the window. One outlet counts for little; many saturate. `scale` grows with the window length.
- **actors**: 0.2 when none of the events involves a state or armed actor (government, military, rebels, insurgents, separatists, intelligence, unaligned armed forces, intergovernmental bodies), rising to 1.0 once half of them do. Crime and culture-war stories are widely covered too, but rarely involve such actors.

**Surge** is the outlet count divided by the mean outlet count of up to six preceding windows of the same length. It is shown once at least three such windows have data.

The **threat index** is the mean score of the 20 highest hotspots; the trend chart shows it per UTC day.

Windows, coverage scales and retention can be overridden under an `etl` key in `config.json` (defaults: `DEFAULT_ETL_CONFIG` in `etl.py`).

## Where the data lives

Hourly aggregates and the published data files are kept on a separate branch, `etl-state`, as a single commit that the workflow replaces on every run, so hourly data does not accumulate in the history of `main`. Runs started from another branch use `etl-state-preview` and do not deploy.

## Event briefs

Hovering an entry in the target list or a marker on the map shows a brief: the kind of activity (from `src/cameo.json`), where, how many outlets and articles, the surge, severity, share of state or armed actors, tone and the most-covered source. For the best-covered article of the top hotspots in each window the ETL also reads the page's title and description metadata and stores them as `headline` and `summary`.

## Adding New Data Sources

To add new data sources, you will primarily need to modify the `etl.py` script.
-   Focus on the sections related to data fetching and processing logic.
-   You'll likely need to implement new functions or classes to handle API interactions, data transformation, and integration with the existing data structure that `process_data` expects.

## Changing Schedule/Timezone

The data update is managed by a GitHub Actions workflow defined in `.github/workflows/daily.yml`, scheduled hourly. GitHub can start scheduled runs late; the ETL catches up on whatever it missed.
-   The schedule is determined by the `cron` string within this file (`'47 * * * *'` runs every hour at minute 47; `'47 */6 * * *'` would run every six hours).
-   **Important:** Cron schedules in GitHub Actions are in UTC by default. Adjust the cron string according to UTC to match your desired local time for the update. The `TZ: Asia/Taipei` environment variable in the workflow sets the timezone for the execution environment, which can be useful for scripts that rely on system time.

## Data Source Attribution and Licensing

-   **GDELT Project:** Data from the GDELT Project is available under an open data policy. Please refer to their website for specific terms and citation guidelines.
-   **Natural Earth:** The world outline is the public-domain Natural Earth 1:50m dataset, bundled through the `world-atlas` package.

## Project Structure

```
.
├── .github/workflows/
│   └── daily.yml        # GitHub Actions workflow: hourly ETL, build and deployment
├── static/data/         # ETL output read by the frontend (git-ignored; produced by the workflow)
│   ├── hotspots.json    # Ranked hotspots for each time window
│   ├── history.json     # Threat index per UTC day
│   ├── news.json        # Ticker headlines
│   └── markets.json     # Ticker market indices
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
---

*Disclaimer: personal research/educational project. Not investment advice; no solicitation or recommendation of any security. Any figures are illustrative and hypothetical; past or backtested results do not indicate future performance.*