import asyncio
import aiohttp
import feedparser
import yaml
from datetime import datetime, timedelta, timezone
import html
import re
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from fastmcp import FastMCP

mcp = FastMCP("RSS Reader")

# Global cache for feeds configuration
_feeds_cache: Optional[Dict] = None
_session: Optional[aiohttp.ClientSession] = None

# Date parsing formats in order of preference
DATE_FORMATS = [
    '%a, %d %b %Y %H:%M:%S %Z',      # RFC 822
    '%a, %d %b %Y %H:%M:%S %z',      # RFC 822 with timezone offset
    '%Y-%m-%dT%H:%M:%S%z',           # ISO 8601 with timezone
    '%Y-%m-%dT%H:%M:%SZ',            # ISO 8601 UTC
    '%Y-%m-%d %H:%M:%S',             # Simple format
    '%Y-%m-%d',                      # Date only
]

# Convert a list of article dictionaries to a markdown-formatted string
# Each article is displayed as a bulleted list item with title, link, published date, and summary preview
def articles_to_markdown(articles):
    if not articles:
        return "No recent articles found."
    lines = []
    for article in articles:
        line = f"- **[{article['title']}]({article['link']})** ({article['published']})\n  {article['summary'][:250]}..."
        lines.append(line)
    return "\n".join(lines)

# Clean and sanitize HTML content from RSS feed summaries
# Removes HTML tags, unescapes entities, and handles encoding issues
# Uses regex for simple cases and BeautifulSoup for complex HTML
def clean_summary(summary: str) -> str:
    if not summary:
        return ""
    
    # Unescape HTML entities
    summary = html.unescape(summary)
    
    # Fast path: if no HTML tags, just return cleaned text
    if '<' not in summary:
        return summary.encode('utf-8', errors='ignore').decode('utf-8')
    
    # Use regex for simple cases (faster than BeautifulSoup)
    simple_tags = re.compile(r'<[^>]+>')
    if not re.search(r'<(script|style|iframe)', summary, re.IGNORECASE):
        text = simple_tags.sub('', summary)
    else:
        # Use BeautifulSoup for complex HTML
        soup = BeautifulSoup(summary, "html.parser")
        text = soup.get_text()
    
    # Clean up whitespace and encode
    text = ' '.join(text.split())
    return text.encode('utf-8', errors='ignore').decode('utf-8')

def get_feeds_config() -> Dict:
    """Get feeds configuration with caching."""
    global _feeds_cache
    if _feeds_cache is None:
        with open('feeds.yaml', 'r') as f:
            _feeds_cache = yaml.safe_load(f)
    return _feeds_cache

