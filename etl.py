"""
ETL for the Geopolitical Risk Dashboard.

Every run catches up on all GDELT 2.0 event exports published since the last
run (one file per 15 minutes), groups conflict events into hotspots by place
and kind of activity, and ranks hotspots by how many distinct news outlets
reported them. Single GDELT events are often miscoded; an event that many
outlets report independently is far more likely to be real.

State lives in a directory given by --state-dir (kept on a separate branch by
the workflow) and the files the frontend reads are written to --out-dir.
"""
import argparse
import csv
import io
import json
import math
import os
import re
import zipfile
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote, urlparse
from xml.etree import ElementTree

import requests

GDELT_BASE = "http://data.gdeltproject.org/gdeltv2/"
EXPORT_INTERVAL = timedelta(minutes=15)
TS_FORMAT = "%Y%m%d%H%M%S"
HOUR_FORMAT = "%Y%m%d%H"

# GDELT 2.0 event export columns (0-based, 61 columns, tab-delimited, no header)
COL = {
    "Actor1Code": 5, "Actor1Name": 6, "Actor1Type1Code": 12, "Actor1Type2Code": 13, "Actor1Type3Code": 14,
    "Actor2Code": 15, "Actor2Name": 16, "Actor2Type1Code": 22, "Actor2Type2Code": 23, "Actor2Type3Code": 24,
    "EventCode": 26, "EventBaseCode": 27, "EventRootCode": 28, "GoldsteinScale": 30,
    "NumArticles": 33, "AvgTone": 34,
    "ActionGeo_FullName": 52, "ActionGeo_CountryCode": 53, "ActionGeo_ADM1Code": 54,
    "ActionGeo_Lat": 56, "ActionGeo_Long": 57, "SOURCEURL": 60,
}

# CAMEO root codes kept as hotspot activity: threats (13) and material conflict (14-20).
CONFLICT_ROOTS = {"13", "14", "15", "16", "17", "18", "19", "20"}
TAG_BY_ROOT = {"13": "threat", "14": "protest", "15": "posture", "16": "sanction",
               "17": "coercion", "18": "conflict", "19": "conflict", "20": "conflict"}

# CAMEO actor types that make an event geopolitical rather than local: government,
# military, rebels, insurgents, separatists, state intelligence, unaligned armed
# forces and intergovernmental organisations.
STRATEGIC_ACTOR_TYPES = {"GOV", "MIL", "REB", "INS", "SEP", "SPY", "UAF", "IGO"}

DEFAULT_ETL_CONFIG = {
    # Hours of exports to fetch when there is no state yet, and the most to catch up on in one run.
    "max_catchup_hours": 24,
    # How long hourly state is kept (the longest window plus room for a baseline).
    "retention_hours": 24 * 9,
    # Ranking windows in hours.
    "windows": {"1h": 1, "6h": 6, "24h": 24, "7d": 168},
    # Outlets at which coverage reaches about 63% of its maximum, per window.
    "coverage_scale": {"1h": 4, "6h": 8, "24h": 15, "7d": 40},
    # Hotspots written per window.
    "max_hotspots": 250,
}


# --- GDELT download ---------------------------------------------------------

def parse_ts(ts):
    return datetime.strptime(ts, TS_FORMAT)


def latest_export_timestamp(timeout=30):
    """Reads lastupdate.txt and returns the newest export timestamp (YYYYMMDDHHMMSS)."""
    resp = requests.get(GDELT_BASE + "lastupdate.txt", timeout=timeout)
    resp.raise_for_status()
    match = re.search(r"/(\d{14})\.export\.CSV\.zip", resp.text)
    if not match:
        raise ValueError("no export file listed in lastupdate.txt")
    return match.group(1)


