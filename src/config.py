"""
Configuration for the Vibe-Campaigning Opening Scanner.
"""

import os
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
DATA_DIR = PROJECT_ROOT / "data"
FRAMEWORKS_DIR = PROJECT_ROOT / "frameworks"

# Scan history (for future recurring use / dedup)
SCAN_HISTORY_FILE = DATA_DIR / "scan_history.json"

# Gmail API settings (reusing credentials from authoritarianism-digest)
GMAIL_CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"
GMAIL_TOKEN_FILE = CREDENTIALS_DIR / "token.json"
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]

# Gmail label the scanner reads from. Create this label in Gmail and apply it
# via a filter (see campaign-spotter-newsletter-tracker.md for the filter string).
GMAIL_LABEL = "campaign-scanner-newsletters"

# Claude API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Time settings
DEFAULT_LOOKBACK_DAYS = 30

# Output settings
MAX_OPENINGS = 200
BATCH_SIZE = 30  # Articles per AI processing batch

# =============================================================================
# RSS Feed Sources (national outlets — same as digest)
# =============================================================================

NATIONAL_RSS_FEEDS = {
    # Wire/Breaking News
    "NPR Politics": "https://feeds.npr.org/1014/rss.xml",
    "The Guardian US": "https://www.theguardian.com/us-news/rss",

    # Major Papers
    "Washington Post Politics": "https://feeds.washingtonpost.com/rss/politics",
    "NYT Politics": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
    "LA Times Politics": "https://www.latimes.com/politics/rss2.0.xml",

    # Democracy/Legal Specialists
    "Democracy Docket": "https://www.democracydocket.com/feed/",
    "Just Security": "https://www.justsecurity.org/feed/",
    "CREW": "https://www.citizensforethics.org/feed/",

    # Movement/Progressive
    "Popular Information": "https://popular.info/feed",
    "Talking Points Memo": "https://talkingpointsmemo.com/feed",
    "The Intercept": "https://theintercept.com/feed/?rss",

    # Analysis/Long-form
    "The Atlantic Politics": "https://www.theatlantic.com/feed/channel/politics/",
    "American Prospect": "https://prospect.org/feed/",

    # Daily Digest
    "WTFJHT": "https://whatthefuckjusthappenedtoday.com/rss.xml",
}

# =============================================================================
# Regional Paper RSS Feeds (strategically important states)
# =============================================================================

REGIONAL_RSS_FEEDS = {
    # --- Swing States ---
    "Arizona Republic": "https://rssfeeds.azcentral.com/phoenix/politics",
    "Atlanta Journal-Constitution": "https://www.ajc.com/politics/feed/",
    "Milwaukee Journal Sentinel": "https://rssfeeds.jsonline.com/milwaukee/news",
    "Detroit Free Press": "https://rssfeeds.freep.com/detroit/news",
    "Philadelphia Inquirer": "https://www.inquirer.com/arcio/rss/category/politics/",
    "Las Vegas Review-Journal": "https://www.reviewjournal.com/feed/",
    "Charlotte Observer": "https://www.charlotteobserver.com/news/politics-government/index.rss",
    "Raleigh News & Observer": "https://www.newsobserver.com/news/politics-government/index.rss",

    # --- Active Resistance/Policy States ---
    "Sacramento Bee": "https://www.sacbee.com/news/politics-government/index.rss",
    "San Francisco Chronicle": "https://www.sfchronicle.com/politics/feed/",
    "Minneapolis Star Tribune": "https://www.startribune.com/politics/rss/",
    "Denver Post": "https://www.denverpost.com/politics/feed/",
    "Seattle Times": "https://www.seattletimes.com/seattle-news/politics/feed/",
    "Boston Globe": "https://www.bostonglobe.com/rss/politics",
    "Chicago Tribune": "https://www.chicagotribune.com/arcio/rss/category/politics/",
    "Portland Oregonian": "https://www.oregonlive.com/politics/rss/",
    "Albany Times Union": "https://www.timesunion.com/politics/feed/",

    # --- States with interesting dynamics ---
    "Austin American-Statesman": "https://www.statesman.com/news/politics-government/index.rss",
    "Miami Herald": "https://www.miamiherald.com/news/politics-government/index.rss",
    "Columbus Dispatch": "https://www.dispatch.com/news/politics/index.rss",
    "Pittsburgh Post-Gazette": "https://www.post-gazette.com/rss/politics",
    "St. Louis Post-Dispatch": "https://www.stltoday.com/news/local/govt-and-politics/rss/",
}

