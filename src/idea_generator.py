"""
Campaign Idea Generator — searches news, generates campaign ideas with
target/ask/constituency/leverage, scores them against a two-stage rubric,
then self-critiques and adjusts.

Replaces the old opening_detector.py.
"""

import json
import anthropic

from models import Article, CampaignIdea
from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    BATCH_SIZE,
    OPENING_CATEGORIES,
    ISSUE_DOMAINS,
)


# =============================================================================
# Campaign Idea Generation Prompt
# =============================================================================

IDEA_GENERATION_CRITERIA = """
## Your Role

You are a creative campaign strategist. You're scanning news to generate
grassroots campaign IDEAS — not just interesting news, but concrete campaign
proposals with a target, an ask, a constituency, and a theory of leverage.

If a news item doesn't suggest all four of those, it's not a campaign idea yet —
it might be a Watch List signal.

## How to Think About Campaign Ideas

Think like a creative campaigner, not a news aggregator:

- **Who is the intermediary?** Often more effective than pressuring the direct target.
  Advertisers, not the platform. Shareholders, not the executives. Local officials,
  not the federal government. Employers' customers, not the employers.

- **Who has unexpected self-interest?** The constituency that makes a campaign powerful
  is usually not the obvious one. Catholic voters in a Pope story. Military families in
  a defense story. Small business owners in a tariff story.

- **What's the binary ask?** Force it into one sentence. If you can't, it's not a
  campaign yet.

- **What does the target have to lose?** If the target can shrug this off, it's not
  a real pressure point.

- **For replicable campaigns, name the best FIRST target.** Don't say "city councils
  considering Flock contracts" — say "Oakland County Board of Commissioners" and note
  it's replicable to 50+ counties. The campaign needs a specific starting point even
  if the model is designed to spread.

- **When the news is a state-level success, name the next vulnerable state, not a class.**
  If a state just passed something (NPV, ranked choice, redistricting reform, campaign
  finance reform, etc.), the campaign idea is NOT "pressure holdout states" — it's
  "pressure [specific next state + named decision-maker] before [specific window closes]."
  Pick the next state by: (a) opportunity (trifecta, governor with authority, live bill),
  (b) window (session schedule, election cycle, trifecta expiration), (c) a named
  decision-maker who could actually deliver. Abstract "holdout states" framing almost
  never produces a winnable campaign.

## Categories of Openings (assign ONE):

1. **Actions That Could Be Replicated**
   Key question: Who did something good that someone else hasn't done yet but could?

2. **Cracks and Fissures**
   Key question: Is someone breaking from the expected alignment?

3. **Gaps and Absences**
   Key question: What's missing that could be created?

4. **Pending Decisions and Leverage Points**
   Key question: Where is there a decision coming that could be influenced?

5. **Emerging Patterns (Uncoordinated Energy)**
   Key question: Where is there energy without infrastructure?

6. **Outrages and Galvanizing Events**
   Key question: Is there an ask that channels this energy?

7. **Defensive Needs**
   Key question: What's coming that people could get ahead of?

## Issue Domains (assign ONE):
""" + "\n".join(f"- {d}" for d in ISSUE_DOMAINS) + """

## What DISQUALIFIES something:
- It's already a well-known, organized campaign (saturated)
- The moment has clearly passed
- It's just commentary or analysis, not an action or event
- It requires ground presence in a crisis zone
- You can't name a specific target, ask, and constituency
"""


