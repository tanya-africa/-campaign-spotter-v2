"""
Reddit fetcher for campaign opening detection using public JSON API.
Adapted from authoritarianism-digest: uses top/month endpoint for 30-day lookback.
"""

import re
import time
from datetime import datetime, timedelta, timezone

import requests

from models import Article
from social_config import (
    REDDIT_USER_AGENT,
    REDDIT_SUBREDDITS,
    REDDIT_KEYWORDS,
    SUBREDDITS_REQUIRE_KEYWORDS,
    MIN_ENGAGEMENT_REDDIT,
)

# Rate limiting: Reddit allows ~10 requests/minute for unauthenticated
REQUEST_DELAY_SECONDS = 6


def build_keyword_pattern():
    return re.compile(
        r'\b(' + '|'.join(re.escape(kw) for kw in REDDIT_KEYWORDS) + r')\b',
        re.IGNORECASE
    )


def fetch_single_subreddit(
    name: str,
    lookback_days: int,
    seen_ids: set,
    keyword_pattern,
    headers: dict,
) -> list[Article]:
    """Fetch top+new for one subreddit. Updates seen_ids in place. No engagement filter applied."""
    cutoff_timestamp = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).timestamp()
    requires_keywords = name.lower() in [s.lower() for s in SUBREDDITS_REQUIRE_KEYWORDS]
    posts = []

    try:
        top_url = f"https://www.reddit.com/r/{name}/top.json?t=month&limit=100"
        response = requests.get(top_url, headers=headers, timeout=30)
        response.raise_for_status()

        for child in response.json().get('data', {}).get('children', []):
            post = child.get('data', {})
            post_id = post.get('id')
            if post_id in seen_ids or post.get('created_utc', 0) < cutoff_timestamp:
                continue
            if requires_keywords:
                if not keyword_pattern.search(f"{post.get('title', '')} {post.get('selftext', '')}"):
                    continue
            seen_ids.add(post_id)
            posts.append(_post_to_article(post))

        time.sleep(2)

        new_url = f"https://www.reddit.com/r/{name}/new.json?limit=50"
        response = requests.get(new_url, headers=headers, timeout=30)
        response.raise_for_status()

        for child in response.json().get('data', {}).get('children', []):
            post = child.get('data', {})
            post_id = post.get('id')
            if post_id in seen_ids or post.get('created_utc', 0) < cutoff_timestamp:
                continue
            if requires_keywords:
                if not keyword_pattern.search(f"{post.get('title', '')} {post.get('selftext', '')}"):
                    continue
            seen_ids.add(post_id)
            posts.append(_post_to_article(post))

    except requests.exceptions.HTTPError as e:
        code = e.response.status_code
        print(f"    {'Rate limited' if code == 429 else 'Error'} on r/{name}: {e}")
    except Exception as e:
        print(f"    Error fetching r/{name}: {e}")

    return posts


def fetch_reddit_posts(
    lookback_days: int = 30,
    subreddits: list = None,
    seen_ids: set = None,
    keyword_pattern=None,
) -> list[Article]:
    """
    Fetch posts from Reddit using the public JSON API.
    Uses top/month endpoint for 30-day lookback (instead of hot/new).
    Returns list of Article objects for unified processing.
    """
    headers = {'User-Agent': REDDIT_USER_AGENT}
    if seen_ids is None:
        seen_ids = set()
    if keyword_pattern is None:
        keyword_pattern = build_keyword_pattern()
    if subreddits is None:
        subreddits = REDDIT_SUBREDDITS

    all_posts = []

    print(f"Fetching Reddit posts (top posts from last month, {len(subreddits)} subreddits)...")

    for i, name in enumerate(subreddits):
        print(f"  [{i+1}/{len(subreddits)}] Fetching r/{name}...")
        if i > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        posts = fetch_single_subreddit(name, lookback_days, seen_ids, keyword_pattern, headers)
        all_posts.extend(posts)
        print(f"    Found {len(posts)} posts")

    filtered = [p for p in all_posts if _get_score(p) >= MIN_ENGAGEMENT_REDDIT]
    print(f"  Reddit total: {len(all_posts)} posts, {len(filtered)} after engagement filter")
    filtered.sort(key=lambda p: _get_score(p), reverse=True)
    return filtered


def _get_score(article: Article) -> int:
    """Extract Reddit score from article content (stored in a parseable format)."""
    # Score is encoded at the start of content
    try:
        if article.content.startswith("[score:"):
            score_str = article.content.split("]")[0].replace("[score:", "")
            return int(score_str)
    except (ValueError, IndexError):
        pass
    return 0


def _post_to_article(post: dict) -> Article:
    """Convert a Reddit post JSON object to an Article."""
    is_self = post.get('is_self', True)
    external_url = None if is_self else post.get('url')

    permalink = post.get('permalink', '')
    if permalink and not permalink.startswith('http'):
        permalink = f"https://reddit.com{permalink}"

    timestamp = datetime.fromtimestamp(post.get('created_utc', 0), tz=timezone.utc)
    score = post.get('score', 0)
    num_comments = post.get('num_comments', 0)
    subreddit = post.get('subreddit', '')

    # Combine title and body text as content, with metadata prefix for score tracking
    title = post.get('title', '')
    selftext = post.get('selftext', '')
    content_parts = [f"[score:{score}] [comments:{num_comments}] [r/{subreddit}]"]
    if selftext:
        content_parts.append(selftext[:2000])
    if external_url:
        content_parts.append(f"External link: {external_url}")

    return Article(
        title=title,
        url=permalink,
        source=f"Reddit: r/{subreddit}",
        published=timestamp,
        content="\n".join(content_parts),
        source_type="reddit",
    )


if __name__ == "__main__":
    posts = fetch_reddit_posts(lookback_days=30)
    print(f"\n{'='*60}")
    print(f"Found {len(posts)} posts")
    print('='*60)

    for i, post in enumerate(posts[:20], 1):
        print(f"\n[{i}] {post.source}: {post.title}")
        print(f"    {post.published.strftime('%Y-%m-%d %H:%M')}")
        print(f"    {post.url}")
