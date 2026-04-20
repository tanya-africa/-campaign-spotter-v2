#!/usr/bin/env python3
"""
Test harness for rubric-v4: AI leverage tag + existing coverage research.

Loads a few scored ideas from data/ideas_raw.json, runs them through the new
critique (MANDATE 4) and coverage research (web_search) passes, and prints a
before/after comparison.

Does NOT re-ingest articles or regenerate ideas — just exercises the two new
passes on existing ideas.

Usage:
    python src/test_rubric_v4.py
"""

import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from models import CampaignIdea
from critique_agent import run_critique, tag_ai_leverage, research_coverage


IDEAS_FILE = Path(__file__).parent.parent / "data" / "ideas_raw.json"


def pick_test_ideas(ideas: list[dict]) -> list[dict]:
    """Pick 3 scored ideas for the test: NPV + two others from different domains."""
    scored = [i for i in ideas if not i.get("is_watch_list", False)
              and i.get("weighted_score", 0) >= 2.0]

    picks = []
    seen_domains = set()

    # Prioritize NPV since that's what prompted this work
    for i in scored:
        if "popular vote" in i.get("headline", "").lower():
            picks.append(i)
            seen_domains.add(i.get("issue_domain", ""))
            break

    # Then pick two more from different issue domains, highest-scored first
    scored_sorted = sorted(scored, key=lambda i: -i["weighted_score"])
    for i in scored_sorted:
        if len(picks) >= 3:
            break
        if i in picks:
            continue
        domain = i.get("issue_domain", "")
        if domain in seen_domains:
            continue
        picks.append(i)
        seen_domains.add(domain)

    return picks


def print_side_by_side(before: CampaignIdea, after: CampaignIdea) -> None:
    bar = "=" * 80
    print(f"\n{bar}")
    print(f"IDEA: {after.headline}")
    print(f"  Domain: {after.issue_domain}  |  Target: {after.target[:60]}")
    print(bar)

    print(f"\n  BEFORE (from ideas_raw.json):")
    print(f"    Score: {before.weighted_score:.2f} (priority {before.priority})")
    print(f"    Dims: choir={before.score_beyond_choir} pressure={before.score_pressure_point} "
          f"antiAuth={before.score_anti_authoritarian} repl={before.score_replication} win={before.score_winnability}")
    print(f"    Critique: {before.critique_notes[:200]}")

    print(f"\n  AFTER (v4 re-critique + coverage research):")
    print(f"    Score: {after.weighted_score:.2f} (priority {after.priority})")
    print(f"    Dims: choir={after.score_beyond_choir} pressure={after.score_pressure_point} "
          f"antiAuth={after.score_anti_authoritarian} repl={after.score_replication} win={after.score_winnability}")
    print(f"    Critique: {after.critique_notes[:200]}")
    print()
    print(f"    >>> AI LEVERAGE: {after.ai_leverage or '(empty)'}")
    print()
    print(f"    >>> EXISTING COVERAGE: {after.existing_coverage or '(empty)'}")


def main():
    if not IDEAS_FILE.exists():
        print(f"No {IDEAS_FILE} found. Run a scan first or point IDEAS_FILE elsewhere.")
        sys.exit(1)

    with open(IDEAS_FILE) as f:
        data = json.load(f)

    picks_dict = pick_test_ideas(data.get("ideas", []))
    if not picks_dict:
        print("No eligible scored ideas found (need weighted_score >= 2.0 and not watch-list).")
        sys.exit(1)

    print(f"Selected {len(picks_dict)} test ideas:")
    for i, p in enumerate(picks_dict, 1):
        print(f"  {i}. [{p['weighted_score']:.2f}] ({p.get('issue_domain','?')}) {p['headline'][:70]}")

    # Snapshot originals, then build fresh CampaignIdea objects for running
    originals = [CampaignIdea.from_dict(p) for p in picks_dict]
    snapshots = [deepcopy(o) for o in originals]

    print(f"\n--- Running critique agent ---")
    critiqued = run_critique(originals)

    print(f"\n--- Running AI leverage tagging (isolated pass) ---")
    tagged = tag_ai_leverage(critiqued)

    print(f"\n--- Running coverage research (web_search pass) ---")
    final = research_coverage(tagged)

    for snap, after in zip(snapshots, final):
        print_side_by_side(snap, after)

    print(f"\n{'='*80}\nTest complete.")


if __name__ == "__main__":
    main()
