#!/usr/bin/env python3
"""
Test run: feed authoritarianism-digest history through the campaign idea generator.
Tracks whether ideas came from 'news' or 'social' source entries.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from models import Article, CampaignIdea
from idea_generator import generate_ideas
from output_formatter import write_json, write_markdown, write_xlsx, print_summary
from config import DATA_DIR


def load_digest_history(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def digest_to_articles(entries: list[dict]) -> list[Article]:
    """Convert digest history entries to Article objects for the idea generator."""
    articles = []
    for i, entry in enumerate(entries):
        # Combine headline and detail as content
        content = f"{entry['headline']}\n\n{entry['detail']}"

        # Use section and source_type in the source field so we can trace it
        source_label = f"Digest [{entry['source_type']}] [{entry['section']}]"

        article = Article(
            title=entry['headline'],
            url=f"digest://entry-{i}",  # synthetic URL for dedup
            source=source_label,
            published=datetime.strptime(entry['date'], '%Y-%m-%d').replace(tzinfo=timezone.utc),
            content=content,
            source_type=entry['source_type'],  # 'news' or 'social'
        )
        articles.append(article)

    return articles


def main():
    digest_path = "/tmp/digest_history.json"

    print(f"{'='*60}")
    print(f"  DIGEST TEST: Running idea generator against digest history")
    print(f"{'='*60}\n")

    # Load digest
    entries = load_digest_history(digest_path)
    print(f"Loaded {len(entries)} digest entries")

    # Breakdown
    news = [e for e in entries if e['source_type'] == 'news']
    social = [e for e in entries if e['source_type'] == 'social']
    print(f"  News: {len(news)}, Social: {len(social)}")

    sections = {}
    for e in entries:
        sections.setdefault(e['section'], 0)
        sections[e['section']] += 1
    for section, count in sorted(sections.items(), key=lambda x: -x[1]):
        print(f"  {section}: {count}")

    # Convert to articles
    articles = digest_to_articles(entries)

    # Run idea generator
    print(f"\nGenerating campaign ideas from {len(articles)} digest entries...\n")
    start = time.time()
    ideas = generate_ideas(articles)
    elapsed = time.time() - start

    # Analyze source breakdown of ideas
    scored = [i for i in ideas if not i.is_watch_list]
    watch = [i for i in ideas if i.is_watch_list]

    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}")
    print(f"  Total ideas: {len(ideas)}")
    print(f"  Scored: {len(scored)} | Watch list: {len(watch)}")

    # Trace back to news vs social
    news_ideas = [i for i in scored if '[news]' in i.source_name.lower()]
    social_ideas = [i for i in scored if '[social]' in i.source_name.lower()]
    print(f"\n  Scored ideas from NEWS sources: {len(news_ideas)}")
    print(f"  Scored ideas from SOCIAL sources: {len(social_ideas)}")

    if scored:
        news_avg = sum(i.weighted_score for i in news_ideas) / len(news_ideas) if news_ideas else 0
        social_avg = sum(i.weighted_score for i in social_ideas) / len(social_ideas) if social_ideas else 0
        print(f"  Avg weighted score — News: {news_avg:.2f} | Social: {social_avg:.2f}")

    # Section breakdown of scored ideas
    print(f"\n  Scored ideas by digest section:")
    section_ideas = {}
    for i in scored:
        # Extract section from source name
        parts = i.source_name.split('[')
        section = parts[2].rstrip(']') if len(parts) >= 3 else 'unknown'
        section_ideas.setdefault(section, []).append(i)
    for section, ideas_list in sorted(section_ideas.items(), key=lambda x: -len(x[1])):
        avg = sum(i.weighted_score for i in ideas_list) / len(ideas_list)
        print(f"    {section}: {len(ideas_list)} ideas (avg score: {avg:.2f})")

    # Write output
    output_dir = DATA_DIR / "digest_test"
    output_dir.mkdir(exist_ok=True)

    write_json(ideas, str(output_dir / "digest_ideas.json"))
    write_markdown(ideas, str(output_dir / "digest_ideas.md"))
    write_xlsx(ideas, str(output_dir / "digest_ideas.xlsx"))

    print_summary(ideas)
    print(f"\n  Completed in {elapsed:.0f} seconds ({elapsed/60:.1f} minutes)")
    print(f"  Output: {output_dir}/")


if __name__ == "__main__":
    main()
