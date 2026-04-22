#!/usr/bin/env python3
"""
Source analysis: run a stratified sample of digest items through the
campaign idea generator to see which sources produce the best ideas.

Samples ~300 items across source types, runs them through idea generation
+ critique, then analyzes results by outlet, source type, and section.
"""

import csv
import json
import re
import sys
import time
import random
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).parent))

from models import Article, CampaignIdea
from idea_generator import generate_ideas
from output_formatter import write_json, write_markdown, write_xlsx, print_summary
from config import DATA_DIR


def parse_sources(sources_field: str) -> list[dict]:
    """Parse the sources field into a list of {outlet, url, source_type}."""
    results = []
    parts = re.split(r';\s*', sources_field)
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Determine source type
        if part.startswith('Reddit:') or 'reddit.com' in part:
            stype = 'reddit'
        elif part.startswith('Bluesky:') or 'bsky.app' in part:
            stype = 'bluesky'
        elif part.startswith('Email:'):
            stype = 'email'
        else:
            stype = 'rss'

        # Extract outlet name
        match = re.match(r'^(.+?)\s*\(https?://', part)
        if match:
            outlet = match.group(1).strip()
        else:
            outlet = part.split('(')[0].strip() if '(' in part else part

        # Extract URL
        url_match = re.search(r'\((https?://[^)]+)\)', part)
        url = url_match.group(1) if url_match else ''

        results.append({'outlet': outlet, 'url': url, 'source_type': stype})

    return results


def load_and_sample(csv_path: str, sample_size: int = 300) -> list[dict]:
    """Load digest CSV and create a stratified sample."""
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)

    print(f"Total digest items: {len(all_rows)}")

    # Parse source type for each row (use first source)
    for row in all_rows:
        sources = parse_sources(row.get('sources', ''))
        row['_sources'] = sources
        row['_source_type'] = sources[0]['source_type'] if sources else 'unknown'
        row['_outlet'] = sources[0]['outlet'] if sources else 'unknown'

    # Stratify by source type
    by_type = defaultdict(list)
    for row in all_rows:
        by_type[row['_source_type']].append(row)

    print(f"\nSource type distribution:")
    for stype, rows in sorted(by_type.items(), key=lambda x: -len(x[1])):
        print(f"  {stype}: {len(rows)}")

    # Sample proportionally, minimum 30 per type
    sampled = []
    for stype, rows in by_type.items():
        proportion = len(rows) / len(all_rows)
        n = max(30, int(sample_size * proportion))
        n = min(n, len(rows))
        sampled.extend(random.sample(rows, n))

    # Shuffle
    random.shuffle(sampled)
    print(f"\nSampled {len(sampled)} items:")
    sample_types = Counter(r['_source_type'] for r in sampled)
    for stype, count in sample_types.most_common():
        print(f"  {stype}: {count}")

    return sampled


def rows_to_articles(rows: list[dict]) -> list[Article]:
    """Convert sampled CSV rows to Article objects, preserving source info."""
    articles = []
    for i, row in enumerate(rows):
        sources = row['_sources']
        first = sources[0] if sources else {'outlet': 'unknown', 'url': f'digest://row-{i}', 'source_type': 'unknown'}

        content = f"{row['headline']}\n\n{row.get('detail', '')}" if row.get('detail') else row['headline']

        # Encode source metadata in the source field
        source_label = f"{first['source_type']}|{first['outlet']}|{row['section']}"

        article = Article(
            title=row['headline'],
            url=first.get('url', f'digest://row-{i}'),
            source=source_label,
            published=datetime.strptime(row['date'], '%Y-%m-%d').replace(tzinfo=timezone.utc),
            content=content,
            source_type=first['source_type'],
        )
        articles.append(article)

    return articles


