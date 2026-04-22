"""
Critique Agent — a deliberately adversarial reviewer of campaign ideas.

Runs as a separate step from generation. Its job is to find weaknesses,
assume first-pass scores are inflated, and adjust harshly. It has
specific mandates to be strict on anti-authoritarian impact, replicability,
and winnability.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import anthropic

from models import CampaignIdea


def _raise_if_credits_error(e: Exception) -> None:
    if isinstance(e, anthropic.APIStatusError) and "credit balance" in str(e).lower():
        raise SystemExit(f"\nFATAL: Anthropic credits exhausted — add credits at console.anthropic.com then rerun.\n({e})")
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from cost_tracker import tracker


CRITIQUE_SYSTEM_PROMPT = """You are a ruthlessly honest campaign strategist whose job is to
kill bad ideas before they waste anyone's time. You've seen hundreds of campaign proposals
that looked great on paper and went nowhere. You are allergic to wishful thinking.

Your default assumption: the first-pass scores are inflated. The generation step is
optimistic by design — it's trying to find campaigns. Your job is to be the cold shower.

You have specific mandates on the highest-weighted dimensions:

MANDATE 1: ACTIONABLE PRESSURE POINT (D2, 25%) — Be harsh.
Can you explain in one sentence why the target would cave? If not, score 0-1.
- "Decision-maker has authority" is necessary but not sufficient. What's the cost
  of inaction TO THEM, specifically from THIS constituency?
- If the campaign requires sustained public pressure over months with no escalation
  path, that's a 1-2, not a 3. Small teams can't sustain that without infrastructure.
- Corporate targets that can wait it out = 1 max. Politicians facing near-term
  electoral consequences = higher.
- Check the leverage chain: does this constituency → this action → this cost to
  target actually hold together as a single chain? If you need two different
  constituencies pressuring two different targets, that's two campaigns, not one.

MANDATE 2: ANTI-AUTHORITARIAN IMPACT (D3, 25%) — Be harsh.
Use the 3Ds lens: does this campaign delegitimize the regime, induce defections
from its coalition, or delay and defend against its attacks?
Corporate power is NOT automatically anti-authoritarian. Score 0-1 unless:
- The target is a government actor exercising or enabling authoritarian power
- The target is a corporate actor who has EXPLICITLY expressed support for
  authoritarian politics or is ACTIVELY supporting government authoritarian action
- The campaign directly targets an institutional pillar of support (military,
  business, faith communities, law enforcement, civil service, media)
- The campaign demonstrably swings a key constituency whose realignment erodes
  the coalition authoritarian politics depends on
Data centers, generic corporate accountability, housing, routine contract disputes, consumer
protection — these score 0 unless there's a DIRECT, SPECIFIC link to government
authoritarian power or the authoritarian coalition. "Tech companies have too much
power" = 0. "Palantir built the database ICE uses to target people" = 3.

MANDATE 3: REPLICATION POTENTIAL (D4, 15%) — Be harsh.
A one-off win is a one-off win. Don't inflate replicability because the issue
is common. Two patterns count as replication — a template for independent local
campaigns (like sanctuary resolutions) and a national campaign with local tactics
(like a coordinated boycott with local actions). Ask specifically:
- Is there a TEMPLATE that someone else could pick up and run? Not "this issue
  exists elsewhere" but "here is a playbook someone could copy."
- Has this model actually been proven somewhere? Theoretical replicability = 1 max.
  Proven template = 3-4.
- If this is a one-off, can the WIN create a template, legal precedent, or proof
  of concept that others will copy? Credit that. A one-off that just wins one
  fight with no downstream leverage = 0-1.

ADDITIONAL CHECKS:

- WINNABILITY (D5): Has anything like this ever actually worked? If not, why would
  it work now? Are there credible messengers who can reach this constituency?

- BEYOND-THE-CHOIR (D1): Is the constituency REAL or ASPIRATIONAL? "Gun owners could
  be organized" = aspirational. "Gun owners are already speaking out" = real. Downgrade
  if aspirational.

- ENERGY POTENTIAL (D6): Are the conditions for self-spreading participation actually
  there? A simple action, a clear moral line, visible participation that recruits the
  next person? Or does this require heavy organized outreach to sustain? Don't confuse
  "people are angry" with "people will act."

