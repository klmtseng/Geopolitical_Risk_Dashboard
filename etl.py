import requests
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote
from xml.etree import ElementTree
import os
import json
import re


def previous_gdelt_export_url(export_url):
    """
    Returns the URL of the export published 15 minutes before `export_url`,
    or None if the URL does not carry a YYYYMMDDHHMMSS timestamp.
    """
    match = re.search(r"(\d{14})(?=\.export\.CSV\.zip)", export_url)
    if not match:
        return None
    previous = datetime.strptime(match.group(1), "%Y%m%d%H%M%S") - timedelta(minutes=15)
    return export_url[:match.start()] + previous.strftime("%Y%m%d%H%M%S") + export_url[match.end():]


def download_gdelt_export(export_url, max_fallbacks=3):
    """
    Downloads a GDELT export zip. lastupdate.txt can list a file a moment before
    it is actually published, which gives a 404; in that case fall back to the
    preceding 15-minute exports instead of ending the run with no data.
    """
    url = export_url
    for attempt in range(max_fallbacks + 1):
        resp = requests.get(url, timeout=60)
        previous_url = previous_gdelt_export_url(url)
        if resp.status_code == 404 and attempt < max_fallbacks and previous_url:
            print(f"GDELT export not published yet ({url}); trying {previous_url}")
            url = previous_url
            continue
        resp.raise_for_status()
        return resp


def fetch_gdelt_events():
    """
    Fetches events from the GDELT 2.0 Event database via the 15-minute CSV dump.
    Uses the lastupdate.txt index to find the latest export file and parses the
    relevant columns (EventCode, EventBaseCode, QuadClass, ActionGeo coords,
    AvgTone, SOURCEURL, Day) from the tab-delimited CSV.
    Returns a list of dicts compatible with the downstream process_data() schema.
    """
    import csv
    import io
    import zipfile

    print("Fetching GDELT events via v2 CSV dump...")

    LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"

    # GDELT v2 export CSV column indices (0-based, 61 columns total, no header row)
    COL = {
        "Day": 1,
        "Actor1Code": 5,
        "Actor1Name": 6,
        "Actor1CountryCode": 7,
        "Actor1Type1Code": 12,
        "Actor1Type2Code": 13,
        "Actor1Type3Code": 14,
        "Actor2Code": 15,
        "Actor2Name": 16,
        "Actor2CountryCode": 17,
        "Actor2Type1Code": 22,
        "Actor2Type2Code": 23,
        "Actor2Type3Code": 24,
        "NumArticles": 33,
        "ActionGeo_FullName": 52,
        "IsRootEvent": 25,
        "EventCode": 26,
        "EventBaseCode": 27,
        "QuadClass": 29,
        "AvgTone": 34,
        "Actor1Geo_Lat": 40,
        "Actor1Geo_Long": 41,
        "Actor2Geo_Lat": 48,
        "Actor2Geo_Long": 49,
        "ActionGeo_CountryCode": 53,
        "ActionGeo_Lat": 56,
        "ActionGeo_Long": 57,
        "SOURCEURL": 60,
    }

    all_events = []
    try:
        # Step 1: Get the URL of the latest export CSV zip
        resp = requests.get(LASTUPDATE_URL, timeout=30)
        resp.raise_for_status()
        export_url = None
        for line in resp.text.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 3 and "export.CSV.zip" in parts[2]:
                export_url = parts[2]
                break
        if not export_url:
            print("ERROR: Could not parse export URL from lastupdate.txt")
            return all_events

        print(f"GDELT CSV URL: {export_url}")

        # Step 2: Download and unzip
        resp2 = download_gdelt_export(export_url)
        with zipfile.ZipFile(io.BytesIO(resp2.content)) as zf:
            csv_filename = zf.namelist()[0]
            with zf.open(csv_filename) as f:
                text = f.read().decode("utf-8", errors="replace")

        # Step 3: Parse TSV (no header row)
        reader = csv.reader(io.StringIO(text), delimiter="\t")
        row_count = 0
        for row in reader:
            if len(row) < 61:
                continue
            row_count += 1
            event = {
                "Day": row[COL["Day"]],
                "Actor1Name": row[COL["Actor1Name"]],
                "Actor2Name": row[COL["Actor2Name"]],
                **{
                    key: row[COL[key]]
                    for key in (
                        "Actor1Code", "Actor1CountryCode", "Actor1Type1Code", "Actor1Type2Code", "Actor1Type3Code",
                        "Actor2Code", "Actor2CountryCode", "Actor2Type1Code", "Actor2Type2Code", "Actor2Type3Code",
                    )
                },
                "NumArticles": row[COL["NumArticles"]],
                "ActionGeo_FullName": row[COL["ActionGeo_FullName"]],
                "IsRootEvent": row[COL["IsRootEvent"]],
                "EventCode": row[COL["EventCode"]],
                "EventBaseCode": row[COL["EventBaseCode"]],
                "QuadClass": row[COL["QuadClass"]],
                "AvgTone": row[COL["AvgTone"]],
                "Actor1Geo_Lat": row[COL["Actor1Geo_Lat"]],
                "Actor1Geo_Long": row[COL["Actor1Geo_Long"]],
                "Actor2Geo_Lat": row[COL["Actor2Geo_Lat"]],
                "Actor2Geo_Long": row[COL["Actor2Geo_Long"]],
                "ActionGeo_CountryCode": row[COL["ActionGeo_CountryCode"]],
                "ActionGeo_Lat": row[COL["ActionGeo_Lat"]],
                "ActionGeo_Long": row[COL["ActionGeo_Long"]],
                "SOURCEURL": row[COL["SOURCEURL"]],
            }
            all_events.append(event)

        print(f"Successfully parsed {len(all_events)} events from GDELT CSV ({row_count} rows read).")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching GDELT data: {e}")
    except zipfile.BadZipFile as e:
        print(f"Error unzipping GDELT CSV: {e}")
    except Exception as e:
        print(f"Unexpected error in fetch_gdelt_events: {e}")

    return all_events

