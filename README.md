# Geopolitical Risk Dashboard

## Project Overview

The Geopolitical Risk Dashboard is a web application designed to display and analyze geopolitical risk factors based on various data sources. It aims to provide users with a visual understanding of global events and trends.

Key Features:
- **Daily Updates:** Data is fetched and processed daily to provide the latest insights.
- **GitHub Pages Hosting:** The dashboard is designed to be easily deployable via GitHub Pages.
- **Multiple Data Sources:** Integrates data from sources like GDELT, ACLED, and potentially others.

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

5.  **Configure environment variables:**
    Create a `.env` file in the project root and add the following variables. These are essential for the ETL script to access data APIs.
    ```env
    ACLED_TOKEN=your_acled_api_token
    OPENAI_API_KEY=your_openai_api_key
    ```
    *Note: Obtain these keys from the respective service providers.*

6.  **Run the ETL script:**
    This script fetches and processes data. As per recent updates, it should save its primary output to `static/data/latest.json` for the frontend and potentially archival data to `data/YYYY-MM-DD.json`.
    ```bash
    python etl.py
    ```

7.  **Run the frontend development server:**
    This will start a local server, typically at `http://localhost:5173`.
    ```bash
    npm run dev
    ```

8.  **Build the frontend for production:**
    This command compiles the Svelte app into static files (typically into a `build` directory if using SvelteKit with `adapter-static`), ready for deployment.
    ```bash
    npm run build
    ```

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
-   **ACLED (Armed Conflict Location & Event Data Project):** If using ACLED data, ensure adherence to their terms of service and citation requirements, typically available on the ACLED website. Be aware of any access tier limitations.
-   **OpenStreetMap:** Maps and geodata may utilize OpenStreetMap data. Data is available under the Open Data Commons Open Database License (ODbL). If you use map tiles from OpenStreetMap, ensure you attribute them correctly, usually with "© OpenStreetMap contributors".
-   **OpenAI:** If using OpenAI's API (e.g., for summarization or analysis), be mindful of their API usage policies, data privacy considerations, and associated costs.

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
├── src/
│   ├── components/      # Svelte components (Map, Timeseries, Hotlist)
│   │   ├── Hotlist.svelte
│   │   ├── Map.svelte
│   │   └── Timeseries.svelte
│   ├── App.svelte       # Main Svelte application component
├── .env.example         # Example environment variables file
├── etl.py               # Python script for Extract, Transform, Load processes
├── package.json         # Node.js project metadata and dependencies
├── svelte.config.js     # SvelteKit configuration (handles adapters like adapter-static)
├── vite.config.js       # Vite configuration for the SvelteKit frontend
├── README.md            # This file: project overview and instructions
├── requirements.txt     # Python dependencies for the ETL script
└── test_etl.py          # Pytest unit tests for etl.py
```
*Note: A `.env` file (not committed to the repository) should be present in the root directory for local development to store API keys and other secrets.*

*Further note on data paths: The `etl.py` script is responsible for generating `static/data/latest.json` (for the frontend) and potentially daily archive files like `data/YYYY-MM-DD.json`. The GitHub Actions workflow is configured to commit changes in both `static/data/` and `data/` directories.*