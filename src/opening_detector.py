"""
Opening Detector - Uses Claude API to identify campaign openings from articles.
This is the core AI processing layer, built around Framework #1 criteria.
"""

import json
import anthropic

from models import Article, Opening
from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    BATCH_SIZE,
    OPENING_CATEGORIES,
    ISSUE_DOMAINS,
)


# =============================================================================
# Framework #1 Criteria - embedded in the AI prompt
# =============================================================================

OPENING_DETECTION_CRITERIA = """
## What You're Looking For: Campaign Openings

An "opening" is raw material for a potential campaign — something that has happened,
exists, or is emerging that a strategist could look at and say "there's something there."
These are OPENINGS, not campaigns.

### An opening has these characteristics:
1. **Something concrete happened** — an action, statement, policy, event, or pattern (not just commentary)
2. **It suggests a replicable or extendable action** — others could do it, or it could be pushed further
3. **No one is systematically working that angle yet** — it's not owned, not saturated, not organized
4. **There's a plausible theory of change** — you can imagine who would be asked to do what

### What DISQUALIFIES something as an opening:
- It's already a well-known campaign (organized groups are already pressuring that target on that ask)
- The moment has clearly passed (news cycle moved on, decision was made, leverage is gone)
- It's saturated (everyone already knows, no new energy to mobilize)
- It's just commentary or analysis, not an action or event
- It's describing an existing network ("Tesla Takedown exists" = not an opening)
- It requires ground presence in a crisis zone (we need things people ELSEWHERE can act on)

### Categories of Openings (assign ONE):

1. **Actions That Could Be Replicated**
   Executive actions (governors, AGs, mayors), institutional actions (school districts,
   universities, hospitals, churches, unions, libraries), business actions, individual actions.
   Key question: Who did something good that someone else hasn't done yet but could?

2. **Cracks and Fissures**
   Law enforcement breaks, political breaks (Republicans criticizing Trump, officials
   breaking ranks), institutional dissent (employees speaking out, resignations),
   unexpected voices (business leaders, military/veterans, religious leaders).
   Key question: Is someone breaking from the expected alignment?

3. **Gaps and Absences**
   Things that should exist but don't (model legislation not yet adopted, coordination
   mechanisms not yet built, mutual aid gaps, legal defense gaps), actors who haven't
   been activated, missing connections between natural allies.
   Key question: What's missing that could be created?

4. **Pending Decisions and Leverage Points**
   Upcoming decisions (contract renewals, legislation being debated, court cases,
   elections, budget decisions), supply chains and complicity networks,
   regulatory moments (comment periods, permit applications, public hearings).
   Key question: Where is there a decision coming that could be influenced?

5. **Emerging Patterns (Uncoordinated Energy)**
   Spontaneous activity that could be organized, protests without coordination,
   social media trends becoming real-world action, informal mutual aid networks,
   shifts in public opinion or behavior (boycotts, changing civic participation).
   Key question: Where is there energy without infrastructure?

6. **Outrages and Galvanizing Events**
   Federal overreach incidents, corporate actions, sympathetic victims/stories,
   shocking revelations, viral moments. NOTE: Only an opening if there's an
   actionable response that isn't already saturated.
   Key question: Is there an ask that channels this energy?

7. **Defensive Needs**
   Anticipated federal actions, state-level attacks, corporate threats,
   legal threats to existing protections.
   Key question: What's coming that people could get ahead of?

### Issue Domains (assign ONE):
""" + "\n".join(f"- {d}" for d in ISSUE_DOMAINS) + """

### Quality Control - Before identifying an opening, verify:
- Is this an action/event, not just commentary?
- Is it specific enough to be replicable?
- Is it NOT already the focus of an organized campaign?
- Could someone outside the original location act on it?
- Is there a clear "who could be asked to do what"?
"""