# =============================================================================
# Google News RSS Queries (targeted by Framework #1 categories)
# =============================================================================

GOOGLE_NEWS_QUERIES = [
    # --- Category 1: Actions That Could Be Replicated ---
    # Executive actions
    "governor executive order sanctuary immigration 2026",
    "governor executive order protect reproductive rights 2026",
    "attorney general lawsuit federal overreach 2026",
    "attorney general legal challenge Trump administration 2026",
    "mayor city council resolution resist federal 2026",
    "state legislation protect immigrants workers 2026",

    # Institutional actions
    "school district sanctuary resolution immigration 2026",
    "university refuse federal mandate sanctuary 2026",
    "hospital refuse comply federal reporting 2026",
    "church sanctuary immigration denomination 2026",
    "union solidarity action resist federal 2026",
    "library resist book ban censorship 2026",

    # Business actions
    "business refuse federal contract protest 2026",
    "company end contract federal government resist 2026",

    # --- Category 2: Cracks and Fissures ---
    "Republican criticize Trump break ranks 2026",
    "Republican oppose Trump policy GOP dissent 2026",
    "sheriff refuse ICE cooperation police 2026",
    "law enforcement criticize federal immigration raid 2026",
    "conservative criticize Trump donor withdraw 2026",
    "government employee resign protest whistleblower 2026",

    # --- Category 3: Gaps and Absences ---
    "model legislation state protect rights 2026",
    "mutual aid network community organize 2026",

    # --- Category 4: Pending Decisions and Leverage Points ---
    "federal contract renewal controversy decision 2026",
    "state legislation debate vote protect rights 2026",
    "court ruling pending federal overreach 2026",
    "comment period federal regulation public 2026",
    "local election school board sheriff DA 2026",

    # --- Category 5: Emerging Patterns ---
    "protest movement rally march growing 2026",
    "boycott campaign consumer grassroots 2026",
    "walkout strike workers resistance 2026",
    "spontaneous protest uncoordinated multiple cities 2026",

    # --- Category 6: Outrages and Galvanizing Events ---
    "federal overreach backlash community outrage 2026",
    "ICE raid community response outrage 2026",
    "DOGE cuts community impact response 2026",

    # --- Category 7: Defensive Needs ---
    "anticipated federal action prepare community defense 2026",
    "state attack voting rights local control 2026",
    "threat existing protections community prepare 2026",

    # --- Cross-cutting / issue-specific ---
    "ACA health care subsidy expire organize 2026",
    "education cuts protest parents organize 2026",
    "trans rights protect state local action 2026",
    "climate action state local resist rollback 2026",
    "press freedom journalist protect information 2026",
    "veterans military criticize administration 2026",

    # --- Category 8: State-Level Democracy Reforms ---
    "National Popular Vote compact state legislature 2026",
    "ranked choice voting state ballot initiative 2026",
    "independent redistricting commission state 2026",
    "state campaign finance reform Citizens United 2026",
    "automatic voter registration state legislation 2026",
    "state voting rights expansion legislation 2026",
    "gerrymandering state reform ballot measure 2026",
    "state small-dollar public financing elections 2026",
]

GOOGLE_NEWS_RSS_TEMPLATE = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

# =============================================================================
# Framework #1 Reference Data
# =============================================================================

OPENING_CATEGORIES = [
    "Actions That Could Be Replicated",
    "Cracks and Fissures",
    "Gaps and Absences",
    "Pending Decisions and Leverage Points",
    "Emerging Patterns",
    "Outrages and Galvanizing Events",
    "Defensive Needs",
]

ISSUE_DOMAINS = [
    "Immigration enforcement",
    "Economic justice / economic security",
    "Attacks on science and research",
    "Voting rights",
    "Reproductive rights",
    "LGBTQ+ rights",
    "Federal workforce/DOGE",
    "Climate/environment",
    "Tariffs/economic disruption",
    "Education",
    "Press freedom/information access",
    "Rule of law/judicial independence",
    "Foreign policy/alliances",
    "Health and Healthcare",
    "Civil liberties",
]
