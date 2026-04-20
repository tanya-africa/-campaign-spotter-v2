#!/usr/bin/env python3
"""
Compare OLD (pre-MANDATE-4) vs NEW critique prompts on the same ideas.

Runs each prompt twice to separate prompt-driven change from run-to-run variance.
"""

import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import anthropic
from models import CampaignIdea
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from critique_agent import CRITIQUE_SYSTEM_PROMPT as NEW_PROMPT, create_critique_prompt
from idea_generator import compute_score_and_priority


OLD_PROMPT = """You are a ruthlessly honest campaign strategist whose job is to
kill bad ideas before they waste anyone's time. You've seen hundreds of campaign proposals
that looked great on paper and went nowhere. You are allergic to wishful thinking.

Your default assumption: the first-pass scores are inflated. The generation step is
optimistic by design — it's trying to find campaigns. Your job is to be the cold shower.

You have three specific mandates:

MANDATE 1: ANTI-AUTHORITARIAN IMPACT (D3) — Be harsh.
Corporate power is NOT automatically anti-authoritarian. Score 0-1 unless:
- The target is a government actor exercising or enabling authoritarian power
- The target is a corporate actor who has EXPLICITLY expressed support for
  authoritarian politics (e.g., Musk) or is ACTIVELY supporting government
  authoritarian action (e.g., Palantir building ICE databases, tech companies
  building government surveillance tools)
- The campaign's theory of change specifically ERODES an institutional pillar
  of authoritarian support (military, business, religious, law enforcement, judiciary)

Data centers, generic corporate accountability, housing, labor disputes, consumer
protection — these score 0 on anti-authoritarian unless there's a DIRECT, SPECIFIC
link to government authoritarian power. "Tech companies have too much power" = 0.
"Palantir built the database ICE uses to target people" = 3.

MANDATE 2: REPLICABILITY (D4) — Be harsh.
A one-off win is a one-off win. Don't inflate replicability because the issue
is common. Ask specifically:
- Is there a TEMPLATE that someone else could pick up and run? Not "this issue
  exists elsewhere" but "here is a playbook someone could copy."
- Has this model actually been proven somewhere? Theoretical replicability = 1 max.
  Proven template = 3-4.
- If this is a one-off campaign, can the WIN be leveraged into a bigger effort?
  A one-off that creates a legal precedent, a model ordinance, or a proof of concept
  that others will copy deserves credit. A one-off that just wins one fight = 0-1.

MANDATE 3: WINNABILITY (D5) — Be harsh.
Ask: has anything like this ever actually worked? If not, why would it work now?
- "Decision-maker has authority" is necessary but not sufficient. Does the
  decision-maker have any REASON to act? What's the cost of inaction TO THEM?
- If the campaign requires sustained public pressure over months, that's a 1-2,
  not a 3. Small teams can't sustain months-long campaigns without infrastructure.
- Corporate targets that can wait it out = 1 max. Politicians facing an election
  in the relevant timeframe = higher.

ADDITIONAL CHECKS:
- REPLICABLE CAMPAIGNS AND TARGETS: If a campaign is designed to be replicated across
  many jurisdictions, the target may be framed as a class ("county commissioners," "city
  councils"). Don't penalize G1 for this if the class is a set of clearly identifiable
  local decision-makers with real authority. BUT: the idea should name a specific FIRST
  target — the best place to run it first. If it doesn't, note that in critique rather
  than failing the gate.
- Is the constituency REAL or ASPIRATIONAL? "Veterans could be organized" = aspirational.
  "Veterans are already speaking out" = real. Downgrade beyond-choir if aspirational.
- Is this ONE campaign or three mashed together? If the target, constituency, and ask
  don't connect in a SINGLE chain, flag it and downgrade.
- Does the target actually CARE about this constituency's pressure? If you can't
  explain in one sentence why the target would cave, pressure point should be 0-1.
- Think about what winning this fight ENABLES. Note it even if you don't score it.
  A campaign whose win creates leverage for the next fight is more valuable than
  one that dead-ends."""


