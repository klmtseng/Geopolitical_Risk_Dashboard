import json
import math
import os
from datetime import datetime

import pytest

import etl
from etl import COL


# --- helpers ---------------------------------------------------------------

def row(root="19", place="IR26", country="IR", name="Tehran, Tehran, Iran", lat="35.7", lon="51.4",
        url="https://a.example/story", articles="2", goldstein="-10", tone="-5",
        actor1=("IRNMIL", "IRAN", "MIL"), actor2=None, base=None):
    """One GDELT export row (61 columns) with the fields the ETL reads."""
    r = [""] * 61
    r[COL["EventRootCode"]] = root
    r[COL["EventBaseCode"]] = base or root + "0"
    r[COL["EventCode"]] = base or root + "0"
    r[COL["GoldsteinScale"]] = goldstein
    r[COL["NumArticles"]] = articles
    r[COL["AvgTone"]] = tone
    r[COL["ActionGeo_FullName"]] = name
    r[COL["ActionGeo_CountryCode"]] = country
    r[COL["ActionGeo_ADM1Code"]] = place
    r[COL["ActionGeo_Lat"]] = lat
    r[COL["ActionGeo_Long"]] = lon
    r[COL["SOURCEURL"]] = url
    for n, actor in ((1, actor1), (2, actor2)):
        if actor:
            r[COL[f"Actor{n}Code"]], r[COL[f"Actor{n}Name"]], r[COL[f"Actor{n}Type1Code"]] = actor
    return r


def loader(hours):
    """load_hour callable over an in-memory {hour_id: state} mapping."""
    return lambda hour_id: hours.get(hour_id)


# --- download planning ------------------------------------------------------

def test_timestamps_to_fetch_catches_up_from_last_run():
    assert etl.timestamps_to_fetch("20261116100000", "20261116104500", 24) == [
        "20261116101500", "20261116103000", "20261116104500"]
    assert etl.timestamps_to_fetch("20261116104500", "20261116104500", 24) == []


def test_timestamps_to_fetch_limits_backfill_and_first_run():
    first = etl.timestamps_to_fetch(None, "20261116104500", 2)
    assert first == ["20261116090000", "20261116091500", "20261116093000", "20261116094500",
                     "20261116100000", "20261116101500", "20261116103000", "20261116104500"]
    # a long gap is capped to the same limit
    assert etl.timestamps_to_fetch("20261101000000", "20261116104500", 2) == first
    assert len(etl.timestamps_to_fetch(None, "20261116104500", 24)) == 96


def test_latest_export_timestamp(monkeypatch):
    class Resp:
        text = ("150383 297a16b493de7cf6ca809a7cc31d0b93 http://data.gdeltproject.org/gdeltv2/20261116104500.export.CSV.zip\n"
                "318084 bb27f78ba45f69a17ea6ed7755e9f8ff http://data.gdeltproject.org/gdeltv2/20261116104500.mentions.CSV.zip\n")
        def raise_for_status(self): pass
    monkeypatch.setattr(etl.requests, "get", lambda url, **kw: Resp())
    assert etl.latest_export_timestamp() == "20261116104500"


# --- aggregation -------------------------------------------------------------

def test_aggregate_rows_groups_by_place_and_root():
    rows = [
        row(url="https://a.example/1", articles="3"),
        row(url="https://www.a.example/2"),                          # same outlet (www stripped)
        row(url="https://b.example/1", actor1=("CVL", "CIVILIAN", "CVL"), name="Karaj, Tehran, Iran"),
        row(root="14", url="https://c.example/p", goldstein="-6.5"),  # other activity, other hotspot
        row(root="04", url="https://d.example/x"),                    # cooperative: ignored
        row(place="", url="https://e.example/x"),                     # no place: ignored
        row(lat="", url="https://f.example/x"),                       # no coordinates: ignored
    ]
    hour = etl.aggregate_rows(rows)
    assert set(hour) == {"IR26|19", "IR26|14"}
    fight = hour["IR26|19"]
    assert fight["domains"] == ["a.example", "b.example"]
    assert (fight["events"], fight["articles"], fight["strategic"]) == (3, 7, 2)
    assert fight["goldstein"] == -30.0
    assert fight["places"]["Tehran, Tehran, Iran"] == [2, 35.7, 51.4]
    assert list(fight["urls"])[0] == "https://a.example/1"            # best covered first
    assert fight["urls"]["https://a.example/1"]["actors"] == ["Iran"]


def test_aggregate_rows_merges_into_existing_hour_and_survives_json():
    hour = etl.aggregate_rows([row(url="https://a.example/1")])
    hour = json.loads(json.dumps(hour))
    etl.aggregate_rows([row(url="https://a.example/1"), row(url="https://b.example/2")], hour)
    cluster = hour["IR26|19"]
    assert cluster["domains"] == ["a.example", "b.example"]
    assert cluster["events"] == 3
    assert cluster["urls"]["https://a.example/1"]["articles"] == 4


# --- scoring -----------------------------------------------------------------