def create_generation_prompt(articles: list[Article]) -> str:
    """Create the prompt for generating campaign ideas from a batch of articles."""

    articles_text = ""
    for i, article in enumerate(articles):
        content_preview = article.content[:2000] if article.content else ""
        articles_text += f"""
---
ARTICLE {i+1}:
Source: {article.source}
Title: {article.title}
URL: {article.url}
Published: {article.published.isoformat()}
Content:
{content_preview}
---
"""

    prompt = f"""You are a campaign strategist scanning news for grassroots campaign
opportunities — pro-democracy, anti-authoritarian campaigns that a small team could run.

{IDEA_GENERATION_CRITERIA}

## Articles to Scan:
{articles_text}

## Instructions:
1. Read each article carefully
2. For each article that suggests a campaign opportunity, GENERATE A CAMPAIGN IDEA —
   not just describe the news, but propose a campaign with all four elements:
   target, ask, constituency, and theory of leverage.
3. Be creative. The best ideas come from unexpected angles — who has self-interest
   that isn't obvious? Who is the intermediary with real leverage?
4. Be selective — most articles will NOT produce campaign ideas. That's fine.
5. An article might suggest multiple campaign ideas, or none.
6. Score each idea against the gates and dimensions below.

Respond with a JSON array. For each campaign idea:
```json
[
  {{
    "article_index": 1,
    "headline": "One-line campaign pitch (action-oriented, specific)",
    "news_hook": "What happened that creates this opening",
    "target": "Named, specific target — who can deliver the win",
    "ask": "Binary ask in one sentence — what specifically are we demanding",
    "constituency": "Who has leverage and self-interest to pressure the target",
    "theory_of_leverage": "Why the target would cave — the specific chain from constituency action to target response",
    "where": "Location",
    "issue_domain": "One of the issue domains listed above",
    "category": "One of the 7 categories listed above",
    "time_sensitivity": "What's the window and when does it close",
    "gate_named_target": 2,
    "gate_binary_ask": 2,
    "gate_time_window": 1,
    "gate_fail_reason": "",
    "watch_list_trigger": "",
    "score_beyond_choir": 3,
    "score_pressure_point": 2,
    "score_anti_authoritarian": 3,
    "score_replication": 2,
    "score_winnability": 3,
    "score_rationale": "1-2 sentences on the dominant factor(s)"
  }}
]
```

## Two-Stage Scoring

### STAGE 1: Gates (pass/fail)
Score each gate 0, 1, or 2. An idea that scores 0 on ANY gate is Watch List.
Set gate_fail_reason to explain which gate(s) failed and why.
Set watch_list_trigger to describe what event could promote it to scored.

GATE 1 — Named, Reachable Target
2 = Specific named target with clear authority (a sheriff, mayor, CEO, state AG, zoning board, specific company)
1 = Target identifiable but less direct (a class of actors like "city councils," a state agency)
0 = No named target, or target is unreachable ("the Trump administration," "Congress," "public opinion").
    Also 0 if the "target" is actually an ally being encouraged to do more.

GATE 2 — Specific, Binary Ask
2 = Clear binary ask ("revoke the permit," "suspend the contract," "pass the moratorium")
1 = Ask identifiable but less crisp ("adopt a version of this policy")
0 = No specific ask ("raise awareness," "hold accountable"). Also 0 if the ask requires
    multiple steps from multiple actors with no single decision point.

GATE 3 — Time Window Still Open
This is a simple open/closed check. Don't penalize longer windows — a campaign with
6 months of runway is more viable than one with 2 weeks, not less.
1 = Window is open. The decision hasn't been made, the leverage still exists, and there's
    enough time to realistically organize a campaign (at least 2-3 weeks).
0 = Window is essentially closed. Decision already made, leverage gone, or the moment
    will have passed before anyone could realistically act on it.

### STAGE 2: Scoring Dimensions (0-4 each)
Only score if ALL gates passed (all scored 1+). If any gate = 0, leave these as 0.

DIMENSION 1 — Beyond-the-Choir Constituency (weight: 25%)
0 = Only mobilizes already-activated progressives
1 = Constituency exists in theory but requires significant persuasion
2 = Clear non-progressive constituency with identifiable self-interest
3 = Strong beyond-the-choir constituency already showing signs of engagement
4 = The beyond-the-choir angle IS the story — the powerful constituency is definitionally not the progressive base

DIMENSION 2 — Actionable Pressure Point (weight: 25%)
0 = Target has no reason to care about this constituency's pressure
1 = Target could theoretically be pressured but no clear mechanism
2 = Clear mechanism exists but target can probably wait it out
3 = Target faces concrete, near-term consequences from this specific constituency
4 = Target is already showing signs of vulnerability — cracking, wavering, making defensive moves

DIMENSION 3 — Anti-Authoritarian Impact (weight: 25%)
0 = No connection to government authoritarian power. Generic corporate accountability, environmental, housing, labor, consumer issues score 0 unless there is a DIRECT link to government authoritarianism.
1 = Tangential connection — corporate actor has not explicitly supported authoritarianism but enables it indirectly (e.g., general government contractor)
2 = Direct link to government authoritarian power: target IS a government actor exercising authoritarian power (ICE, DOJ political prosecutions, voter suppression), OR target is a corporate actor who has EXPLICITLY supported authoritarian politics (e.g., Musk) or is ACTIVELY building tools of government authoritarian control (e.g., Palantir's ICE databases, surveillance tech for government use)
3 = Directly anti-authoritarian AND targets an institutional pillar (military, business, religious, law enforcement, judiciary) — the campaign's theory of change erodes a specific support structure
4 = Structurally weakens authoritarian support by driving a wedge into a major institutional pillar at a moment of visible fracture

DIMENSION 4 — Replication Potential (weight: 12.5%)
0 = One-off situation
1 = Could theoretically happen elsewhere with significant adaptation
2 = Same dynamic exists in multiple places
3 = Template exists or could be easily created
4 = Template is already proven AND applicable in dozens or hundreds of locations

DIMENSION 5 — Winnability in Weeks-Months (weight: 12.5%)
0 = Requires national legislation, years of litigation, or massive infrastructure
1 = Achievable but requires sustained multi-month effort with uncertain outcome
2 = Clear path to a decision within months
3 = Decision-maker has unilateral authority and comparable wins have happened
4 = Win is achievable in days to weeks

The system will compute weighted_score and priority from your scores.
Do NOT include weighted_score or priority in your response.

If NO campaign ideas are found in this batch, return an empty array: []

IMPORTANT: Return ONLY the JSON array, no other text."""

    return prompt


    # Old self-critique prompt removed — replaced by critique_agent.py


