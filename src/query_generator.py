"""
Dynamic Query Generator — uses AI to generate Google News search queries
based on broad search categories and current news context.

Replaces the hardcoded GOOGLE_NEWS_QUERIES for broad search while keeping
the existing RSS feeds and any targeted queries as baseline inputs.
"""

import json
from datetime import datetime

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL


# =============================================================================
# Search categories — the AI generates queries for each
# =============================================================================

# Always searched
CORE_CATEGORIES = [
    {
        "name": "National news — biggest stories",
        "description": "The 3-5 biggest national news stories right now. Focus on stories with identifiable actors, decisions, and pressure points — not just commentary.",
    },
    {
        "name": "Republican dissent and cracks",
        "description": "Republicans breaking ranks, retiring, criticizing Trump or party leadership, internal party conflict. Elected officials, donors, operatives, military/intelligence figures.",
    },
    {
        "name": "Corporate accountability",
        "description": "Companies facing pressure from consumers, employees, or regulators. Federal contracts under scrutiny. Corporate complicity in government overreach. Boycotts and consumer campaigns.",
    },
    {
        "name": "War, defense, and profiteering",
        "description": "Defense contracts, arms sales, war authorization debates, military spending, profiteering, veterans opposing military actions. Companies making money from conflict.",
    },
    {
        "name": "State and local resistance",
        "description": "Governors, AGs, mayors, city councils, school boards taking action to resist or protect against federal overreach. Sanctuary policies, executive orders, lawsuits, ordinances.",
    },
    {
        "name": "Immigration enforcement and ICE",
        "description": "ICE operations, detention facilities, sanctuary policies, local cooperation or resistance, court challenges, community defense efforts.",
    },
]

# Rotated — pick 2-3 per run to keep breadth without overwhelming
ROTATING_CATEGORIES = [
    {
        "name": "Housing, rent, and economic justice",
        "description": "Rent-fixing algorithms, eviction crises, housing policy, wage theft, gig economy, economic hardship from tariffs or policy changes.",
    },
    {
        "name": "Labor and workers",
        "description": "Strikes, union organizing, walkouts, worker resistance, labor board decisions, gig worker fights, federal workforce impacts from DOGE.",
    },
    {
        "name": "Religion and faith communities",
        "description": "Faith leaders speaking out, church-state conflicts, religious institutions taking political stances, faith-based organizing, Catholic/evangelical dynamics.",
    },
    {
        "name": "Police, surveillance, and criminal justice",
        "description": "Police accountability, surveillance technology contracts, criminal justice reform, local police cooperating with or resisting federal agencies.",
    },
    {
        "name": "Tech, AI, and surveillance",
        "description": "Tech company accountability, AI regulation, data centers, government surveillance, social media censorship, digital rights.",
    },
    {
        "name": "Education",
        "description": "School funding cuts, book bans, university funding threats, student organizing, teacher actions, school board fights.",
    },
    {
        "name": "Health and reproductive rights",
        "description": "ACA/healthcare access, reproductive rights, maternal health, drug pricing, hospital accountability, public health threats.",
    },
    {
        "name": "Climate and environment",
        "description": "Environmental rollbacks, local climate action, pipeline fights, corporate pollution, renewable energy battles, environmental justice.",
    },
    {
        "name": "Voting rights and elections",
        "description": "Voter suppression, election administration, redistricting, ballot access, election security, polling place intimidation.",
    },
    {
        "name": "Press freedom and information",
        "description": "Attacks on journalism, FOIA fights, government transparency, whistleblower protection, information access.",
    },
]

QUERY_GENERATION_PROMPT = """You are helping a campaign scanner find today's news stories that could become grassroots campaign opportunities.

The following queries already run as a fixed static set every day. Do NOT generate queries that are near-duplicates of these — you would just be wasting a Google News request on something already covered. Instead, prefer queries that either:
  (a) target a SPECIFIC current event you know is happening right now (named people, specific pending decisions, recent developments from the last 1-2 weeks), OR
  (b) explore angles, constituencies, or decision-maker types that the static set does not cover.

Static queries already running:
{static_queries_list}

For each search category below, generate 2-3 Google News search queries that would surface relevant stories from the last 48 hours. The queries should:

1. Be specific enough to find actionable stories (not just commentary)
2. Include current names, places, and events — you know what's in the news right now
3. Target stories where there's a specific actor, decision, or pressure point
4. Use terms that Google News RSS would match well (news headline language, not academic)
5. Include the current month and year to bias toward recent results

Search categories:
{categories_text}

Respond with a JSON object where each key is the category name and the value is a list of 2-3 search query strings.

Example format:
```json
{{
  "War, defense, and profiteering": [
    "defense contractor stock price Iran war authorization April 2026",
    "Lockheed Raytheon contract Pentagon audit 2026",
    "veterans oppose military action Iran 2026"
  ],
  "Republican dissent and cracks": [
    "Republican senator criticize Trump Iran April 2026",
    "GOP donor withdraw support 2026"
  ]
}}
```

IMPORTANT: Return ONLY the JSON object, no other text."""


def select_categories(num_rotating: int = 3) -> list[dict]:
    """Select all core categories plus a rotating subset of extras."""
    import random
    rotating = random.sample(ROTATING_CATEGORIES, min(num_rotating, len(ROTATING_CATEGORIES)))
    selected = CORE_CATEGORIES + rotating

    print(f"  Search categories ({len(selected)}):")
    for cat in selected:
        marker = "*" if cat in ROTATING_CATEGORIES else " "
        print(f"    {marker} {cat['name']}")

    return selected


def generate_queries(categories: list[dict] = None) -> dict[str, list[str]]:
    """Use AI to generate Google News search queries for each category.

    Returns a dict mapping category name -> list of query strings.
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set.")

    if categories is None:
        categories = select_categories()

    categories_text = ""
    for cat in categories:
        categories_text += f"\n**{cat['name']}**: {cat['description']}\n"

    from config import GOOGLE_NEWS_QUERIES
    static_queries_list = "\n".join(f"- {q}" for q in GOOGLE_NEWS_QUERIES)

    now = datetime.now()
    prompt = QUERY_GENERATION_PROMPT.replace("{categories_text}", categories_text)
    prompt = prompt.replace("{static_queries_list}", static_queries_list)
    # Inject current date context
    prompt = f"Today is {now.strftime('%B %d, %Y')}.\n\n" + prompt

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        queries = json.loads(text)

        total = sum(len(v) for v in queries.values())
        print(f"  Generated {total} search queries across {len(queries)} categories")

        return queries

    except (json.JSONDecodeError, anthropic.APIError) as e:
        print(f"  Warning: Query generation failed ({e}), using fallback queries")
        return _fallback_queries()


def _fallback_queries() -> dict[str, list[str]]:
    """Minimal fallback if dynamic generation fails."""
    now = datetime.now()
    month_year = now.strftime("%B %Y")
    return {
        "National news": [
            f"breaking news politics {month_year}",
            f"federal government controversy {month_year}",
        ],
        "State and local resistance": [
            f"governor attorney general resist federal {month_year}",
            f"city council sanctuary ordinance {month_year}",
        ],
        "Corporate accountability": [
            f"boycott company federal contract controversy {month_year}",
        ],
        "War and defense": [
            f"defense spending war authorization {month_year}",
            f"military veterans oppose {month_year}",
        ],
    }
