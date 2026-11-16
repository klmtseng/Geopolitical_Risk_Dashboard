import pytest
import json
import os
from datetime import datetime, timedelta
import shutil
import etl
from etl import build_history, calculate_risk_score, cleanup_old_data

# Test cases for calculate_risk_score
# Each tuple: (tone, event_base_code, expected_score, description)
test_data = [
    # Test Case 1: Valid inputs, mid-range score.
    # Tone: 50 -> abs(50)/2 = 25. Event '14' (Protest) weight: 20. Total: 45.
    (50, '141', 45, "Valid inputs, mid-range score"),
    (50, '14', 45, "Valid inputs (2-digit code), mid-range score"),

    # Test Case 2: Negative tone, high conflict event.
    # Tone: -80 -> abs(-80)/2 = 40. Event '19' (Fight) weight: 50. Total: 90.
    (-80, '190', 90, "Negative tone, high conflict event"),
    (-80, '19', 90, "Negative tone (2-digit code), high conflict event"),

    # Test Case 3: Zero tone, low conflict event.
    # Tone: 0 -> 0/2 = 0. Event '04' (Consult) weight: 5. Total: 5.
    (0, '040', 5, "Zero tone, low conflict event (Consult)"),
    (0, '04', 5, "Zero tone (2-digit code), low conflict event (Consult)"),

    # Test Case 3b: Zero tone, specific low conflict (Appeal).
    # Tone: 0 -> 0/2 = 0. Event '13' (Appeal) weight: 10. Total: 10.
    (0, '13', 10, "Zero tone, specific low conflict (Appeal)"),

    # Test Case 4: Max tone contribution, max conflict event (should cap at 100).
    # Tone: 100 -> abs(100)/2 = 50. Event '20' (Mass violence) weight: 50. Total: 100.
    (100, '200', 100, "Max tone, max conflict event (cap at 100)"),
    (100, '20', 100, "Max tone (2-digit code), max conflict event (cap at 100)"),

    # Test Case 4b: Score exceeding 100 before cap.
    # Tone: 100 -> 50. Event '19' (Fight) weight 50. Total 100.
    # If an event had weight 60, 50 + 60 = 110, capped to 100.
    # Using existing '19' which results in 100.
    (100, '195', 100, "Score sums to 100, at cap"),

    # Test Case 5: Tone leading to >50 for tone part (already covered by abs(tone)/2, e.g. 100/2=50)
    # This is implicitly tested by cases with tone 100.

    # Test Case 6: Missing or None event_base_code.
    # Tone: 50 -> abs(50)/2 = 25. Event None weight: 0. Total: 25.
    (50, None, 25, "None event_base_code"),

    # Test Case 7: Missing or None tone.
    # Tone: None -> 0. Event '14' (Protest) weight: 20. Total: 20.
    (None, '141', 20, "None tone"),

    # Test Case 8: Event code not in defined map (should use default weight 0).
    # Tone: 20 -> abs(20)/2 = 10. Event '999' weight: 0. Total: 10.
    (20, '999', 10, "Unknown event_base_code (not in map)"),

    # Test Case 9: Non-numeric tone string
    ("invalid_tone", '141', 20, "Non-numeric tone string"), # Tone part becomes 0

    # Test Case 10: Both None
    (None, None, 0, "Both tone and event_base_code are None"),

    # Test Case 11: Event Base Code '18' (Assault)
    # Tone: 30 -> 15. Event '18' weight: 40. Total: 55.
    (30, '18', 55, "Event code for Assault"),

    # Test Case 12: Event Base Code '10' (Demand)
    # Tone: -10 -> 5. Event '10' weight: 15. Total: 20.
    (-10, '10', 20, "Event code for Demand")
]

@pytest.mark.parametrize("tone, event_base_code, expected_score, description", test_data)
def test_calculate_risk_score(tone, event_base_code, expected_score, description):
    """Tests calculate_risk_score with various inputs."""
    assert calculate_risk_score(tone, event_base_code) == expected_score, description


