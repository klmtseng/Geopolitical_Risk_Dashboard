import requests
from datetime import datetime, timedelta
import os
import json


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
        resp2 = requests.get(export_url, timeout=60)
        resp2.raise_for_status()
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

def calculate_risk_score(tone, event_base_code):
    """
    Calculates a risk score based on GDELT tone and event base code.
    Score is capped at 100.
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

    risk_score = min(normalized_tone_score + conflict_weight_score, 100) # Cap at 100
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

        risk_score = calculate_risk_score(event.get("AvgTone"), event.get("EventBaseCode"))

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
            unified_data.append({
                "timestamp": timestamp,
                "country": country_code,
                "lat": float(lat),
                "lon": float(lon),
                "risk_score": risk_score,
                "title": f"GDELT Event: {event.get('EventBaseCode', 'N/A')} in {country_code}", # More descriptive title
                "source_url": event.get("SOURCEURL", ""),
                "tag": tag
            })

    return unified_data


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
        # 3. Save data
        print("\n--- Saving Data ---")
        save_data(processed_unified_data)

    # 4. Rebuild the 14-day trend for the frontend from the archive
    print("\n--- Building History ---")
    build_history()

    # 5. Cleanup old data (always runs regardless of fetch outcome)
    print("\n--- Cleaning Old Data ---")
    cleanup_old_data(days_to_keep=90)

    print("\nETL script finished.")
