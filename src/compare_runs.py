#!/usr/bin/env python3
"""
Compare two idea runs to measure net-new idea yield.

Usage:
    python3 compare_runs.py                          # compares data_run1/ vs data_run2/
    python3 compare_runs.py path/to/run1 path/to/run2
    python3 compare_runs.py --use-claude             # semantic match via Claude (costs $)

Default mode uses fuzzy string matching on target+ask — fast, free, good enough
for premise validation. Use --use-claude for the more accurate semantic comparison.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


# =============================================================================
# Helpers
# =============================================================================

def load_ideas(run_dir: Path) -> list[dict]:
    ideas_path = run_dir / "ideas.json"
    if not ideas_path.exists():
        raise FileNotFoundError(f"No ideas.json in {run_dir}")
    data = json.loads(ideas_path.read_text())
    ideas = data.get("ideas", data) if isinstance(data, dict) else data
    return [i for i in ideas if not i.get("is_watch_list", False)]


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()


def _words(text: str) -> frozenset:
    stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
                 "for", "of", "with", "by", "from", "is", "are", "was", "were",
                 "be", "as", "their", "this", "that", "will", "we", "our", "who"}
    return frozenset(w for w in _normalize(text).split() if w not in stopwords and len(w) > 2)


def _similarity(a: dict, b: dict) -> float:
    """Jaccard similarity on words in target+ask."""
    wa = _words(a.get("target", "") + " " + a.get("ask", ""))
    wb = _words(b.get("target", "") + " " + b.get("ask", ""))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def find_net_new(run1: list[dict], run2: list[dict], threshold: float = 0.35) -> tuple[list[dict], list[tuple]]:
    """
    For each idea in run2, check if a similar idea exists in run1.
    Returns (net_new_ideas, matched_pairs).
    threshold: Jaccard similarity above which two ideas are considered the same campaign.
    0.35 is deliberately loose — catches "Pressure Wisconsin sheriffs" vs
    "Recruit county sheriffs in swing states" as the same campaign.
    """
    net_new = []
    matched = []  # (run2_idea, best_run1_match, similarity)

    for idea2 in run2:
        best_sim = 0.0
        best_match = None
        for idea1 in run1:
            sim = _similarity(idea2, idea1)
            if sim > best_sim:
                best_sim = sim
                best_match = idea1

        if best_sim >= threshold:
            matched.append((idea2, best_match, best_sim))
        else:
            net_new.append(idea2)

    return net_new, matched


def find_net_new_claude(run1: list[dict], run2: list[dict]) -> tuple[list[dict], list[tuple]]:
    """Semantic dedup via Claude — more accurate, costs API credits."""
    from models import CampaignIdea
    import anthropic
    from config import ANTHROPIC_API_KEY
    from idea_generator import deduplicate_ideas, _deduplicate_in_chunks

    # Tag ideas with run number so we can separate them after dedup
    ideas1 = [CampaignIdea.from_dict(d) for d in run1]
    ideas2 = [CampaignIdea.from_dict(d) for d in run2]

    # Add a marker via headline prefix (dedup looks at target+ask, not headline)
    for i in ideas1:
        i.headline = f"[RUN1] {i.headline}"
    for i in ideas2:
        i.headline = f"[RUN2] {i.headline}"

    combined = ideas1 + ideas2
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    deduped = deduplicate_ideas(combined, client)

    run1_survivors = [i for i in deduped if i.headline.startswith("[RUN1]")]
    run2_survivors = [i for i in deduped if i.headline.startswith("[RUN2]")]

    # Strip markers
    for i in run1_survivors + run2_survivors:
        i.headline = i.headline[7:]  # remove "[RUNX] "

    net_new = [i.to_dict() for i in run2_survivors]
    matched_run2 = [i for i in ideas2 if i not in run2_survivors]
    return net_new, [(i.to_dict(), None, None) for i in matched_run2]


# =============================================================================
# Report
# =============================================================================

def print_report(run1: list[dict], run2: list[dict], net_new: list[dict],
                 matched: list[tuple], threshold: float, use_claude: bool) -> None:
    method = "Claude semantic match" if use_claude else f"fuzzy string match (threshold={threshold})"
    overlap = len(matched)

    print(f"\n{'='*60}")
    print(f"  RUN COMPARISON REPORT")
    print(f"  Method: {method}")
    print(f"{'='*60}")
    print(f"\n  Run 1 scored ideas:  {len(run1)}")
    print(f"  Run 2 scored ideas:  {len(run2)}")
    print(f"  Matched (overlap):   {overlap}  ({overlap/len(run2)*100:.0f}% of run 2)")
    print(f"  Net-new from run 2:  {len(net_new)}  ({len(net_new)/len(run2)*100:.0f}% of run 2)")

    # Score distribution of net-new ideas
    scores = [i.get("weighted_score", 0) for i in net_new]
    if scores:
        strong = sum(1 for s in scores if s >= 2.5)
        solid  = sum(1 for s in scores if 1.5 <= s < 2.5)
        low    = sum(1 for s in scores if s < 1.5)
        print(f"\n  Net-new score breakdown:")
        print(f"    ≥2.5 Strong: {strong}")
        print(f"    ≥1.5 Solid:  {solid}")
        print(f"    <1.5 Low:    {low}")

    # Top net-new ideas
    top = sorted(net_new, key=lambda i: i.get("weighted_score", 0), reverse=True)[:10]
    if top:
        print(f"\n  Top net-new ideas (up to 10):")
        for i, idea in enumerate(top, 1):
            score = idea.get("weighted_score", 0)
            print(f"\n  {i}. [{score:.2f}] {idea.get('headline', '')[:80]}")
            print(f"     Target: {idea.get('target', '')[:70]}")
            print(f"     Ask:    {idea.get('ask', '')[:70]}")

    # Sample matched pairs to spot-check threshold
    if matched and not use_claude:
        print(f"\n  Sample matched pairs (spot-check threshold):")
        for idea2, idea1, sim in sorted(matched, key=lambda x: x[2])[:5]:
            print(f"\n  Similarity {sim:.2f}:")
            print(f"    Run2: {idea2.get('target', '')[:60]} | {idea2.get('ask', '')[:50]}")
            print(f"    Run1: {idea1.get('target', '')[:60]} | {idea1.get('ask', '')[:50]}")

    print(f"\n{'='*60}")
    print(f"  VERDICT")
    pct = len(net_new) / len(run2) * 100
    if pct >= 25:
        print(f"  {pct:.0f}% net-new — three-run mode likely worth the 3x cost.")
    elif pct >= 10:
        print(f"  {pct:.0f}% net-new — marginal. Review quality of net-new ideas before committing.")
    else:
        print(f"  {pct:.0f}% net-new — diminishing returns. Three-run mode probably not worth it.")
    print(f"{'='*60}\n")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Compare two idea runs to measure net-new yield")
    parser.add_argument("run1_dir", nargs="?", default="../data_run1",
                        help="Path to first run output dir (default: ../data_run1)")
    parser.add_argument("run2_dir", nargs="?", default="../data_run2",
                        help="Path to second run output dir (default: ../data_run2)")
    parser.add_argument("--threshold", type=float, default=0.35,
                        help="Jaccard similarity threshold for string match (default: 0.35)")
    parser.add_argument("--use-claude", action="store_true",
                        help="Use Claude semantic dedup instead of string match (costs API credits)")
    args = parser.parse_args()

    run1_dir = Path(args.run1_dir)
    run2_dir = Path(args.run2_dir)

    print(f"Loading run 1 from: {run1_dir}")
    print(f"Loading run 2 from: {run2_dir}")

    try:
        run1 = load_ideas(run1_dir)
        run2 = load_ideas(run2_dir)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"Loaded {len(run1)} run-1 ideas, {len(run2)} run-2 ideas")

    if args.use_claude:
        print("Running Claude semantic dedup (this costs API credits)...")
        net_new, matched = find_net_new_claude(run1, run2)
    else:
        net_new, matched = find_net_new(run1, run2, threshold=args.threshold)

    print_report(run1, run2, net_new, matched, args.threshold, args.use_claude)


if __name__ == "__main__":
    main()