# CAMEO actor types that make an event geopolitical rather than local:
# government, military, rebels, insurgents, separatists, state intelligence,
# unaligned armed forces and intergovernmental organisations.
STRATEGIC_ACTOR_TYPES = {"GOV", "MIL", "REB", "INS", "SEP", "SPY", "UAF", "IGO"}

LOCAL_ACTOR_FACTOR = 0.4   # weight kept for events with no state or armed actor
CROSS_BORDER_BONUS = 15    # added when state/armed actors of two countries are involved


def _actor_kind(event, n):
    """Classifies actor `n` (1 or 2) of a raw GDELT event as 'strategic', 'local' or None."""
    if not event.get(f"Actor{n}Code"):
        return None
    types = {event.get(f"Actor{n}Type{i}Code") for i in (1, 2, 3)} - {None, ""}
    if types & STRATEGIC_ACTOR_TYPES:
        return "strategic"
    if not types and event.get(f"Actor{n}CountryCode"):
        return "strategic"  # a bare country code is how GDELT records a state acting
    return "local"


def actor_profile(event):
    """
    Returns (weight_factor, bonus, label) describing who is involved.

    The event code alone cannot tell a border clash from a police shootout, so
    the conflict weight is reduced when no state or armed actor takes part and
    a bonus is added when such actors of two different countries are involved.
    Events without any actor codes (older data, tests) are scored as before.
    """
    kinds = [_actor_kind(event, 1), _actor_kind(event, 2)]
    if kinds == [None, None]:
        return 1.0, 0, None
    if "strategic" not in kinds:
        return LOCAL_ACTOR_FACTOR, 0, "local"
    countries = {event.get("Actor1CountryCode"), event.get("Actor2CountryCode")} - {None, ""}
    if len(countries) == 2:
        return 1.0, CROSS_BORDER_BONUS, "cross-border"
    return 1.0, 0, "state or armed"


