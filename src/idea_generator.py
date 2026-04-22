"""
Campaign Idea Generator — searches news, generates campaign ideas with
target/ask/constituency/leverage, scores them against a two-stage rubric,
then self-critiques and adjusts.

Replaces the old opening_detector.py.
"""

import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

from models import Article, CampaignIdea


def _raise_if_credits_error(e: Exception) -> None:
    if isinstance(e, anthropic.APIStatusError) and "credit balance" in str(e).lower():
        raise SystemExit(f"\nFATAL: Anthropic credits exhausted — add credits at console.anthropic.com then rerun.\n({e})")
from cost_tracker import tracker
from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    BATCH_SIZE,
    DATA_DIR,
    OPENING_CATEGORIES,
    ISSUE_DOMAINS,
)


# =============================================================================
# Campaign Idea Generation Prompt
# =============================================================================

IDEA_GENERATION_CRITERIA = """

# Your Role

You are a pro-democracy creative campaign strategist whose job is to fight
authoritarianism. You're scanning news to generate grassroots campaign IDEAS —
concrete campaign proposals with a target, an ask, a constituency, and a
theory of leverage.

If a news item doesn't suggest all four, it's not a campaign idea yet —
it might be a Watch List signal.

Your strategic framework has three modes (the 3Ds):

- **Delegitimate**: Undermine the regime's authority, competence, or moral
  standing — in the eyes of its own supporters, not just opponents. This
  includes exposing hypocrisy and broken promises, but also humor, mockery,
  and spectacle that make the regime look ridiculous rather than frightening.
  (e.g., MAHA supporters confronting the Monsanto reversal — using the base's
  own values against the regime; town hall confrontations that go viral and
  shift the narrative from "strong leader" to "can't face constituents")

- **Induce Defections**: Split people or institutions away from the authoritarian
  coalition. Three levels — all count:
  - *Speaking*: Getting someone to publicly oppose (e.g., Naval Academy alumni
    signing a letter rejecting censorship)
  - *Acting*: Getting an institution to actively participate in opposition
    (e.g., Tesla investors pressuring Musk to leave DOGE)
  - *Standing in the Way*: Supporting people in refusing to cooperate
    (e.g., California school districts refusing to dismantle DEI programs,
    federal workers slowing DOGE implementation)

- **Delay and Defend**: Throw sand in the gears. Protect people, institutions,
  or rights under active attack. Get ahead of attacks before they fully land.
  Disincentivize capitulation — make it easier for institutions under pressure
  to keep resisting than to fold. (e.g., rallying alumni support for universities
  resisting federal threats; organizing customers behind companies facing
  regulatory retaliation; legal challenges that buy time for organizing)

Every strong campaign idea maps to at least one of these. If it doesn't,
it's probably commentary, not a campaign.

## How to Design a Strong Campaign Idea

### Target
- Name a specific person or institution, not a class. Not "city councils" —
  "Oakland County Board of Commissioners."
- Map their pressure points. Targets can be vulnerable to different kinds
  of pressure:
  - *Economic*: their customers, donors, investors, or revenue stream
  - *Political*: their voters, party leadership, or re-election prospects
  - *Institutional*: their board, regulator, accreditor, or funder
  - *Social*: their reputation, peer standing, or public legitimacy
  Sometimes that means going through an intermediary (advertisers, not the
  platform). Sometimes it means pressuring the target directly with a
  constituency whose opinion they can't afford to ignore.
- For state-level wins, name the next vulnerable state and decision-maker,
  not "holdout states." Pick by: live bill, closing window, named person
  who could deliver.
- Prefer campaigns that work in many places. Name the best FIRST target to
  make it concrete, then note how many other places the same campaign could
  run. A one-off situation unique to a single city is rarely worth pursuing
  unless the stakes are extraordinary.

### Ask
- One sentence, binary. "Revoke the permit." "Suspend the contract."
  If you can't force it into one sentence, it's not a campaign yet.

### Constituency
- Who has self-interest AND leverage over this specific target? Sometimes
  it's the obvious group — federal workers fighting cuts to their own
  agencies. But sometimes the most powerful constituency isn't the first one
  you think of. A tariff story might be about consumers, but small business
  owners have more leverage and are harder for a Republican target to dismiss.
- The strongest campaigns pair a constituency that cares with a target that
  has to listen to them specifically.


### Theory of leverage
- Why would the target cave? Trace a single chain: this constituency takes
  this action, which costs the target this thing they care about. If you
  need two different constituencies pressuring two different targets, that's
  two campaign ideas, not one.
- If the target can shrug it off, it's not a real pressure point.
- Is there a non-cooperation angle? Boycotts, strikes, refusal, slow-downs.
  Campaigns where people withdraw something the target depends on are often
  stronger than campaigns where people ask for something.
- Is the regime attacking someone whose natural allies haven't mobilized yet?
  Defense campaigns work best when you arrive before the crisis peaks.

### Check yourself
- Energy potential: do people care deeply about this AND is there an intuitive
  avenue for action? High anger + no obvious lever = not a campaign.

## Categories of Openings (assign ONE):

1. **Actions That Could Be Replicated**
   Key question: Who did something good that someone else hasn't done yet
   but could?

2. **Cracks and Fissures**
   Key question: Is someone breaking from the expected alignment? Is there
   a way to split someone off the MAGA coalition or wedge two factions
   against each other?

3. **Pending Decisions and Leverage Points**
   Key question: Where is there a decision coming that could be influenced?

4. **Energy Without a Campaign**
   Key question: People are angry or mobilizing — is there a specific target
   and ask that could channel it? This could be a sudden outrage (a galvanizing
   event) or a slow build (scattered local actions, rising public frustration
   with no focal point).

5. **Defensive Needs**
   Key question: What's coming that people could get ahead of? Is the regime
   attacking a group whose allies haven't mobilized yet?

## Issue Domains (assign ONE):
""" + "\n".join(f"- {d}" for d in ISSUE_DOMAINS) + """

## What DISQUALIFIES something:
- It's already a well-known, organized campaign (saturated)
- The moment has clearly passed
- It's just commentary or analysis, not an action or event
- You can't name a specific target, ask, and constituency
- High anger but no intuitive avenue for action (energy without a lever)

## Selectivity
- Most articles will NOT produce campaign ideas. That's fine — skip them
  entirely rather than forcing a weak idea.
- A strong article might suggest multiple campaign ideas with different
  targets or different theories of leverage. Generate them separately —
  each idea needs its own complete target/ask/constituency/leverage chain.
- Quantity is not the goal. A batch of 20 articles might yield 2 ideas
  or 10. Both are fine. Zero weak ideas is better than five mediocre ones.
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

## Tools available (use sparingly):

You have `web_search`. Use it ONLY when you need specific facts you don't have, and
those facts would change the campaign design:

- For state-level political events, identify the next vulnerable state — which state
  has a live bill on the same topic, which has a Dem/Rep trifecta with a closing
  window, who chairs the relevant committee. This matters when the news is "State X
  just passed Y" and you need to name the next target state.
- To name a specific legislator, sheriff, AG, mayor, or official by name when the
  article references them only by title ("the Michigan Senate Majority Leader").
- To verify whether a campaign or policy window is still open.

Do NOT search for background context, explanations, or anything that doesn't
directly affect target/ask/constituency/leverage. Budget is tight — prefer to
skip generating a campaign idea over burning searches on nice-to-have context.

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
    "category": "One of the 5 categories listed above",
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
    "score_energy_potential": 3,
    "score_non_compliance": 1,
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
2 = Specific named target with clear authority (a sheriff, mayor, CEO, state AG,
    zoning board, specific company)
1 = Target identifiable but less direct (a class of actors like "city councils,"
    a state agency)
0 = No named target, or target is unreachable ("the Trump administration,"
    "Congress," "public opinion"). Also 0 if the "target" is actually an ally
    being encouraged to do more.

GATE 2 — Specific, Binary Ask
2 = Clear binary ask ("revoke the permit," "suspend the contract," "pass the
    moratorium")
1 = Ask identifiable but less crisp ("adopt a version of this policy")
0 = No specific ask ("raise awareness," "hold accountable"). Also 0 if the ask
    requires multiple steps from multiple actors with no single decision point.

GATE 3 — Time Window Still Open
This is a simple open/closed check. Don't penalize longer windows — a campaign
with 6 months of runway is more viable than one with 2 weeks, not less.
1 = Window is open. The decision hasn't been made, the leverage still exists, and
    there's enough time to realistically organize (at least 2-3 weeks).
0 = Window is essentially closed. Decision already made, leverage gone, or the
    moment will have passed before anyone could realistically act.

### STAGE 2: Scoring Dimensions (0-4 each)

Only score if ALL gates passed (all scored 1+). If any gate = 0, leave these as 0.

DIMENSION 1 — Beyond-the-Choir Constituency (weight: 10%)
0 = Only mobilizes already-activated progressives
1 = Constituency exists in theory but requires significant persuasion
2 = Clear non-progressive constituency with identifiable self-interest
3 = Strong beyond-the-choir constituency already showing signs of engagement
4 = The beyond-the-choir angle IS the story — the powerful constituency is
    definitionally not the progressive base

DIMENSION 2 — Actionable Pressure Point (weight: 25%)
0 = Target has no reason to care about this constituency's pressure
1 = Target could theoretically be pressured but no clear mechanism
2 = Clear mechanism exists but target can probably wait it out
3 = Target faces concrete, near-term consequences from this specific constituency
4 = Target is already showing signs of vulnerability — cracking, wavering,
    making defensive moves

DIMENSION 3 — Anti-Authoritarian Impact (weight: 25%)
Score on whichever pathway applies. Use the 3Ds lens: does this campaign
delegitimize the regime, induce defections from its coalition, or delay and
defend against its attacks?

0 = No anti-authoritarian connection. Generic corporate accountability,
    environmental, housing, consumer, or infrastructure issues with no link
    to authoritarian politics or the coalition behind it.
1 = Tangential connection — corporate actor enables authoritarianism indirectly
    OR campaign addresses an issue where the beyond-choir constituency has mild
    anti-authoritarian tilt but swinging them isn't the point.
2 = Direct link to government authoritarian power (ICE, DOJ political
    prosecutions, voter suppression) OR corporate actor explicitly supporting
    authoritarian politics OR campaign that demonstrably swings a key
    constituency whose realignment meaningfully erodes the authoritarian
    coalition.
3 = Directly targets an institutional pillar of support (military, business,
    faith communities, law enforcement, civil service, media) OR drives a
    deep wedge into a major constituency at a moment of visible fracture.
    Maps clearly to at least one D.
4 = Structurally weakens authoritarian power by fracturing a major pillar at
    a moment of visible, accelerating crack — AND the campaign design
    explicitly aims to induce defections or delegitimize the regime, not just
    win a policy outcome.

DIMENSION 4 — Replication Potential (weight: 15%)
Two patterns count: (1) a template for independent local campaigns that can
run in many places (like Indivisible chapters or warrant-only sanctuary
resolutions), and (2) a national campaign with local tactics that could take
root in lots of places (like a coordinated boycott with local actions).

0 = One-off situation, unique to this specific context.
1 = Could theoretically happen elsewhere with significant adaptation.
2 = Same dynamic exists in multiple places but no clear template yet.
3 = Template exists or could be easily created, applicable in 10+ locations.
4 = Template already proven AND applicable in dozens or hundreds of locations.

DIMENSION 5 — Winnability (weight: 10%)
Score on whether this campaign can win given the target's incentives, the
constituency's leverage, AND whether credible messengers exist to activate
that constituency.

0 = Target has no real incentive to cave, no comparable wins, or no credible
    messengers exist to reach the constituency.
1 = Campaigns like this have tried but rarely won — target can outlast
    pressure, OR constituency is real but no clear path to messenger access.
2 = Mixed track record — some comparable wins, target has some skin in the
    game, messenger access possible but requires groundwork.
3 = Clear precedent, target meaningfully vulnerable, credible messengers
    either exist or are readily recruitable.
4 = Target acutely vulnerable, proven playbook, constituency already
    mobilized, credible messengers already in the room.

DIMENSION 6 — Energy Potential (weight: 10%)
Will this campaign spread on its own once started? Score on whether the
conditions exist for rapid, self-recruiting participation.

0 = No visceral hook. Policy-wonk issue, no clear moral line, action
    requires significant effort or expertise.
1 = People care, but the action is complicated, the moral line is blurry,
    or participation isn't visible enough to recruit others.
2 = Clear moral line and a plausible action, but participation requires
    organized outreach to sustain — it won't spread on its own.
3 = Strong conditions: clear moral line, simple action, visible
    participation. The ingredients are there but it hasn't ignited yet.
4 = Already catching fire or nearly there. People are self-organizing,
    the action is identity-defining (participating says something about
    who you are), and every act of participation is visible enough to
    recruit the next person. The action IS the message.

DIMENSION 7 — Non-Compliance Potential (weight: 5%)
Does this campaign include a theory of non-cooperation — refusing, withdrawing,
or disrupting rather than just asking or symbolically protesting?

0 = Pure symbolic action or petition — no withdrawal of cooperation involved.
1 = Campaign could theoretically include a non-compliance element but it's
    not central to the theory of leverage.
2 = Non-compliance is part of the campaign design but not the primary lever.
3 = Non-compliance IS the primary theory of leverage — the campaign wins by
    withdrawing something the target depends on.
4 = Mass non-cooperation at scale — a strike, coordinated boycott, or
    collective refusal that directly disrupts the target's ability to function.

The system will compute weighted_score from your scores.
Do NOT include weighted_score in your response.

If NO campaign ideas are found in this batch, return an empty array: []

IMPORTANT: Return ONLY the JSON array, no other text."""

    return prompt


    # Old self-critique prompt removed — replaced by critique_agent.py