def _cluster(outlets, goldstein=-10.0, events=1, strategic=None):
    return {"domains": [f"d{i}" for i in range(outlets)], "events": events, "goldstein": goldstein * events,
            "strategic": events if strategic is None else strategic}


def test_score_rises_with_outlets_and_saturates():
    scores = [etl.score_cluster(_cluster(n), 8) for n in (1, 3, 8, 20, 200)]
    assert scores == sorted(scores) and scores[0] < 15 and scores[-1] == 100
    assert scores[2] == round(100 * (1 - math.exp(-1)))


def test_score_uses_severity_and_actors():
    assert etl.score_cluster(_cluster(200, goldstein=-5.0), 8) == 50
    assert etl.score_cluster(_cluster(200, goldstein=3.0), 8) == 0            # cooperative on balance
    assert etl.score_cluster(_cluster(200, strategic=0), 8) == 50             # no state or armed actor
    assert etl.score_cluster(_cluster(200, events=4, strategic=2), 8) == 75


# --- windows -----------------------------------------------------------------

def _hours(spec):
    """spec: {hour_id: [rows]} -> {hour_id: aggregated state}"""
    return {hour_id: etl.aggregate_rows(rows) for hour_id, rows in spec.items()}


def test_rank_window_counts_distinct_outlets_across_hours():
    hours = _hours({
        "2026111609": [row(url="https://a.example/1"), row(url="https://b.example/1")],
        "2026111610": [row(url="https://a.example/2"), row(url="https://c.example/1"),
                       row(place="US06", country="US", name="California, United States", url="https://z.example/1")],
    })
    window = etl.rank_window(loader(hours), "2026111610", 2, 4, 50)
    assert (window["from"], window["to"], window["hours_covered"], window["total"]) == ("2026111609", "2026111610", 2, 2)
    top, other = window["hotspots"]
    assert (top["id"], top["outlets"], top["events"]) == ("IR26|19", 3, 4)     # a.example counted once
    assert top["location"] == "Tehran, Tehran, Iran" and (top["lat"], top["lon"]) == (35.7, 51.4)
    assert top["tag"] == "conflict" and top["severity"] == 10.0 and top["strategic_share"] == 1.0
    assert len(top["links"]) == 3 and top["source_url"] == top["links"][0]["url"]
    assert other["outlets"] == 1 and top["risk_score"] > other["risk_score"]
    assert top["surge"] is None                                                # no earlier hours stored

    one_hour = etl.rank_window(loader(hours), "2026111610", 1, 4, 50)
    assert one_hour["hotspots"][0]["outlets"] == 2


def test_rank_window_reports_missing_hours_and_limits_output():
    hours = _hours({"2026111610": [row(place=f"X{i}", url=f"https://o{i}.example/") for i in range(5)]})
    window = etl.rank_window(loader(hours), "2026111610", 6, 8, 3)
    assert window["hours_covered"] == 1 and window["total"] == 5 and len(window["hotspots"]) == 3


def test_surge_compares_with_previous_windows():
    quiet = [row(url="https://a.example/1")]
    busy = [row(url=f"https://o{i}.example/") for i in range(6)]
    hours = _hours({"2026111607": quiet, "2026111608": quiet, "2026111609": quiet, "2026111610": busy})
    window = etl.rank_window(loader(hours), "2026111610", 1, 4, 50)
    assert window["hotspots"][0]["surge"] == 6.0
    # fewer than three complete previous windows: no baseline yet
    del hours["2026111608"]
    assert etl.rank_window(loader(hours), "2026111610", 1, 4, 50)["hotspots"][0]["surge"] is None


def test_surge_for_a_new_hotspot_uses_a_floor_of_one_outlet():
    other = [row(place="US06", url="https://z.example/1")]
    hours = _hours({"2026111607": other, "2026111608": other, "2026111609": other,
                    "2026111610": [row(url=f"https://o{i}.example/") for i in range(4)]})
    hotspot = next(h for h in etl.rank_window(loader(hours), "2026111610", 1, 4, 50)["hotspots"] if h["id"] == "IR26|19")
    assert hotspot["surge"] == 4.0


def test_global_index():
    assert etl.global_index([]) is None
    assert etl.global_index([{"risk_score": s} for s in (90, 70, 50)], top=2) == 80


def test_build_history_covers_days_with_data():
    hours = _hours({"2026111523": [row(url=f"https://o{i}.example/") for i in range(30)],
                    "2026111602": [row(url="https://a.example/1")]})
    history = etl.build_history(loader(hours), "2026111602", etl.DEFAULT_ETL_CONFIG, days=3)
    assert [h["date"] for h in history] == ["2026-11-14", "2026-11-15", "2026-11-16"]
    assert history[0]["avgRisk"] is None and history[0]["hours_covered"] == 0
    assert history[1]["avgRisk"] > history[2]["avgRisk"] > 0
    assert history[2]["hours_covered"] == 1                                    # today so far: hours 00-02


# --- ingest: state on disk ---------------------------------------------------