def test_cleanup_old_data():
    """Tests the cleanup_old_data function."""
    test_archive_dir = "temp_test_archive_dir_cleanup"
    days_to_keep = 30
    # Use a fixed 'current date' for predictable test outcomes
    mock_today = datetime(2023, 10, 15) # Example date for test consistency

    try:
        os.makedirs(test_archive_dir, exist_ok=True)

        # --- Create test files ---
        # File older than cutoff (should be deleted)
        old_date_val = mock_today - timedelta(days=days_to_keep + 1)
        old_date_str = old_date_val.strftime("%Y-%m-%d")
        old_file_path = os.path.join(test_archive_dir, f"{old_date_str}.json")
        with open(old_file_path, "w") as f:
            f.write('{"data": "old"}')

        # File exactly at cutoff (should be deleted, as cleanup is "older than")
        cutoff_date_val = mock_today - timedelta(days=days_to_keep)
        cutoff_date_str = cutoff_date_val.strftime("%Y-%m-%d")
        cutoff_file_path = os.path.join(test_archive_dir, f"{cutoff_date_str}.json")
        with open(cutoff_file_path, "w") as f:
            f.write('{"data": "cutoff"}')

        # File newer than cutoff (should be kept)
        new_date_val = mock_today - timedelta(days=days_to_keep -1)
        new_date_str = new_date_val.strftime("%Y-%m-%d")
        new_file_path = os.path.join(test_archive_dir, f"{new_date_str}.json")
        with open(new_file_path, "w") as f:
            f.write('{"data": "new"}')

        # 'latest.json' (should be kept)
        latest_file_path = os.path.join(test_archive_dir, "latest.json")
        with open(latest_file_path, "w") as f:
            f.write('{"data": "latest"}')

        # 'unexpected_file.txt' (should be kept as it's not a dated JSON)
        unexpected_file_path = os.path.join(test_archive_dir, "unexpected_file.txt")
        with open(unexpected_file_path, "w") as f:
            f.write("some text data")

        # --- Call cleanup_old_data ---
        # We need to mock datetime.utcnow() for cleanup_old_data to use mock_today
        # This is a bit more involved, usually done with pytest-mock or unittest.mock
        # For now, let's adjust the file dates drastically so that real utcnow() still works predictably for the test logic.

        # Re-calculate dates based on actual datetime.utcnow() for more robust testing without mocking utcnow directly in this step
        # This means the test is relative to the day it's run.
        # To make it deterministic as requested, we will hardcode file dates and use a fixed mock_today for cutoff calculation
        # *within the test logic*, but cleanup_old_data itself uses datetime.utcnow().
        # The prompt implies cleanup_old_data should be tested as is, so we'll use a fixed 'days_to_keep'
        # and create files very far in the past or very recent relative to actual runtime.

        # Let's stick to the fixed mock_today logic for creating files, and pass days_to_keep.
        # The key is that cleanup_old_data's internal `datetime.utcnow()` will be *later* than mock_today,
        # so files dated according to mock_today will appear "old" correctly.

        # For this test, let's use a very small `days_to_keep` and make files accordingly.
        # This is simpler than mocking `datetime.utcnow()` within `cleanup_old_data` without `pytest-mock`.

        # Redefine files based on a small days_to_keep and current time.
        # This makes the test more about the logic of "older than X days" rather than fixed dates.
        os.remove(old_file_path)
        os.remove(cutoff_file_path)
        os.remove(new_file_path)

        current_utc_time = datetime.utcnow() # cleanup_old_data will use this

        days_to_keep_dynamic = 5 # Keep files from the last 5 days

        # Older file (should be deleted)
        file_older_than_cutoff_dt = current_utc_time - timedelta(days=days_to_keep_dynamic + 1)
        file_older_than_cutoff_str = file_older_than_cutoff_dt.strftime("%Y-%m-%d")
        older_file = os.path.join(test_archive_dir, f"{file_older_than_cutoff_str}.json")
        with open(older_file, "w") as f: f.write('{"data": "very old"}')

        # Newer file (should be kept)
        file_newer_than_cutoff_dt = current_utc_time - timedelta(days=days_to_keep_dynamic -1)
        file_newer_than_cutoff_str = file_newer_than_cutoff_dt.strftime("%Y-%m-%d")
        newer_file = os.path.join(test_archive_dir, f"{file_newer_than_cutoff_str}.json")
        with open(newer_file, "w") as f: f.write('{"data": "very new"}')


        # Call cleanup_old_data
        cleanup_old_data(archive_data_dir=test_archive_dir, days_to_keep=days_to_keep_dynamic)

        # --- Assertions ---
        assert not os.path.exists(older_file), f"Old file '{older_file}' should have been deleted."
        assert os.path.exists(newer_file), f"New file '{newer_file}' should still exist."
        assert os.path.exists(latest_file_path), "'latest.json' should still exist."
        assert os.path.exists(unexpected_file_path), "'unexpected_file.txt' should still exist."

    finally:
        if os.path.exists(test_archive_dir):
            shutil.rmtree(test_archive_dir)