- NON-COMPLIANCE (D7): If the generator scored this high on non-compliance, check
  whether the non-cooperation theory actually holds. Is there something real to
  withdraw? Would enough people actually refuse?

- REPLICABLE CAMPAIGNS AND TARGETS: If a campaign is designed to be replicated across
  many jurisdictions, the target may be framed as a class ("county commissioners").
  Don't penalize G1 for this if the class is clearly identifiable local decision-makers
  with real authority. BUT: the idea should name a specific FIRST target. If it doesn't,
  note that in critique rather than failing the gate.

- Think about what winning this fight ENABLES. A campaign whose win creates leverage,
  precedent, or proof of concept for the next fight is more valuable than one that
  dead-ends."""


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
Scores: beyond_choir={idea.score_beyond_choir} pressure={idea.score_pressure_point} anti_auth={idea.score_anti_authoritarian} replication={idea.score_replication} winnability={idea.score_winnability} energy={idea.score_energy_potential} non_compliance={idea.score_non_compliance}
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
   that's open for months is GOOD. Only fail if the moment has genuinely passed.

2. **Pressure point (D2)** — Apply your mandate. Can you explain in one sentence why
   the target would cave? Does the leverage chain hold as a single chain?

3. **Anti-authoritarian impact (D3)** — Apply your mandate. Use the 3Ds lens.
   Corporate power alone = 0. Only score 2+ with a direct, specific link.

4. **Replicability (D4)** — Apply your mandate. Is there an actual template? Has it
   been proven? Can the win create downstream leverage?

5. **Beyond-choir (D1)** — Is the constituency real or aspirational?

6. **Winnability (D5)** — Has this worked before? Are credible messengers available?

7. **Energy potential (D6)** — Will this spread on its own? Simple action, clear moral
   line, visible participation? Or does it require heavy outreach to sustain?

8. **Non-compliance (D7)** — If scored high, does the non-cooperation theory hold?

9. **What does winning enable?** — Note flow-on potential.

10. **Duplicates** — Are any of these the same campaign from different angles?

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
    "score_energy_potential": 2,
    "score_non_compliance": 1,
    "critique_notes": "D3 downgraded from 2 to 0: data center opposition is environmental/corporate, not anti-authoritarian. D4 downgraded: theoretical replicability only. Win could create precedent for other zoning fights if it produces model ordinance language.",
    "win_enables": "If this produces model ordinance language, it becomes a template for 50+ other communities facing the same issue."
  }}
]
```

Rules:
- Return adjusted scores for EVERY idea, even if unchanged
- Explain every score change in critique_notes
- If scores hold up, say "Scores hold up under scrutiny" and explain briefly why
- win_enables: one sentence on what winning creates for the next fight. Empty if dead-end.
- Be genuinely harsh. You are doing the campaign a favor by killing weak ideas early.

IMPORTANT: Return ONLY the JSON array, no other text."""

    return prompt


def run_critique(ideas: list[CampaignIdea]) -> list[CampaignIdea]:
    """Run the critique agent on scored ideas. Returns all ideas with adjusted scores."""

    if not ideas:
        return ideas

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=4)

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
                max_tokens=16000,
                system=CRITIQUE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )

            tracker.record(response)
            response_text = response.content[0].text.strip()

            # Parse JSON
            text = response_text
            if "```" in text:
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
                    idea.score_energy_potential = critique.get("score_energy_potential", idea.score_energy_potential)
                    idea.score_non_compliance = critique.get("score_non_compliance", idea.score_non_compliance)
                    idea.critique_notes = critique.get("critique_notes", "")

                    # Capture win_enables in critique notes if present
                    win_enables = critique.get("win_enables", "")
                    if win_enables and win_enables not in idea.critique_notes:
                        idea.critique_notes += f" Win enables: {win_enables}"

                    # Recompute scores
                    from idea_generator import compute_score
                    compute_score(idea)

                    if idea.weighted_score != idea.pre_critique_score:
                        adjustments += 1
                    if idea.is_watch_list:
                        demoted += 1

            print(f"    Adjusted {adjustments}/{len(chunk)} scores, demoted {demoted} to watch list")

        except (json.JSONDecodeError, anthropic.APIError) as e:
            _raise_if_credits_error(e)
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

