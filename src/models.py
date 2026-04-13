"""
Data models for the Vibe-Campaigning Opening Scanner.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Article:
    """
    Unified input format for content from any source (RSS, Gmail, Reddit, Bluesky).
    URL is the unique identifier for deduplication.
    """
    title: str
    url: str
    source: str
    published: datetime
    content: str
    raw_html: Optional[str] = None
    source_type: str = "rss"  # rss, gmail, reddit, bluesky, gnews

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        if not isinstance(other, Article):
            return False
        return self.url == other.url


@dataclass
class Opening:
    """
    A campaign opening identified by the AI detector.
    Based on Framework #1's output format.
    """
    what_happened: str           # Concrete, specific description
    who: str                     # Specific actor
    when: str                    # Date/timeframe
    where: str                   # Location
    source_url: str              # Primary source link
    source_name: str             # Primary source name
    additional_sources: list[str] = field(default_factory=list)  # Other source URLs (after dedup merging)
    issue_domain: str = ""       # From Framework #1 list (15 domains)
    category: str = ""           # From Framework #1 categories (7 types)
    replication_potential: str = ""   # Who else could do this, where
    campaign_status: str = ""    # Is anyone already working this?
    time_sensitivity: str = ""   # Window? When does it close?
    raw_material_note: str = ""  # Brief note on why this is an opening
    priority: int = 3            # 1-5 score (5 = highest)
    # Stage 1: Gates (0/1/2, all must be 1+ to pass)
    gate_named_target: int = 0
    gate_binary_ask: int = 0
    gate_time_window: int = 0
    is_watch_list: bool = False   # True if any gate = 0
    gate_fail_reason: str = ""    # Why the opening failed gating
    # Stage 2: Scoring dimensions (0/1/2, only meaningful if gates pass)
    score_beyond_choir: int = 0       # D1: beyond-the-choir constituency (30%)
    score_pressure_point: int = 0     # D2: actionable pressure point (30%)
    score_replication: int = 0        # D3: replication potential (20%)
    score_winnability: int = 0        # D4: winnability in weeks-months (20%)
    weighted_score: float = 0.0
    score_rationale: str = ""
    campaign_group: str = ""          # Group ID for related openings (same campaign, different angles)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Opening":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
