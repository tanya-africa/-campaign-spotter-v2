# How the Campaign Opening Scanner Works

This document explains the full pipeline — what it searches, how it filters, and the exact prompts and queries it uses to identify campaign openings.

## Overview

The scanner runs a 5-step pipeline:

1. **Fetch** articles from ~150 sources (RSS feeds, Google News, Gmail newsletters, Reddit, Bluesky)
2. **Deduplicate** by URL and normalized title
3. **Detect openings** by sending articles to Claude AI in batches of 30 with a detailed prompt framework
4. **Deduplicate openings** across batches using a second AI pass
5. **Output** results as JSON, Markdown, and Excel

---

## Step 1: Sources

### National RSS Feeds (14 outlets)

| Outlet | Focus |
|--------|-------|
| NPR Politics | Breaking news, policy |
| The Guardian US | US news, rights |
| Washington Post Politics | Federal politics |
| NYT Politics | Federal politics |
| LA Times Politics | West coast, policy |
| Democracy Docket | Voting rights, legal |
| Just Security | Legal, national security |
| CREW | Ethics, accountability |
| Popular Information | Corporate accountability |
| Talking Points Memo | Politics, investigations |
| The Intercept | Investigations, civil liberties |
| The Atlantic Politics | Analysis, long-form |
| American Prospect | Progressive policy |
| WTFJHT | Daily digest |

### Regional RSS Feeds (22 newspapers)

Strategically selected from swing states and states with active resistance/policy dynamics:

**Swing states:** Arizona Republic, Atlanta Journal-Constitution, Milwaukee Journal Sentinel, Detroit Free Press, Philadelphia Inquirer, Las Vegas Review-Journal, Charlotte Observer, Raleigh News & Observer

**Active resistance/policy states:** Sacramento Bee, SF Chronicle, Minneapolis Star Tribune, Denver Post, Seattle Times, Boston Globe, Chicago Tribune, Portland Oregonian, Albany Times Union

**Interesting dynamics:** Austin American-Statesman, Miami Herald, Columbus Dispatch, Pittsburgh Post-Gazette, St. Louis Post-Dispatch

### Google News RSS Queries (48 queries)

Google News results are fetched via RSS using this URL template:
```
https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en
```

#### Category 1: Actions That Could Be Replicated
```
governor executive order sanctuary immigration 2026
governor executive order protect reproductive rights 2026
attorney general lawsuit federal overreach 2026
attorney general legal challenge Trump administration 2026
mayor city council resolution resist federal 2026
state legislation protect immigrants workers 2026
school district sanctuary resolution immigration 2026
university refuse federal mandate sanctuary 2026
hospital refuse comply federal reporting 2026
church sanctuary immigration denomination 2026
union solidarity action resist federal 2026
library resist book ban censorship 2026
business refuse federal contract protest 2026
company end contract federal government resist 2026
```

#### Category 2: Cracks and Fissures
```
Republican criticize Trump break ranks 2026
Republican oppose Trump policy GOP dissent 2026
sheriff refuse ICE cooperation police 2026
law enforcement criticize federal immigration raid 2026
conservative criticize Trump donor withdraw 2026
government employee resign protest whistleblower 2026
```

#### Category 3: Gaps and Absences
```
model legislation state protect rights 2026
mutual aid network community organize 2026
```

#### Category 4: Pending Decisions and Leverage Points
```
federal contract renewal controversy decision 2026
state legislation debate vote protect rights 2026
court ruling pending federal overreach 2026
comment period federal regulation public 2026
local election school board sheriff DA 2026
```

#### Category 5: Emerging Patterns
```
protest movement rally march growing 2026
boycott campaign consumer grassroots 2026
walkout strike workers resistance 2026
spontaneous protest uncoordinated multiple cities 2026
```

#### Category 6: Outrages and Galvanizing Events
```
federal overreach backlash community outrage 2026
ICE raid community response outrage 2026
DOGE cuts community impact response 2026
```

#### Category 7: Defensive Needs
```
anticipated federal action prepare community defense 2026
state attack voting rights local control 2026
threat existing protections community prepare 2026
```