IDEAS_FILE = Path(__file__).parent.parent / "data" / "ideas_raw.json"


def pick_test_ideas(ideas_dicts: list[dict]) -> list[CampaignIdea]:
    """Same selection as test_rubric_v4.py for apples-to-apples."""
    scored = [i for i in ideas_dicts if not i.get("is_watch_list", False)
              and i.get("weighted_score", 0) >= 2.0]
    picks = []
    seen_domains = set()
    for i in scored:
        if "popular vote" in i.get("headline", "").lower():
            picks.append(i); seen_domains.add(i.get("issue_domain", "")); break
    for i in sorted(scored, key=lambda x: -x["weighted_score"]):
        if len(picks) >= 3:
            break
        if i in picks:
            continue
        d = i.get("issue_domain", "")
        if d in seen_domains:
            continue
        picks.append(i); seen_domains.add(d)
    return [CampaignIdea.from_dict(p) for p in picks]


def run_one_critique(client, system_prompt: str, ideas: list[CampaignIdea]) -> list[CampaignIdea]:
    """Run one critique pass with the given system prompt. Returns fresh copies with scores applied."""
    fresh = [deepcopy(i) for i in ideas]
    user_prompt = create_critique_prompt(fresh)

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    critiques = json.loads(text)

    for critique in critiques:
        idx = critique.get("idea_index", 0) - 1
        if 0 <= idx < len(fresh):
            idea = fresh[idx]
            idea.gate_named_target = critique.get("gate_named_target", idea.gate_named_target)
            idea.gate_binary_ask = critique.get("gate_binary_ask", idea.gate_binary_ask)
            idea.gate_time_window = critique.get("gate_time_window", idea.gate_time_window)
            idea.score_beyond_choir = critique.get("score_beyond_choir", idea.score_beyond_choir)
            idea.score_pressure_point = critique.get("score_pressure_point", idea.score_pressure_point)
            idea.score_anti_authoritarian = critique.get("score_anti_authoritarian", idea.score_anti_authoritarian)
            idea.score_replication = critique.get("score_replication", idea.score_replication)
            idea.score_winnability = critique.get("score_winnability", idea.score_winnability)
            compute_score_and_priority(idea)

    return fresh


def main():
    with open(IDEAS_FILE) as f:
        data = json.load(f)
    ideas = pick_test_ideas(data.get("ideas", []))

    original_scores = [(i.headline[:60], i.weighted_score) for i in ideas]
    print("Baseline (scores from Apr 14 scan stored in ideas_raw.json):")
    for headline, score in original_scores:
        print(f"  {score:.2f}  {headline}")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    runs = []
    for label, prompt in [("OLD run 1", OLD_PROMPT), ("OLD run 2", OLD_PROMPT),
                          ("NEW run 1", NEW_PROMPT), ("NEW run 2", NEW_PROMPT)]:
        print(f"\nRunning {label}...")
        # Retry once on JSON parse failure
        result = None
        for attempt in range(2):
            try:
                result = run_one_critique(client, prompt, ideas)
                break
            except json.JSONDecodeError as e:
                print(f"  JSON parse failed on attempt {attempt+1}: {e}")
        if result is None:
            print(f"  {label} failed twice, recording as None")
            runs.append((label, [None] * len(ideas)))
        else:
            runs.append((label, [r.weighted_score for r in result]))

    print("\n" + "=" * 100)
    print(f"{'Idea':<62}{'Apr14':>8}{'OLD#1':>8}{'OLD#2':>8}{'NEW#1':>8}{'NEW#2':>8}")
    print("=" * 100)
    for idx, (headline, orig) in enumerate(original_scores):
        row = f"{headline:<62}{orig:>8.2f}"
        for label, scores in runs:
            row += f"{scores[idx]:>8.2f}"
        print(row)


if __name__ == "__main__":
    main()
