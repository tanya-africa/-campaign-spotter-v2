# Campaign Opening Scanner

An automated pipeline that scans news, social media, and newsletters to identify **campaign openings** — concrete events, decisions, or patterns that could form the basis for a pro-democracy, anti-authoritarian grassroots campaign.

The scanner pulls from ~150 sources, deduplicates the results, sends them to Claude (Anthropic's AI) with a detailed strategic framework, and produces structured output ranked by priority.

A 30-day scan typically processes **2,000-3,000 articles** and identifies **150-200 campaign openings** in approximately 30-45 minutes.

## What It Finds

The scanner identifies openings across **7 categories**:

1. **Actions That Could Be Replicated** — executive, institutional, or business actions others could copy
2. **Cracks and Fissures** — breaks in expected alignment (officials dissenting, unexpected voices speaking out)
3. **Gaps and Absences** — things that should exist but don't (model legislation, coordination mechanisms, mutual aid)
4. **Pending Decisions and Leverage Points** — upcoming decisions that could be influenced
5. **Emerging Patterns** — uncoordinated energy that could be organized
6. **Outrages and Galvanizing Events** — incidents with actionable responses that aren't already saturated
7. **Defensive Needs** — anticipated threats people could get ahead of

Each opening is classified into one of **15 issue domains**: immigration enforcement, economic justice, attacks on science, voting rights, reproductive rights, LGBTQ+ rights, federal workforce/DOGE, climate/environment, tariffs/economic disruption, education, press freedom, rule of law, foreign policy, health/healthcare, civil liberties.

## Sources

| Source Type | How It Works | Approx. Volume |
|---|---|---|
| **National RSS** (14 feeds) | NPR, Guardian, WaPo, NYT, LA Times, Democracy Docket, Just Security, CREW, Popular Info, TPM, Intercept, Atlantic, American Prospect, WTFJHT | ~300 articles |
| **Regional RSS** (22 papers) | Swing state and resistance-hub newspapers (AZ, GA, WI, MI, PA, NV, NC, CA, MN, CO, WA, MA, IL, OR, NY, TX, FL, OH, PA, MO) | ~400 articles |
| **Google News RSS** (48 queries) | Targeted queries for each of the 7 opening categories + cross-cutting issue queries | ~1,500 articles |
| **Reddit** (27 subreddits) | Resistance, organizing, issues, and local subs + keyword-filtered broad subs | ~200 posts |
| **Bluesky** (120+ accounts, 5 hashtags) | Movement orgs, unions, Indivisible chapters, organizers, documenters | ~100 posts |
| **Gmail** (optional) | Newsletter extraction from a configured Gmail account | varies |

## Requirements

- Python 3.7+
- An **Anthropic API key** (for Claude — this does the AI analysis)
- A **Bluesky account** (optional — scanner works without it)
- **Gmail OAuth credentials** (optional — scanner works without it)

### Python Dependencies

```bash
pip install -r requirements.txt
```

The requirements:
- `feedparser` — RSS feed parsing
- `requests` — HTTP requests
- `anthropic` — Claude API client
- `beautifulsoup4` — HTML parsing
- `html2text` — HTML to text conversion
- `python-dateutil` — date parsing
- `openpyxl` — Excel file generation
- `atproto` — Bluesky API client (optional)
- `google-auth`, `google-auth-oauthlib`, `google-auth-httplib2`, `google-api-python-client` — Gmail API (optional)

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/vibe-campaigning.git
cd vibe-campaigning
pip install -r requirements.txt
```

### 2. Set your Anthropic API key (required)

The scanner uses Claude to analyze articles and identify campaign openings. You need an API key from [console.anthropic.com](https://console.anthropic.com/).

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

Add this to your `~/.zshrc` or `~/.bashrc` to make it permanent.

**Cost:** A full 30-day scan processes ~2,500 articles in batches of 30. This costs approximately $5-15 in API usage depending on article length and number of openings found.

### 3. (Optional) Set Bluesky credentials

```bash
export BLUESKY_HANDLE="yourhandle.bsky.social"
export BLUESKY_APP_PASSWORD="your-app-password"
```

Generate an app password at: Settings > App Passwords in the Bluesky app.

If not set, the scanner skips Bluesky and continues with other sources.

### 4. (Optional) Set up Gmail

Gmail requires Google OAuth credentials:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable the Gmail API
3. Create OAuth 2.0 credentials (Desktop application type)
4. Download the credentials JSON file
5. Place it at `credentials/credentials.json`

The first time you run with Gmail enabled, it will open a browser for OAuth authorization and save a token to `credentials/token.json`.

If you don't set this up, use `--preview` mode to skip Gmail.

### 5. No Reddit credentials needed

Reddit uses the public JSON API — no account or API key required.

## Usage

### Full scan (all sources, 30-day lookback)

```bash
cd src
python main.py
```

### Preview mode (skip Gmail)

```bash
python main.py --preview
```

### Other options

```bash
python main.py --lookback-days 7           # Last 7 days only
python main.py --lookback-days 60          # 60-day lookback
python main.py --sources gnews,reddit      # Only specific sources
python main.py --max-openings 100          # Cap output at 100 openings
python main.py --output-dir ./my-output    # Custom output directory
```

Available source types: `rss`, `regional`, `gnews`, `gmail`, `reddit`, `bluesky`

### Expected runtime

| Lookback | Approx. Articles | Approx. Time |
|---|---|---|
| 7 days | ~800 | ~15 minutes |
| 30 days | ~2,500 | ~35 minutes |
| 60 days | ~3,500 | ~50 minutes |

Most time is spent on AI analysis (processing articles in batches of 30).

## Output

The scanner produces three output files in the `data/` directory:

### `openings.json`
Machine-readable JSON with all openings and full metadata.

### `openings.md`
Human-readable Markdown with:
- Summary statistics (total, by category, by issue domain, by priority level)
- All openings organized by category, sorted by priority

### `openings.xlsx`
Sortable/filterable Excel spreadsheet with columns: Priority, What Happened, Campaign Type, Issue Domain, Who, When, Where, Campaign Rationale, Time Sensitivity, Source URL. Includes a summary sheet.

## How the AI Detection Works

See `data/how-the-scanner-works.md` for the full technical process document, including the complete AI prompt framework, all 48 search queries, all 7 opening categories with detection criteria, disqualification rules, and the quality control checklist.

In brief: articles are sent to Claude in batches of 30 with a prompt that includes:
- The 7 opening categories with detailed descriptions and key questions
- Detection criteria (what qualifies as an opening)
- Disqualification criteria (what doesn't)
- 15 issue domains
- A quality control checklist
- A 1-5 priority scale

The AI returns structured JSON for each opening, which is then deduplicated across batches and formatted into the three output files.

## Customizing

### Adding RSS feeds

Edit `src/config.py` — add entries to `NATIONAL_RSS_FEEDS` or `REGIONAL_RSS_FEEDS`:

```python
REGIONAL_RSS_FEEDS = {
    # ...existing feeds...
    "Your Paper": "https://yourpaper.com/politics/feed/",
}
```

### Adding Google News queries

Edit `src/config.py` — add entries to `GOOGLE_NEWS_QUERIES`:

```python
GOOGLE_NEWS_QUERIES = [
    # ...existing queries...
    "your specific search query 2026",
]
```

### Adding Reddit subreddits

Edit `src/social_config.py` — add to the appropriate list:

```python
REDDIT_SUBREDDITS_RESISTANCE = [
    # ...existing subs...
    "YourSubreddit",
]
```

For broad subreddits that need keyword filtering, also add them to `SUBREDDITS_REQUIRE_KEYWORDS`.

### Adding Bluesky accounts

Edit `src/social_config.py` — add to `BLUESKY_ACCOUNTS`:

```python
BLUESKY_ACCOUNTS = [
    # ...existing accounts...
    "newaccount.bsky.social",
]
```

## Relationship to Other Projects

This scanner was adapted into a **healthcare-specific version** (the Patients' Union Campaign Opening Scanner) that:
- Replaces the 7 anti-authoritarian opening categories with 25 healthcare campaign types
- Adds geographic scoping via media markets (state/metro level)
- Adds three-way locality classification (statewide/hyperlocal/replicable)
- Adds institution-specific search queries (hospital systems, legislators, agencies by name)
- Removes Gmail integration (not needed for healthcare news)

The architecture is the same: fetch → deduplicate → AI detect → deduplicate openings → output.

## Project Structure

```
vibe-campaigning/
├── src/
│   ├── main.py              # Entry point — orchestrates the scan pipeline
│   ├── config.py             # Opening categories, RSS feeds, Google News queries
│   ├── social_config.py      # Bluesky accounts/hashtags, Reddit subreddits, keywords
│   ├── models.py             # Data models (Article, Opening)
│   ├── rss_fetcher.py        # RSS feed fetcher (national, regional, Google News)
│   ├── gmail_reader.py       # Gmail newsletter reader (optional)
│   ├── reddit_fetcher.py     # Reddit public API fetcher
│   ├── bluesky_fetcher.py    # Bluesky API fetcher
│   ├── opening_detector.py   # AI detection — sends articles to Claude, parses responses
│   └── output_formatter.py   # Writes JSON, Markdown, Excel output
├── data/
│   └── how-the-scanner-works.md  # Full process documentation
├── requirements.txt
└── README.md
```
