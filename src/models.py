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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Opening":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
