"""
RSS Feed Fetcher - Fetches from national RSS feeds, regional papers, and Google News RSS.
Adapted from authoritarianism-digest for campaign opening detection.
"""

import feedparser
import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote_plus
import html2text
import time

from models import Article
from config import (
    NATIONAL_RSS_FEEDS,
    REGIONAL_RSS_FEEDS,
    GOOGLE_NEWS_QUERIES,
    GOOGLE_NEWS_RSS_TEMPLATE,
    DEFAULT_LOOKBACK_DAYS,
    DATA_DIR,
)


def _log_query_yield(entries: list[dict]) -> None:
    """Append per-query yield records to data/query_yield_log.json."""
    if not entries:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_path = DATA_DIR / "query_yield_log.json"
    existing = []
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = []
    existing.extend(entries)
    log_path.write_text(json.dumps(existing, indent=2))


def parse_date(entry) -> Optional[datetime]:
    """Parse publication date from feed entry."""
    for field in ['published_parsed', 'updated_parsed', 'created_parsed']:
        if hasattr(entry, field) and getattr(entry, field):
            try:
                time_tuple = getattr(entry, field)
                dt = datetime(*time_tuple[:6])
                return dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue

    for field in ['published', 'updated', 'created']:
        if hasattr(entry, field) and getattr(entry, field):
            try:
                from dateutil import parser
                return parser.parse(getattr(entry, field))
            except (ValueError, TypeError):
                continue

    return None


def extract_content(entry) -> tuple[str, Optional[str]]:
    """Extract text content from feed entry, returning (plain_text, raw_html)."""
    html_content = None

    if hasattr(entry, 'content') and entry.content:
        for c in entry.content:
            if isinstance(c, dict) and 'value' in c:
                html_content = c['value']
                break
    elif hasattr(entry, 'summary') and entry.summary:
        html_content = entry.summary
    elif hasattr(entry, 'description') and entry.description:
        html_content = entry.description

    if not html_content:
        return entry.get('title', ''), None

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.body_width = 0
    plain_text = h.handle(html_content)

    return plain_text.strip(), html_content


def fetch_feed(name: str, url: str, cutoff_time: datetime, source_type: str = "rss") -> list[Article]:
    """Fetch a single RSS feed and return articles newer than cutoff."""
    articles = []

    try:
        response = requests.get(
            url,
            timeout=30,
            headers={'User-Agent': 'VibeCampaigning/1.0 (campaign opening scanner)'}
        )
        response.raise_for_status()

        feed = feedparser.parse(response.content)

        if feed.bozo and feed.bozo_exception:
            print(f"    Warning: Feed {name} had parsing issues: {feed.bozo_exception}")

        for entry in feed.entries:
            pub_date = parse_date(entry)

            if not pub_date:
                pub_date = datetime.now(timezone.utc)
            elif pub_date < cutoff_time:
                continue

            entry_url = entry.get('link', '')
            if not entry_url:
                continue

            content, raw_html = extract_content(entry)

            article = Article(
                title=entry.get('title', 'No title'),
                url=entry_url,
                source=name,
                published=pub_date,
                content=content,
                raw_html=raw_html,
                source_type=source_type,
            )
            articles.append(article)

    except requests.RequestException as e:
        print(f"    Error fetching {name}: {e}")
    except Exception as e:
        print(f"    Unexpected error processing {name}: {e}")

    return articles


