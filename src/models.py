"""
Data models for the Vibe-Campaigning Campaign Idea Generator.
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
    source_query: str = ""   # full query string for gnews articles; empty for other sources

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        if not isinstance(other, Article):
            return False
        return self.url == other.url


@dataclass
class CampaignIdea:
    """
    A campaign idea generated from news analysis.
    Includes target, ask, constituency, theory of leverage, and scored rubric.
    """
    # Core campaign concept
    headline: str                    # One-line campaign pitch
    news_hook: str                   # What happened that creates this opening
    target: str                      # Named, specific target (who can deliver the win)
    ask: str                         # Binary ask in one sentence
    constituency: str                # Who has leverage and self-interest
    theory_of_leverage: str          # Why the target would cave — one chain
    # Context
    source_url: str                  # Primary source link
    source_name: str                 # Primary source name
    additional_sources: list[str] = field(default_factory=list)
    issue_domain: str = ""
    category: str = ""               # Opening category (7 types)
    where: str = ""                  # Location
    time_sensitivity: str = ""       # Window description
    # Stage 1: Gates (0/1/2, all must be 1+ to pass)
    gate_named_target: int = 0
    gate_binary_ask: int = 0
    gate_time_window: int = 0
    is_watch_list: bool = False
    gate_fail_reason: str = ""
    watch_list_trigger: str = ""     # What event could promote this to scored
    # Stage 2: Scoring dimensions (0-4 each)
    score_beyond_choir: int = 0      # D1: 10%
    score_pressure_point: int = 0    # D2: 25%
    score_anti_authoritarian: int = 0  # D3: 25%
    score_replication: int = 0       # D4: 15%
    score_winnability: int = 0       # D5: 10%
    score_energy_potential: int = 0  # D6: 10%
    score_non_compliance: int = 0    # D7: 5%
    weighted_score: float = 0.0
    score_rationale: str = ""
    # Self-critique annotations (filled by second pass)
    critique_notes: str = ""         # What the critique step found
    pre_critique_score: float = 0.0  # Score before adjustment
    # Fit-for-us tags (filled by critique + coverage research)
    ai_leverage: str = ""            # Where AI-augmentation changes the odds, or ""
    existing_coverage: str = ""      # Who else is on this + what gap we'd fill, or ""
    coverage_score: Optional[int] = None  # 0=saturated, 1=crowded, 2=gap, 3=wide open
    source_query: str = ""               # full gnews query that sourced this idea; empty for other sources
    # Grouping

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CampaignIdea":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