# =============================================================================
# Score computation
# =============================================================================

def compute_score(idea: CampaignIdea) -> None:
    """Compute watch_list status and weighted_score from gate/dimension scores."""
    if idea.gate_named_target == 0 or idea.gate_binary_ask == 0 or idea.gate_time_window == 0:
        idea.is_watch_list = True
        idea.weighted_score = 0.0
        return

    # D1: 10%, D2: 25%, D3: 25%, D4: 15%, D5: 10%, D6: 10%, D7: 5%
    idea.weighted_score = (
        idea.score_beyond_choir * 0.10
        + idea.score_pressure_point * 0.25
        + idea.score_anti_authoritarian * 0.25
        + idea.score_replication * 0.15
        + idea.score_winnability * 0.10
        + idea.score_energy_potential * 0.10
        + idea.score_non_compliance * 0.05
    )


# =============================================================================
# JSON parsing helper
# =============================================================================

def _parse_json_response(response_text: str):
    """Parse JSON from Claude response, handling markdown code blocks."""
    text = response_text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


# =============================================================================
# Main generation pipeline
# =============================================================================

def _run_batch(client, batch: list[Article], batch_idx: int, total_batches: int):
    """Run one generation batch. Returns (batch_idx, batch, ideas, error_str)."""
    print(f"  Processing batch {batch_idx}/{total_batches} ({len(batch)} articles)...")
    prompt = create_generation_prompt(batch)
    last_error = None
    for attempt in range(2):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=16000,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
                messages=[{"role": "user", "content": prompt}]
            )
            text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
            response_text = (text_blocks[-1] if text_blocks else "").strip()
            tracker.record(response)
            if not response_text:
                last_error = f"empty response (stop_reason={response.stop_reason})"
                print(f"    Batch {batch_idx}: {last_error}{', retrying...' if attempt == 0 else ''}")
                continue
            results = _parse_json_response(response_text)
            ideas = []
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
                        source_query=article.source_query,
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
                        score_energy_potential=item.get("score_energy_potential", 0),
                        score_non_compliance=item.get("score_non_compliance", 0),
                        score_rationale=item.get("score_rationale", ""),
                    )
                    compute_score(idea)
                    ideas.append(idea)
            return batch_idx, batch, ideas, None
        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e}"
            print(f"    Batch {batch_idx}: {last_error}{', retrying...' if attempt == 0 else ''}")
        except anthropic.APIError as e:
            _raise_if_credits_error(e)
            last_error = f"API error: {e}"
            print(f"    Batch {batch_idx}: {last_error}{', retrying...' if attempt == 0 else ''}")
    return batch_idx, batch, [], last_error