def _fake_gdelt(monkeypatch, latest, files):
    """files: {ts: rows | None (404) | Exception}"""
    requested = []
    monkeypatch.setattr(etl, "latest_export_timestamp", lambda: latest)

    def fake_download(ts):
        requested.append(ts)
        result = files.get(ts)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(etl, "download_export", fake_download)
    return requested


def test_ingest_first_run_then_catch_up(tmp_path, monkeypatch):
    state = str(tmp_path)
    config = {**etl.DEFAULT_ETL_CONFIG, "max_catchup_hours": 1}
    requested = _fake_gdelt(monkeypatch, "20261116101500", {
        "20261116093000": [row(url="https://a.example/1")],
        "20261116094500": None,
        "20261116100000": [row(url="https://b.example/1")],
        "20261116101500": [row(url="https://c.example/1")],
    })
    assert etl.ingest(state, config) == "20261116101500"
    assert requested == ["20261116093000", "20261116094500", "20261116100000", "20261116101500"]
    assert etl.stored_hours(state) == ["2026111609", "2026111610"]
    assert json.load(open(etl.hour_path(state, "2026111610")))["IR26|19"]["domains"] == ["b.example", "c.example"]

    # next run: only the new files, merged into the hour already on disk
    requested = _fake_gdelt(monkeypatch, "20261116104500", {
        "20261116103000": [row(url="https://d.example/1")],
        "20261116104500": [row(url="https://b.example/2")],
    })
    assert etl.ingest(state, config) == "20261116104500"
    assert requested == ["20261116103000", "20261116104500"]
    assert json.load(open(etl.hour_path(state, "2026111610")))["IR26|19"]["domains"] == [
        "b.example", "c.example", "d.example"]


def test_ingest_keeps_state_when_nothing_could_be_fetched(tmp_path, monkeypatch):
    state = str(tmp_path)
    config = {**etl.DEFAULT_ETL_CONFIG, "max_catchup_hours": 1}
    _fake_gdelt(monkeypatch, "20261116100000", {"20261116100000": [row()]})
    etl.ingest(state, config)
    _fake_gdelt(monkeypatch, "20261116103000", {
        "20261116101500": etl.requests.exceptions.ConnectionError("down"), "20261116103000": None})
    assert etl.ingest(state, config) is None
    assert json.load(open(os.path.join(state, "meta.json")))["last_export"] == "20261116100000"   # will retry


def test_ingest_prunes_old_hours(tmp_path, monkeypatch):
    state = str(tmp_path)
    config = {**etl.DEFAULT_ETL_CONFIG, "max_catchup_hours": 1, "retention_hours": 2}
    for ts in ("20261116060000", "20261116080000", "20261116100000"):
        _fake_gdelt(monkeypatch, ts, {ts: [row()]})
        etl.ingest(state, config)
    assert etl.stored_hours(state) == ["2026111608", "2026111610"]


def test_build_outputs_and_main_write_frontend_files(tmp_path, monkeypatch):
    state, out = str(tmp_path / "state"), str(tmp_path / "out")
    _fake_gdelt(monkeypatch, "20261116100000", {"20261116100000": [row(url=f"https://o{i}.example/") for i in range(3)]})
    monkeypatch.setattr(etl, "enrich_hotspots", lambda windows: None)
    monkeypatch.setattr(etl, "fetch_news", lambda feeds: [])
    monkeypatch.setattr(etl, "fetch_markets", lambda markets: [{"name": "X"}])
    monkeypatch.setattr(etl, "DEFAULT_ETL_CONFIG", {**etl.DEFAULT_ETL_CONFIG, "max_catchup_hours": 1})
    etl.main(["--state-dir", state, "--out-dir", out, "--config", str(tmp_path / "missing.json")])

    payload = json.load(open(os.path.join(out, "hotspots.json")))
    assert payload["data_through"] == "20261116100000"
    assert set(payload["windows"]) == {"1h", "6h", "24h", "7d"}
    assert payload["windows"]["24h"]["hotspots"][0]["outlets"] == 3
    assert payload["windows"]["24h"]["index"] == payload["windows"]["24h"]["hotspots"][0]["risk_score"]
    assert json.load(open(os.path.join(out, "history.json")))[-1]["date"] == "2026-11-16"
    assert os.path.exists(os.path.join(out, "markets.json"))
    assert not os.path.exists(os.path.join(out, "news.json"))                  # empty fetch leaves no file


def test_enrich_hotspots_fetches_each_url_once_and_survives_errors(monkeypatch):
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
    a, b, c = ({"source_url": u} for u in ("https://ok.example/a", "https://bad.example/b", "https://ok.example/c"))
    windows = {"1h": {"hotspots": [a, b, {"source_url": ""}]}, "24h": {"hotspots": [dict(a), c]}}
    etl.enrich_hotspots(windows, per_window=2)
    assert calls == ["https://ok.example/a", "https://bad.example/b", "https://ok.example/c"]
    assert a["headline"] == "Headline" and windows["24h"]["hotspots"][0]["summary"] == "Summary"
    assert "headline" not in b and c["headline"] == "Headline"


# --- article metadata, news and market parsing ------------------------------

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