# =============================================================================
# Score computation
# =============================================================================

def compute_score_and_priority(idea: CampaignIdea) -> None:
    """Compute watch_list status, weighted_score, and priority from gate/dimension scores."""
    if idea.gate_named_target == 0 or idea.gate_binary_ask == 0 or idea.gate_time_window == 0:
        idea.is_watch_list = True
        idea.weighted_score = 0.0
        idea.priority = 0
        return

    # Weighted score from dimensions (each scored 0-4)
    # D1: 25%, D2: 25%, D3: 25%, D4: 12.5%, D5: 12.5%
    idea.weighted_score = (
        idea.score_beyond_choir * 0.25
        + idea.score_pressure_point * 0.25
        + idea.score_anti_authoritarian * 0.25
        + idea.score_replication * 0.125
        + idea.score_winnability * 0.125
    )

    # Map weighted score (0.0 - 4.0) to priority
    ws = idea.weighted_score
    if ws >= 3.5:
        idea.priority = 5  # Exceptional
    elif ws >= 2.5:
        idea.priority = 4  # Strong
    elif ws >= 1.5:
        idea.priority = 3  # Solid
    else:
        idea.priority = 2  # Low priority


# =============================================================================
# JSON parsing helper
# =============================================================================

def _parse_json_response(response_text: str):
    """Parse JSON from Claude response, handling markdown code blocks."""
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


# =============================================================================
# Main generation pipeline
# =============================================================================

