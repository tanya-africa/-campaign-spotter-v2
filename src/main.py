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
import json
import re
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
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
    parser.add_argument(
        '--resume', action='store_true',
        help="Resume from the latest checkpoint (skips article fetching, picks up where credits ran out)"
    )
    parser.add_argument(
        '--all-categories', action='store_true',
        help="Run all 16 dynamic categories instead of the default 6 core + 3 rotating (use for comprehensive baseline runs)"
    )
    return parser.parse_args()


def _title_words(title: str) -> frozenset:
    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                 'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'as'}
    words = re.sub(r'[^a-z0-9\s]', '', title.lower()).split()
    return frozenset(w for w in words if w not in stopwords and len(w) > 2)


def _is_near_duplicate(words: frozenset, seen: list[frozenset], threshold: float = 0.8) -> bool:
    for existing in seen:
        union = words | existing
        if not union:
            continue
        if len(words & existing) / len(union) >= threshold:
            return True
    return False


def deduplicate_articles(articles: list[Article]) -> list[Article]:
    """Deduplicate articles by URL, exact title, and fuzzy title match (Jaccard >= 0.8)."""
    seen_urls = set()
    seen_title_keys = set()
    seen_title_words: list[frozenset] = []
    unique = []

    for article in articles:
        url_key = article.url.lower().rstrip('/')
        title_key = re.sub(r'[^a-z0-9]', '', article.title.lower())

        if url_key in seen_urls:
            continue
        if title_key and title_key in seen_title_keys:
            continue

        words = _title_words(article.title)
        if words and _is_near_duplicate(words, seen_title_words):
            continue

        seen_urls.add(url_key)
        if title_key:
            seen_title_keys.add(title_key)
        if words:
            seen_title_words.append(words)
        unique.append(article)

    return unique


_RATE_LIMIT_THRESHOLD = 0.40  # runs with >40% zero-yield are considered rate-limited


def print_query_pruning_report(output_dir: Path) -> None:
    """Read query_yield_log.json and recommend queries to drop or revise."""
    log_path = output_dir / "query_yield_log.json"
    if not log_path.exists():
        return

    try:
        entries = json.loads(log_path.read_text())
    except (json.JSONDecodeError, OSError):
        return

    # Group entries by run_ts (added going forward); fall back to date for old entries
    runs_map = defaultdict(list)
    for e in entries:
        key = e.get("run_ts") or e["date"]
        runs_map[key].append(e)

    # Classify each run as clean or rate-limited
    clean_entries = []
    n_clean = 0
    n_excluded = 0
    for run_entries in runs_map.values():
        total = len(run_entries)
        zeros = sum(1 for e in run_entries if e.get("count", 0) == 0)
        zero_rate = zeros / total if total else 0
        if zero_rate > _RATE_LIMIT_THRESHOLD:
            n_excluded += 1
        else:
            clean_entries.extend(run_entries)
            n_clean += 1

    # Group by query across clean runs only
    stats = defaultdict(lambda: {"total": 0, "dates": set()})
    for e in clean_entries:
        q = e["query"]
        stats[q]["total"] += e.get("count", 0)
        stats[q]["dates"].add(e["date"])

    dead = sorted(q for q, s in stats.items() if len(s["dates"]) >= 2 and s["total"] == 0)
    low  = sorted(q for q, s in stats.items() if len(s["dates"]) >= 2 and 1 <= s["total"] <= 2)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Assess today's run quality before building zero_today list
    today_entries = [e for e in entries if e["date"] == today]
    today_total = len(today_entries)
    today_zeros = sum(1 for e in today_entries if e.get("count", 0) == 0)
    today_zero_rate = today_zeros / today_total if today_total else 0
    today_is_clean = today_zero_rate <= _RATE_LIMIT_THRESHOLD

    zero_today = sorted(set(
        e["query"] for e in today_entries
        if e.get("count", 0) == 0 and e.get("source") == "hardcoded"
        and e["query"] not in dead
    )) if today_is_clean else []

    print(f"\n{'='*60}")
    print(f"  QUERY YIELD REPORT")
    print(f"{'='*60}")

    if n_excluded:
        print(f"\n  Note: {n_excluded} run(s) excluded (>{int(_RATE_LIMIT_THRESHOLD*100)}% zero-yield, likely rate-limited). {n_clean} clean run(s) used.")

    if n_clean < 2:
        print(f"\n  Need ≥2 clean runs for dead-query detection (have {n_clean}).")
    else:
        if dead:
            print(f"\n  DROP THESE ({len(dead)} — zero yield across ≥2 clean runs):")
            for q in dead:
                print(f"    \"{q}\"  ({len(stats[q]['dates'])} runs, 0 articles)")

        if low:
            print(f"\n  CONSIDER REVISING ({len(low)} — ≤2 articles across ≥2 clean runs):")
            for q in low:
                s = stats[q]
                print(f"    \"{q}\"  ({len(s['dates'])} runs, {s['total']} total)")

        if not dead and not low:
            print("\n  All queries returning results in clean runs. No pruning needed.")

    if today_is_clean and zero_today:
        print(f"\n  ZERO TODAY — watch after next run ({min(len(zero_today), 15)} shown):")
        for q in zero_today[:15]:
            print(f"    \"{q}\"")
        if len(zero_today) > 15:
            print(f"    ... and {len(zero_today) - 15} more")
    elif not today_is_clean and today_total > 0:
        print(f"\n  TODAY'S RUN was rate-limited ({int(today_zero_rate*100)}% zero-yield) — zero-today list suppressed.")

    print(f"{'='*60}")