def generate_ideas(articles: list[Article], resume_from: "Path | None" = None) -> list[CampaignIdea]:
    """
    Process articles through Claude to generate campaign ideas.
    Two passes: generate+score, then self-critique+adjust.

    resume_from: path to a checkpoint_passN.json file. If provided, skips all
    passes already completed and resumes from the next one.
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=4)

    from output_formatter import write_json as _checkpoint_write
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Determine which pass to start from
    resume_pass = 0  # 0 = start from scratch
    all_ideas = []
    if resume_from is not None:
        name = Path(resume_from).name
        pass_map = {"checkpoint_pass1.json": 1, "checkpoint_pass2.json": 2, "checkpoint_pass3.json": 3}
        resume_pass = pass_map.get(name, 0)
        if resume_pass == 0:
            raise ValueError(f"Unrecognised checkpoint file: {resume_from}")
        print(f"  Resuming from {name} (skipping passes 1–{resume_pass})")
        loaded = json.loads(Path(resume_from).read_text())
        raw_ideas = loaded.get("ideas", loaded) if isinstance(loaded, dict) else loaded
        all_ideas = [CampaignIdea.from_dict(d) for d in raw_ideas]
        print(f"  Loaded {len(all_ideas)} ideas from checkpoint")

    if resume_pass == 0:
        if not articles:
            return []
        # =====================================================================
        # Pass 1: Generate and score campaign ideas (batches run in parallel)
        # =====================================================================
        batches = [articles[i:i + BATCH_SIZE] for i in range(0, len(articles), BATCH_SIZE)]
        total_batches = len(batches)

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(_run_batch, client, batch, idx + 1, total_batches): idx
                for idx, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                batch_idx, batch, ideas, error = future.result()
                if error:
                    print(f"    Warning: batch {batch_idx} failed — {error}")
                else:
                    all_ideas.extend(ideas)
                    print(f"    Batch {batch_idx}: {len(ideas)} campaign ideas")

        scored = [i for i in all_ideas if not i.is_watch_list]
        watch = [i for i in all_ideas if i.is_watch_list]
        print(f"\n  Pass 1 complete: {len(scored)} scored ideas, {len(watch)} watch list")
        print(tracker.summary("Pass 1"))
        _checkpoint_write(all_ideas, str(DATA_DIR / "checkpoint_pass1.json"))
        print(f"  Checkpoint saved → {DATA_DIR / 'checkpoint_pass1.json'}")

    # =========================================================================
    # Pass 2: Critique agent (separate adversarial reviewer)
    # =========================================================================
    if resume_pass < 2:
        scored = [i for i in all_ideas if not i.is_watch_list]
        watch = [i for i in all_ideas if i.is_watch_list]
        if scored:
            from critique_agent import run_critique
            print(f"\n  Running critique agent on {len(scored)} scored ideas...")
            all_ideas = run_critique(scored + watch)
        else:
            all_ideas = scored + watch
        _checkpoint_write(all_ideas, str(DATA_DIR / "checkpoint_pass2.json"))
        print(f"  Checkpoint saved → {DATA_DIR / 'checkpoint_pass2.json'}")
        print(tracker.summary("Pass 2"))

    # =========================================================================
    # Pass 3: AI leverage tagging (isolated from scoring)
    # =========================================================================
    if resume_pass < 3:
        from critique_agent import tag_ai_leverage
        all_ideas = tag_ai_leverage(all_ideas)
        _checkpoint_write(all_ideas, str(DATA_DIR / "checkpoint_pass3.json"))
        print(f"  Checkpoint saved → {DATA_DIR / 'checkpoint_pass3.json'}")
        print(tracker.summary("Pass 3"))

    # =========================================================================
    # Pass 4: Coverage research (web_search on high-scored ideas only)
    # =========================================================================
    from critique_agent import research_coverage
    all_ideas = research_coverage(all_ideas)

    # =========================================================================
    # Sort and return
    # =========================================================================
    scored = [i for i in all_ideas if not i.is_watch_list]
    watch = [i for i in all_ideas if i.is_watch_list]
    scored.sort(key=lambda i: i.weighted_score, reverse=True)
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
            max_tokens=8000,
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
        _raise_if_credits_error(e)
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