def timestamps_to_fetch(last_ts, latest_ts, max_hours):
    """
    Export timestamps after `last_ts` up to `latest_ts`, oldest first, limited
    to the most recent `max_hours`. With no `last_ts` the whole limit is fetched.
    """
    latest = parse_ts(latest_ts)
    start = latest - timedelta(hours=max_hours) + EXPORT_INTERVAL
    if last_ts:
        start = max(start, parse_ts(last_ts) + EXPORT_INTERVAL)
    # exports are published on quarter hours
    start -= timedelta(minutes=start.minute % 15, seconds=start.second)
    out = []
    current = start
    while current <= latest:
        out.append(current.strftime(TS_FORMAT))
        current += EXPORT_INTERVAL
    return out


def download_export(ts, timeout=60):
    """
    Downloads one export and returns its rows, or None when the file is not
    there (GDELT skips an interval now and then, and lastupdate.txt can list a
    file a moment before it is published).
    """
    resp = requests.get(f"{GDELT_BASE}{ts}.export.CSV.zip", timeout=timeout)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        with zf.open(zf.namelist()[0]) as f:
            text = f.read().decode("utf-8", errors="replace")
    return [row for row in csv.reader(io.StringIO(text), delimiter="\t") if len(row) >= 61]


# --- Hourly aggregation -----------------------------------------------------

def source_domain(url):
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _is_strategic(row, n):
    types = {row[COL[f"Actor{n}Type{i}Code"]] for i in (1, 2, 3)}
    return bool(types & STRATEGIC_ACTOR_TYPES)


def aggregate_rows(rows, into=None):
    """
    Groups conflict rows into hotspots keyed by "<ADM1 code>|<CAMEO root>" and
    merges them into `into` (the state of one hour). Each hotspot keeps the
    distinct outlet domains, article and event counts, the Goldstein sum, how
    many events involve a state or armed actor, place-name counts and the
    best-covered source URLs.
    """
    hour = into if into is not None else {}
    for row in rows:
        root = row[COL["EventRootCode"]]
        place = row[COL["ActionGeo_ADM1Code"]]
        lat, lon = _to_float(row[COL["ActionGeo_Lat"]]), _to_float(row[COL["ActionGeo_Long"]])
        if root not in CONFLICT_ROOTS or not place or lat is None or lon is None:
            continue
        url = row[COL["SOURCEURL"]]
        domain = source_domain(url)
        articles = int(_to_float(row[COL["NumArticles"]]) or 1)
        cluster = hour.setdefault(f"{place}|{root}", {
            "country": row[COL["ActionGeo_CountryCode"]], "domains": [], "events": 0, "articles": 0,
            "goldstein": 0.0, "tone": 0.0, "strategic": 0, "places": {}, "urls": {},
        })
        cluster["events"] += 1
        cluster["articles"] += articles
        cluster["goldstein"] += _to_float(row[COL["GoldsteinScale"]]) or 0.0
        cluster["tone"] += _to_float(row[COL["AvgTone"]]) or 0.0
        if _is_strategic(row, 1) or _is_strategic(row, 2):
            cluster["strategic"] += 1
        if domain and domain not in cluster["domains"]:
            cluster["domains"].append(domain)
        name = row[COL["ActionGeo_FullName"]]
        if name:
            entry = cluster["places"].setdefault(name, [0, lat, lon])
            entry[0] += 1
        if url.startswith(("http://", "https://")):
            entry = cluster["urls"].setdefault(url, {
                "articles": 0, "code": row[COL["EventBaseCode"]],
                "actors": [a.title() for a in (row[COL["Actor1Name"]], row[COL["Actor2Name"]]) if a],
            })
            entry["articles"] += articles
    # keep hour files small: only the best-covered URLs and most common place names
    for cluster in hour.values():
        cluster["urls"] = dict(sorted(cluster["urls"].items(), key=lambda kv: -kv[1]["articles"])[:5])
        cluster["places"] = dict(sorted(cluster["places"].items(), key=lambda kv: -kv[1][0])[:5])
    return hour


# --- State on disk ----------------------------------------------------------

def _read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))