def test_build_history(tmp_path):
    archive_dir = tmp_path / "data"
    static_dir = tmp_path / "static"
    archive_dir.mkdir()
    today = datetime.utcnow().date()

    def write(day, payload):
        (archive_dir / f"{day.strftime('%Y-%m-%d')}.json").write_text(payload)

    write(today, json.dumps([{"risk_score": 10}, {"risk_score": 21}, {"title": "no score"}]))
    write(today - timedelta(days=1), "not json")
    write(today - timedelta(days=30), json.dumps([{"risk_score": 99}]))  # outside window

    history = build_history(str(archive_dir), str(static_dir), days=3)

    assert history == [
        {"date": (today - timedelta(days=2)).strftime("%Y-%m-%d"), "avgRisk": None},
        {"date": (today - timedelta(days=1)).strftime("%Y-%m-%d"), "avgRisk": None},
        {"date": today.strftime("%Y-%m-%d"), "avgRisk": 16},
    ]
    assert json.loads((static_dir / "history.json").read_text()) == history


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise etl.requests.exceptions.HTTPError(f"{self.status_code} error")


BASE = "http://data.gdeltproject.org/gdeltv2/"


def test_previous_gdelt_export_url():
    assert etl.previous_gdelt_export_url(BASE + "20261116000000.export.CSV.zip") == \
        BASE + "20261115234500.export.CSV.zip"
    assert etl.previous_gdelt_export_url("http://example.com/file.zip") is None


def test_download_gdelt_export_falls_back_on_404(monkeypatch):
    statuses = {
        BASE + "20261116054500.export.CSV.zip": 404,
        BASE + "20261116053000.export.CSV.zip": 200,
    }
    requested = []

    def fake_get(url, timeout):
        requested.append(url)
        return _FakeResponse(statuses[url])

    monkeypatch.setattr(etl.requests, "get", fake_get)
    resp = etl.download_gdelt_export(BASE + "20261116054500.export.CSV.zip")
    assert resp.status_code == 200
    assert requested == list(statuses)


def test_download_gdelt_export_gives_up(monkeypatch):
    requested = []

    def fake_get(url, timeout):
        requested.append(url)
        return _FakeResponse(404)

    monkeypatch.setattr(etl.requests, "get", fake_get)
    with pytest.raises(etl.requests.exceptions.HTTPError):
        etl.download_gdelt_export(BASE + "20261116054500.export.CSV.zip", max_fallbacks=2)
    assert len(requested) == 3


def test_download_gdelt_export_other_errors_do_not_fall_back(monkeypatch):
    requested = []

    def fake_get(url, timeout):
        requested.append(url)
        return _FakeResponse(500)

    monkeypatch.setattr(etl.requests, "get", fake_get)
    with pytest.raises(etl.requests.exceptions.HTTPError):
        etl.download_gdelt_export(BASE + "20261116054500.export.CSV.zip")
    assert len(requested) == 1


# --- hover-brief fields, article metadata, news and market parsing ---

def test_process_data_adds_context_fields():
    rows = [{
        "Day": "20261115", "EventBaseCode": "190", "AvgTone": "-8.04",
        "ActionGeo_Lat": "35.7", "ActionGeo_Long": "51.4", "ActionGeo_CountryCode": "IR",
        "ActionGeo_FullName": "Tehran, Tehran, Iran", "Actor1Name": "IRAN", "Actor2Name": "",
        "NumArticles": "12", "SOURCEURL": "https://example.com/a",
    }]
    (item,) = etl.process_data(rows)
    assert item["title"] == "GDELT Event: 190 in IR"  # unchanged, the frontend parses it
    assert item["event_code"] == "190"
    assert item["location"] == "Tehran, Tehran, Iran"
    assert item["actors"] == ["Iran"]
    assert item["tone"] == -8.0
    assert item["articles"] == 12


