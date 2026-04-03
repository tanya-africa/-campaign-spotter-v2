"""
Gmail Reader - Fetches and parses newsletter emails from Gmail inbox.
Adapted from authoritarianism-digest for campaign opening detection.
Stripped of subscription/feedback management (not needed for scanner).
"""

import base64
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import html2text
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from models import Article
from config import (
    GMAIL_CREDENTIALS_FILE,
    GMAIL_TOKEN_FILE,
    GMAIL_SCOPES,
    CREDENTIALS_DIR,
    DEFAULT_LOOKBACK_DAYS,
)


# Domains to skip when extracting URLs
SKIP_URL_PATTERNS = [
    r'unsubscribe',
    r'manage.?preferences',
    r'email.?settings',
    r'click\.',
    r'track\.',
    r'list-manage\.com',
    r'mailchimp\.com',
    r'twitter\.com',
    r'x\.com',
    r'facebook\.com',
    r'instagram\.com',
    r'linkedin\.com',
    r'mailto:',
    r'tel:',
    r'#$',
]

# Known news domains to prioritize
NEWS_DOMAINS = [
    'nytimes.com', 'washingtonpost.com', 'reuters.com', 'apnews.com',
    'theguardian.com', 'bbc.com', 'npr.org', 'politico.com', 'axios.com',
    'theatlantic.com', 'newyorker.com', 'lawfaremedia.org', 'thebulwark.com',
    'propublica.org', 'vox.com', 'slate.com', 'thedailybeast.com',
]


def extract_substack_url(headers: list, from_addr: str) -> Optional[str]:
    """Extract the post URL from Substack newsletter emails using List-Post header."""
    if '@substack.com' not in from_addr.lower():
        return None

    list_post = get_header(headers, 'List-Post')
    if list_post:
        match = re.search(r'<([^>]+)>', list_post)
        if match:
            return match.group(1)

    return None


def extract_primary_url(html_content: Optional[str], plain_text: str, from_addr: str = "", headers: list = None) -> Optional[str]:
    """Extract the primary article URL from newsletter email content."""
    if headers and from_addr:
        substack_url = extract_substack_url(headers, from_addr)
        if substack_url:
            return substack_url

    urls_found = []

    if html_content:
        soup = BeautifulSoup(html_content, 'html.parser')

        read_more_patterns = [
            r'read\s*(more|full|article|story)',
            r'continue\s*reading',
            r'full\s*(story|article)',
            r'click\s*here\s*to\s*read',
            r'view\s*(online|article|story)',
        ]

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            link_text = link.get_text().lower().strip()

            if not href or href.startswith('#') or href.startswith('mailto:'):
                continue

            should_skip = False
            for pattern in SKIP_URL_PATTERNS:
                if re.search(pattern, href, re.IGNORECASE):
                    should_skip = True
                    break
            if should_skip:
                continue

            for pattern in read_more_patterns:
                if re.search(pattern, link_text, re.IGNORECASE):
                    return href

            urls_found.append(href)

        for url in urls_found:
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower().replace('www.', '')
                for news_domain in NEWS_DOMAINS:
                    if news_domain in domain:
                        return url
            except Exception:
                continue

        for url in urls_found:
            try:
                parsed = urlparse(url)
                if parsed.path and parsed.path != '/':
                    return url
            except Exception:
                continue

    if plain_text:
        url_pattern = r'https?://[^\s<>"\')\]]+[^\s<>"\')\].,]'
        matches = re.findall(url_pattern, plain_text)

        for url in matches:
            should_skip = False
            for pattern in SKIP_URL_PATTERNS:
                if re.search(pattern, url, re.IGNORECASE):
                    should_skip = True
                    break
            if not should_skip:
                return url

    return None


