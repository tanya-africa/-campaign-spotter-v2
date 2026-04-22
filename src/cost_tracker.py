"""
API cost tracker for the campaign spotter pipeline.

Accumulates token usage across all Claude API calls and computes estimated cost.
Thread-safe — safe to use from parallel coverage research workers.

Pricing: claude-sonnet-4-6 as of 2026-04. Verify at https://anthropic.com/pricing.
"""

import threading

INPUT_COST_PER_MTOK = 3.00    # $ per million input tokens
OUTPUT_COST_PER_MTOK = 15.00  # $ per million output tokens
WEB_SEARCH_COST_EACH = 0.01   # $ per web_search tool invocation


class _CostTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self.input_tokens = 0
        self.output_tokens = 0
        self.web_searches = 0
        self.api_calls = 0

    def record(self, response) -> None:
        """Extract usage from a Claude API response and accumulate."""
        if not hasattr(response, "usage"):
            return
        searches = sum(
            1 for block in response.content
            if getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == "web_search"
        )
        with self._lock:
            self.input_tokens += response.usage.input_tokens
            self.output_tokens += response.usage.output_tokens
            self.web_searches += searches
            self.api_calls += 1

    @property
    def cost(self) -> float:
        return (
            self.input_tokens / 1_000_000 * INPUT_COST_PER_MTOK
            + self.output_tokens / 1_000_000 * OUTPUT_COST_PER_MTOK
            + self.web_searches * WEB_SEARCH_COST_EACH
        )

    def summary(self, label: str = "") -> str:
        prefix = f"[{label}] " if label else ""
        search_note = f", {self.web_searches} web searches" if self.web_searches else ""
        return (
            f"  {prefix}Cost so far: ${self.cost:.4f} "
            f"({self.input_tokens:,} in / {self.output_tokens:,} out tokens"
            f"{search_note}, {self.api_calls} API calls)"
        )


tracker = _CostTracker()