def hour_path(state_dir, hour_id):
    return os.path.join(state_dir, "hours", f"{hour_id}.json")


def stored_hours(state_dir):
    try:
        names = os.listdir(os.path.join(state_dir, "hours"))
    except OSError:
        return []
    return sorted(name[:-5] for name in names if re.fullmatch(r"\d{10}\.json", name))


def prune_hours(state_dir, newest_hour, retention_hours):
    cutoff = (datetime.strptime(newest_hour, HOUR_FORMAT) - timedelta(hours=retention_hours)).strftime(HOUR_FORMAT)
    removed = 0
    for hour_id in stored_hours(state_dir):
        if hour_id < cutoff:
            os.remove(hour_path(state_dir, hour_id))
            removed += 1
    return removed


def ingest(state_dir, etl_config):
    """
    Fetches every export published since the last run into the hourly state.
    Returns the newest export timestamp, or None when nothing could be fetched
    (the state is then left untouched so the next run retries).
    """
    meta_path = os.path.join(state_dir, "meta.json")
    meta = _read_json(meta_path, {})
    latest = latest_export_timestamp()
    todo = timestamps_to_fetch(meta.get("last_export"), latest, etl_config["max_catchup_hours"])
    print(f"GDELT: latest export {latest}, {len(todo)} file(s) to fetch.")

    hours = {}
    fetched = missing = failed = 0
    for ts in todo:
        try:
            rows = download_export(ts)
        except Exception as e:
            print(f"Error fetching export {ts}: {e}")
            failed += 1
            continue
        if rows is None:
            missing += 1
            continue
        fetched += 1
        hour_id = ts[:10]
        if hour_id not in hours:
            hours[hour_id] = _read_json(hour_path(state_dir, hour_id), {})
        aggregate_rows(rows, hours[hour_id])
    print(f"GDELT: {fetched} fetched, {missing} not published, {failed} failed.")

    if todo and fetched == 0:
        return None
    for hour_id, clusters in hours.items():
        _write_json(hour_path(state_dir, hour_id), clusters)
    meta["last_export"] = latest
    _write_json(meta_path, meta)
    removed = prune_hours(state_dir, latest[:10], etl_config["retention_hours"])
    print(f"State: {len(stored_hours(state_dir))} hour(s) kept, {removed} pruned.")
    return latest


# --- Windows, scoring, surge ------------------------------------------------

def hour_range(end_hour, length):
    """The `length` hour ids ending with `end_hour`, oldest first."""
    end = datetime.strptime(end_hour, HOUR_FORMAT)
    return [(end - timedelta(hours=i)).strftime(HOUR_FORMAT) for i in range(length - 1, -1, -1)]


def merge_hours(hour_states):
    """Merges several hours of hotspots into one set (domains become sets)."""
    merged = {}
    for state in hour_states:
        for key, cluster in state.items():
            target = merged.setdefault(key, {
                "country": cluster["country"], "domains": set(), "events": 0, "articles": 0,
                "goldstein": 0.0, "tone": 0.0, "strategic": 0, "places": {}, "urls": {},
            })
            target["domains"].update(cluster["domains"])
            for field in ("events", "articles", "goldstein", "tone", "strategic"):
                target[field] += cluster[field]
            for name, (count, lat, lon) in cluster["places"].items():
                entry = target["places"].setdefault(name, [0, lat, lon])
                entry[0] += count
            for url, info in cluster["urls"].items():
                entry = target["urls"].setdefault(url, {**info, "articles": 0})
                entry["articles"] += info["articles"]
    return merged


def score_cluster(cluster, coverage_scale):
    """
    0-100: severity x coverage x actor factor.
      severity  how conflictual the events are (mean Goldstein scale, 0 to -10)
      coverage  1 - exp(-outlets / scale): one outlet counts for little, many saturate
      actors    0.5 when no event involves a state or armed actor, up to 1.0 when all do
    """
    events = max(cluster["events"], 1)
    severity = min(max(-cluster["goldstein"] / events, 0.0), 10.0) / 10.0
    coverage = 1.0 - math.exp(-len(cluster["domains"]) / coverage_scale)
    actors = 0.5 + 0.5 * (cluster["strategic"] / events)
    return round(100 * severity * coverage * actors)


