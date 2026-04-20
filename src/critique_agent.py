"""
Critique Agent — a deliberately adversarial reviewer of campaign ideas.

Runs as a separate step from generation. Its job is to find weaknesses,
assume first-pass scores are inflated, and adjust harshly. It has
specific mandates to be strict on anti-authoritarian impact, replicability,
and winnability.
"""

import json
import anthropic

from models import CampaignIdea
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL


CRITIQUE_SYSTEM_PROMPT = """You are a ruthlessly honest campaign strategist whose job is to
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


def create_critique_prompt(ideas: list[CampaignIdea]) -> str:
    """Create the critique prompt for a batch of ideas."""

    ideas_text = ""
    for i, idea in enumerate(ideas):
        ideas_text += f"""
---
IDEA {i+1}: {idea.headline}
News hook: {idea.news_hook}
Target: {idea.target}
Ask: {idea.ask}
Constituency: {idea.constituency}
Theory of leverage: {idea.theory_of_leverage}
Where: {idea.where}
Time sensitivity: {idea.time_sensitivity}
Issue domain: {idea.issue_domain}

Gates: target={idea.gate_named_target} ask={idea.gate_binary_ask} window={idea.gate_time_window}
Scores: beyond_choir={idea.score_beyond_choir} pressure={idea.score_pressure_point} anti_auth={idea.score_anti_authoritarian} replication={idea.score_replication} winnability={idea.score_winnability}
Weighted score: {idea.weighted_score:.2f}
Rationale: {idea.score_rationale}
---
"""

    prompt = f"""Review these campaign ideas. Your job is to stress-test every score
and adjust where the first pass was too generous. Default assumption: scores are inflated.

## Ideas to Review:
{ideas_text}

## For each idea, evaluate:

1. **Gates** — Do they actually hold up? Is the target truly named and reachable?
   Is the ask truly binary? Is the window truly open? Be strict: if the "target" is
   an ally being encouraged, or the "ask" has multiple steps with no single decision
   point, fail the gate. For G3 (time window): this is open/closed only. A window
   that's open for months is GOOD — more time to organize. Only fail if the moment
   has genuinely passed or will pass before anyone could realistically act.

2. **Anti-authoritarian impact (D3)** — Apply your mandate. Corporate power alone = 0.
   Only score 2+ if there's a direct, specific link to government authoritarian power
   or the campaign erodes an institutional pillar of support.

3. **Replicability (D4)** — Apply your mandate. "Issue exists elsewhere" ≠ replicable.
   Is there an actual template? Has it been proven? If it's a one-off, can the win
   be leveraged into something bigger? Be specific about what the leverage would be.

4. **Winnability (D5)** — Apply your mandate. Has anything like this worked before?
   What's the cost of inaction to the target? Can a small team realistically force
   this in weeks-months?

5. **Beyond-choir (D1)** — Is the constituency real or aspirational?

6. **Pressure point (D2)** — Can you explain in one sentence why the target would cave?

7. **What does winning enable?** — Note the flow-on potential. Does this win create
   leverage, precedent, or proof of concept for the next fight? Or is it a dead end?

8. **Duplicates** — Are any of these the same campaign from different angles?

## Response Format

Return a JSON array with one entry per idea:
```json
[
  {{
    "idea_index": 1,
    "gate_named_target": 2,
    "gate_binary_ask": 2,
    "gate_time_window": 1,
    "score_beyond_choir": 2,
    "score_pressure_point": 3,
    "score_anti_authoritarian": 0,
    "score_replication": 1,
    "score_winnability": 2,
    "critique_notes": "D3 downgraded from 2 to 0: data center opposition is environmental/corporate, not anti-authoritarian — no direct link to government power. D4 downgraded: theoretical replicability only, no proven template yet. Win could create precedent for other zoning fights if it produces model ordinance language.",
    "campaign_group": "",
    "win_enables": "If this produces model ordinance language, it becomes a template for 50+ other communities facing the same issue."
  }}
]
```

Rules:
- Return adjusted scores for EVERY idea, even if unchanged
- Explain every score change in critique_notes
- If scores hold up, say "Scores hold up under scrutiny" and explain briefly why
- campaign_group: label if multiple ideas target the same campaign. Empty for unique ideas.
- win_enables: one sentence on what winning this fight creates for the next fight. Empty if dead-end.
- Be genuinely harsh. You are doing the campaign a favor by killing weak ideas early.