def create_detection_prompt(articles: list[Article]) -> str:
    """Create the prompt for detecting campaign openings in a batch of articles."""

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

    prompt = f"""You are a campaign strategist scanning news and social media for
campaign openings — raw material that could form the basis for a pro-democracy,
anti-authoritarian grassroots campaign.

{OPENING_DETECTION_CRITERIA}

## Articles to Scan:
{articles_text}

## Instructions:
1. Read each article carefully
2. Identify any campaign OPENINGS (not just interesting news — openings per the criteria above)
3. For each opening found, provide ALL of the following fields
4. Be selective — most articles will NOT contain openings. That's fine.
5. An article might contain multiple openings, or none.
6. If similar openings appear in multiple articles, pick the best source and consolidate.

Respond with a JSON array. For each opening:
```json
[
  {{
    "article_index": 1,
    "what_happened": "Concrete, specific description of what happened",
    "who": "Specific actor (name, title, institution)",
    "when": "Date or timeframe",
    "where": "Location (city, state, or national)",
    "issue_domain": "One of the issue domains listed above",
    "category": "One of the 7 opening categories listed above",
    "replication_potential": "Who else could do this? Where? How many potential targets?",
    "campaign_status": "Is anyone already systematically working this angle? If so, who?",
    "time_sensitivity": "Is there a window? When does it close? Or is this ongoing?",
    "raw_material_note": "1-2 sentences on why this is an opening and what a campaign might look like",
    "priority": 4
  }}
]
```

Priority scale:
- 5: Exceptional opening (high replication potential + clear theory of change + timely)
- 4: Strong opening (most criteria met, actionable)
- 3: Solid opening (worth considering, some constraints)
- 2: Marginal opening (interesting but significant barriers)
- 1: Weak opening (barely meets criteria but worth noting)

If NO openings are found in this batch, return an empty array: []

IMPORTANT: Return ONLY the JSON array, no other text."""

    return prompt


def create_dedup_prompt(openings: list[Opening]) -> str:
    """Create prompt for deduplicating openings across batches."""

    items_text = ""
    for i, opening in enumerate(openings):
        items_text += f"""
---
OPENING {i+1}:
What happened: {opening.what_happened}
Who: {opening.who}
Where: {opening.where}
Category: {opening.category}
Issue: {opening.issue_domain}
Sources: {opening.source_url}
---
"""

    prompt = f"""You are helping deduplicate a list of campaign openings. Below are {len(openings)} openings
that were identified from different news sources.

Your task: Identify openings that describe the SAME underlying event or action
(not just the same topic or issue domain).

{items_text}

## Instructions:
Return a JSON array where each element represents a unique opening.
- For unique openings: include just the index
- For duplicates: include all indices that should be merged, and note which one has the best detail

Format:
```json
[
  {{"indices": [1], "keep": 1}},
  {{"indices": [2, 5, 8], "keep": 5}},
  {{"indices": [3], "keep": 3}}
]
```

Rules:
- Only merge openings about the SAME specific event/action
- Different actions by different actors on the same topic = KEEP SEPARATE
- Same action reported by different sources = MERGE
- Every opening index must appear exactly once

IMPORTANT: Return ONLY the JSON array, no other text."""

    return prompt