#### Cross-cutting / Issue-specific
```
ACA health care subsidy expire organize 2026
education cuts protest parents organize 2026
trans rights protect state local action 2026
climate action state local resist rollback 2026
press freedom journalist protect information 2026
veterans military criticize administration 2026
```

### Reddit (27 subreddits)

**Resistance:** r/50501, r/esist, r/fuckthealtright, r/MarchAgainstNazis, r/Keep_Track

**Organizing:** r/Political_Revolution, r/VoteDEM, r/DemocraticSocialism, r/antiwork, r/WorkReform, r/LateStageCapitalism

**Issues:** r/prochoice, r/ExtinctionRebellion, r/ClimateOffensive

**Local:** r/DenverProtests

**Broad (keyword-filtered):** r/politics, r/news, r/immigration, r/Teachers, r/law, r/WhitePeopleTwitter, r/TwoXChromosomes

Broad subreddits are filtered to only include posts matching resistance/organizing keywords (protest, rally, sanctuary, ICE, DOGE, boycott, mutual aid, etc.).

Uses the public Reddit JSON API (no authentication needed). Rate limited to ~10 requests/minute.

### Bluesky (120+ accounts, 5 hashtags)

**Hashtags searched:** #50501, #buildtheresistance, #NoKings, #resist, #HandsOff

**Accounts monitored include:**
- National movement orgs (Indivisible, 50501, MoveOn, ACLU, Democracy Now, etc.)
- Unions (SEIU, UAW, UNITE HERE, CWA, AFSCME, etc.)
- 40+ Indivisible chapters nationwide
- Organizers and movement voices
- Documenters (Aaron Rupar, Acyn)

**Search terms:** protest, rally, march, organizing, direct action, boycott, sanctuary, executive order, resist, walkout, strike, defection

### Gmail (optional)

Reads newsletters from a configured Gmail account. Extracts URLs from email bodies, filters for known news domains, and converts to articles. Requires Google OAuth credentials.

---

## Step 2: Deduplication

Articles are deduplicated by:
1. Normalized URL (lowercased, trailing slash removed)
2. Normalized title (alphanumeric characters only, lowercased)

If either matches a previously seen article, the duplicate is dropped.

---

## Step 3: AI Detection

Articles are sent to Claude (Sonnet) in batches of 30 with the following prompt framework.

### The Full Detection Prompt

