import requests
import pandas as pd
import feedparser
from datetime import datetime, timedelta
import time
import os
from dotenv import load_dotenv
import json # Added
import random # For mocked OpenAI sentiment

# Mocking openai library if not available or for testing without API key
try:
    import openai
except ImportError:
    print("INFO: 'openai' library not found. Mocking OpenAI calls.")
    # Define a mock structure if openai is not installed
    class MockOpenAI:
        class ChatCompletion:
            @staticmethod
            def create(*args, **kwargs):
                # Simulate an API response structure
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps({
                                    "summary": "This is a sample summary from mock OpenAI.",
                                    "sentiment_score": random.uniform(-0.8, 0.8) # Random sentiment
                                })
                            }
                        }
                    ]
                }

        class OpenAIError(Exception): # Mock base OpenAI error
            pass

    openai = MockOpenAI()


# Load environment variables from .env file
load_dotenv()

# --- Existing Fetching Functions (fetch_gdelt_events, fetch_acled_data, fetch_rss_feeds) ---
# These will be kept as they are from the previous subtask for now.
# I will paste them here without modification to ensure the file is complete.

def fetch_gdelt_events():
    """
    Fetches events from the GDELT 2.0 Event database for the last 24 hours.
    Selects specific fields relevant for geopolitical risk analysis.
    Uses dynamic dates, but may be affected by sandbox clock or GDELT rate limiting.
    """
    print("Fetching GDELT events...")
    gdelt_base_url = "https://api.gdeltproject.org/api/v2/events/events"

    end_datetime_api = datetime.utcnow()
    start_datetime_api = end_datetime_api - timedelta(days=1)

    start_date_str = start_datetime_api.strftime("%Y%m%d%H%M%S")
    end_date_str = end_datetime_api.strftime("%Y%m%d%H%M%S")

    print(f"INFO: GDELT attempting to fetch for timespan: {start_date_str} to {end_date_str}")

    query_fields = [
        "EventCode", "EventBaseCode", "IsRootEvent", "QuadClass", # Added QuadClass for potential categorization
        "ActionGeo_Lat", "ActionGeo_Long", "ActionGeo_CountryCode",
        "Actor1Geo_Lat", "Actor1Geo_Long",
        "Actor2Geo_Lat", "Actor2Geo_Long",
        "SOURCEURL", "AvgTone", "Day" # Day field contains YYYYMMDD
    ]
    fields_param = ",".join(query_fields)

    params = {
        "query": f"timespan:{start_date_str}-{end_date_str}",
        "mode": "event",
        "format": "json",
        "fields": fields_param,
        "maxrecords": 250
    }

    all_events = []
    try:
        prepared_request = requests.Request('GET', gdelt_base_url, params=params).prepare()
        print(f"GDELT API Request URL: {prepared_request.url}")

        response = requests.get(gdelt_base_url, params=params, timeout=60)
        response.raise_for_status()

        data = response.json()
        events = data.get("events", []) if isinstance(data, dict) else data

        all_events.extend(events)
        print(f"Successfully fetched {len(events)} initial events from GDELT.")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching GDELT data: {e}")
    except ValueError as e: # Includes JSONDecodeError
        print(f"Error decoding GDELT JSON response: {e}")
        print(f"Response text: {response.text if 'response' in locals() else 'No response object'}")
    return all_events

def fetch_acled_data(api_key, country=None, days_limit=7):
    print("Fetching ACLED data (placeholder)...")
    # This function returns a pre-defined structure for testing purposes.
    # In a real scenario, it would query the ACLED API.
    placeholder_event_date = (datetime.utcnow() - timedelta(days=random.randint(1, days_limit))).strftime("%Y-%m-%d")
    return [
        {
            "data_id": random.randint(10000, 99999),
            "iso": "USA", # Using ISO3 for consistency if possible
            "event_date": placeholder_event_date,
            "year": int(placeholder_event_date[:4]),
            "event_type": "Protests", # Common ACLED event type
            "sub_event_type": "Peaceful protest",
            "actor1": "Protesters",
            "location": "New York City", # Example location
            "latitude": 40.7128,
            "longitude": -74.0060,
            "source": "ACLED Placeholder Data",
            "fatalities": 0,
            "notes": "This is a sample ACLED event (placeholder)."
        }
    ]