IMPORTANT: Return ONLY the JSON array, no other text."""

    return prompt


def run_critique(ideas: list[CampaignIdea]) -> list[CampaignIdea]:
    """Run the critique agent on scored ideas. Returns all ideas with adjusted scores."""

    if not ideas:
        return ideas

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Only critique scored ideas (not watch list)
    scored = [i for i in ideas if not i.is_watch_list]
    watch = [i for i in ideas if i.is_watch_list]

    if not scored:
        return ideas

    print(f"  Critique agent reviewing {len(scored)} scored ideas...")

    # Process in chunks to stay within token limits
    chunk_size = 15
    all_critiqued = []

    for chunk_start in range(0, len(scored), chunk_size):
        chunk = scored[chunk_start:chunk_start + chunk_size]
        print(f"    Reviewing {len(chunk)} ideas...")

        # Save pre-critique scores
        for idea in chunk:
            idea.pre_critique_score = idea.weighted_score

        prompt = create_critique_prompt(chunk)

        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4000,
                system=CRITIQUE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            # Parse JSON
            text = response_text
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            critiques = json.loads(text)

            adjustments = 0
            demoted = 0
            for critique in critiques:
                idx = critique.get("idea_index", 0) - 1
                if 0 <= idx < len(chunk):
                    idea = chunk[idx]

                    # Apply adjusted scores
                    idea.gate_named_target = critique.get("gate_named_target", idea.gate_named_target)
                    idea.gate_binary_ask = critique.get("gate_binary_ask", idea.gate_binary_ask)
                    idea.gate_time_window = critique.get("gate_time_window", idea.gate_time_window)
                    idea.score_beyond_choir = critique.get("score_beyond_choir", idea.score_beyond_choir)
                    idea.score_pressure_point = critique.get("score_pressure_point", idea.score_pressure_point)
                    idea.score_anti_authoritarian = critique.get("score_anti_authoritarian", idea.score_anti_authoritarian)
                    idea.score_replication = critique.get("score_replication", idea.score_replication)
                    idea.score_winnability = critique.get("score_winnability", idea.score_winnability)
                    idea.critique_notes = critique.get("critique_notes", "")
                    idea.campaign_group = critique.get("campaign_group", idea.campaign_group)

                    # Capture win_enables in critique notes if present
                    win_enables = critique.get("win_enables", "")
                    if win_enables and win_enables not in idea.critique_notes:
                        idea.critique_notes += f" Win enables: {win_enables}"

                    # Recompute scores
                    from idea_generator import compute_score_and_priority
                    compute_score_and_priority(idea)

                    if idea.weighted_score != idea.pre_critique_score:
                        adjustments += 1
                    if idea.is_watch_list:
                        demoted += 1

            print(f"    Adjusted {adjustments}/{len(chunk)} scores, demoted {demoted} to watch list")

        except (json.JSONDecodeError, anthropic.APIError) as e:
            print(f"    Warning: Critique failed ({e}), keeping original scores")

        all_critiqued.extend(chunk)

    still_scored = [i for i in all_critiqued if not i.is_watch_list]
    newly_watch = [i for i in all_critiqued if i.is_watch_list]

    if newly_watch:
        print(f"    Total demoted to watch list by critique: {len(newly_watch)}")

    return still_scored + newly_watch + watch


# =============================================================================
# AI Leverage Tagging — independent of scoring, isolated from critique
# =============================================================================

AI_LEVERAGE_SYSTEM_PROMPT = """You are evaluating whether AI-augmentation specifically
increases the odds of success for a campaign. This evaluation is INDEPENDENT of whether
the campaign is good. You are NOT scoring the campaign. Do NOT comment on winnability,
constituency strength, or target specificity. Only assess AI-augmentation fit.

HIGH AI leverage mechanisms:
- Personalized outreach at scale across many targets
- Rapid research on dozens of targets/institutions in parallel
- Real-time stakeholder mapping and network analysis
- Synthesizing public comment dumps or other noisy data
- Iterating content across many audiences/regions
- Monitoring signals in noisy data streams
- Building and maintaining target-specific playbooks

LOW AI leverage mechanisms:
- Shoe-leather field organizing in one locality
- Coalition convening that requires trusted relationships
- Lobbying a single statehouse or decision-maker
- Courtroom work
- Fundamentally ground-presence-dependent campaigns

Output for each idea: one sentence naming the specific mechanism where AI helps,
or "no clear AI leverage — better suited to a conventional campaign team" if the
campaign is fundamentally relationship- or ground-presence-dependent."""


AI_LEVERAGE_MIN_SCORE = 2.0
AI_LEVERAGE_CHUNK_SIZE = 10


def _build_ai_leverage_prompt(ideas: list[CampaignIdea]) -> str:
    ideas_text = ""
    for i, idea in enumerate(ideas):
        ideas_text += f"""
---
IDEA {i+1}: {idea.headline}
Target: {idea.target}
Ask: {idea.ask}
Constituency: {idea.constituency}
Theory of leverage: {idea.theory_of_leverage}
Where: {idea.where}
---
"""
    return f"""Evaluate AI-augmentation fit for each campaign idea below.

{ideas_text}

Return a JSON array with one entry per idea:
```json
[
  {{"idea_index": 1, "ai_leverage": "one-sentence mechanism statement"}},
  {{"idea_index": 2, "ai_leverage": "..."}}
]
```

