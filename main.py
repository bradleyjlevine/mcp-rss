import feedparser
import yaml
from datetime import datetime, timedelta
import html
import re
from bs4 import BeautifulSoup
from fastmcp import FastMCP

mcp = FastMCP("RSS Reader")

def articles_to_markdown(articles):
    if not articles:
        return "No recent articles found."
    lines = []
    for article in articles:
        line = f"- **[{article['title']}]({article['link']})** ({article['published']})\n  {article['summary'][:250]}..."
        lines.append(line)
    return "\n".join(lines)

def clean_summary(summary):
    # Unescape HTML entities
    summary = html.unescape(summary)
    # Strip HTML tags
    soup = BeautifulSoup(summary, "html.parser")
    text = soup.get_text()
    # Optionally convert to ASCII only
    text = text.encode('utf-8', errors='ignore').decode('utf-8')
    return text

def parse_yaml_feeds(filepath):
    with open(filepath, 'r') as f:
        feeds = yaml.safe_load(f)
    return feeds

def filter_entries_since(entries, since_dt, per_feed_limit):
    filtered = []
    for entry in entries:
        published = getattr(entry, 'published_parsed', None)
        if not published:
            continue
        entry_dt = datetime(*published[:6])
        if entry_dt >= since_dt:
            filtered.append(entry)
        if len(filtered) >= per_feed_limit:
            break
    return filtered

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
def fetch_feeds(category: str = "Example", limit: int = 20, per_feed_limit: int = 5, since_date: str = None) -> dict:
    return fetch_feeds_impl(category, limit, per_feed_limit, since_date)

def fetch_feeds_impl(category: str = "Example", limit: int = 20, per_feed_limit: int = 5, since_date: str = None) -> dict:
    # Handle since_date parameter (YYYY-mm-dd); default is 7 days ago
    if since_date is None:
        since_dt = datetime.now() - timedelta(days=7)
    else:
        try:
            since_dt = datetime.strptime(since_date, "%Y-%m-%d")
        except Exception:
            return {"error": "Parameter 'since_date' must be in YYYY-mm-dd format."}

    feeds_by_cat = parse_yaml_feeds('feeds.yaml')
    feed_urls = feeds_by_cat.get(category, [])
    if not feed_urls:
        return {"error": f"No RSS feeds found for category '{category}'."}

    all_articles = []
    for url in feed_urls:
        feed = feedparser.parse(url)
        entries = filter_entries_since(feed.entries, since_dt, per_feed_limit)
        for entry in entries:
            # Try to get 'published', 'pubDate', or fallback
            published_str = getattr(entry, 'published', None) or getattr(entry, 'pubDate', None) or ''
            if not published_str:
                # Try common alternatives if needed
                published_str = getattr(entry, 'updated', '')  # For Atom feeds
            all_articles.append({
                'title': getattr(entry, 'title', ''),
                'link': getattr(entry, 'link', ''),
                'summary': clean_summary(getattr(entry, 'summary', '')),
                'published': published_str,
                'source': url
            })

    # Sort by published date (newest first)
    def get_published_dt(article):
        try:
            # Try to parse RFC822 format dates
            return datetime.strptime(article['published'], '%a, %d %b %Y %H:%M:%S %Z')
        except Exception:
            return datetime.min

    all_articles.sort(key=get_published_dt, reverse=True)

    markdown = articles_to_markdown(all_articles[:limit])
    return {'markdown': markdown, 'articles': all_articles[:limit]}  # Optionally return both



if __name__ == "__main__":
    mcp.run(transport="stdio")