def fetch_rss_feeds(rss_urls):
    print(f"Fetching RSS feeds from: {rss_urls}")
    all_feed_items = []
    for url in rss_urls:
        try:
            print(f"Fetching feed: {url}")
            feed = feedparser.parse(url)

            if feed.bozo:
                raise Exception(f"Feed at {url} is ill-formed: {feed.bozo_exception}")

            for entry in feed.entries:
                item = {
                    "title": entry.get("title"),
                    "link": entry.get("link"),
                    "published": entry.get("published") or entry.get("pubDate") or entry.get("updated"),
                    "source_feed": feed.feed.get("title", url)
                }
                item["published_parsed"] = None
                if item["published"]:
                    try:
                        parsed_date_struct = feedparser.parse_date(item["published"])
                        if parsed_date_struct:
                           dt_obj = datetime(*parsed_date_struct[:6])
                           item["published_parsed"] = dt_obj.isoformat() + "Z"
                    except (TypeError, ValueError):
                        pass
                    except Exception:
                        pass

                all_feed_items.append(item)
            print(f"Successfully fetched {len(feed.entries)} items from {url}")
        except Exception as e:
            print(f"Error fetching or parsing RSS feed {url}: {e}")
    return all_feed_items

# --- New Processing and Storage Functions ---

def get_summary_and_sentiment(text, api_key=None):
    """
    Gets a summary and sentiment score for the given text.
    Uses OpenAI GPT if API key is provided, otherwise returns mocked data.
    """
    if not api_key: # Or if openai is the mock class and no real key
        # print("INFO: OpenAI API key not provided or library mocked. Using dummy summary/sentiment.")
        return "This is a sample summary (mocked).", random.uniform(-0.5, 0.5)

    # This part would be for actual OpenAI call
    # For now, it will use the MockOpenAI if the real one isn't imported/configured
    try:
        # print(f"DEBUG: Attempting OpenAI call for text: {text[:100]}...") # Debug
        # Prompt for summarization (max 280 chars) and sentiment score (-1 to 1)
        prompt_content = f"""Analyze the following text and provide:
1. A concise summary (max 280 characters).
2. A sentiment score (a float between -1.0 for very negative, and 1.0 for very positive).

Return your response as a JSON object with keys "summary" and "sentiment_score".

Text:
\"\"\"
{text}
\"\"\"
"""
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an AI assistant that summarizes text and provides sentiment scores."},
                {"role": "user", "content": prompt_content}
            ],
            temperature=0.3, # Lower temperature for more factual summary
        )

        response_content = completion.choices[0].message.content
        # print(f"DEBUG: OpenAI raw response: {response_content}") # Debug

        parsed_response = json.loads(response_content)
        summary = parsed_response.get("summary", "Summary not found in response.")
        sentiment = float(parsed_response.get("sentiment_score", 0.0))

        return summary, sentiment

    except openai.OpenAIError as e: # More specific error handling
        print(f"OpenAI API Error: {e}. Using mock data.")
        return "OpenAI API error occurred (mocked summary).", random.uniform(-0.3, 0.3)
    except Exception as e:
        print(f"Error in OpenAI call or parsing response: {e}. Using mock data.")
        return "Error processing OpenAI response (mocked summary).", random.uniform(-0.3, 0.3)


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