def analyze_results(ideas: list[CampaignIdea]):
    """Analyze which sources produce the best campaign ideas."""
    scored = [i for i in ideas if not i.is_watch_list]
    watch = [i for i in ideas if i.is_watch_list]

    print(f"\n{'='*70}")
    print(f"  SOURCE ANALYSIS RESULTS")
    print(f"{'='*70}")
    print(f"  Total ideas: {len(ideas)} | Scored: {len(scored)} | Watch: {len(watch)}")

    # Parse source metadata from source_name field (format: "type|outlet|section")
    def parse_meta(idea):
        parts = idea.source_name.split('|')
        if len(parts) >= 3:
            return {'type': parts[0], 'outlet': parts[1], 'section': parts[2]}
        return {'type': 'unknown', 'outlet': idea.source_name, 'section': 'unknown'}

    # === By source TYPE ===
    print(f"\n{'='*70}")
    print(f"  BY SOURCE TYPE")
    print(f"{'='*70}")
    type_ideas = defaultdict(list)
    for i in scored:
        meta = parse_meta(i)
        type_ideas[meta['type']].append(i)

    for stype in ['rss', 'reddit', 'bluesky', 'email']:
        ideas_list = type_ideas.get(stype, [])
        if not ideas_list:
            print(f"\n  {stype.upper()}: 0 ideas")
            continue
        avg = sum(i.weighted_score for i in ideas_list) / len(ideas_list)
        top = max(i.weighted_score for i in ideas_list)
        p5 = sum(1 for i in ideas_list if i.priority == 5)
        p4 = sum(1 for i in ideas_list if i.priority == 4)
        print(f"\n  {stype.upper()}: {len(ideas_list)} ideas | avg: {avg:.2f} | top: {top:.2f} | P5: {p5} | P4: {p4}")

    # === By OUTLET (top 20) ===
    print(f"\n{'='*70}")
    print(f"  BY OUTLET (top 20 by idea count)")
    print(f"{'='*70}")
    outlet_ideas = defaultdict(list)
    for i in scored:
        meta = parse_meta(i)
        outlet_ideas[meta['outlet']].append(i)

    # Sort by count, then by avg score
    ranked_outlets = sorted(
        outlet_ideas.items(),
        key=lambda x: (-len(x[1]), -sum(i.weighted_score for i in x[1])/len(x[1]))
    )
    print(f"\n  {'Outlet':<45} {'Count':>5} {'Avg':>6} {'Top':>6} {'P5':>4} {'P4':>4}")
    print(f"  {'-'*45} {'-'*5} {'-'*6} {'-'*6} {'-'*4} {'-'*4}")
    for outlet, ideas_list in ranked_outlets[:20]:
        avg = sum(i.weighted_score for i in ideas_list) / len(ideas_list)
        top = max(i.weighted_score for i in ideas_list)
        p5 = sum(1 for i in ideas_list if i.priority == 5)
        p4 = sum(1 for i in ideas_list if i.priority == 4)
        print(f"  {outlet[:45]:<45} {len(ideas_list):>5} {avg:>6.2f} {top:>6.2f} {p4:>4} {p4:>4}")

    # === By OUTLET (top 20 by avg score, min 3 ideas) ===
    print(f"\n{'='*70}")
    print(f"  BY OUTLET (top 20 by avg score, min 3 ideas)")
    print(f"{'='*70}")
    ranked_quality = sorted(
        [(o, il) for o, il in outlet_ideas.items() if len(il) >= 3],
        key=lambda x: -sum(i.weighted_score for i in x[1])/len(x[1])
    )
    print(f"\n  {'Outlet':<45} {'Count':>5} {'Avg':>6} {'Top':>6}")
    print(f"  {'-'*45} {'-'*5} {'-'*6} {'-'*6}")
    for outlet, ideas_list in ranked_quality[:20]:
        avg = sum(i.weighted_score for i in ideas_list) / len(ideas_list)
        top = max(i.weighted_score for i in ideas_list)
        print(f"  {outlet[:45]:<45} {len(ideas_list):>5} {avg:>6.2f} {top:>6.2f}")

    # === By SECTION ===
    print(f"\n{'='*70}")
    print(f"  BY DIGEST SECTION")
    print(f"{'='*70}")
    section_ideas = defaultdict(list)
    for i in scored:
        meta = parse_meta(i)
        section_ideas[meta['section']].append(i)

    for section, ideas_list in sorted(section_ideas.items(), key=lambda x: -len(x[1])):
        avg = sum(i.weighted_score for i in ideas_list) / len(ideas_list)
        top = max(i.weighted_score for i in ideas_list)
        print(f"  {section:<35} {len(ideas_list):>4} ideas | avg: {avg:.2f} | top: {top:.2f}")

    # === Setup effort recommendation ===
    print(f"\n{'='*70}")
    print(f"  SETUP RECOMMENDATIONS")
    print(f"{'='*70}")

    type_summary = {}
    for stype, ideas_list in type_ideas.items():
        if ideas_list:
            avg = sum(i.weighted_score for i in ideas_list) / len(ideas_list)
            type_summary[stype] = {'count': len(ideas_list), 'avg': avg}

    print(f"\n  Source type performance summary:")
    for stype in ['rss', 'reddit', 'bluesky', 'email']:
        s = type_summary.get(stype, {'count': 0, 'avg': 0})
        setup = {'rss': 'Easy (already done)', 'reddit': 'Medium (API key needed)',
                 'bluesky': 'Medium (AT Protocol)', 'email': 'Hard (Gmail OAuth)'}
        print(f"    {stype.upper():>10}: {s['count']:>3} ideas, avg {s['avg']:.2f} — Setup: {setup.get(stype, '?')}")


def main():
    csv_path = "/tmp/digest_all_items.csv"

    print(f"{'='*70}")
    print(f"  SOURCE ANALYSIS: Which outlets produce the best campaign ideas?")
    print(f"{'='*70}\n")

    # Sample
    random.seed(42)  # reproducible
    sampled = load_and_sample(csv_path, sample_size=300)

    # Convert to articles
    articles = rows_to_articles(sampled)

    # Generate ideas
    print(f"\nGenerating campaign ideas from {len(articles)} sampled digest items...\n")
    start = time.time()
    ideas = generate_ideas(articles)
    elapsed = time.time() - start

    # Write raw output
    output_dir = DATA_DIR / "source_analysis"
    output_dir.mkdir(exist_ok=True)
    write_json(ideas, str(output_dir / "source_ideas.json"))
    write_markdown(ideas, str(output_dir / "source_ideas.md"))
    write_xlsx(ideas, str(output_dir / "source_ideas.xlsx"))

    # Analyze
    analyze_results(ideas)
    print_summary(ideas)

    print(f"\n  Completed in {elapsed:.0f} seconds ({elapsed/60:.1f} minutes)")
    print(f"  Output: {output_dir}/")


if __name__ == "__main__":
    main()