CORE PRINCIPLE: AI can act as an organizer and communicator, not just a research tool.
If you can get a list of people to contact — volunteers to brief, constituents to mobilize,
officials to pressure, commissioners to lobby — AI can conduct those conversations at scale.
A campaign that looks like "shoe-leather organizing" is high AI leverage if the organizing
is fundamentally about reaching identifiable people through calls, messages, or email.

HIGH AI leverage mechanisms:
- Constituent outreach to officials: AI can run the calls, texts, or emails from
  identified constituents to a named decision-maker
- Volunteer coordination and briefing: AI can onboard, brief, and coordinate volunteers
  who will take a specific action (call their county clerk, attend a hearing, etc.)
- Personalized pressure at scale: AI can run individualized contact campaigns across
  many targets simultaneously
- Rapid research on dozens of targets/institutions in parallel
- Stakeholder and donor mapping from public records
- Synthesizing public comment dumps, petition signers, or noisy data
- Iterating messaging across audiences, regions, or languages
- Monitoring signals and tracking responses across many fronts

LOW AI leverage — genuinely low, not just "seems local":
- Requires irreplaceable in-person physical presence (a march, direct action, a physical
  blockade, door-knocking where the door-knock itself IS the ask)
- Requires a specific named personal trust relationship that cannot be proxied — e.g.,
  a union president calling in a 20-year personal favor with a specific politician
- Courtroom work and legal proceedings
- Campaigns where the decisive action is a single private negotiation between two
  specific individuals with a prior relationship

Output for each idea: one sentence naming the specific AI-organizer mechanism,
or "low AI leverage — requires [specific reason]" if it genuinely falls in the low category."""


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

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=4)
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
            tracker.record(response)
            text = response.content[0].text.strip()
            if "```" in text:
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
            _raise_if_credits_error(e)
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
organizing of the constituency), describe the gap concretely.

Coverage score definitions:
0 = Saturated: major orgs already running this exact ask — a new effort adds noise
1 = Crowded: significant coverage exists, gap is narrow or marginal
2 = Gap: coverage exists but clear opening on this specific angle, tactic, or target
3 = Wide open: little to no organized coverage of this specific ask"""


COVERAGE_RESEARCH_MIN_SCORE = 2.0


def _research_one_idea(client: anthropic.Anthropic, idea: CampaignIdea) -> tuple[str, int]:
    """Run a single coverage-research call with web_search. Returns (summary, score)."""

    user_prompt = f"""Research existing organizing coverage for this campaign:

- Target: {idea.target}
- Ask: {idea.ask}
- Issue: {idea.issue_domain}
- Where: {idea.where}
- Theory of leverage: {idea.theory_of_leverage}

Use web search to identify which organizations are actively campaigning on this.

Return a JSON object with two fields:
{{
  "score": <0-3 integer using the scale in your instructions>,
  "summary": "<ONE paragraph ≤120 words covering: the 2-4 most relevant existing orgs and what they are doing, and specifically what gap a new small AI-augmented team could fill — or state plainly that no meaningful gap exists>"
}}

Return ONLY the JSON object, no other text."""

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
    tracker.record(response)

    text_parts = [
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    ]
    raw = " ".join(p.strip() for p in text_parts if p.strip())

    try:
        text = raw.strip()
        # Model sometimes prepends prose before the code block
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        data = json.loads(text)
        return data.get("summary", raw), int(data.get("score", -1))
    except (json.JSONDecodeError, ValueError):
        return raw, -1


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

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=4)
    n = len(eligible)
    print(f"  Coverage research: running web_search on {n} ideas (score ≥ {COVERAGE_RESEARCH_MIN_SCORE})...")

    def _research_one(item):
        i, idea = item
        print(f"    [{i}/{n}] {idea.headline[:70]}")
        try:
            summary, score = _research_one_idea(client, idea)
            idea.existing_coverage = summary if summary else "research failed (empty response)"
            idea.coverage_score = score if score >= 0 else None
        except (anthropic.APIError, anthropic.APIStatusError) as e:
            _raise_if_credits_error(e)
            print(f"      Warning: research failed ({type(e).__name__}: {e})")
            idea.existing_coverage = "research failed"
            idea.coverage_score = None
        except Exception as e:
            print(f"      Warning: research failed ({type(e).__name__}: {e})")
            idea.existing_coverage = "research failed"
            idea.coverage_score = None

    max_workers = min(3, n)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_research_one, item): item for item in enumerate(eligible, 1)}
        for future in as_completed(futures):
            future.result()

    return ideas
