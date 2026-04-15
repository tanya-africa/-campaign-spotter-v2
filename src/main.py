#!/usr/bin/env python3
"""
Vibe-Campaigning Campaign Idea Generator v3

Searches news broadly (RSS feeds + dynamic AI-generated queries),
generates campaign ideas with target/ask/constituency/leverage,
scores them against a two-stage rubric, and self-critiques.

Usage:
    python main.py                          # Full scan, all sources
    python main.py --lookback-days 7        # Last 7 days only
    python main.py --sources gnews,reddit   # Only specific sources
    python main.py --max-ideas 50           # Cap at 50 ideas
    python main.py --preview                # Skip Gmail, use RSS + social + dynamic queries
    python main.py --skip-dynamic           # Skip dynamic query generation (RSS + hardcoded only)
"""

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config import DEFAULT_LOOKBACK_DAYS, MAX_OPENINGS, DATA_DIR, GOOGLE_NEWS_QUERIES
from models import Article


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate campaign ideas from news across multiple sources"
    )
    parser.add_argument(
        '--lookback-days', type=int, default=DEFAULT_LOOKBACK_DAYS,
        help=f"How many days back to scan (default: {DEFAULT_LOOKBACK_DAYS})"
    )
    parser.add_argument(
        '--sources', type=str, default=None,
        help="Comma-separated source types: rss,regional,gnews,gmail,reddit,bluesky,dynamic (default: all)"
    )
    parser.add_argument(
        '--max-ideas', type=int, default=MAX_OPENINGS,
        help=f"Maximum number of ideas to output (default: {MAX_OPENINGS})"
    )
    parser.add_argument(
        '--output-dir', type=str, default=None,
        help="Directory for output files (default: ./data)"
    )
    parser.add_argument(
        '--preview', action='store_true',
        help="Preview mode: skip Gmail, use RSS + social + dynamic queries"
    )
    parser.add_argument(
        '--skip-dynamic', action='store_true',
        help="Skip dynamic query generation (use only RSS feeds + hardcoded queries)"
    )
    return parser.parse_args()


def deduplicate_articles(articles: list[Article]) -> list[Article]:
    """Deduplicate articles by URL and normalized title."""
    seen_urls = set()
    seen_titles = set()
    unique = []

    for article in articles:
        url_key = article.url.lower().rstrip('/')
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
        sources = ['rss', 'regional', 'gnews', 'dynamic', 'reddit', 'bluesky']
    else:
        sources = ['rss', 'regional', 'gnews', 'dynamic', 'gmail', 'reddit', 'bluesky']

    if args.skip_dynamic and 'dynamic' in sources:
        sources.remove('dynamic')

    # Output directory
    output_dir = Path(args.output_dir) if args.output_dir else DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'='*60}")
    print(f"  VIBE-CAMPAIGNING: Campaign Idea Generator v3")
    print(f"  Lookback: {lookback_days} days")
    print(f"  Sources: {', '.join(sources)}")
    print(f"  Max ideas: {args.max_ideas}")
    print(f"{'='*60}\n")

    # =========================================================================
    # Step 1: Fetch from all sources
    # =========================================================================
    all_articles = []

    # RSS-based sources (national, regional, hardcoded Google News queries)
    rss_sources = [s for s in sources if s in ('rss', 'regional', 'gnews')]
    if rss_sources:
        from rss_fetcher import fetch_all_feeds
        rss_articles = fetch_all_feeds(lookback_days=lookback_days, sources=rss_sources)
        all_articles.extend(rss_articles)
        print(f"\n  RSS-based sources: {len(rss_articles)} articles")

    # Dynamic AI-generated queries
    if 'dynamic' in sources:
        print(f"\n[Step 1b] Generating dynamic search queries via AI...")
        from query_generator import select_categories, generate_queries
        from rss_fetcher import fetch_google_news_queries

        categories = select_categories(num_rotating=3)
        dynamic_queries = generate_queries(categories)

        # Flatten to a list of query strings
        query_list = []
        for cat_queries in dynamic_queries.values():
            query_list.extend(cat_queries)

        if query_list:
            print(f"  Fetching articles for {len(query_list)} dynamic queries...")
            dynamic_articles = fetch_google_news_queries(
                query_list, lookback_days=lookback_days
            )
            all_articles.extend(dynamic_articles)
            print(f"  Dynamic queries: {len(dynamic_articles)} articles")

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
    # Step 3: Generate campaign ideas (includes self-critique)
    # =========================================================================
    print(f"\n[Step 3] Generating campaign ideas via AI...")
    print(f"  Processing {len(unique_articles)} articles in batches...")

    from idea_generator import generate_ideas, deduplicate_ideas
    from output_formatter import write_json as _write_json_raw

    ideas = generate_ideas(unique_articles)

    print(f"\n  Ideas generated: {len(ideas)}")

    # Save raw ideas before dedup
    raw_path = str(output_dir / "ideas_raw.json")
    _write_json_raw(ideas, raw_path)
    print(f"  Raw ideas saved to: {raw_path}")

    # =========================================================================
    # Step 3b: Cross-batch deduplication
    # =========================================================================
    scored = [i for i in ideas if not i.is_watch_list]
    watch = [i for i in ideas if i.is_watch_list]

    if len(scored) > 1:
        print(f"\n[Step 3b] Deduplicating {len(scored)} scored ideas...")
        import anthropic
        from config import ANTHROPIC_API_KEY
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        scored = deduplicate_ideas(scored, client)

    ideas = scored + watch

    # =========================================================================
    # Step 4: Cap and sort
    # =========================================================================
    scored = [i for i in ideas if not i.is_watch_list]
    watch = [i for i in ideas if i.is_watch_list]

    scored.sort(key=lambda i: (i.weighted_score, i.priority), reverse=True)
    watch.sort(key=lambda i: i.headline)

    if len(scored) > args.max_ideas:
        print(f"\n[Step 4] Capping scored ideas to {args.max_ideas} (from {len(scored)})...")
        scored = scored[:args.max_ideas]

    ideas = scored + watch

    # =========================================================================
    # Step 5: Write output
    # =========================================================================
    print(f"\n[Step 5] Writing output...")

    from output_formatter import write_json, write_markdown, write_xlsx, print_summary

    json_path = write_json(ideas, str(output_dir / "ideas.json"))
    print(f"  JSON: {json_path}")

    md_path = write_markdown(ideas, str(output_dir / "ideas.md"))
    print(f"  Markdown: {md_path}")

    xlsx_path = write_xlsx(ideas, str(output_dir / "ideas.xlsx"))
    print(f"  Excel: {xlsx_path}")

    print_summary(ideas)

    elapsed = time.time() - start_time
    print(f"\n  Completed in {elapsed:.0f} seconds ({elapsed/60:.1f} minutes)")

    return True


if __name__ == "__main__":
    success = run_scan()
    sys.exit(0 if success else 1)