def _parse_json_response(response_text: str) -> list:
    """Parse JSON from Claude response, handling markdown code blocks."""
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def detect_openings(articles: list[Article]) -> list[Opening]:
    """
    Process articles through Claude to identify campaign openings.
    Handles batching, parsing, and within-batch dedup.
    """
    if not articles:
        return []

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    all_openings = []

    # Process in batches
    total_batches = (len(articles) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(0, len(articles), BATCH_SIZE):
        batch = articles[batch_num:batch_num + BATCH_SIZE]
        batch_idx = batch_num // BATCH_SIZE + 1
        print(f"  Processing batch {batch_idx}/{total_batches} ({len(batch)} articles)...")

        prompt = create_detection_prompt(batch)

        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()
            results = _parse_json_response(response_text)

            batch_openings = 0
            for item in results:
                idx = item.get("article_index", 0) - 1
                if 0 <= idx < len(batch):
                    article = batch[idx]
                    opening = Opening(
                        what_happened=item.get("what_happened", ""),
                        who=item.get("who", ""),
                        when=item.get("when", ""),
                        where=item.get("where", ""),
                        source_url=article.url,
                        source_name=article.source,
                        issue_domain=item.get("issue_domain", ""),
                        category=item.get("category", ""),
                        replication_potential=item.get("replication_potential", ""),
                        campaign_status=item.get("campaign_status", ""),
                        time_sensitivity=item.get("time_sensitivity", ""),
                        raw_material_note=item.get("raw_material_note", ""),
                        priority=item.get("priority", 3),
                    )
                    all_openings.append(opening)
                    batch_openings += 1

            print(f"    Found {batch_openings} openings in this batch")

        except json.JSONDecodeError as e:
            print(f"    Warning: Failed to parse AI response: {e}")
            print(f"    Response was: {response_text[:500]}...")
        except anthropic.APIError as e:
            print(f"    API error: {e}")

    print(f"\n  Total openings before dedup: {len(all_openings)}")

    # Cross-batch deduplication
    if len(all_openings) > 1:
        print("  Running cross-batch deduplication...")
        all_openings = deduplicate_openings(all_openings, client)

    # Sort by priority
    all_openings.sort(key=lambda o: o.priority, reverse=True)

    return all_openings


def deduplicate_openings(openings: list[Opening], client: anthropic.Anthropic) -> list[Opening]:
    """Use Claude to identify and merge duplicate openings."""

    if len(openings) <= 1:
        return openings

    # If the list is very long, process in chunks to stay within token limits
    if len(openings) > 80:
        return _deduplicate_in_chunks(openings, client)

    prompt = create_dedup_prompt(openings)

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

            # Convert to 0-based
            indices = [i - 1 for i in indices]
            valid_indices = [i for i in indices if 0 <= i < len(openings)]
            if not valid_indices:
                continue

            keep_idx = instruction.get("keep", indices[0] + 1) - 1
            if keep_idx not in valid_indices:
                keep_idx = valid_indices[0]

            base = openings[keep_idx]

            # Merge additional source URLs from duplicates
            additional = list(base.additional_sources)
            highest_priority = base.priority
            for idx in valid_indices:
                if idx != keep_idx:
                    other = openings[idx]
                    if other.source_url not in additional and other.source_url != base.source_url:
                        additional.append(other.source_url)
                    highest_priority = max(highest_priority, other.priority)

            base.additional_sources = additional
            base.priority = highest_priority
            deduplicated.append(base)

        removed = len(openings) - len(deduplicated)
        if removed > 0:
            print(f"    Dedup: {len(openings)} → {len(deduplicated)} (merged {removed} duplicates)")

        return deduplicated

    except (json.JSONDecodeError, anthropic.APIError) as e:
        print(f"    Warning: Deduplication failed ({e}), keeping all openings")
        return openings


def _deduplicate_in_chunks(openings: list[Opening], client: anthropic.Anthropic, max_passes: int = 5) -> list[Opening]:
    """Deduplicate a large list by processing in chunks, then deduping the results."""
    chunk_size = 60
    current = openings

    for pass_num in range(max_passes):
        first_pass = []
        for i in range(0, len(current), chunk_size):
            chunk = current[i:i + chunk_size]
            print(f"    Dedup chunk {i//chunk_size + 1} ({len(chunk)} openings)...")
            deduped_chunk = deduplicate_openings(chunk, client)
            first_pass.extend(deduped_chunk)

        removed = len(current) - len(first_pass)
        print(f"    Pass {pass_num + 1}: {len(current)} → {len(first_pass)} ({removed} duplicates removed)")

        if removed == 0 or len(first_pass) <= 80:
            break

        print(f"    Another dedup pass ({len(first_pass)} openings)...")
        current = first_pass

    if len(first_pass) > 1 and len(first_pass) <= 80:
        print(f"    Final dedup pass ({len(first_pass)} openings)...")
        return deduplicate_openings(first_pass, client)

    return first_pass


if __name__ == "__main__":
    # Test with a small set of sample articles
    test_articles = [
        Article(
            title="Oregon Governor Signs Executive Order Protecting Immigrants",
            url="https://example.com/1",
            source="Test Source",
            published=__import__('datetime').datetime.now(__import__('datetime').timezone.utc),
            content="Oregon Governor Tina Kotek signed an executive order limiting state cooperation with federal immigration enforcement...",
            source_type="rss",
        ),
    ]

    print("Testing opening detector with sample article...")
    openings = detect_openings(test_articles)
    for o in openings:
        print(f"\n  [{o.priority}] {o.what_happened}")
        print(f"      Category: {o.category}")
        print(f"      Replication: {o.replication_potential}")