Return ONLY the JSON array, no other text."""


def tag_ai_leverage(ideas: list[CampaignIdea]) -> list[CampaignIdea]:
    """
    Tag scored ideas above AI_LEVERAGE_MIN_SCORE with an AI-augmentation
    assessment. Runs after critique so it uses post-critique scores as the
    filter, but is completely isolated from scoring — the agent cannot adjust
    scores here.
    """
    if not ideas:
        return ideas

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set.")

    eligible = [
        i for i in ideas
        if not i.is_watch_list and i.weighted_score >= AI_LEVERAGE_MIN_SCORE
    ]

    if not eligible:
        print("  AI leverage tagging: no ideas scored high enough")
        return ideas

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    print(f"  AI leverage tagging: evaluating {len(eligible)} ideas...")

    for chunk_start in range(0, len(eligible), AI_LEVERAGE_CHUNK_SIZE):
        chunk = eligible[chunk_start:chunk_start + AI_LEVERAGE_CHUNK_SIZE]
        prompt = _build_ai_leverage_prompt(chunk)

        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2000,
                system=AI_LEVERAGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            tags = json.loads(text)

            for tag in tags:
                idx = tag.get("idea_index", 0) - 1
                if 0 <= idx < len(chunk):
                    chunk[idx].ai_leverage = tag.get("ai_leverage", "")

        except (json.JSONDecodeError, anthropic.APIError) as e:
            print(f"    Warning: AI leverage chunk failed ({type(e).__name__}: {e})")
            for idea in chunk:
                if not idea.ai_leverage:
                    idea.ai_leverage = "tagging failed"

    return ideas


# =============================================================================
# Coverage Research — uses web_search to identify existing org coverage
# =============================================================================

COVERAGE_RESEARCH_SYSTEM_PROMPT = """You are researching existing organizing coverage for
a campaign idea. Your job is to identify:
1. Which established organizations are actively campaigning on this
2. How active they are — full-time staff, ongoing effort, or quiet/dormant
3. What specific gap a new small AI-augmented team could fill — a geography,
   a tactic, a constituency, or a target the existing orgs aren't touching

Be honest. If the campaign is already well-covered by experienced organizations
and a new effort would just add noise, say so plainly. If there's a real gap
(e.g., national org focuses on legal/legislative but no one's doing local
organizing of the constituency), describe the gap concretely."""


COVERAGE_RESEARCH_MIN_SCORE = 2.0


def _research_one_idea(client: anthropic.Anthropic, idea: CampaignIdea) -> str:
    """Run a single coverage-research call with web_search. Returns the coverage summary."""

    user_prompt = f"""Research existing organizing coverage for this campaign:

- Target: {idea.target}
- Ask: {idea.ask}
- Issue: {idea.issue_domain}
- Where: {idea.where}
- Theory of leverage: {idea.theory_of_leverage}

Use web search to identify which organizations are actively campaigning on this.

Then write ONE paragraph (≤120 words) covering:
1. The 2-4 most relevant existing organizations and what they are doing
2. Specifically what gap a new small AI-augmented team could fill, OR state
   plainly that there is no meaningful gap and a new effort would duplicate
   existing work.

Do not include a preamble. Just the paragraph."""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=COVERAGE_RESEARCH_SYSTEM_PROMPT,
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
        }],
        messages=[{"role": "user", "content": user_prompt}],
    )

    text_parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)

    return " ".join(p.strip() for p in text_parts if p.strip())


def research_coverage(ideas: list[CampaignIdea]) -> list[CampaignIdea]:
    """
    For each scored idea above COVERAGE_RESEARCH_MIN_SCORE, research existing
    organizational coverage using web_search and write the result to
    existing_coverage. Watch-list and low-score ideas are skipped.
    Failures write 'research failed' so the omission is visible in output.
    """
    if not ideas:
        return ideas

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set.")

    eligible = [
        i for i in ideas
        if not i.is_watch_list and i.weighted_score >= COVERAGE_RESEARCH_MIN_SCORE
    ]

    if not eligible:
        print("  Coverage research: no ideas scored high enough to research")
        return ideas

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    print(f"  Coverage research: running web_search on {len(eligible)} ideas (score ≥ {COVERAGE_RESEARCH_MIN_SCORE})...")

    for i, idea in enumerate(eligible, 1):
        print(f"    [{i}/{len(eligible)}] {idea.headline[:70]}")
        try:
            summary = _research_one_idea(client, idea)
            idea.existing_coverage = summary if summary else "research failed (empty response)"
        except (anthropic.APIError, anthropic.APIStatusError) as e:
            print(f"      Warning: research failed ({type(e).__name__}: {e})")
            idea.existing_coverage = "research failed"
        except Exception as e:
            print(f"      Warning: research failed ({type(e).__name__}: {e})")
            idea.existing_coverage = "research failed"

    return ideas
