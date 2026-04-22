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
CLAUDE_MODEL = "claude-sonnet-4-6"

# Time settings
DEFAULT_LOOKBACK_DAYS = 30

# Output settings
MAX_OPENINGS = 400
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
    # Most regional papers have killed public RSS or block automated requests.
    # Dead/blocked feeds are replaced by Google News site: queries below.
    "Las Vegas Review-Journal": "https://www.reviewjournal.com/news/politics-and-government/feed/",
    "Seattle Times": "https://www.seattletimes.com/seattle-news/politics/feed/",
    "Pittsburgh Post-Gazette": "https://www.post-gazette.com/rss/politics",
}

# =============================================================================
# Google News RSS Queries (targeted by Framework #1 categories)
# =============================================================================

GOOGLE_NEWS_QUERIES = [
    # --- Category 1: Actions That Could Be Replicated ---
    # Executive actions
    "governor executive order sanctuary immigration",
    "governor executive order protect reproductive rights",
    "state legislation protect immigrants workers",

    # Institutional actions
    "school district sanctuary resolution immigration",
    "university refuse federal mandate sanctuary",
    "hospital refuse comply federal reporting",
    "church sanctuary immigration denomination",
    "union solidarity action resist federal",
    "library resist book ban censorship",

    # Business actions
    "company end contract federal government resist",

    # --- Category 2: Cracks and Fissures ---
    "law enforcement criticize federal immigration raid",
    "conservative criticize Trump donor withdraw",
    "government employee resign protest whistleblower",
    "Republican senator breaks ranks Trump",
    "conservative Republican official criticize ICE Trump immigration",

    # --- Category 3: Gaps and Absences ---
    "model legislation state protect rights",
    "mutual aid network community organize",

    # --- Category 4: Pending Decisions and Leverage Points ---
    "federal contract renewal controversy decision",
    "state legislation debate vote protect rights",
    "court ruling pending federal overreach",
    "comment period federal regulation public",
    "local election school board sheriff DA",

    # --- Category 5: Emerging Patterns ---
    "protest movement rally march growing",
    "boycott campaign consumer grassroots",
    "walkout strike workers resistance",
    "spontaneous protest uncoordinated multiple cities",

    # --- Category 6: Outrages and Galvanizing Events ---
    "federal overreach backlash community outrage",
    "ICE raid community response outrage",
    "DOGE cuts community impact response",

    # --- Category 7: Defensive Needs ---
    "anticipated federal action prepare community defense",
    "state attack voting rights local control",
    "threat existing protections community prepare",

    # --- Cross-cutting / issue-specific ---
    "ACA health care subsidy expire organize",
    "education cuts protest parents organize",
    "trans rights protect state local action",
    "climate action state local resist rollback",
    "press freedom journalist protect information",
    "veterans military criticize administration",

    # --- Category 8: State-Level Democracy Reforms ---
    "National Popular Vote compact state legislature",
    "ranked choice voting state ballot initiative",
    "independent redistricting commission state",
    "state campaign finance reform Citizens United",
    "automatic voter registration state legislation",
    "state voting rights expansion legislation",
    "gerrymandering state reform ballot measure",
    "state small-dollar public financing elections",

    # --- Corporate contractor pressure ---
    "company drops ICE contract protest",
    "ICE contractor community pressure campaign",

    # --- Detention infrastructure / warehouse buildout ---
    "warehouse ICE detention community opposition",
    "ICE detention facility permit denied blocked",
    "utility board ICE detention water sewer",
    "ICE facility acquisition community fight",

    # --- Small business and economic impact ---
    "small business ICE raid economic loss",
    "restaurant business ICE enforcement revenue decline",
    "chamber of commerce ICE immigration stance",

    # --- Conservative and Republican cracks ---
    "Republican mayor oppose ICE detention",
    "property rights ICE warrant search",

    # --- Platform and surveillance accountability ---
    "Google Meta subpoena ICE user data",
    "tech platform government data request ICE",
    "administrative subpoena ICE First Amendment",

    # --- Detention conditions and medical ---
    "immigration detention medical neglect lawsuit",
    "ICE detention deaths conditions report",
    "detention center health violation children",

    # --- Coalition fracture (MAHA-style) ---
    "MAHA Republican coalition fracture Trump policy",
    "health voters pesticide food safety Republican",
    "Trump base opposition policy betrayal",

    # --- Local government action ---
    # Immigration / ICE
    "county commission ICE detention ordinance 2026",
    "sheriff refuse ICE detainer cooperation 2026",
    "city council sanctuary resolution vote 2026",
    "local government refuse DOGE cooperate federal 2026",

    # Education
    "school board refuse federal directive 2026",
    "state legislature book ban curriculum restrict 2026",
    "university board federal funding compliance 2026",

    # Elections / voting rights
    "state legislature ballot access voting rights bill 2026",
    "county election board certification policy 2026",

    # State-level federal resistance
    "state attorney general lawsuit federal government 2026",
    "state legislature preemption local government 2026",

    # Surveillance
    "city council surveillance technology contract vote 2026",

    # Divestment
    "state treasurer divestment resolution 2026",

    # Homelessness
    "city council homeless encampment sweep resist 2026",

    # Labor
    "state legislature right to work repeal 2026",
    "city council project labor agreement vote 2026",

    # Reproductive rights
    "state attorney general abortion prosecute 2026",
    "district attorney refuse prosecute abortion 2026",

    # --- Housing ---
    "city council rent control ordinance vote 2026",
    "tenant union rent strike eviction organize 2026",
    "state legislature rent stabilization tenant protection 2026",
    "zoning affordable housing council community vote 2026",

    # --- Labor beyond strike/walkout ---
    "public employee collective bargaining state legislature 2026",
    "state legislature worker protection wage theft 2026",
    "NLRB captive audience meeting worker rights 2026",

    # --- Environmental / utility ---
    "pipeline permit community opposition state 2026",
    "state public utility commission rate increase hearing 2026",
    "agricultural pollution rural community organize 2026",

    # --- Police accountability (non-ICE) ---
    "civilian review board police department vote 2026",
    "consent decree police reform community oversight 2026",

    # --- LGBTQ+ state-level ---
    "state legislature gender affirming care ban 2026",
    "school board trans student policy vote 2026",

    # --- Disability / Medicaid ---
    "state Medicaid home care cuts community response 2026",
    "disability services state budget cut advocate 2026",

    # --- Religious-right fractures ---
    "religious denomination statement Trump policy immigration 2026",
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