def calculate_risk_score(tone, event_base_code, weight_factor=1.0, bonus=0):
    """
    Calculates a risk score based on GDELT tone and event base code.
    `weight_factor` scales the event-code weight and `bonus` is added on top
    (see actor_profile). Score is capped at 100.
    """
    normalized_tone_score = 0
    if tone is not None:
        try:
            # AvgTone range is typically -100 to +100.
            # Abs(Tone) makes it 0 to 100.
            # Scale this to 0-50 for its contribution to the risk score.
            normalized_tone_score = abs(float(tone)) / 2.0
        except ValueError:
            normalized_tone_score = 0 # Default if tone is not a valid number

    conflict_weights = {
        # Violent events (higher weights)
        '18': 40, # Assault (includes various forms of physical attack)
        '19': 50, # Fight (armed conflict, clashes)
        '20': 50, # Mass violence (genocide, mass killings) - very high impact
        # Protests (moderate weights)
        '14': 20, # Protest (demonstrations, riots)
        # Other potentially relevant categories (lower weights)
        '10': 15, # Demand (ultimatums, threats)
        '13': 10, # Appeal (requests for aid, resources, not inherently conflict but can indicate instability)
        '04': 5,  # Consult (diplomatic meetings, could be positive or negative context)
    }

    conflict_weight_score = 0
    if event_base_code:
        # Check first two digits for broader categories, or full code if specific
        code_prefix = str(event_base_code)[:2]
        conflict_weight_score = conflict_weights.get(code_prefix, 0)

    # The bonus only applies to events that carry a conflict weight at all.
    actor_part = conflict_weight_score * weight_factor + (bonus if conflict_weight_score else 0)
    risk_score = min(normalized_tone_score + actor_part, 100) # Cap at 100
    return round(risk_score)


def process_data(gdelt_data):
    """
    Normalizes GDELT events into the schema the frontend expects.
    """
    unified_data = []
    current_time_iso = datetime.utcnow().isoformat() + "Z"

    # Process GDELT Data
    for event in gdelt_data:
        lat = event.get("ActionGeo_Lat") or event.get("Actor1Geo_Lat") or event.get("Actor2Geo_Lat")
        lon = event.get("ActionGeo_Long") or event.get("Actor1Geo_Long") or event.get("Actor2Geo_Long")

        # GDELT 'Day' is YYYYMMDD, SOURCEURL often has more precise time if needed, but less reliable to parse
        # For now, using the 'Day' and setting time to midnight.
        # A more robust solution would be to parse GDELT's 15-min interval timestamp if available.
        timestamp_str = str(event.get("Day", ""))
        timestamp = current_time_iso # Default
        if timestamp_str:
            try:
                # Assuming Day is YYYYMMDD, create datetime and then ISO format
                dt_obj = datetime.strptime(timestamp_str, "%Y%m%d")
                timestamp = dt_obj.isoformat() + "Z"
            except ValueError:
                pass # Keep default if parsing fails

        weight_factor, bonus, actor_class = actor_profile(event)
        risk_score = calculate_risk_score(event.get("AvgTone"), event.get("EventBaseCode"), weight_factor, bonus)

        tag = "neutral" # Default tag
        event_base_code_prefix = str(event.get("EventBaseCode",""))[:2]
        if event_base_code_prefix in ['18', '19', '20']:
            tag = "conflict"
        elif event_base_code_prefix in ['14', '10']:
            tag = "protest"

        # GDELT uses FIPS country codes. For simplicity, we'll use it directly.
        # Mapping to ISO3 would require a conversion table.
        country_code = event.get("ActionGeo_CountryCode", "Unknown")

        if lat and lon: # Only include if we have geo-coordinates
            item = {
                "timestamp": timestamp,
                "country": country_code,
                "lat": float(lat),
                "lon": float(lon),
                "risk_score": risk_score,
                "title": f"GDELT Event: {event.get('EventBaseCode', 'N/A')} in {country_code}", # More descriptive title
                "source_url": event.get("SOURCEURL", ""),
                "tag": tag
            }
            # Optional context for the frontend's hover brief
            if event.get("EventBaseCode"):
                item["event_code"] = str(event["EventBaseCode"])
            if event.get("ActionGeo_FullName"):
                item["location"] = event["ActionGeo_FullName"]
            actors = [a.title() for a in (event.get("Actor1Name"), event.get("Actor2Name")) if a]
            if actors:
                item["actors"] = actors
            if actor_class:
                item["actor_class"] = actor_class
            tone = _to_float(event.get("AvgTone"))
            if tone is not None:
                item["tone"] = round(tone, 1)
            articles = _to_float(event.get("NumArticles"))
            if articles is not None:
                item["articles"] = int(articles)
            unified_data.append(item)

    return unified_data


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --- Article headlines and summaries for the highest-risk events ---

