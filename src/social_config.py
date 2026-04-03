"""
Configuration for social media sources (Bluesky, Reddit).
Adapted from authoritarianism-digest for opening detection.
"""

import os

# =============================================================================
# Bluesky Configuration
# =============================================================================

BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE", "")
BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD", "")

# Hashtags to search (without the #)
BLUESKY_HASHTAGS = [
    "50501",
    "buildtheresistance",
    "NoKings",
    "resist",
    "HandsOff",
]

# Accounts to fetch posts from
BLUESKY_ACCOUNTS = [
    # === National Movement Orgs ===
    "indivisible.org",
    "50501movement.bsky.social",
    "moveon.org",
    "moreperfectunion.bsky.social",
    "aclu.org",
    "democracynow.org",
    "votersoftomorrow.org",
    "democracystorm.bsky.social",
    "protectdemocracy.org",
    "momsdemandaction.org",
    "americanprogressaction.org",
    "rootsaction.org",
    "movementvoter.bsky.social",
    "resistlist.bsky.social",
    "iceoutofca.bsky.social",
    "fairfightaction.bsky.social",
    "50501supporters.bsky.social",
    "riseandresist.bsky.social",
    "democracyactionnet.bsky.social",
    "blackvotersmatterfund.org",
    "reprorights.org",
    "boldprogressives.org",
    "fightforaunion.bsky.social",
    "imcivicaction.bsky.social",
    "workers4democracy.bsky.social",
    "hopeandactionsf.bsky.social",

    # === Unions ===
    "seiu.org",
    "uaw.org",
    "unitehere.org",
    "sbworkersunited.org",
    "cwaunion.bsky.social",
    "afscme.bsky.social",
    "alphabetworkersunion.org",
    "ufw.bsky.social",
    "newsguild.org",
    "ctulocal1.bsky.social",
    "onionunion.bsky.social",
    "splcunion.bsky.social",
    "seiuhcmnia.bsky.social",

    # === Indivisible Chapters ===
    "indivisiblechicago.bsky.social",
    "bkindivisible.bsky.social",
    "indivisiblephl.bsky.social",
    "njindivisible.bsky.social",
    "indivisiblesf.bsky.social",
    "azindivisible.bsky.social",
    "indivisiblebaltoco.bsky.social",
    "indivisible-oregon.bsky.social",
    "indivisible-co.bsky.social",
    "indivisiblemi.bsky.social",
    "indivisiblevent.bsky.social",
    "esindivisible.bsky.social",
    "sufa-indivisible.bsky.social",
    "indivisiblegreen.bsky.social",
    "indivisibletx-24.bsky.social",
    "indivisiblenwi.bsky.social",
    "indivisiblewhidbey.org",
    "indivisiblejackson.bsky.social",
    "indivisiblemv.bsky.social",
    "indivisiblegconc.bsky.social",
    "indivisiblesouthoc.bsky.social",
    "indivisiblemanh.bsky.social",
    "nwsofa-indivisible.bsky.social",
    "sdindivisible.bsky.social",
    "indivisiblelrca.bsky.social",
    "indivisiblerahway.bsky.social",
    "wctindivisible.bsky.social",
    "indivisiblemayday.bsky.social",
    "mkindivisible.bsky.social",
    "indivisiblenaz.bsky.social",
    "indivisibleuppercape.org",
    "indivisibleec.bsky.social",
    "indivisibleri.bsky.social",
    "maindivisible.bsky.social",
    "indivisiblels.bsky.social",
    "indivisibletucson.bsky.social",
    "indivisibleroc.bsky.social",
    "indivisible515.bsky.social",
    "indivisible49.com",

    # === Organizers & Movement Voices ===
    "benwikler.bsky.social",
    "eli.bsky.social",
    "jonathansmucker.bsky.social",
    "prisonculture.bsky.social",

    # === Documenters ===
    "atrupar.com",
    "acyn.bsky.social",
]

# Search terms for opening detection (broader than digest)
BLUESKY_SEARCH_TERMS = [
    "protest",
    "rally",
    "march",
    "organizing",
    "direct action",
    "boycott",
    "sanctuary",
    "executive order",
    "resist",
    "walkout",
    "strike",
    "defection",
]

# =============================================================================
# Reddit Configuration
# =============================================================================

REDDIT_USER_AGENT = "VibeCampaigning/1.0 (campaign opening scanner)"

# Subreddits to monitor
REDDIT_SUBREDDITS_RESISTANCE = [
    "50501",
    "esist",
    "fuckthealtright",
    "MarchAgainstNazis",
    "Keep_Track",
]

REDDIT_SUBREDDITS_ORGANIZING = [
    "Political_Revolution",
    "VoteDEM",
    "DemocraticSocialism",
    "antiwork",
    "WorkReform",
    "LateStageCapitalism",
]

REDDIT_SUBREDDITS_ISSUES = [
    "prochoice",
    "ExtinctionRebellion",
    "ClimateOffensive",
]

REDDIT_SUBREDDITS_LOCAL = [
    "DenverProtests",
]

REDDIT_SUBREDDITS_BROAD = [
    "politics",
    "news",
    "immigration",
    "Teachers",
    "law",
    "WhitePeopleTwitter",
    "TwoXChromosomes",
]

REDDIT_SUBREDDITS = (
    REDDIT_SUBREDDITS_RESISTANCE +
    REDDIT_SUBREDDITS_ORGANIZING +
    REDDIT_SUBREDDITS_ISSUES +
    REDDIT_SUBREDDITS_LOCAL +
    REDDIT_SUBREDDITS_BROAD
)

# Keywords for filtering broad subs
REDDIT_KEYWORDS = [
    # Protest/action terms
    "protest", "rally", "march", "demonstration", "mobilize", "mobilization",
    "organizing", "action", "strike", "walkout", "boycott", "sit-in",
    # Resistance terms
    "resist", "resistance", "hands off", "50501", "no kings",
    # Government/policy terms
    "ICE", "deportation", "immigration enforcement", "raids",
    "authoritarianism", "fascism", "democracy", "constitutional",
    "executive order", "DOGE", "mass firing", "purge",
    # Movement terms
    "civil rights", "voting rights", "reproductive rights", "union",
    "ACLU", "indivisible",
    # Opening-specific terms
    "sanctuary", "refuse", "defy", "break ranks", "defection",
    "model legislation", "mutual aid", "coalition",
]

# =============================================================================
# Processing Settings
# =============================================================================

# Engagement thresholds (lower for 30-day scan to catch more openings)
MIN_ENGAGEMENT_BLUESKY = 3    # minimum likes
MIN_ENGAGEMENT_REDDIT = 5     # minimum score

SUBREDDITS_REQUIRE_KEYWORDS = [
    "politics",
    "news",
    "immigration",
    "Teachers",
    "law",
    "WhitePeopleTwitter",
    "TwoXChromosomes",
]
