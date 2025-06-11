# Geopolitical Risk Dashboard (地缘政治风险仪表盘)

## Project Overview (项目概述)

The Geopolitical Risk Dashboard is a web application designed to display and analyze geopolitical risk factors based on various data sources. It aims to provide users with a visual understanding of global events and trends.
(地缘政治风险仪表盘是一个旨在根据各种数据源显示和分析地缘政治风险因素的Web应用程序。它旨在为用户提供对全球事件和趋势的可视化理解。)

Key Features (主要特点):
- **Daily Updates (每日更新):** Data is fetched and processed daily to provide the latest insights. (每日获取和处理数据以提供最新的见解。)
- **GitHub Pages Hosting (GitHub Pages托管):** The dashboard is designed to be easily deployable via GitHub Pages. (仪表盘设计为可通过GitHub Pages轻松部署。)
- **Multiple Data Sources (多数据源):** Integrates data from sources like GDELT, ACLED, and potentially others. (集成来自GDELT、ACLED等多种来源的数据。)

## Local Setup and Running (本地设置与运行)

### Prerequisites (先决条件)

- Python (3.8+ recommended)
- Node.js and npm (LTS version recommended)

### Steps (步骤)

1.  **Clone the repository (克隆代码库):**
    ```bash
    git clone https://github.com/your-username/geopolitical-risk-dashboard.git
    cd geopolitical-risk-dashboard
    ```

2.  **Set up Python virtual environment (设置Python虚拟环境):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install Python dependencies (安装Python依赖):**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Install Node.js dependencies (安装Node.js依赖):**
    ```bash
    npm install
    ```

5.  **Configure environment variables (配置环境变量):**
    Create a `.env` file in the project root and add the following variables. These are essential for the ETL script to access data APIs.
    (在项目根目录创建一个`.env`文件，并添加以下变量。这些对于ETL脚本访问数据API至关重要。)
    ```env
    ACLED_TOKEN=your_acled_api_token
    OPENAI_API_KEY=your_openai_api_key
    ```
    *Note: Obtain these keys from the respective service providers.*
    (注意：请从各自的服务提供商处获取这些密钥。)

6.  **Run the ETL script (运行ETL脚本):**
    This script fetches and processes data, saving the output to `data/latest.json`.
    (此脚本获取并处理数据，将输出保存到`data/latest.json`。)
    ```bash
    python etl.py
    ```

7.  **Run the frontend development server (运行前端开发服务器):**
    This will start a local server, typically at `http://localhost:5173`.
    (这将启动一个本地服务器，通常在`http://localhost:5173`。)
    ```bash
    npm run dev
    ```

8.  **Build the frontend for production (构建生产版本的前端):**
    This command compiles the Svelte app into static files in the `dist` directory, ready for deployment.
    (此命令将Svelte应用程序编译为`dist`目录中的静态文件，以供部署。)
    ```bash
    npm run build
    ```

## Adding New Data Sources (添加新数据源)

To add new data sources, you will primarily need to modify the `etl.py` script.
(要添加新的数据源，您主要需要修改`etl.py`脚本。)
-   Look for sections related to data fetching and processing.
    (查找与数据获取和处理相关的部分。)
-   You'll need to implement new functions or classes to handle the API interaction, data transformation, and integration with the existing data structure.
    (您需要实现新的函数或类来处理API交互、数据转换以及与现有数据结构的集成。)

## Changing Schedule/Timezone (更改计划/时区)

The daily data update is managed by a GitHub Actions workflow defined in `.github/workflows/daily.yml`.
(每日数据更新由`.github/workflows/daily.yml`中定义的GitHub Actions工作流管理。)
-   The schedule is determined by the `cron` string within this file:
    (计划由该文件中的`cron`字符串确定：)
    ```yaml
    on:
      schedule:
        - cron: '0 1 * * *' # Runs at 01:00 UTC every day
    ```
-   **Important (重要):** Cron schedules in GitHub Actions are in UTC by default. Adjust the cron string according to UTC to match your desired local time.
    (GitHub Actions中的Cron计划默认为UTC。请根据UTC调整cron字符串以匹配您期望的本地时间。)

## Data Source Attribution and Licensing (数据源署名与许可)

-   **GDELT Project:** Data from the GDELT Project is available under an open data policy. Please refer to their website for specific terms and citation guidelines.
    (GDELT项目：来自GDELT项目的数据根据开放数据政策提供。具体条款和引用指南请参考其网站。)
-   **ACLED (Armed Conflict Location & Event Data Project):** We utilize the free access tier for ACLED data. Please adhere to their terms of service and citation requirements available on the ACLED website.
    (ACLED（武装冲突地点和事件数据项目）：我们使用ACLED数据的免费访问层。请遵守ACLED网站上提供的服务条款和引用要求。)
-   **OpenStreetMap:** Maps and geodata may utilize OpenStreetMap data. Data is available under the Open Data Commons Open Database License (ODbL). If you use map tiles from OpenStreetMap, you must attribute them with "© OpenStreetMap contributors".
    (OpenStreetMap：地图和地理数据可能使用OpenStreetMap数据。数据根据Open Data Commons Open Database License (ODbL)提供。如果您使用OpenStreetMap的地图瓦片，则必须注明“© OpenStreetMap contributors”。)
-   **OpenAI:** If using OpenAI's API (e.g., for summarization or analysis), be mindful of their API usage policies, data privacy considerations, and associated costs.
    (OpenAI：如果使用OpenAI的API（例如，用于摘要或分析），请注意其API使用政策、数据隐私注意事项以及相关成本。)

## Project Structure (项目结构)

```
.
├── .github/workflows/
│   └── daily.yml        # GitHub Actions workflow for daily ETL (每日ETL的GitHub Actions工作流)
├── data/
│   └── latest.json      # Stores the latest processed data (存储最新的已处理数据)
├── src/
│   ├── components/      # Svelte components (Svelte组件)
│   │   ├── Hotlist.svelte
│   │   ├── Map.svelte
│   │   └── Timeseries.svelte
│   ├── App.svelte       # Main Svelte application component (主要的Svelte应用组件)
├── .env.example         # Example environment variables (环境变量示例) - You should create a .env file
├── etl.py               # Python script for Extract, Transform, Load processes (用于提取、转换、加载过程的Python脚本)
├── package.json         # Node.js project metadata and dependencies (Node.js项目元数据和依赖项)
├── README.md            # This file (本项目自述文件)
├── requirements.txt     # Python dependencies (Python依赖项)
└── vite.config.js       # Vite configuration for the frontend (前端Vite配置)
```
*Note: A `.env` file (not committed to the repository) should be present in the root for local development to store API keys and other secrets.*
(注意：为了本地开发，根目录中应包含一个`.env`文件（不提交到代码库）以存储API密钥和其他秘密。)