USER_AGENT = "Mozilla/5.0 (compatible; geopolitical-risk-dashboard-etl)"
MAX_HEADLINE_CHARS = 160
MAX_SUMMARY_CHARS = 280


class _MetaParser(HTMLParser):
    """Collects <title> and description/OpenGraph meta tags from an HTML page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            attrs = dict(attrs)
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            content = attrs.get("content")
            if key and content and key not in self.meta:
                self.meta[key] = content

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def _clean_text(text, limit):
    """Collapses whitespace, drops markup, and truncates on a word boundary."""
    text = re.sub(r"<[^>]+>", " ", unescape(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
    return text


def extract_article_meta(html):
    """Returns (headline, summary) from an article page's metadata; either may be ''."""
    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:
        pass  # keep whatever was collected before the malformed markup
    meta = parser.meta
    headline = meta.get("og:title") or meta.get("twitter:title") or parser.title
    summary = meta.get("og:description") or meta.get("description") or meta.get("twitter:description")
    return _clean_text(headline, MAX_HEADLINE_CHARS), _clean_text(summary, MAX_SUMMARY_CHARS)


def enrich_top_events(data_items, limit=20, timeout=8):
    """
    Adds "headline" and "summary" to the highest-risk events by reading the
    title/description metadata of their source articles. Each distinct URL is
    fetched once; failures are skipped so a slow or blocked site never fails the run.
    """
    fetched = {}
    ranked = sorted(data_items, key=lambda item: item.get("risk_score") or 0, reverse=True)
    for item in ranked:
        url = item.get("source_url") or ""
        if not url.startswith(("http://", "https://")):
            continue
        if url not in fetched:
            if len(fetched) >= limit:
                break
            try:
                resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT}, stream=True)
                resp.raise_for_status()
                # metadata lives in <head>; no need for the whole page
                body = resp.raw.read(200_000, decode_content=True)
                resp.close()
                fetched[url] = extract_article_meta(body.decode(resp.encoding or "utf-8", errors="replace"))
            except Exception as e:
                print(f"Could not read article metadata from {url}: {e}")
                fetched[url] = ("", "")
        headline, summary = fetched[url]
        if headline:
            item["headline"] = headline
        if summary:
            item["summary"] = summary
    found = sum(1 for headline, _ in fetched.values() if headline)
    print(f"Article metadata: {found} of {len(fetched)} pages gave a headline.")
    return data_items


# --- Ticker data: news headlines and market indices ---

def load_config(path="config.json"):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f"Could not read {path}: {e}")
        return {}


def parse_rss(xml_text, source_name):
    """Parses an RSS 2.0 or Atom feed into news items."""
    root = ElementTree.fromstring(xml_text)
    strip = lambda tag: tag.rsplit("}", 1)[-1]
    items = []
    for node in root.iter():
        if strip(node.tag) not in ("item", "entry"):
            continue
        fields = {}
        for child in node:
            name = strip(child.tag)
            if name == "link" and not (child.text or "").strip():
                fields.setdefault("link", child.get("href", ""))  # Atom
            else:
                fields.setdefault(name, child.text or "")
        title = _clean_text(fields.get("title"), MAX_HEADLINE_CHARS)
        link = (fields.get("link") or "").strip()
        if not title or not link.startswith(("http://", "https://")):
            continue
        published = None
        raw_date = fields.get("pubDate") or fields.get("published") or fields.get("updated") or ""
        try:
            parsed = parsedate_to_datetime(raw_date) if "," in raw_date else datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            published = parsed.isoformat(timespec="seconds") + "Z"
        except (TypeError, ValueError):
            pass
        items.append({
            "title": title,
            "link": link,
            "source": source_name,
            "published": published,
            "summary": _clean_text(fields.get("description") or fields.get("summary"), MAX_SUMMARY_CHARS),
        })
    return items