def process_data(gdelt_data, acled_data, rss_data, openai_api_key):
    """
    Normalizes and unifies data from GDELT, ACLED, and RSS feeds
    into a common schema.
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

    # Process ACLED Data (Placeholder)
    for event in acled_data:
        # Using placeholder values, adapt to ACLED's actual structure if implemented
        unified_data.append({
            "timestamp": datetime.strptime(event["event_date"], "%Y-%m-%d").isoformat() + "Z" if event.get("event_date") else current_time_iso,
            "country": event.get("iso", "ACLED_PH"), # Placeholder country
            "lat": float(event.get("latitude", 0.0)),
            "lon": float(event.get("longitude", 0.0)),
            "risk_score": random.randint(30, 70), # Dummy risk score for ACLED placeholder
            "title": f"ACLED Event: {event.get('event_type', 'Placeholder Event')}",
            "source_url": event.get("source", "acleddata.com"),
            "tag": "conflict" # ACLED primarily tracks conflict/protest
        })

    # Process RSS Feeds
    for item in rss_data:
        summary, sentiment = get_summary_and_sentiment(item.get("title", ""), api_key=openai_api_key)

        # Risk score from sentiment: sentiment is -1 to 1.
        # Abs(sentiment * 50) + 50 could give a 0-100 score (e.g. highly negative/positive = high risk/attention)
        # Or, if sentiment is a proxy for "tone", map it more directly.
        # For now, let's use a simple scale: (sentiment + 1)/2 * 70 to make it 0-70, assuming news isn't max risk.
        rss_risk_score = round(((sentiment + 1) / 2.0) * 70)

        timestamp = item.get("published_parsed") or current_time_iso

        unified_data.append({
            "timestamp": timestamp,
            "country": "GL", # Global / Not Applicable for most news
            "lat": None, # RSS feeds typically don't have coordinates
            "lon": None,
            "risk_score": rss_risk_score,
            "title": item.get("title", "RSS Item"),
            "source_url": item.get("link", ""),
            "tag": "news" # Generic tag for RSS items
        })
        # print(f"DEBUG RSS processed: {item.get('title', '')} -> Risk: {rss_risk_score}, Summary: {summary}")


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
                    os.remove(os.path.join(data_dir, filename))
                    print(f"Deleted old data file: {filename}")
                    cleaned_count +=1
            except ValueError: # If filename is not in YYYY-MM-DD format
                print(f"Skipping file with unexpected name format: {filename}")
            except OSError as e:
                print(f"Error deleting file {filename}: {e}")
    print(f"Cleanup finished. Deleted {cleaned_count} old files.")


if __name__ == "__main__":
    print("Starting ETL script...")

    # Load API keys (even if mocked, good practice for structure)
    # For GDELT, no specific API key is usually required for public data via HTTP.
    acled_api_key = os.getenv("ACLED_TOKEN")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("INFO: OPENAI_API_KEY not found in .env. Mocked OpenAI responses will be used for RSS summaries.")

    # 1. Fetch data
    print("\n--- Fetching Data ---")
    gdelt_events_raw = fetch_gdelt_events()
    acled_data_raw = fetch_acled_data(api_key=acled_api_key) # ACLED key passed here

    sample_rss_urls = [
        "http://rss.cnn.com/rss/cnn_world.rss",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        # "http://feeds.aljazeera.net/utilities/alertsRssGenerator/AlertsRssDispatcher.aspx" # Known problematic
    ]
    rss_items_raw = fetch_rss_feeds(sample_rss_urls)

    # 2. Process data
    print("\n--- Processing Data ---")
    processed_unified_data = process_data(
        gdelt_events_raw,
        acled_data_raw,
        rss_items_raw,
        openai_api_key # OpenAI key passed for summaries
    )
    print(f"Total unified items processed: {len(processed_unified_data)}")
    if processed_unified_data:
        print(f"Sample of processed data (first item): {json.dumps(processed_unified_data[0], indent=2)}")


    # 3. Save data
    print("\n--- Saving Data ---")
    # save_data now uses default "data" for archives and "static/data" for frontend's latest.json
    save_data(processed_unified_data)

    # 4. Cleanup old data
    print("\n--- Cleaning Old Data ---")
    # cleanup_old_data now defaults to "data" directory for archives
    cleanup_old_data(days_to_keep=90)

    print("\nETL script finished.")
