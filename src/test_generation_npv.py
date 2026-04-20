#!/usr/bin/env python3
"""
Test generation against a synthetic VA NPV article to validate:
1. Sonnet 4.6 works for generation
2. web_search tool integration works
3. New "next vulnerable state" prompt produces a better NPV idea
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import anthropic
from models import Article
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from idea_generator import create_generation_prompt


# Synthetic article approximating the one that produced the weak NPV idea
ARTICLE = Article(
    title="Virginia joins National Popular Vote compact, bringing total to 222 electoral votes",
    url="https://www.theguardian.com/us-news/2026/apr/14/majority-vote-for-president-us-constitution",
    source="The Guardian US",
    published=datetime(2026, 4, 14, tzinfo=timezone.utc),
    content="""Virginia has become the latest state to join the National Popular Vote Interstate
Compact, an agreement among US states to award their electoral votes to the winner of the
national popular vote. With Virginia's 13 electoral votes, the compact now has commitments
from states representing 222 electoral votes, just 48 short of the 270 needed to take effect.

The compact would only activate once enough states signed on to guarantee the presidency to
the popular-vote winner. Supporters argue it preserves the Electoral College's structure while
ensuring the president is chosen by majority vote.

Analysts note that several other states are considering legislation to join the compact,
including Michigan, Wisconsin, Pennsylvania, and Arizona, though political dynamics in each
state vary significantly. Michigan currently has a Democratic trifecta, but that could change
in 2026 elections.""",
)


def main():
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = create_generation_prompt([ARTICLE])

    print(f"Model: {CLAUDE_MODEL}")
    print(f"Article: {ARTICLE.title}")
    print(f"Calling generation with web_search enabled...\n")

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 5,
        }],
        messages=[{"role": "user", "content": prompt}],
    )

    # Count tool uses
    tool_uses = [b for b in response.content if getattr(b, "type", None) == "server_tool_use"]
    tool_results = [b for b in response.content if getattr(b, "type", None) == "web_search_tool_result"]
    text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]

    print(f"Content blocks: {len(response.content)}")
    print(f"  Tool uses (searches): {len(tool_uses)}")
    print(f"  Tool results: {len(tool_results)}")
    print(f"  Text blocks: {len(text_blocks)}")

    for i, tu in enumerate(tool_uses, 1):
        query = getattr(tu, "input", {}).get("query", "?") if hasattr(tu, "input") else "?"
        print(f"  Search {i}: {query}")

    # Parse the final JSON
    final_text = (text_blocks[-1] if text_blocks else "").strip()
    if final_text.startswith("```"):
        final_text = final_text.split("```")[1]
        if final_text.startswith("json"):
            final_text = final_text[4:]
        final_text = final_text.strip()

    print(f"\n{'='*80}\nGENERATED IDEAS:\n{'='*80}")
    try:
        ideas = json.loads(final_text)
        for i, idea in enumerate(ideas, 1):
            print(f"\n--- Idea {i} ---")
            print(f"Headline:       {idea.get('headline','')}")
            print(f"Target:         {idea.get('target','')}")
            print(f"Ask:            {idea.get('ask','')}")
            print(f"Constituency:   {idea.get('constituency','')}")
            print(f"Leverage:       {idea.get('theory_of_leverage','')}")
            print(f"Where:          {idea.get('where','')}")
            print(f"Time:           {idea.get('time_sensitivity','')}")
            print(f"Gates:          target={idea.get('gate_named_target')} ask={idea.get('gate_binary_ask')} win={idea.get('gate_time_window')}")
            print(f"Dims:           choir={idea.get('score_beyond_choir')} pressure={idea.get('score_pressure_point')} antiAuth={idea.get('score_anti_authoritarian')} repl={idea.get('score_replication')} win={idea.get('score_winnability')}")
    except json.JSONDecodeError as e:
        print(f"JSON parse failed: {e}")
        print(f"Raw final text:\n{final_text[:2000]}")


if __name__ == "__main__":
    main()