def fetch_national_feeds(lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> list[Article]:
    """Fetch all national RSS feeds in parallel."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    print(f"Fetching national RSS feeds in parallel (last {lookback_days} days)...")

    def _fetch(item):
        name, url = item
        articles = fetch_feed(name, url, cutoff, source_type="rss")
        print(f"  {name}: {len(articles)} articles")
        return articles

    all_articles = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        for result in as_completed([executor.submit(_fetch, item) for item in NATIONAL_RSS_FEEDS.items()]):
            all_articles.extend(result.result())

    unique = list({a.url: a for a in all_articles}.values())
    print(f"  National feeds: {len(unique)} unique articles from {len(NATIONAL_RSS_FEEDS)} feeds")
    return sorted(unique, key=lambda a: a.published, reverse=True)


def fetch_regional_feeds(lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> list[Article]:
    """Fetch all regional paper RSS feeds in parallel."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    print(f"\nFetching regional paper RSS feeds in parallel (last {lookback_days} days)...")

    def _fetch(item):
        name, url = item
        articles = fetch_feed(name, url, cutoff, source_type="rss")
        print(f"  {name}: {len(articles)} articles")
        return articles

    all_articles = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        for result in as_completed([executor.submit(_fetch, item) for item in REGIONAL_RSS_FEEDS.items()]):
            all_articles.extend(result.result())

    unique = list({a.url: a for a in all_articles}.values())
    print(f"  Regional feeds: {len(unique)} unique articles from {len(REGIONAL_RSS_FEEDS)} feeds")
    return sorted(unique, key=lambda a: a.published, reverse=True)


def fetch_google_news(lookback_days: int = DEFAULT_LOOKBACK_DAYS, interleave_fn=None, interleave_every: int = 5, batch_pause_every: int = 25, batch_pause_secs: int = 120) -> list[Article]:
    """Fetch Google News RSS feeds using targeted queries from Framework #1."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    all_articles = []
    seen_urls = set()

    print(f"\nFetching Google News RSS ({len(GOOGLE_NEWS_QUERIES)} targeted queries)...")

    # Canary check — if high-traffic queries return zero, we're rate-limited
    canary_queries = ["Trump Congress", "United States politics"]
    canary_hits = 0
    for cq in canary_queries:
        try:
            r = requests.get(
                GOOGLE_NEWS_RSS_TEMPLATE.format(query=quote_plus(cq)),
                timeout=30,
                headers={'User-Agent': 'VibeCampaigning/1.0 (campaign opening scanner)'}
            )
            r.raise_for_status()
            canary_hits += len(feedparser.parse(r.content).entries)
        except Exception:
            pass
    if canary_hits == 0:
        print("  ABORT: Google News canary queries returned zero results — rate-limited. Wait and retry.")
        return []
    print(f"  Canary check passed ({canary_hits} results) — proceeding.")

    _now = datetime.now(timezone.utc)
    run_date = _now.strftime("%Y-%m-%d")
    run_ts = _now.isoformat()
    yield_log = []

    for i, query in enumerate(GOOGLE_NEWS_QUERIES):
        encoded_query = quote_plus(query)
        url = GOOGLE_NEWS_RSS_TEMPLATE.format(query=encoded_query)

        print(f"  [{i+1}/{len(GOOGLE_NEWS_QUERIES)}] Searching: {query[:60]}...")

        try:
            response = requests.get(
                url,
                timeout=30,
                headers={'User-Agent': 'VibeCampaigning/1.0 (campaign opening scanner)'}
            )
            response.raise_for_status()

            feed = feedparser.parse(response.content)
            count = 0

            for entry in feed.entries:
                pub_date = parse_date(entry)
                if not pub_date:
                    pub_date = datetime.now(timezone.utc)
                elif pub_date < cutoff:
                    continue

                entry_url = entry.get('link', '')
                if not entry_url or entry_url in seen_urls:
                    continue

                seen_urls.add(entry_url)

                # Google News entries often have minimal content
                content = entry.get('summary', entry.get('title', ''))
                # Strip HTML from summary
                h = html2text.HTML2Text()
                h.ignore_links = True
                h.ignore_images = True
                h.body_width = 0
                content = h.handle(content).strip() if '<' in content else content

                article = Article(
                    title=entry.get('title', 'No title'),
                    url=entry_url,
                    source=f"Google News: {query[:40]}",
                    published=pub_date,
                    content=content,
                    source_type="gnews",
                    source_query=query,
                )
                all_articles.append(article)
                count += 1

            print(f"    Found {count} articles")
            yield_log.append({"date": run_date, "run_ts": run_ts, "query": query, "count": count, "source": "hardcoded"})

        except requests.RequestException as e:
            print(f"    Error: {e}")
            yield_log.append({"date": run_date, "run_ts": run_ts, "query": query, "count": 0, "source": "hardcoded", "error": str(e)})
            count = 0
        except Exception as e:
            print(f"    Unexpected error: {e}")
            yield_log.append({"date": run_date, "run_ts": run_ts, "query": query, "count": 0, "source": "hardcoded", "error": str(e)})
            count = 0

        if batch_pause_every and (i + 1) % batch_pause_every == 0 and (i + 1) < len(GOOGLE_NEWS_QUERIES):
            print(f"  [batch pause] {batch_pause_secs}s cooldown after query {i+1} to reduce rate limiting...")
            time.sleep(batch_pause_secs)

        if interleave_fn and (i + 1) % interleave_every == 0:
            interleave_fn()
        elif count == 0:
            print(f"    (zero results — backing off 30s, then retrying)")
            time.sleep(30)
            # Retry once to distinguish rate-limiting from genuine zero results
            try:
                retry_response = requests.get(url, timeout=30,
                    headers={'User-Agent': 'VibeCampaigning/1.0 (campaign opening scanner)'})
                retry_response.raise_for_status()
                retry_feed = feedparser.parse(retry_response.content)
                retry_count = 0
                for entry in retry_feed.entries:
                    pub_date = parse_date(entry)
                    if not pub_date:
                        pub_date = datetime.now(timezone.utc)
                    elif pub_date < cutoff:
                        continue
                    entry_url = entry.get('link', '')
                    if not entry_url or entry_url in seen_urls:
                        continue
                    seen_urls.add(entry_url)
                    content = entry.get('summary', entry.get('title', ''))
                    h = html2text.HTML2Text()
                    h.ignore_links = True
                    h.ignore_images = True
                    h.body_width = 0
                    content = h.handle(content).strip() if '<' in content else content
                    article = Article(
                        title=entry.get('title', 'No title'),
                        url=entry_url,
                        source=f"Google News: {query[:40]}",
                        published=pub_date,
                        content=content,
                        source_type="gnews",
                        source_query=query,
                    )
                    all_articles.append(article)
                    retry_count += 1
                if retry_count > 0:
                    print(f"    (retry recovered {retry_count} articles — was rate-limited)")
                    yield_log[-1]["count"] = retry_count
                    yield_log[-1]["rate_limited"] = True
                else:
                    print(f"    (retry also zero — genuine no results)")
                    yield_log[-1]["genuine_zero"] = True
            except Exception:
                pass
            time.sleep(2)
        else:
            time.sleep(2)

    _log_query_yield(yield_log)
    print(f"  Google News: {len(all_articles)} unique articles from {len(GOOGLE_NEWS_QUERIES)} queries")
    return sorted(all_articles, key=lambda a: a.published, reverse=True)


def fetch_google_news_queries(queries: list[str], lookback_days: int = DEFAULT_LOOKBACK_DAYS, batch_pause_every: int = 25, batch_pause_secs: int = 120) -> list[Article]:
    """Fetch Google News RSS for an arbitrary list of query strings (e.g., from dynamic generation)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    all_articles = []
    seen_urls = set()

    _now = datetime.now(timezone.utc)
    run_date = _now.strftime("%Y-%m-%d")
    run_ts = _now.isoformat()
    yield_log = []

    for i, query in enumerate(queries):
        encoded_query = quote_plus(query)
        url = GOOGLE_NEWS_RSS_TEMPLATE.format(query=encoded_query)

        print(f"    [{i+1}/{len(queries)}] {query[:60]}...")

        try:
            response = requests.get(
                url,
                timeout=30,
                headers={'User-Agent': 'VibeCampaigning/1.0 (campaign idea generator)'}
            )
            response.raise_for_status()

            feed = feedparser.parse(response.content)
            count = 0

            for entry in feed.entries:
                pub_date = parse_date(entry)
                if not pub_date:
                    pub_date = datetime.now(timezone.utc)
                elif pub_date < cutoff:
                    continue

                entry_url = entry.get('link', '')
                if not entry_url or entry_url in seen_urls:
                    continue

                seen_urls.add(entry_url)

                content = entry.get('summary', entry.get('title', ''))
                h = html2text.HTML2Text()
                h.ignore_links = True
                h.ignore_images = True
                h.body_width = 0
                content = h.handle(content).strip() if '<' in content else content

                article = Article(
                    title=entry.get('title', 'No title'),
                    url=entry_url,
                    source=f"Dynamic: {query[:40]}",
                    published=pub_date,
                    content=content,
                    source_type="gnews",
                    source_query=query,
                )
                all_articles.append(article)
                count += 1

            if count > 0:
                print(f"      Found {count} articles")
            yield_log.append({"date": run_date, "run_ts": run_ts, "query": query, "count": count, "source": "dynamic"})

        except requests.RequestException as e:
            print(f"      Error: {e}")
            yield_log.append({"date": run_date, "run_ts": run_ts, "query": query, "count": 0, "source": "dynamic", "error": str(e)})
            count = 0
        except Exception as e:
            print(f"      Unexpected error: {e}")
            yield_log.append({"date": run_date, "run_ts": run_ts, "query": query, "count": 0, "source": "dynamic", "error": str(e)})
            count = 0

        if batch_pause_every and (i + 1) % batch_pause_every == 0 and (i + 1) < len(queries):
            print(f"    [batch pause] {batch_pause_secs}s cooldown after query {i+1} to reduce rate limiting...")
            time.sleep(batch_pause_secs)

        if count == 0:
            print(f"      (zero results — backing off 30s, then retrying)")
            time.sleep(30)
            try:
                retry_response = requests.get(url, timeout=30,
                    headers={'User-Agent': 'VibeCampaigning/1.0 (campaign idea generator)'})
                retry_response.raise_for_status()
                retry_feed = feedparser.parse(retry_response.content)
                retry_count = 0
                for entry in retry_feed.entries:
                    pub_date = parse_date(entry)
                    if not pub_date:
                        pub_date = datetime.now(timezone.utc)
                    elif pub_date < cutoff:
                        continue
                    entry_url = entry.get('link', '')
                    if not entry_url or entry_url in seen_urls:
                        continue
                    seen_urls.add(entry_url)
                    content = entry.get('summary', entry.get('title', ''))
                    h = html2text.HTML2Text()
                    h.ignore_links = True
                    h.ignore_images = True
                    h.body_width = 0
                    content = h.handle(content).strip() if '<' in content else content
                    article = Article(
                        title=entry.get('title', 'No title'),
                        url=entry_url,
                        source=f"Dynamic: {query[:40]}",
                        published=pub_date,
                        content=content,
                        source_type="gnews",
                        source_query=query,
                    )
                    all_articles.append(article)
                    retry_count += 1
                if retry_count > 0:
                    print(f"      (retry recovered {retry_count} articles — was rate-limited)")
                    yield_log[-1]["count"] = retry_count
                    yield_log[-1]["rate_limited"] = True
                else:
                    print(f"      (retry also zero — genuine no results)")
                    yield_log[-1]["genuine_zero"] = True
            except Exception:
                pass
            time.sleep(2)
        else:
            time.sleep(2)

    _log_query_yield(yield_log)
    print(f"  Dynamic queries: {len(all_articles)} unique articles from {len(queries)} queries")
    return sorted(all_articles, key=lambda a: a.published, reverse=True)


def fetch_all_feeds(lookback_days: int = DEFAULT_LOOKBACK_DAYS, sources: list[str] = None, interleave_fn=None) -> list[Article]:
    """Fetch all configured RSS-based feeds and return combined articles.

    Args:
        lookback_days: How many days back to look
        sources: List of source types to include ('rss', 'regional', 'gnews'). None = all.
    """
    if sources is None:
        sources = ['rss', 'regional', 'gnews']

    all_articles = []

    if 'rss' in sources:
        all_articles.extend(fetch_national_feeds(lookback_days))

    if 'regional' in sources:
        all_articles.extend(fetch_regional_feeds(lookback_days))

    if 'gnews' in sources:
        all_articles.extend(fetch_google_news(lookback_days, interleave_fn=interleave_fn))

    # Deduplicate by URL
    unique = list({a.url: a for a in all_articles}.values())

    print(f"\nTotal RSS-based sources: {len(unique)} unique articles")
    return sorted(unique, key=lambda a: a.published, reverse=True)


if __name__ == "__main__":
    articles = fetch_all_feeds(lookback_days=7)
    print("\n--- Sample Articles ---")
    for article in articles[:10]:
        print(f"\n[{article.source_type}] {article.source}: {article.title}")
        print(f"  URL: {article.url}")
        print(f"  Published: {article.published}")
        print(f"  Content preview: {article.content[:200]}...")