def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string using multiple formats, normalize to UTC."""
    if not date_str:
        return None
    
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Convert to UTC if timezone-aware
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except ValueError:
            continue
    
    # Fallback: try feedparser's date parsing
    try:
        import time
        parsed = feedparser._parse_date(date_str)
        if parsed:
            dt = datetime(*parsed[:6])
            # feedparser returns UTC time tuples
            return dt
    except:
        pass
    
    return None

# Filter RSS feed entries to only include those published after a given datetime
# Handles multiple date field formats and timezone conversion
# Returns entries sorted by date (newest first) and limited per feed
def filter_entries_since(entries: List, since_dt: datetime, per_feed_limit: int) -> List:
    """Filter and sort entries by date, respecting per-feed limit."""
    filtered = []
    for entry in entries:
        # Try multiple date fields
        published_parsed = getattr(entry, 'published_parsed', None)
        if published_parsed:
            # feedparser returns UTC time tuples
            entry_dt = datetime(*published_parsed[:6])
        else:
            # Fallback to string parsing
            date_str = (getattr(entry, 'published', '') or 
                       getattr(entry, 'pubDate', '') or 
                       getattr(entry, 'updated', ''))
            entry_dt = parse_date(date_str)
            if not entry_dt:
                continue
        
        # Ensure since_dt is timezone-naive for comparison
        compare_since = since_dt
        if since_dt.tzinfo is not None:
            compare_since = since_dt.astimezone(timezone.utc).replace(tzinfo=None)
        
        if entry_dt >= compare_since:
            filtered.append((entry, entry_dt))
    
    # Sort by date (newest first) and limit
    filtered.sort(key=lambda x: x[1], reverse=True)
    return [entry for entry, _ in filtered[:per_feed_limit]]

async def get_session() -> aiohttp.ClientSession:
    """Get or create aiohttp session."""
    global _session
    if _session is None or _session.closed:
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=10)
        _session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={'User-Agent': 'RSS-MCP-Server/1.0'}
        )
    return _session

# Asynchronously fetch and parse a single RSS feed URL
# Handles HTTP errors, feed parsing warnings, and date filtering
# Returns a list of article dictionaries with cleaned summaries
async def fetch_single_feed(session: aiohttp.ClientSession, url: str, since_dt: datetime, per_feed_limit: int) -> List[Dict]:
    """Fetch and parse a single RSS feed."""
    try:
        async with session.get(url) as response:
            if response.status != 200:
                logging.warning(f"Failed to fetch {url}: HTTP {response.status}")
                return []
            
            content = await response.text()
            feed = feedparser.parse(content)
            
            if feed.bozo and feed.bozo_exception:
                logging.warning(f"Feed parsing warning for {url}: {feed.bozo_exception}")
            
            entries = filter_entries_since(feed.entries, since_dt, per_feed_limit)
            articles = []
            
            for entry in entries:
                published_str = (getattr(entry, 'published', '') or 
                               getattr(entry, 'pubDate', '') or 
                               getattr(entry, 'updated', ''))
                
                articles.append({
                    'title': getattr(entry, 'title', ''),
                    'link': getattr(entry, 'link', ''),
                    'summary': clean_summary(getattr(entry, 'summary', '')),
                    'published': published_str,
                    'source': url,
                    'published_dt': parse_date(published_str)  # For sorting
                })
            
            return articles
            
    except asyncio.TimeoutError:
        logging.error(f"Timeout fetching {url}")
        return []
    except Exception as e:
        logging.error(f"Error fetching {url}: {e}")
        return []

@mcp.tool(
    name="fetch_feeds",
    title="Fetch RSS Feed Articles",
    description=(
        "Fetches articles from configured RSS feeds in a given category, filtered by date. "
        "Parameters include category, maximum returned articles, per-feed limit, and a since_date "
        "in YYYY-mm-dd format. Returns both a Markdown summary and a list of article objects."
    ),
    output_schema={
        "type": "object",
        "properties": {
            "markdown": {
                "type": "string",
                "description": "Markdown-formatted summary of returned articles."
            },
            "articles": {
                "type": "array",
                "description": "List of structured article objects.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "link": {"type": "string"},
                        "summary": {"type": "string"},
                        "published": {"type": "string"},
                        "source": {"type": "string"}
                    },
                    "required": ["title", "link", "published", "source"]
                }
            }
        },
        "required": ["markdown", "articles"]
    }
)
# MCP tool wrapper function that validates parameters and calls the implementation
# Provides the external interface for fetching RSS feeds by category
async def fetch_feeds(category: str = "Example", limit: int = 20, per_feed_limit: int = 5, since_date: str = None) -> dict:
    return await fetch_feeds_impl(category, limit, per_feed_limit, since_date)

# Main implementation for fetching RSS feeds from a specified category
# Fetches multiple feeds concurrently, combines and sorts articles by date
# Returns both markdown summary and structured article data
async def fetch_feeds_impl(category: str = "Example", limit: int = 20, per_feed_limit: int = 5, since_date: str = None) -> dict:
    # Handle since_date parameter (YYYY-mm-dd); default is 7 days ago
    if since_date is None:
        since_dt = datetime.now() - timedelta(days=7)
    else:
        try:
            since_dt = datetime.strptime(since_date, "%Y-%m-%d")
        except Exception:
            return {"error": "Parameter 'since_date' must be in YYYY-mm-dd format."}

    feeds_by_cat = get_feeds_config()
    feed_urls = feeds_by_cat.get(category, [])
    if not feed_urls:
        return {"error": f"No RSS feeds found for category '{category}'."}

    # Fetch all feeds concurrently
    session = await get_session()
    tasks = [fetch_single_feed(session, url, since_dt, per_feed_limit) for url in feed_urls]
    
    try:
        feed_results = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logging.error(f"Error in concurrent feed fetching: {e}")
        return {"error": "Failed to fetch feeds"}
    
    # Combine all articles
    all_articles = []
    for result in feed_results:
        if isinstance(result, list):
            all_articles.extend(result)
        elif isinstance(result, Exception):
            logging.error(f"Feed fetch exception: {result}")
    
    # Sort by published date (newest first), handling None dates
    # Use timezone-naive datetime.min for consistent comparison
    all_articles.sort(
        key=lambda x: x.get('published_dt') or datetime.min.replace(tzinfo=None), 
        reverse=True
    )
    
    # Remove the sorting helper field
    for article in all_articles:
        article.pop('published_dt', None)
    
    # Limit results
    limited_articles = all_articles[:limit]
    markdown = articles_to_markdown(limited_articles)
    
    return {'markdown': markdown, 'articles': limited_articles}



# Cleanup function to properly close aiohttp session on application shutdown
# Prevents resource leaks and ensures graceful termination
async def cleanup():
    """Cleanup resources on shutdown."""
    global _session
    if _session and not _session.closed:
        await _session.close()

if __name__ == "__main__":
    import atexit
    
    # Register cleanup
    # Synchronous wrapper for cleanup function to work with atexit.register
    # Creates new event loop to run async cleanup when program exits
    def sync_cleanup():
        if _session and not _session.closed:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_session.close())
            loop.close()
    
    atexit.register(sync_cleanup)
    mcp.run(transport="stdio")