def get_gmail_service():
    """Authenticate and return Gmail API service."""
    creds = None

    CREDENTIALS_DIR.mkdir(exist_ok=True)

    if GMAIL_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN_FILE), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not GMAIL_CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found at {GMAIL_CREDENTIALS_FILE}. "
                    "Please download credentials.json from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(GMAIL_CREDENTIALS_FILE), GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(GMAIL_TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def extract_email_body(payload) -> tuple[str, Optional[str]]:
    """Extract plain text and HTML from email payload."""
    plain_text = ""
    html_content = None

    def process_parts(parts):
        nonlocal plain_text, html_content

        for part in parts:
            mime_type = part.get('mimeType', '')
            body = part.get('body', {})
            data = body.get('data', '')

            if 'parts' in part:
                process_parts(part['parts'])
            elif mime_type == 'text/plain' and data:
                plain_text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            elif mime_type == 'text/html' and data:
                html_content = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

    if 'parts' not in payload:
        body = payload.get('body', {})
        data = body.get('data', '')
        mime_type = payload.get('mimeType', '')

        if data:
            decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            if mime_type == 'text/html':
                html_content = decoded
            else:
                plain_text = decoded
    else:
        process_parts(payload['parts'])

    if not plain_text and html_content:
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        plain_text = h.handle(html_content)

    return plain_text.strip(), html_content


def get_header(headers: list, name: str) -> str:
    """Get a specific header value from email headers."""
    for header in headers:
        if header['name'].lower() == name.lower():
            return header['value']
    return ""


def fetch_emails(lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> list[Article]:
    """Fetch emails from Gmail inbox from the last N days."""
    articles = []
    lookback_hours = lookback_days * 24

    try:
        service = get_gmail_service()

        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        after_timestamp = int(cutoff.timestamp())

        query = f"after:{after_timestamp}"

        print(f"Fetching emails from Gmail (last {lookback_days} days)...")

        # Gmail API paginates at 100 messages per request
        # For 30-day lookback, we may need multiple pages
        all_messages = []
        page_token = None

        while True:
            kwargs = {
                'userId': 'me',
                'q': query,
                'maxResults': 100,
            }
            if page_token:
                kwargs['pageToken'] = page_token

            results = service.users().messages().list(**kwargs).execute()
            messages = results.get('messages', [])
            all_messages.extend(messages)

            page_token = results.get('nextPageToken')
            if not page_token:
                break

            print(f"  Fetching more messages (have {len(all_messages)} so far)...")

        if not all_messages:
            print("  No emails found")
            return articles

        print(f"  Found {len(all_messages)} emails to process...")

        for i, msg_info in enumerate(all_messages):
            if i > 0 and i % 50 == 0:
                print(f"  Processing email {i}/{len(all_messages)}...")

            try:
                message = service.users().messages().get(
                    userId='me',
                    id=msg_info['id'],
                    format='full'
                ).execute()

                payload = message.get('payload', {})
                headers = payload.get('headers', [])

                subject = get_header(headers, 'Subject')
                from_addr = get_header(headers, 'From')
                date_str = get_header(headers, 'Date')

                try:
                    from dateutil import parser
                    pub_date = parser.parse(date_str)
                    if pub_date.tzinfo is None:
                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pub_date = datetime.now(timezone.utc)

                if pub_date < cutoff:
                    continue

                content, raw_html = extract_email_body(payload)

                if not content:
                    continue

                source = from_addr
                if '<' in source:
                    source = source.split('<')[0].strip().strip('"')

                extracted_url = extract_primary_url(raw_html, content, from_addr, headers)
                article_url = extracted_url if extracted_url else f"gmail://message/{msg_info['id']}"

                article = Article(
                    title=subject,
                    url=article_url,
                    source=f"Email: {source}",
                    published=pub_date,
                    content=content,
                    raw_html=raw_html,
                    source_type="gmail",
                )
                articles.append(article)

            except HttpError as e:
                print(f"    Error fetching message: {e}")
                continue

        print(f"  Processed {len(articles)} newsletter emails")

    except FileNotFoundError as e:
        print(f"Gmail setup required: {e}")
        return []
    except HttpError as e:
        print(f"Gmail API error: {e}")
        return []

    return sorted(articles, key=lambda a: a.published, reverse=True)


if __name__ == "__main__":
    emails = fetch_emails(lookback_days=7)
    print("\n--- Sample Emails ---")
    for email in emails[:5]:
        print(f"\n{email.source}: {email.title}")
        print(f"  Published: {email.published}")
        print(f"  Content preview: {email.content[:300]}...")