def fetch_news(feeds, limit=30, timeout=20):
    """Fetches the configured feeds and returns the newest `limit` headlines."""
    items = []
    for feed in feeds:
        try:
            resp = requests.get(feed["url"], timeout=timeout, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            parsed = parse_rss(resp.content, feed.get("name") or feed["url"])
            print(f"News feed {feed.get('name')}: {len(parsed)} items")
            items.extend(parsed)
        except Exception as e:
            print(f"Error fetching news feed {feed.get('url')}: {e}")
    seen = set()
    unique = []
    for item in sorted(items, key=lambda i: i["published"] or "", reverse=True):
        if item["link"] not in seen:
            seen.add(item["link"])
            unique.append(item)
    return unique[:limit]


def _percent_change(closes, sessions_back):
    if len(closes) <= sessions_back or not closes[-1 - sessions_back]:
        return None
    return round((closes[-1] / closes[-1 - sessions_back] - 1) * 100, 2)


def parse_market_chart(payload, name, symbol):
    """Turns a Yahoo Finance chart response (daily bars) into one ticker entry."""
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    raw_closes = result["indicators"]["quote"][0]["close"]
    bars = [(t, c) for t, c in zip(timestamps, raw_closes) if c is not None]
    if len(bars) < 2:
        raise ValueError("fewer than two daily closes")
    closes = [c for _, c in bars]
    return {
        "name": name,
        "symbol": symbol,
        "price": round(closes[-1], 2),
        "currency": (result.get("meta") or {}).get("currency"),
        "as_of": datetime.utcfromtimestamp(bars[-1][0]).strftime("%Y-%m-%d"),
        "change_1d": _percent_change(closes, 1),
        "change_1w": _percent_change(closes, 5),
        "change_1m": _percent_change(closes, len(closes) - 1),
    }


def fetch_markets(markets, timeout=20):
    """Fetches about a month of daily closes for each configured symbol."""
    items = []
    for market in markets:
        symbol = market["symbol"]
        try:
            resp = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}",
                params={"range": "1mo", "interval": "1d"},
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            items.append(parse_market_chart(resp.json(), market.get("name") or symbol, symbol))
        except Exception as e:
            print(f"Error fetching market data for {symbol}: {e}")
    print(f"Market data: {len(items)} of {len(markets)} symbols fetched.")
    return items


def save_json(payload, filename, static_data_dir="static/data"):
    os.makedirs(static_data_dir, exist_ok=True)
    path = os.path.join(static_data_dir, filename)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Saved {path}")


def save_data(data_items, archive_data_dir="data", static_data_dir="static/data"):
    """
    Saves the processed data to JSON files:
    - A date-stamped archive file in `archive_data_dir`.
    - `latest.json` in `static_data_dir` for the frontend.
    """
    # Ensure directories exist
    if not os.path.exists(archive_data_dir):
        os.makedirs(archive_data_dir)
        print(f"Created archive data directory: {archive_data_dir}")

    if not os.path.exists(static_data_dir):
        os.makedirs(static_data_dir)
        print(f"Created static data directory: {static_data_dir}")

    today_date_str = datetime.utcnow().strftime("%Y-%m-%d")

    # Define filenames
    dated_filename = os.path.join(archive_data_dir, f"{today_date_str}.json")
    latest_filename_for_frontend = os.path.join(static_data_dir, "latest.json")

    try:
        # Save the dated archive file
        with open(dated_filename, 'w') as f:
            json.dump(data_items, f, indent=2)
        print(f"Archival data saved to {dated_filename}")

        # Save/overwrite latest.json for the frontend
        with open(latest_filename_for_frontend, 'w') as f:
            json.dump(data_items, f, indent=2)
        print(f"Frontend data saved to {latest_filename_for_frontend}")
    except IOError as e:
        print(f"Error saving data: {e}")


