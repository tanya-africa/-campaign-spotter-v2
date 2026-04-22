# Campaign Spotter — Improvement Backlog

## Waiting on 7-day run data before deciding

**Three-run coverage pass**
Run generator 3x on same corpus, merge pools, dedup on target+ask, single critique pass.
Premise needs validation first — run `compare_runs.py` after 7-day finishes (sequence in memory).
Worth building if ≥25% net-new ideas on run 2. Not worth it if <10%.

**Query pruning round 2**
Use per-query idea yield report (new, prints at end of each run) to cut zero-idea queries.
Article yield alone wasn't enough signal — now tracking which queries actually produce ideas.

---

## Small, low-risk — build when there's a moment

**News-aware dynamic query generation**
Currently: Claude generates queries from training knowledge + current date. Can't see yesterday's breaking news.
Static set has the same blind spot — framework bakes in assumptions about which issue areas matter.

Proposed 4-step mechanic:
1. Pull RSS, Bluesky, Gmail first (cheap, no Google rate limiting). Take headlines only (~500-800 from 24h window).
2. Haiku pass: "here are today's headlines — what 8-12 emerging themes fit the shape of a campaign-relevant story?" Shape = named reachable decision-maker facing a binary pending decision where a grassroots constituency could plausibly influence the outcome. Don't specify issue areas.
3. Take those themes, generate Google News queries grounded in what actually happened today.
4. Run queries on top of existing static + framework-dynamic floor.

Key design decision — give Haiku the shape, not the content:
Don't pass it the 7 framework categories (it'll just re-map everything into them). Instead pass the gate criteria (G1 named target, G2 binary ask, G3 time window, grassroots constituency). Those gates are issue-agnostic — a housing fight, a labor action in a new sector, a church taking a stance on Pope-vs-Trump all pass; data center zoning and crypto drama don't (no grassroots leverage over a single decision-maker).

When it matters: days when something breaks that the framework doesn't cover. Housing organizing wave, new category of worker action, religious-right internal fracture — none in static set, current dynamic layer won't catch them either.
When it matters less: stable news cycles (more ICE, more voting rights, more Iran) — current approach is close to news-aware anyway.

Prerequisite diagnostic: **check 7-day idea yield report for category distribution first.** If output is already ranging widely across issue areas, the bottleneck may be the generator prompt or rubric, not the query layer — fixing queries won't help. If output is clustering around a narrow set, this is the right fix.

Pipeline change needed: RSS/Bluesky must complete before Google News queries start. Currently Bluesky runs concurrently with Google News — this breaks that parallelism, adding sequential latency to the fetch phase.

Spot-audit check before shipping: run Haiku on a few days of headlines and verify it's spotting genuinely novel themes, not just recapitulating the framework with different words.

**Gmail/newsletters OAuth verification**
Credentials exist but OAuth flow is untested. Either confirm it works or remove from default pipeline.

---

## Medium — needs design before building

**Reddit pre-filter (Haiku pass)**
Drop memes, commentary, and low-signal Reddit posts before sending to generator.
Hold until after 7-day run gives real data on how much Reddit contributes to final ideas.
If Reddit yield is low relative to its article volume, this becomes a priority cost/quality fix.

**Dynamic queries "diverse ideas" mode**
Prompt later generator runs to find campaigns *different* from earlier runs.
Explicitly out of scope for the three-run coverage pass spec.
Only relevant if three-run mode gets built and temperature variance alone isn't producing enough breadth.

---

## Discussed, not prioritised

**--max-gnews-queries runtime cap**
Simple flag to limit total Google News queries at runtime without editing config.
Low priority now that rate limiting is better managed via backoff + interleave changes.

**News-aware dynamic categories**
Making the rotating categories themselves dynamic (Claude proposes which categories are most active today) is a more ambitious version of the news-aware query generation entry above. Build that first; this is a natural extension.
