"""
Bluesky fetcher for campaign opening detection.
Adapted from authoritarianism-digest with extended lookback and broader search terms.
"""

from datetime import datetime, timedelta, timezone

from models import Article
from social_config import (
    BLUESKY_HANDLE,
    BLUESKY_APP_PASSWORD,
    BLUESKY_HASHTAGS,
    BLUESKY_ACCOUNTS,
    BLUESKY_SEARCH_TERMS,
    MIN_ENGAGEMENT_BLUESKY,
)


def fetch_bluesky_posts(lookback_days: int = 30) -> list[Article]:
    """
    Fetch posts from Bluesky matching our criteria.
    Returns list of Article objects for unified processing.
    """
    try:
        from atproto import Client
    except ImportError:
        print("Error: atproto package not installed. Run: pip install atproto")
        return []

    if not BLUESKY_HANDLE or not BLUESKY_APP_PASSWORD:
        print("Warning: BLUESKY_HANDLE and BLUESKY_APP_PASSWORD not set, skipping Bluesky")
        return []

    client = Client()

    try:
        client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
        print(f"  Authenticated as {BLUESKY_HANDLE}")
    except Exception as e:
        print(f"Error: Failed to authenticate with Bluesky: {e}")
        return []

    cutoff_time = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    all_posts = []
    seen_uris = set()

    print(f"Fetching Bluesky posts (last {lookback_days} days)...")

    # Search by hashtags
    for hashtag in BLUESKY_HASHTAGS:
        print(f"  Searching #{hashtag}...")
        try:
            response = client.app.bsky.feed.search_posts(
                params={'q': f"#{hashtag}", 'limit': 100}
            )
            posts = _process_search_results(response, cutoff_time, seen_uris)
            all_posts.extend(posts)
            print(f"    Found {len(posts)} recent posts")
        except Exception as e:
            print(f"    Error searching #{hashtag}: {e}")

    # Search by terms
    for term in BLUESKY_SEARCH_TERMS:
        print(f"  Searching '{term}'...")
        try:
            response = client.app.bsky.feed.search_posts(
                params={'q': term, 'limit': 100}
            )
            posts = _process_search_results(response, cutoff_time, seen_uris)
            all_posts.extend(posts)
            print(f"    Found {len(posts)} recent posts")
        except Exception as e:
            print(f"    Error searching '{term}': {e}")

    # Fetch from specific accounts
    print(f"  Fetching from {len(BLUESKY_ACCOUNTS)} accounts...")
    for account in BLUESKY_ACCOUNTS:
        try:
            response = client.app.bsky.feed.get_author_feed(
                params={'actor': account, 'limit': 50}
            )
            posts = _process_author_feed(response, cutoff_time, seen_uris)
            all_posts.extend(posts)
        except Exception as e:
            # Don't print every account error — too noisy
            pass

    # Filter by minimum engagement
    filtered = [p for p in all_posts if _get_likes(p) >= MIN_ENGAGEMENT_BLUESKY]

    print(f"  Bluesky total: {len(all_posts)} posts, {len(filtered)} after engagement filter")

    # Sort by engagement
    filtered.sort(key=lambda p: _get_likes(p), reverse=True)

    return filtered


def _get_likes(article: Article) -> int:
    """Extract like count from article content metadata."""
    try:
        if "[likes:" in article.content:
            likes_str = article.content.split("[likes:")[1].split("]")[0]
            return int(likes_str)
    except (ValueError, IndexError):
        pass
    return 0


def _process_search_results(response, cutoff_time, seen_uris) -> list[Article]:
    """Process search results into Article objects."""
    posts = []

    for post_view in response.posts:
        uri = post_view.uri
        if uri in seen_uris:
            continue

        created_at = _parse_timestamp(post_view.record.created_at)
        if created_at < cutoff_time:
            continue

        seen_uris.add(uri)
        article = _post_view_to_article(post_view)
        posts.append(article)

    return posts


def _process_author_feed(response, cutoff_time, seen_uris) -> list[Article]:
    """Process author feed into Article objects."""
    posts = []

    for feed_item in response.feed:
        post_view = feed_item.post
        uri = post_view.uri

        if uri in seen_uris:
            continue

        created_at = _parse_timestamp(post_view.record.created_at)
        if created_at < cutoff_time:
            continue

        seen_uris.add(uri)
        article = _post_view_to_article(post_view)
        posts.append(article)

    return posts


def _post_view_to_article(post_view) -> Article:
    """Convert a Bluesky post view to an Article."""
    record = post_view.record
    author = post_view.author

    # Build URL
    uri_parts = post_view.uri.split('/')
    post_id = uri_parts[-1] if uri_parts else ''
    url = f"https://bsky.app/profile/{author.handle}/post/{post_id}"

    # Extract hashtags
    hashtags = []
    if hasattr(record, 'facets') and record.facets:
        for facet in record.facets:
            for feature in facet.features:
                if hasattr(feature, 'tag'):
                    hashtags.append(feature.tag)

    likes = post_view.like_count or 0
    reposts = post_view.repost_count or 0
    replies = post_view.reply_count or 0
    display_name = author.display_name or author.handle

    # Encode metadata in content for downstream processing
    hashtag_str = ", ".join(f"#{t}" for t in hashtags) if hashtags else ""
    content_parts = [
        f"[likes:{likes}] [reposts:{reposts}] [replies:{replies}]",
        f"Author: {display_name} (@{author.handle})",
        record.text,
    ]
    if hashtag_str:
        content_parts.append(f"Hashtags: {hashtag_str}")

    return Article(
        title=f"@{author.handle}: {record.text[:100]}",
        url=url,
        source=f"Bluesky: @{author.handle}",
        published=_parse_timestamp(record.created_at),
        content="\n".join(content_parts),
        source_type="bluesky",
    )


def _parse_timestamp(ts_string: str) -> datetime:
    """Parse ISO timestamp string to datetime."""
    ts_string = ts_string.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(ts_string)
    except ValueError:
        return datetime.now(timezone.utc)


if __name__ == "__main__":
    posts = fetch_bluesky_posts(lookback_days=7)
    print(f"\n{'='*60}")
    print(f"Found {len(posts)} posts")
    print('='*60)

    for i, post in enumerate(posts[:20], 1):
        print(f"\n[{i}] {post.source}")
        print(f"    {post.published.strftime('%Y-%m-%d %H:%M')}")
        print(f"    {post.title}")
        print(f"    {post.url}")