def rank_window(load_hour, end_hour, length, coverage_scale, max_hotspots, baseline_windows=6):
    """
    Ranks the hotspots of the `length` hours ending at `end_hour`.

    "surge" compares the outlet count with the mean of up to `baseline_windows`
    preceding windows of the same length; it is None until at least three such
    windows are fully covered by stored data.
    """
    hours = hour_range(end_hour, length)
    states = [load_hour(h) for h in hours]
    covered = sum(1 for state in states if state is not None)
    merged = merge_hours([state for state in states if state])

    previous = []
    for i in range(1, baseline_windows + 1):
        end = (datetime.strptime(end_hour, HOUR_FORMAT) - timedelta(hours=i * length)).strftime(HOUR_FORMAT)
        prev_states = [load_hour(h) for h in hour_range(end, length)]
        if any(state is None for state in prev_states):
            break
        previous.append(merge_hours(prev_states))

    hotspots = []
    for key, cluster in merged.items():
        place_code, root = key.split("|")
        name, (_, lat, lon) = max(cluster["places"].items(), key=lambda kv: kv[1][0]) if cluster["places"] \
            else (cluster["country"], (0, None, None))
        outlets = len(cluster["domains"])
        surge = None
        if len(previous) >= 3:
            baseline = sum(len(p[key]["domains"]) if key in p else 0 for p in previous) / len(previous)
            surge = round(outlets / max(baseline, 1.0), 1)
        links = [
            {"url": url, "domain": source_domain(url), "code": info["code"], "actors": info["actors"]}
            for url, info in sorted(cluster["urls"].items(), key=lambda kv: -kv[1]["articles"])[:3]
        ]
        events = max(cluster["events"], 1)
        hotspots.append({
            "id": key,
            "risk_score": score_cluster(cluster, coverage_scale),
            "country": cluster["country"],
            "location": name,
            "lat": lat,
            "lon": lon,
            "event_code": root,
            "tag": TAG_BY_ROOT.get(root, "conflict"),
            "outlets": outlets,
            "articles": cluster["articles"],
            "events": cluster["events"],
            "severity": round(min(max(-cluster["goldstein"] / events, 0.0), 10.0), 1),
            "tone": round(cluster["tone"] / events, 1),
            "strategic_share": round(cluster["strategic"] / events, 2),
            "surge": surge,
            "links": links,
            "source_url": links[0]["url"] if links else "",
        })
    hotspots.sort(key=lambda h: (-h["risk_score"], -h["outlets"], h["id"]))
    return {
        "from": hours[0], "to": hours[-1], "hours": length, "hours_covered": covered,
        "total": len(hotspots), "hotspots": hotspots[:max_hotspots],
    }


def global_index(hotspots, top=20):
    """One number for a window: the mean score of its `top` highest hotspots."""
    scores = sorted((h["risk_score"] for h in hotspots), reverse=True)[:top]
    return round(sum(scores) / len(scores)) if scores else None


def build_history(load_hour, end_hour, etl_config, days=14):
    """Daily global index for the UTC days that have stored data, oldest first."""
    end = datetime.strptime(end_hour, HOUR_FORMAT)
    history = []
    for offset in range(days - 1, -1, -1):
        day = (end - timedelta(days=offset)).replace(hour=23)
        last_hour = min(day, end).strftime(HOUR_FORMAT)
        length = int(last_hour[8:]) + 1
        window = rank_window(load_hour, last_hour, length, etl_config["coverage_scale"]["24h"],
                             etl_config["max_hotspots"], baseline_windows=0)
        history.append({
            "date": day.strftime("%Y-%m-%d"),
            "avgRisk": global_index(window["hotspots"]) if window["hours_covered"] else None,
            "hours_covered": window["hours_covered"],
        })
    return history