def generate_ideas(articles: list[Article]) -> list[CampaignIdea]:
    """
    Process articles through Claude to generate campaign ideas.
    Two passes: generate+score, then self-critique+adjust.
    """
    if not articles:
        return []

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    all_ideas = []

    # =========================================================================
    # Pass 1: Generate and score campaign ideas
    # =========================================================================
    total_batches = (len(articles) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(0, len(articles), BATCH_SIZE):
        batch = articles[batch_num:batch_num + BATCH_SIZE]
        batch_idx = batch_num // BATCH_SIZE + 1
        print(f"  Processing batch {batch_idx}/{total_batches} ({len(batch)} articles)...")

        prompt = create_generation_prompt(batch)

        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()
            results = _parse_json_response(response_text)

            batch_ideas = 0
            for item in results:
                idx = item.get("article_index", 0) - 1
                if 0 <= idx < len(batch):
                    article = batch[idx]
                    idea = CampaignIdea(
                        headline=item.get("headline", ""),
                        news_hook=item.get("news_hook", ""),
                        target=item.get("target", ""),
                        ask=item.get("ask", ""),
                        constituency=item.get("constituency", ""),
                        theory_of_leverage=item.get("theory_of_leverage", ""),
                        source_url=article.url,
                        source_name=article.source,
                        issue_domain=item.get("issue_domain", ""),
                        category=item.get("category", ""),
                        where=item.get("where", ""),
                        time_sensitivity=item.get("time_sensitivity", ""),
                        gate_named_target=item.get("gate_named_target", 0),
                        gate_binary_ask=item.get("gate_binary_ask", 0),
                        gate_time_window=item.get("gate_time_window", 0),
                        gate_fail_reason=item.get("gate_fail_reason", ""),
                        watch_list_trigger=item.get("watch_list_trigger", ""),
                        score_beyond_choir=item.get("score_beyond_choir", 0),
                        score_pressure_point=item.get("score_pressure_point", 0),
                        score_anti_authoritarian=item.get("score_anti_authoritarian", 0),
                        score_replication=item.get("score_replication", 0),
                        score_winnability=item.get("score_winnability", 0),
                        score_rationale=item.get("score_rationale", ""),
                    )
                    compute_score_and_priority(idea)
                    all_ideas.append(idea)
                    batch_ideas += 1

            print(f"    Found {batch_ideas} campaign ideas in this batch")

        except json.JSONDecodeError as e:
            print(f"    Warning: Failed to parse AI response: {e}")
        except anthropic.APIError as e:
            print(f"    API error: {e}")

    scored = [i for i in all_ideas if not i.is_watch_list]
    watch = [i for i in all_ideas if i.is_watch_list]
    print(f"\n  Pass 1 complete: {len(scored)} scored ideas, {len(watch)} watch list")

    # =========================================================================
    # Pass 2: Critique agent (separate adversarial reviewer)
    # =========================================================================
    if scored:
        from critique_agent import run_critique
        print(f"\n  Running critique agent on {len(scored)} scored ideas...")
        all_ideas = run_critique(scored + watch)
    else:
        all_ideas = scored + watch

    # =========================================================================
    # Pass 3: AI leverage tagging (isolated from scoring)
    # =========================================================================
    from critique_agent import tag_ai_leverage, research_coverage
    all_ideas = tag_ai_leverage(all_ideas)

    # =========================================================================
    # Pass 4: Coverage research (web_search on high-scored ideas only)
    # =========================================================================
    all_ideas = research_coverage(all_ideas)

    # =========================================================================
    # Sort and return
    # =========================================================================
    scored = [i for i in all_ideas if not i.is_watch_list]
    watch = [i for i in all_ideas if i.is_watch_list]
    scored.sort(key=lambda i: (i.weighted_score, i.priority), reverse=True)
    watch.sort(key=lambda i: i.headline)

    return scored + watch


    # Old self_critique function removed — replaced by critique_agent.py


# =============================================================================
# Dedup (kept from old system, simplified)
# =============================================================================

def create_dedup_prompt(ideas: list[CampaignIdea]) -> str:
    """Create prompt for deduplicating ideas across batches."""

    items_text = ""
    for i, idea in enumerate(ideas):
        items_text += f"""
---
IDEA {i+1}: {idea.headline}
Target: {idea.target}
Ask: {idea.ask}
Where: {idea.where}
Category: {idea.category}
Issue: {idea.issue_domain}
Source: {idea.source_url}
---
"""

    prompt = f"""You are helping deduplicate a list of campaign ideas. Below are {len(ideas)} ideas
that were generated from different news sources.

Identify ideas that describe the SAME campaign — same target and same ask.

{items_text}

Return a JSON array where each element represents a unique idea:
- For unique ideas: include just the index
- For duplicates: include all indices, note which has the best detail

```json
[
  {{"indices": [1], "keep": 1}},
  {{"indices": [2, 5, 8], "keep": 5}},
  {{"indices": [3], "keep": 3}}
]
```

Rules:
- Only merge ideas with the SAME target AND the SAME ask
- Different targets or different asks on the same topic = KEEP SEPARATE
- Every idea index must appear exactly once

IMPORTANT: Return ONLY the JSON array, no other text."""

    return prompt


def deduplicate_ideas(ideas: list[CampaignIdea], client: anthropic.Anthropic) -> list[CampaignIdea]:
    """Deduplicate ideas with same target+ask."""

    if len(ideas) <= 1:
        return ideas

    # Process in chunks if very large
    if len(ideas) > 60:
        return _deduplicate_in_chunks(ideas, client)

    prompt = create_dedup_prompt(ideas)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()
        merge_instructions = _parse_json_response(response_text)

        deduplicated = []
        for instruction in merge_instructions:
            indices = instruction.get("indices", [])
            if not indices:
                continue

            indices = [i - 1 for i in indices]
            valid_indices = [i for i in indices if 0 <= i < len(ideas)]
            if not valid_indices:
                continue

            keep_idx = instruction.get("keep", indices[0] + 1) - 1
            if keep_idx not in valid_indices:
                keep_idx = valid_indices[0]

            base = ideas[keep_idx]

            additional = list(base.additional_sources)
            for idx in valid_indices:
                if idx != keep_idx:
                    other = ideas[idx]
                    if other.source_url not in additional and other.source_url != base.source_url:
                        additional.append(other.source_url)

            base.additional_sources = additional
            deduplicated.append(base)

        removed = len(ideas) - len(deduplicated)
        if removed > 0:
            print(f"    Dedup: {len(ideas)} → {len(deduplicated)} (merged {removed} duplicates)")

        return deduplicated

    except (json.JSONDecodeError, anthropic.APIError) as e:
        print(f"    Warning: Deduplication failed ({e}), keeping all ideas")
        return ideas


def _deduplicate_in_chunks(ideas: list[CampaignIdea], client: anthropic.Anthropic) -> list[CampaignIdea]:
    """Deduplicate a large list by processing in chunks."""
    chunk_size = 50
    first_pass = []
    for i in range(0, len(ideas), chunk_size):
        chunk = ideas[i:i + chunk_size]
        print(f"    Dedup chunk {i//chunk_size + 1} ({len(chunk)} ideas)...")
        deduped_chunk = deduplicate_ideas(chunk, client)
        first_pass.extend(deduped_chunk)

    if len(first_pass) > 1 and len(first_pass) <= 60:
        print(f"    Final dedup pass ({len(first_pass)} ideas)...")
        return deduplicate_ideas(first_pass, client)

    return first_pass
