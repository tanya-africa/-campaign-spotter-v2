#!/usr/bin/env python3
"""
Vibe-Campaigning Opening Scanner

Scans multiple sources for campaign openings using Framework #1 criteria.
Produces a structured list of openings for collaborative review.

Usage:
    python main.py                          # Full 30-day scan, all sources
    python main.py --lookback-days 7        # Last 7 days only
    python main.py --sources gnews,reddit   # Only specific sources
    python main.py --max-openings 100       # Cap at 100 openings
    python main.py --preview                # Skip Gmail, use RSS + social + Google News
"""

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config import DEFAULT_LOOKBACK_DAYS, MAX_OPENINGS, DATA_DIR
from models import Article


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scan for campaign openings across multiple sources"
    )
    parser.add_argument(
        '--lookback-days', type=int, default=DEFAULT_LOOKBACK_DAYS,
        help=f"How many days back to scan (default: {DEFAULT_LOOKBACK_DAYS})"
    )
    parser.add_argument(
        '--sources', type=str, default=None,
        help="Comma-separated source types: rss,regional,gnews,gmail,reddit,bluesky (default: all)"
    )
    parser.add_argument(
        '--max-openings', type=int, default=MAX_OPENINGS,
        help=f"Maximum number of openings to output (default: {MAX_OPENINGS})"
    )
    parser.add_argument(
        '--output-dir', type=str, default=None,
        help="Directory for output files (default: ./data)"
    )
    parser.add_argument(
        '--preview', action='store_true',
        help="Preview mode: skip Gmail, use only RSS + social + Google News"
    )
    return parser.parse_args()


def deduplicate_articles(articles: list[Article]) -> list[Article]:
    """Deduplicate articles by URL and normalized title."""
    seen_urls = set()
    seen_titles = set()
    unique = []

    for article in articles:
        # Normalize URL
        url_key = article.url.lower().rstrip('/')

        # Normalize title (alphanumeric only)
        title_key = re.sub(r'[^a-z0-9]', '', article.title.lower())

        if url_key in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue

        seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        unique.append(article)

    return unique


def run_scan():
    args = parse_args()

    start_time = time.time()
    lookback_days = args.lookback_days

    # Determine which sources to use
    if args.sources:
        sources = [s.strip() for s in args.sources.split(',')]
    elif args.preview:
        sources = ['rss', 'regional', 'gnews', 'reddit', 'bluesky']
    else:
        sources = ['rss', 'regional', 'gnews', 'gmail', 'reddit', 'bluesky']

    # Output directory
    output_dir = Path(args.output_dir) if args.output_dir else DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'='*60}")
    print(f"  VIBE-CAMPAIGNING: Campaign Opening Scanner")
    print(f"  Lookback: {lookback_days} days")
    print(f"  Sources: {', '.join(sources)}")
    print(f"  Max openings: {args.max_openings}")
    print(f"{'='*60}\n")

    # =========================================================================
    # Step 1: Fetch from all sources
    # =========================================================================
    all_articles = []

    # RSS-based sources (national, regional, Google News)
    rss_sources = [s for s in sources if s in ('rss', 'regional', 'gnews')]
    if rss_sources:
        from rss_fetcher import fetch_all_feeds
        rss_articles = fetch_all_feeds(lookback_days=lookback_days, sources=rss_sources)
        all_articles.extend(rss_articles)
        print(f"\n  RSS-based sources: {len(rss_articles)} articles")

    # Gmail newsletters
    if 'gmail' in sources:
        try:
            from gmail_reader import fetch_emails
            gmail_articles = fetch_emails(lookback_days=lookback_days)
            all_articles.extend(gmail_articles)
            print(f"  Gmail newsletters: {len(gmail_articles)} articles")
        except Exception as e:
            print(f"  Warning: Gmail fetch failed ({e}), continuing without email sources")

    # Reddit
    if 'reddit' in sources:
        try:
            from reddit_fetcher import fetch_reddit_posts
            reddit_articles = fetch_reddit_posts(lookback_days=lookback_days)
            all_articles.extend(reddit_articles)
            print(f"  Reddit: {len(reddit_articles)} posts")
        except Exception as e:
            print(f"  Warning: Reddit fetch failed ({e}), continuing")

    # Bluesky
    if 'bluesky' in sources:
        try:
            from bluesky_fetcher import fetch_bluesky_posts
            bluesky_articles = fetch_bluesky_posts(lookback_days=lookback_days)
            all_articles.extend(bluesky_articles)
            print(f"  Bluesky: {len(bluesky_articles)} posts")
        except Exception as e:
            print(f"  Warning: Bluesky fetch failed ({e}), continuing")

    if not all_articles:
        print("\nNo articles fetched from any source. Exiting.")
        return False

    # =========================================================================
    # Step 2: Deduplicate articles
    # =========================================================================
    print(f"\n[Step 2] Deduplicating {len(all_articles)} articles...")
    unique_articles = deduplicate_articles(all_articles)
    print(f"  After dedup: {len(unique_articles)} unique articles")

    # =========================================================================
    # Step 3: Detect openings via AI
    # =========================================================================
    print(f"\n[Step 3] Detecting campaign openings via AI...")
    print(f"  Processing {len(unique_articles)} articles in batches...")

    from opening_detector import detect_openings
    from output_formatter import write_json as _write_json_raw

    openings = detect_openings(unique_articles)

    print(f"\n  Openings detected: {len(openings)}")

    # Save raw openings before dedup (for resume capability)
    raw_path = str(output_dir / "openings_raw.json")
    _write_json_raw(openings, raw_path)
    print(f"  Raw openings saved to: {raw_path}")

    # =========================================================================
    # Step 4: Cap and sort
    # =========================================================================
    if len(openings) > args.max_openings:
        print(f"\n[Step 4] Capping to {args.max_openings} openings (from {len(openings)})...")
        openings = sorted(openings, key=lambda o: o.priority, reverse=True)[:args.max_openings]
    else:
        openings = sorted(openings, key=lambda o: o.priority, reverse=True)

    # =========================================================================
    # Step 5: Write output
    # =========================================================================
    print(f"\n[Step 5] Writing output...")

    from output_formatter import write_json, write_markdown, write_xlsx, print_summary

    json_path = write_json(openings, str(output_dir / "openings.json"))
    print(f"  JSON: {json_path}")

    md_path = write_markdown(openings, str(output_dir / "openings.md"))
    print(f"  Markdown: {md_path}")

    xlsx_path = write_xlsx(openings, str(output_dir / "openings.xlsx"))
    print(f"  Excel: {xlsx_path}")

    # Print summary
    print_summary(openings)

    elapsed = time.time() - start_time
    print(f"\n  Completed in {elapsed:.0f} seconds ({elapsed/60:.1f} minutes)")

    return True


if __name__ == "__main__":
    success = run_scan()
    sys.exit(0 if success else 1)