def build_outputs(state_dir, end_hour, etl_config):
    """Returns (hotspots payload, history) from the stored hours."""
    cache = {}
    available = set(stored_hours(state_dir))

    def load_hour(hour_id):
        if hour_id not in available:
            return None
        if hour_id not in cache:
            cache[hour_id] = _read_json(hour_path(state_dir, hour_id), {})
        return cache[hour_id]

    windows = {}
    for name, length in etl_config["windows"].items():
        window = rank_window(load_hour, end_hour, length, etl_config["coverage_scale"][name],
                             etl_config["max_hotspots"])
        window["index"] = global_index(window["hotspots"])
        windows[name] = window
        print(f"Window {name}: {window['total']} hotspots, {window['hours_covered']}/{length}h covered, "
              f"index {window['index']}")
    return windows, build_history(load_hour, end_hour, etl_config)


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


def enrich_hotspots(windows, per_window=10, limit=30, timeout=8):
    """
    Adds "headline" and "summary" to the top hotspots of every window from the
    title/description metadata of their best-covered article. Each URL is
    fetched once; failures are skipped so a slow or blocked site never fails the run.
    """
    fetched = {}
    for window in windows.values():
        for hotspot in window["hotspots"][:per_window]:
            url = hotspot.get("source_url") or ""
            if not url:
                continue
            if url not in fetched:
                if len(fetched) >= limit:
                    continue
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
                hotspot["headline"] = headline
            if summary:
                hotspot["summary"] = summary
    found = sum(1 for headline, _ in fetched.values() if headline)
    print(f"Article metadata: {found} of {len(fetched)} pages gave a headline.")


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


def save_json(payload, filename, static_data_dir="static/data", indent=2):
    os.makedirs(static_data_dir, exist_ok=True)
    path = os.path.join(static_data_dir, filename)
    with open(path, "w") as f:
        json.dump(payload, f, indent=indent, ensure_ascii=False)
    print(f"Saved {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--state-dir", default="_state/state", help="where hourly state is kept between runs")
    parser.add_argument("--out-dir", default="static/data", help="where the frontend's data files are written")
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args(argv)

    print("Starting ETL script...")
    config = load_config(args.config)
    etl_config = {**DEFAULT_ETL_CONFIG, **config.get("etl", {})}
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    print("\n--- Fetching GDELT ---")
    try:
        latest = ingest(args.state_dir, etl_config)
    except Exception as e:
        print(f"GDELT ingest failed: {e}")
        latest = None
    if latest is None:
        # Nothing new could be fetched; rebuild from what is stored, if anything.
        hours = stored_hours(args.state_dir)
        latest = hours[-1] + "0000" if hours else None

    if latest:
        print("\n--- Ranking Hotspots ---")
        windows, history = build_outputs(args.state_dir, latest[:10], etl_config)
        print("\n--- Reading Article Metadata ---")
        enrich_hotspots(windows)
        save_json({"updated": fetched_at, "data_through": latest, "windows": windows}, "hotspots.json", args.out_dir, indent=None)
        save_json(history, "history.json", args.out_dir)
    else:
        print("WARNING: no GDELT data stored or fetched; hotspot files left unchanged.")

    # Ticker feeds. Each file is only replaced when its fetch returned something,
    # so a failed source leaves the previous data in place.
    print("\n--- Fetching Ticker Data ---")
    news_items = fetch_news(config.get("news_feeds", []))
    if news_items:
        save_json({"updated": fetched_at, "items": news_items}, "news.json", args.out_dir)
    market_items = fetch_markets(config.get("markets", []))
    if market_items:
        save_json({"updated": fetched_at, "items": market_items}, "markets.json", args.out_dir)

    print("\nETL script finished.")


if __name__ == "__main__":
    main()