def test_extract_article_meta_prefers_opengraph():
    html = """<html><head><title>Site | Fallback title</title>
      <meta name="description" content="Plain description.">
      <meta property="og:title" content="Troops cross the border &amp; hold a town">
      <meta property="og:description" content="  A longer   summary\nof the event. "></head><body><p>ignored</p></body></html>"""
    assert etl.extract_article_meta(html) == (
        "Troops cross the border & hold a town", "A longer summary of the event.")


def test_extract_article_meta_falls_back_and_truncates():
    html = "<title>Only a title</title><meta name='description' content='" + "word " * 100 + "'>"
    headline, summary = etl.extract_article_meta(html)
    assert headline == "Only a title"
    assert len(summary) <= etl.MAX_SUMMARY_CHARS + 1 and summary.endswith("…")
    assert etl.extract_article_meta("") == ("", "")


def test_enrich_top_events_fetches_each_url_once_and_survives_errors(monkeypatch):
    class Resp:
        encoding = "utf-8"
        def __init__(self, body): self.raw = self; self._body = body
        def read(self, n, decode_content=False): return self._body
        def raise_for_status(self): pass
        def close(self): pass

    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if "bad" in url:
            raise etl.requests.exceptions.ConnectionError("blocked")
        return Resp(b'<meta property="og:title" content="Headline"><meta name="description" content="Summary">')

    monkeypatch.setattr(etl.requests, "get", fake_get)
    items = [
        {"risk_score": 50, "source_url": "https://ok.example/a"},
        {"risk_score": 49, "source_url": "https://ok.example/a"},
        {"risk_score": 48, "source_url": "https://bad.example/b"},
        {"risk_score": 1, "source_url": "https://ok.example/c"},
        {"risk_score": 60, "source_url": ""},
    ]
    etl.enrich_top_events(items, limit=2)
    assert calls == ["https://ok.example/a", "https://bad.example/b"]
    assert items[0]["headline"] == "Headline" and items[1]["summary"] == "Summary"
    assert "headline" not in items[2] and "headline" not in items[3]


RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Feed</title>
<item><title>Older &amp; story</title><link>https://n.example/1</link>
  <description>&lt;p&gt;Body text&lt;/p&gt;</description><pubDate>Sat, 14 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>Newer story</title><link>https://n.example/2</link><pubDate>Sun, 15 Nov 2026 08:30:00 +0800</pubDate></item>
<item><title>No link</title></item>
</channel></rss>"""

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom story</title>
<link href="https://n.example/3"/><updated>2026-11-15T12:00:00Z</updated><summary>Short</summary></entry></feed>"""


def test_parse_rss_and_atom():
    items = etl.parse_rss(RSS, "Feed")
    assert [i["title"] for i in items] == ["Older & story", "Newer story"]
    assert items[0]["summary"] == "Body text"
    assert items[0]["published"] == "2026-11-14T10:00:00Z"
    assert items[1]["published"] == "2026-11-15T00:30:00Z"  # converted to UTC
    (atom,) = etl.parse_rss(ATOM, "A")
    assert atom == {"title": "Atom story", "link": "https://n.example/3", "source": "A",
                    "published": "2026-11-15T12:00:00Z", "summary": "Short"}


def test_fetch_news_sorts_dedupes_and_skips_failed_feeds(monkeypatch):
    class Resp:
        def __init__(self, content): self.content = content
        def raise_for_status(self): pass

    def fake_get(url, **kwargs):
        if "down" in url:
            raise etl.requests.exceptions.Timeout("slow")
        return Resp(RSS)

    monkeypatch.setattr(etl.requests, "get", fake_get)
    feeds = [{"name": "One", "url": "https://one"}, {"name": "Down", "url": "https://down"},
             {"name": "Two", "url": "https://two"}]
    items = etl.fetch_news(feeds)
    assert [i["link"] for i in items] == ["https://n.example/2", "https://n.example/1"]


def _chart(closes, start=1794700800):
    return {"chart": {"result": [{
        "meta": {"currency": "USD"},
        "timestamp": [start + 86400 * i for i in range(len(closes))],
        "indicators": {"quote": [{"close": closes}]},
    }]}}