def build_history(archive_data_dir="data", static_data_dir="static/data", days=14):
    """
    Writes `history.json` to `static_data_dir`: one {"date", "avgRisk"} entry per
    day for the last `days` days, averaged from the daily archive snapshots.
    Days without a usable snapshot get avgRisk None so the chart shows a gap.
    """
    today = datetime.utcnow().date()
    history = []
    for offset in range(days - 1, -1, -1):
        day_str = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        avg_risk = None
        try:
            with open(os.path.join(archive_data_dir, f"{day_str}.json")) as f:
                scores = [
                    item["risk_score"] for item in json.load(f)
                    if isinstance(item, dict) and isinstance(item.get("risk_score"), (int, float))
                ]
            if scores:
                avg_risk = round(sum(scores) / len(scores))
        except (OSError, ValueError) as e:
            print(f"No usable archive snapshot for {day_str}: {e}")
        history.append({"date": day_str, "avgRisk": avg_risk})

    os.makedirs(static_data_dir, exist_ok=True)
    history_filename = os.path.join(static_data_dir, "history.json")
    with open(history_filename, 'w') as f:
        json.dump(history, f, indent=2)
    print(f"History data saved to {history_filename}")
    return history


def cleanup_old_data(archive_data_dir="data", days_to_keep=90):
    """Deletes JSON files in archive_data_dir older than days_to_keep."""
    print(f"Cleaning up old data files from {archive_data_dir} older than {days_to_keep} days...")
    if not os.path.isdir(archive_data_dir):
        print(f"Archive data directory {archive_data_dir} not found. Skipping cleanup.")
        return

    cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
    cleaned_count = 0
    # Only clean up dated files, not 'latest.json' which might be in 'data' if paths were misconfigured.
    # The primary 'latest.json' for the frontend is now in 'static/data/'.
    for filename in os.listdir(archive_data_dir):
        if filename.endswith(".json") and filename != "latest.json": # Explicitly avoid deleting a root 'latest.json' if it exists
            try:
                # Assumes YYYY-MM-DD.json format for archived files
                file_date_str = filename.split('.')[0]
                file_date = datetime.strptime(file_date_str, "%Y-%m-%d")
                if file_date < cutoff_date:
                    os.remove(os.path.join(archive_data_dir, filename))
                    print(f"Deleted old data file: {filename}")
                    cleaned_count +=1
            except ValueError: # If filename is not in YYYY-MM-DD format
                print(f"Skipping file with unexpected name format: {filename}")
            except OSError as e:
                print(f"Error deleting file {filename}: {e}")
    print(f"Cleanup finished. Deleted {cleaned_count} old files.")


if __name__ == "__main__":
    print("Starting ETL script...")

    # 1. Fetch data
    print("\n--- Fetching Data ---")
    gdelt_events_raw = fetch_gdelt_events()

    # 2. Process data
    print("\n--- Processing Data ---")
    processed_unified_data = process_data(gdelt_events_raw)
    print(f"Total unified items processed: {len(processed_unified_data)}")
    if processed_unified_data:
        print(f"Sample of processed data (first item): {json.dumps(processed_unified_data[0], indent=2)}")

    # Graceful fallback: if no new data was produced, preserve the previous latest.json
    # and warn rather than overwriting with empty data or crashing the workflow.
    if not processed_unified_data:
        print("WARNING: No data produced by ETL this run. Keeping existing data files unchanged.")
    else:
        print("\n--- Reading Article Metadata ---")
        enrich_top_events(processed_unified_data)

        # 3. Save data
        print("\n--- Saving Data ---")
        save_data(processed_unified_data)

    # Ticker feeds. Each file is only replaced when its fetch returned something,
    # so a failed source leaves the previous data in place.
    print("\n--- Fetching Ticker Data ---")
    config = load_config()
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    news_items = fetch_news(config.get("news_feeds", []))
    if news_items:
        save_json({"updated": fetched_at, "items": news_items}, "news.json")
    market_items = fetch_markets(config.get("markets", []))
    if market_items:
        save_json({"updated": fetched_at, "items": market_items}, "markets.json")

    # 4. Rebuild the 14-day trend for the frontend from the archive
    print("\n--- Building History ---")
    build_history()

    # 5. Cleanup old data (always runs regardless of fetch outcome)
    print("\n--- Cleaning Old Data ---")
    cleanup_old_data(days_to_keep=90)

    print("\nETL script finished.")