```
You are a campaign strategist scanning news and social media for
campaign openings — raw material that could form the basis for a
pro-democracy, anti-authoritarian grassroots campaign.

## What You're Looking For: Campaign Openings

An "opening" is raw material for a potential campaign — something
that has happened, exists, or is emerging that a strategist could
look at and say "there's something there." These are OPENINGS,
not campaigns.

### An opening has these characteristics:
1. Something concrete happened — an action, statement, policy,
   event, or pattern (not just commentary)
2. It suggests a replicable or extendable action — others could
   do it, or it could be pushed further
3. No one is systematically working that angle yet — it's not
   owned, not saturated, not organized
4. There's a plausible theory of change — you can imagine who
   would be asked to do what

### What DISQUALIFIES something as an opening:
- It's already a well-known campaign (organized groups are already
  pressuring that target on that ask)
- The moment has clearly passed (news cycle moved on, decision was
  made, leverage is gone)
- It's saturated (everyone already knows, no new energy to mobilize)
- It's just commentary or analysis, not an action or event
- It's describing an existing network ("Tesla Takedown exists" =
  not an opening)
- It requires ground presence in a crisis zone (we need things
  people ELSEWHERE can act on)

### Categories of Openings (assign ONE):

1. Actions That Could Be Replicated
   Executive actions (governors, AGs, mayors), institutional actions
   (school districts, universities, hospitals, churches, unions,
   libraries), business actions, individual actions.
   Key question: Who did something good that someone else hasn't
   done yet but could?

2. Cracks and Fissures
   Law enforcement breaks, political breaks (Republicans criticizing
   Trump, officials breaking ranks), institutional dissent (employees
   speaking out, resignations), unexpected voices (business leaders,
   military/veterans, religious leaders).
   Key question: Is someone breaking from the expected alignment?

3. Gaps and Absences
   Things that should exist but don't (model legislation not yet
   adopted, coordination mechanisms not yet built, mutual aid gaps,
   legal defense gaps), actors who haven't been activated, missing
   connections between natural allies.
   Key question: What's missing that could be created?

4. Pending Decisions and Leverage Points
   Upcoming decisions (contract renewals, legislation being debated,
   court cases, elections, budget decisions), supply chains and
   complicity networks, regulatory moments (comment periods, permit
   applications, public hearings).
   Key question: Where is there a decision coming that could be
   influenced?

5. Emerging Patterns (Uncoordinated Energy)
   Spontaneous activity that could be organized, protests without
   coordination, social media trends becoming real-world action,
   informal mutual aid networks, shifts in public opinion or
   behavior (boycotts, changing civic participation).
   Key question: Where is there energy without infrastructure?

6. Outrages and Galvanizing Events
   Federal overreach incidents, corporate actions, sympathetic
   victims/stories, shocking revelations, viral moments.
   NOTE: Only an opening if there's an actionable response that
   isn't already saturated.
   Key question: Is there an ask that channels this energy?

7. Defensive Needs
   Anticipated federal actions, state-level attacks, corporate
   threats, legal threats to existing protections.
   Key question: What's coming that people could get ahead of?

### Issue Domains (assign ONE):
- Immigration enforcement
- Economic justice / economic security
- Attacks on science and research
- Voting rights
- Reproductive rights
- LGBTQ+ rights
- Federal workforce/DOGE
- Climate/environment
- Tariffs/economic disruption
- Education
- Press freedom/information access
- Rule of law/judicial independence
- Foreign policy/alliances
- Health and Healthcare
- Civil liberties

### Quality Control - Before identifying an opening, verify:
- Is this an action/event, not just commentary?
- Is it specific enough to be replicable?
- Is it NOT already the focus of an organized campaign?
- Could someone outside the original location act on it?
- Is there a clear "who could be asked to do what"?

## Articles to Scan:
[30 articles with source, title, URL, date, and content preview]

## Instructions:
1. Read each article carefully
2. Identify any campaign OPENINGS (not just interesting news)
3. For each opening found, provide ALL of the following fields
4. Be selective — most articles will NOT contain openings
5. An article might contain multiple openings, or none
6. If similar openings appear in multiple articles, pick the
   best source and consolidate

Priority scale:
- 5: Exceptional (high replication potential + clear theory of
     change + timely)
- 4: Strong (most criteria met, actionable)
- 3: Solid (worth considering, some constraints)
- 2: Marginal (interesting but significant barriers)
- 1: Weak (barely meets criteria but worth noting)
```

### Output Format

For each opening, the AI returns:
- `what_happened` — concrete description
- `who` — specific actor (name, title, institution)
- `when` — date or timeframe
- `where` — location
- `issue_domain` — from the 15 domains
- `category` — from the 7 opening categories
- `replication_potential` — who else could do this, where, how many targets
- `campaign_status` — is anyone already working this angle
- `time_sensitivity` — is there a window, when does it close
- `raw_material_note` — why this is an opening, what a campaign might look like
- `priority` — 1-5 scale

---

## Step 4: Cross-Batch Deduplication

Since the same event may appear in articles across different batches, a second AI pass merges duplicate openings:

- Same specific event/action reported by different sources = **merge** (keep the version with best detail, collect all source URLs)
- Different actions by different actors on the same topic = **keep separate**
- For large result sets (80+ openings), dedup runs in chunks of 60 with multiple passes

---

## Step 5: Output

### JSON (`openings.json`)
Machine-readable with all fields, metadata, and source URLs.

### Markdown (`openings.md`)
Human-readable with:
- Summary statistics (total, by category, by issue domain, by priority)
- All openings organized by category, then sorted by priority within each category

### Excel (`openings.xlsx`)
Sortable spreadsheet with columns: Priority, What Happened, Campaign Type, Issue Domain, Who, When, Where, Campaign Rationale, Time Sensitivity, Source URL. Includes a summary sheet with category and domain breakdowns.