def test_parse_market_chart():
    closes = [100, 101, None, 102, 103, 104, 105, 110]
    entry = etl.parse_market_chart(_chart(closes), "Index", "^IDX")
    assert entry["price"] == 110 and entry["currency"] == "USD"
    assert entry["change_1d"] == round((110 / 105 - 1) * 100, 2)
    assert entry["change_1w"] == round((110 / 101 - 1) * 100, 2)  # 5 sessions back, skipping the null bar
    assert entry["change_1m"] == 10.0
    assert entry["as_of"] == datetime.utcfromtimestamp(1794700800 + 86400 * 7).strftime("%Y-%m-%d")
    with pytest.raises(ValueError):
        etl.parse_market_chart(_chart([100, None]), "Index", "^IDX")


def test_fetch_markets_skips_symbols_that_fail(monkeypatch):
    class Resp:
        def raise_for_status(self): pass
        def json(self): return _chart([10, 11])

    def fake_get(url, **kwargs):
        if "BAD" in url:
            raise etl.requests.exceptions.HTTPError("429")
        assert kwargs["params"] == {"range": "1mo", "interval": "1d"}
        return Resp()

    monkeypatch.setattr(etl.requests, "get", fake_get)
    items = etl.fetch_markets([{"name": "Good", "symbol": "^GOOD"}, {"name": "Bad", "symbol": "BAD"}])
    assert [i["name"] for i in items] == ["Good"]
    assert "%5EGOOD" not in items[0]["symbol"]


# --- actor-aware scoring ---

def _raw(a1=None, a2=None, code="190", tone="-10"):
    """a1/a2: (actor code, country code, [type codes]) or None."""
    event = {"EventBaseCode": code, "AvgTone": tone}
    for n, actor in ((1, a1), (2, a2)):
        if actor:
            actor_code, country, types = actor
            event[f"Actor{n}Code"] = actor_code
            event[f"Actor{n}CountryCode"] = country
            for i, type_code in enumerate(types, start=1):
                event[f"Actor{n}Type{i}Code"] = type_code
    return event


@pytest.mark.parametrize("event, expected", [
    (_raw(), (1.0, 0, None)),                                                      # no actor codes: unchanged
    (_raw(("CRM", "", ["CRM"]), ("COP", "", ["COP"])), (0.4, 0, "local")),          # robbers vs police
    (_raw(("PAKCOP", "PAK", ["COP"])), (0.4, 0, "local")),                          # country-tagged police is still local
    (_raw(("CVL", "", ["CVL"]), None), (0.4, 0, "local")),
    (_raw(("PAKMIL", "PAK", ["MIL"])), (1.0, 0, "state or armed")),
    (_raw(("REB", "", ["REB"]), ("CVL", "", ["CVL"])), (1.0, 0, "state or armed")),
    (_raw(("IRN", "IRN", []), ("ISR", "ISR", [])), (1.0, 15, "cross-border")),      # bare countries = states
    (_raw(("USAGOV", "USA", ["GOV"]), ("USAMIL", "USA", ["MIL"])), (1.0, 0, "state or armed")),
    (_raw(("RUSMIL", "RUS", ["MIL"]), ("UKRCVL", "UKR", ["CVL"])), (1.0, 15, "cross-border")),
    (_raw(("BUS", "", ["BUS"]), ("MED", "", ["MED"])), (0.4, 0, "local")),
])
def test_actor_profile(event, expected):
    assert etl.actor_profile(event) == expected


def test_risk_score_with_actor_adjustments():
    # tone -10 -> 5; fight weight 50
    assert calculate_risk_score(-10, "190") == 55
    assert calculate_risk_score(-10, "190", 0.4, 0) == 25
    assert calculate_risk_score(-10, "190", 1.0, 15) == 70
    assert calculate_risk_score(-10, "020", 1.0, 15) == 5      # no conflict weight: no bonus either
    assert calculate_risk_score(-90, "200", 1.0, 15) == 100    # capped


def test_process_data_scores_by_actors():
    common = {"Day": "20261116", "ActionGeo_Lat": "1", "ActionGeo_Long": "2", "ActionGeo_CountryCode": "XX"}
    rows = [
        {**_raw(("CRM", "", ["CRM"]), ("COP", "", ["COP"])), **common},
        {**_raw(("IRN", "IRN", []), ("ISR", "ISR", [])), **common},
        {**_raw(), **common},
    ]
    local, interstate, legacy = etl.process_data(rows)
    assert (local["risk_score"], local["actor_class"]) == (25, "local")
    assert (interstate["risk_score"], interstate["actor_class"]) == (70, "cross-border")
    assert legacy["risk_score"] == 55 and "actor_class" not in legacy