def print_idea_yield_report(ideas: list, output_dir: Path) -> None:
    """Print per-query idea yield alongside article yield for gnews queries."""
    from collections import Counter

    # Count scored ideas (not watch-list) per source_query
    idea_counts = Counter(
        i.source_query for i in ideas
        if not i.is_watch_list and i.source_query
    )

    if not idea_counts:
        return

    # Load article counts from yield log for the most recent run of each query
    log_path = output_dir / "query_yield_log.json"
    article_counts: dict[str, int] = {}
    if log_path.exists():
        try:
            entries = json.loads(log_path.read_text())
            # Use the most recent entry per query
            latest: dict[str, dict] = {}
            for e in entries:
                q = e["query"]
                if q not in latest or e.get("run_ts", "") > latest[q].get("run_ts", ""):
                    latest[q] = e
            article_counts = {q: e.get("count", 0) for q, e in latest.items()}
        except (json.JSONDecodeError, OSError):
            pass

    # All gnews queries that appeared in this run (union of idea sources + yield log)
    all_queries = sorted(
        set(idea_counts.keys()) | {q for q in article_counts if article_counts[q] > 0},
        key=lambda q: (-idea_counts.get(q, 0), q)
    )

    if not all_queries:
        return

    # Load dynamic category map if available (for per-category summary)
    cat_map: dict[str, list[str]] = {}
    cat_map_path = output_dir / "dynamic_query_categories.json"
    if cat_map_path.exists():
        try:
            cat_map = json.loads(cat_map_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    query_to_category = {q: cat for cat, qs in cat_map.items() for q in qs}

    print(f"\n{'='*60}")
    print(f"  IDEA YIELD BY QUERY")
    print(f"{'='*60}")
    print(f"  {'Ideas':>5}  {'Articles':>8}  Query")
    print(f"  {'-'*5}  {'-'*8}  {'-'*40}")
    for q in all_queries:
        ideas_n = idea_counts.get(q, 0)
        articles_n = article_counts.get(q, "?")
        marker = "  " if ideas_n > 0 else "○ "
        print(f"  {marker}{ideas_n:>4}  {articles_n:>8}  {q}")

    # Per-category summary for dynamic queries
    if cat_map:
        print(f"\n  DYNAMIC QUERY YIELD BY CATEGORY")
        print(f"  {'-'*50}")
        for cat, qs in cat_map.items():
            cat_ideas = sum(idea_counts.get(q, 0) for q in qs)
            cat_articles = sum(article_counts.get(q, 0) for q in qs)
            marker = "  " if cat_ideas > 0 else "○ "
            print(f"  {marker}{cat_ideas:>4} ideas  {cat_articles:>6} articles  {cat}")

    print(f"{'='*60}")


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
    # Resume mode: skip article fetching, pick up from latest checkpoint
    # =========================================================================
    if args.resume:
        articles_log_path = output_dir / "articles_deduped.json"
        if not articles_log_path.exists():
            print("ERROR: --resume requires articles_deduped.json but none found. Run without --resume first.")
            return False

        # Find the latest checkpoint
        checkpoint_names = ["checkpoint_pass3.json", "checkpoint_pass2.json", "checkpoint_pass1.json"]
        resume_checkpoint = None
        for name in checkpoint_names:
            p = output_dir / name
            if p.exists():
                resume_checkpoint = p
                break

        print(f"  Loading articles from {articles_log_path}")
        raw = json.loads(articles_log_path.read_text())
        from datetime import timezone as _tz
        from models import Article as _Article
        unique_articles = []
        for d in raw:
            pub = datetime.fromisoformat(d["published"])
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=_tz.utc)
            unique_articles.append(_Article(
                url=d["url"], title=d["title"], published=pub,
                source=d["source"], source_type=d.get("source_type", "rss"),
                source_query=d.get("source_query", ""),
                content=d.get("content", ""),
            ))
        print(f"  Loaded {len(unique_articles)} articles")

        if resume_checkpoint:
            print(f"  Latest checkpoint: {resume_checkpoint.name}")
        else:
            print("  No checkpoint found — will re-run all AI passes")

        from idea_generator import generate_ideas, deduplicate_ideas
        from output_formatter import write_json as _write_json_raw
        ideas = generate_ideas(unique_articles, resume_from=resume_checkpoint)

        print(f"\n  Ideas after resume: {len(ideas)}")
        raw_path = str(output_dir / "ideas_raw.json")
        _write_json_raw(ideas, raw_path)

        scored = [i for i in ideas if not i.is_watch_list]
        watch = [i for i in ideas if i.is_watch_list]
        if len(scored) > 1:
            print(f"\n[Step 3b] Deduplicating {len(scored)} scored ideas...")
            import anthropic as _anthropic
            from config import ANTHROPIC_API_KEY as _KEY
            client = _anthropic.Anthropic(api_key=_KEY)
            scored = deduplicate_ideas(scored, client)

        ideas = scored + watch
        scored = [i for i in ideas if not i.is_watch_list]
        watch = [i for i in ideas if i.is_watch_list]
        scored.sort(key=lambda i: i.weighted_score, reverse=True)
        watch.sort(key=lambda i: i.headline)
        if len(scored) > args.max_ideas:
            scored = scored[:args.max_ideas]
        ideas = scored + watch

        from output_formatter import write_json, write_markdown, write_xlsx, print_summary
        write_json(ideas, str(output_dir / "ideas.json"))
        write_markdown(ideas, str(output_dir / "ideas.md"))
        write_xlsx(ideas, str(output_dir / "ideas.xlsx"))
        print_summary(ideas)

        from cost_tracker import tracker as _tracker
        elapsed = time.time() - start_time
        print(f"\n  Completed in {elapsed:.0f} seconds ({elapsed/60:.1f} minutes)")
        print(_tracker.summary("Total"))
        print_query_pruning_report(output_dir)
        print_idea_yield_report(ideas, output_dir)
        return True

    # =========================================================================
    # Step 1: Fetch from all sources
    # =========================================================================
    all_articles = []

    # RSS-based sources (national, regional, hardcoded Google News queries)
    rss_sources = [s for s in sources if s in ('rss', 'regional', 'gnews')]

    # Start Bluesky in background so it runs concurrently with Google News + Reddit
    bluesky_results = []
    bluesky_exc = [None]
    bluesky_thread = None
    if 'bluesky' in sources:
        def _fetch_bluesky():
            try:
                from bluesky_fetcher import fetch_bluesky_posts
                bluesky_results.extend(fetch_bluesky_posts(lookback_days=lookback_days))
            except Exception as e:
                bluesky_exc[0] = e
        bluesky_thread = threading.Thread(target=_fetch_bluesky, daemon=True)
        bluesky_thread.start()
        print("  [Bluesky] Fetching in background...")

    # Set up Reddit interleaving: consume subreddits one-at-a-time during the Google News loop
    # so Google gets natural gaps instead of rapid-fire queries.
    reddit_raw = []
    reddit_seen_ids = set()
    reddit_keyword_pattern = None
    reddit_remaining = []
    interleave_fn = None

    if 'reddit' in sources and 'gnews' in rss_sources:
        from reddit_fetcher import build_keyword_pattern, fetch_single_subreddit
        from social_config import REDDIT_SUBREDDITS, REDDIT_USER_AGENT
        reddit_headers = {'User-Agent': REDDIT_USER_AGENT}
        reddit_keyword_pattern = build_keyword_pattern()
        reddit_remaining = list(REDDIT_SUBREDDITS)

        def interleave_fn():
            if reddit_remaining:
                name = reddit_remaining.pop(0)
                posts = fetch_single_subreddit(
                    name, lookback_days, reddit_seen_ids, reddit_keyword_pattern, reddit_headers
                )
                reddit_raw.extend(posts)
                print(f"    [Reddit interleave] r/{name}: {len(posts)} posts")

    if rss_sources:
        from rss_fetcher import fetch_all_feeds
        rss_articles = fetch_all_feeds(lookback_days=lookback_days, sources=rss_sources, interleave_fn=interleave_fn)
        all_articles.extend(rss_articles)
        print(f"\n  RSS-based sources: {len(rss_articles)} articles")

    # Dynamic AI-generated queries
    if 'dynamic' in sources:
        print(f"\n[Step 1b] Generating dynamic search queries via AI...")
        from query_generator import select_categories, generate_queries, ROTATING_CATEGORIES
        from rss_fetcher import fetch_google_news_queries

        num_rotating = len(ROTATING_CATEGORIES) if args.all_categories else 3
        if args.all_categories:
            print(f"  [--all-categories] Running all 16 dynamic categories for comprehensive baseline")
        categories = select_categories(num_rotating=num_rotating)
        dynamic_queries = generate_queries(categories)

        # Save category→query map for per-category yield report
        cat_map_path = output_dir / "dynamic_query_categories.json"
        with open(cat_map_path, "w") as _f:
            json.dump(dynamic_queries, _f, indent=2)

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

    # Reddit: fetch any subreddits not yet consumed during Google News interleaving
    if 'reddit' in sources:
        try:
            from reddit_fetcher import fetch_reddit_posts, fetch_single_subreddit
            from social_config import MIN_ENGAGEMENT_REDDIT, REDDIT_USER_AGENT
            from reddit_fetcher import _get_score

            if reddit_remaining:
                reddit_headers = {'User-Agent': REDDIT_USER_AGENT}
                print(f"\n  Fetching remaining {len(reddit_remaining)} Reddit subreddits...")
                for i, name in enumerate(list(reddit_remaining)):
                    if i > 0:
                        time.sleep(6)
                    print(f"    [{i+1}/{len(reddit_remaining)}] r/{name}...")
                    posts = fetch_single_subreddit(
                        name, lookback_days, reddit_seen_ids, reddit_keyword_pattern, reddit_headers
                    )
                    reddit_raw.extend(posts)
                    print(f"      Found {len(posts)} posts")

            if reddit_raw:
                reddit_filtered = [p for p in reddit_raw if _get_score(p) >= MIN_ENGAGEMENT_REDDIT]
                reddit_filtered.sort(key=lambda p: _get_score(p), reverse=True)
                all_articles.extend(reddit_filtered)
                print(f"  Reddit: {len(reddit_raw)} posts, {len(reddit_filtered)} after engagement filter")
            elif 'gnews' not in rss_sources:
                # interleaving never ran (no gnews step) — fetch normally
                reddit_articles = fetch_reddit_posts(lookback_days=lookback_days)
                all_articles.extend(reddit_articles)
                print(f"  Reddit: {len(reddit_articles)} posts")
        except Exception as e:
            print(f"  Warning: Reddit fetch failed ({e}), continuing")

    # Collect Bluesky (started in background above)
    if bluesky_thread is not None:
        bluesky_thread.join()
        if bluesky_exc[0]:
            print(f"  Warning: Bluesky fetch failed ({bluesky_exc[0]}), continuing")
        else:
            all_articles.extend(bluesky_results)
            print(f"  Bluesky: {len(bluesky_results)} posts")

    if not all_articles:
        print("\nNo articles fetched from any source. Exiting.")
        return False

    # =========================================================================
    # Step 2: Deduplicate articles
    # =========================================================================
    print(f"\n[Step 2] Deduplicating {len(all_articles)} articles...")
    unique_articles = deduplicate_articles(all_articles)
    print(f"  After dedup: {len(unique_articles)} unique articles (from {len(all_articles)} fetched)")

    # Temporary: dump article list for inspecting near-dupes and source waste. Remove once satisfied.
    articles_log_path = output_dir / "articles_deduped.json"
    with open(articles_log_path, 'w') as f:
        json.dump([
            {"title": a.title, "source": a.source, "source_type": a.source_type,
             "url": a.url, "published": a.published.isoformat(),
             "source_query": a.source_query}
            for a in unique_articles
        ], f, indent=2)
    print(f"  Article list saved → {articles_log_path}")

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

    scored.sort(key=lambda i: i.weighted_score, reverse=True)
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

    from cost_tracker import tracker
    elapsed = time.time() - start_time
    print(f"\n  Completed in {elapsed:.0f} seconds ({elapsed/60:.1f} minutes)")
    print(tracker.summary("Total"))

    print_query_pruning_report(output_dir)
    print_idea_yield_report(ideas, output_dir)

    return True


if __name__ == "__main__":
    success = run_scan()
    sys.exit(0 if success else 1)
