# RSS MCP Server

An MCP (Model Context Protocol) server that fetches and processes RSS feeds, returning them as structured data and formatted markdown. Built with FastMCP and designed for efficient concurrent feed processing.

## Features

- **Concurrent Feed Processing**: Fetches multiple RSS feeds simultaneously using asyncio
- **Date-based Filtering**: Filter articles by publication date (default: last 7 days)
- **Category Organization**: Organize feeds by categories in YAML configuration
- **HTML Content Cleaning**: Automatically strips HTML tags and cleans article summaries
- **Robust Date Parsing**: Handles multiple date formats (RFC 822, ISO 8601, etc.)
- **Rate Limiting**: Built-in connection limits and timeouts for reliable fetching
- **Caching**: In-memory configuration caching for better performance

## Tool Functions

### `fetch_feeds`

Fetches articles from configured RSS feeds in a specified category.

**Parameters:**
- `category` (str, default: "Example"): The feed category to fetch from
- `limit` (int, default: 20): Maximum number of articles to return across all feeds
- `per_feed_limit` (int, default: 5): Maximum number of articles to fetch from each individual feed
- `since_date` (str, optional): Filter articles since this date in YYYY-MM-DD format (default: 7 days ago)

**Returns:**
- `markdown`: Formatted markdown summary of articles
- `articles`: Array of structured article objects containing:
  - `title`: Article title
  - `link`: Article URL
  - `summary`: Cleaned article summary (HTML stripped, max 250 chars)
  - `published`: Publication date string
  - `source`: Original RSS feed URL

## Configuration

### feeds.yaml

The `feeds.yaml` file organizes RSS feeds by category. Each category contains a list of RSS feed URLs.

**Structure:**
```yaml
CategoryName:
  - "https://example.com/feed.xml"
  - "https://another-example.com/rss"

AnotherCategory:
  - "https://feed1.com/rss"
  - "https://feed2.com/atom.xml"
```

**Example Configuration:**
```yaml
CyberSecurity:
  - "https://krebsonsecurity.com/feed/"
  - "https://www.cloudvulndb.org/rss/feed.xml"
  - "https://www.schneier.com/feed/atom/"
  - "https://www.darkreading.com/rss.xml"

Developer:
  - "https://feed.infoq.com/"
  - "https://stackoverflow.blog/feed/"
  - "https://aws.amazon.com/blogs/aws/feed/"

ServiceStatus:
  - "https://status.anthropic.com/history.rss"
  - "https://status.openai.com/"
  - "https://www.cloudflarestatus.com/history.rss"
```

**Configuration Guidelines:**
- Use descriptive category names (CamelCase recommended)
- Include the full URL with protocol (http:// or https://)
- Test feed URLs to ensure they're valid RSS/Atom feeds
- Group related feeds logically by topic or purpose
- Consider feed update frequency when grouping

## Installation & Setup

### Prerequisites
- Python 3.11 or higher
- uv package manager (recommended) or pip

### Local Development
```bash
# Clone the repository
git clone <repository-url>
cd rss

# Install dependencies with uv
uv sync

# Or with pip
pip install -r requirements.txt

# Configure your feeds
cp feeds.yaml.example feeds.yaml
# Edit feeds.yaml with your desired RSS feeds

# Run the MCP server
uv run main.py
# Or with python
python main.py
```

### Docker Deployment
```bash
# Build the Docker image
docker build -t rss-mcp-server .

# Run the container
docker run -v $(pwd)/feeds.yaml:/app/feeds.yaml rss-mcp-server
```

## Dependencies

- **aiohttp**: Async HTTP client for concurrent feed fetching
- **feedparser**: RSS/Atom feed parsing
- **fastmcp**: MCP server framework
- **pyyaml**: YAML configuration parsing
- **beautifulsoup4**: HTML content cleaning

## Usage Examples

### Fetch Recent CyberSecurity Articles
```python
result = await fetch_feeds(
    category="CyberSecurity",
    limit=10,
    per_feed_limit=3,
    since_date="2024-01-01"
)
```

### Get Developer News from Last 30 Days
```python
result = await fetch_feeds(
    category="Developer", 
    limit=15,
    since_date="2023-12-01"
)
```

## Architecture

The server uses an efficient async architecture:
- **Connection Pooling**: Reuses HTTP connections with configurable limits
- **Concurrent Processing**: Fetches all feeds in a category simultaneously  
- **Smart Caching**: Caches feed configuration and HTTP sessions
- **Error Handling**: Graceful degradation when individual feeds fail
- **Resource Cleanup**: Automatic session cleanup on shutdown

## Logging

The server provides detailed logging for:
- Failed HTTP requests with status codes
- Feed parsing warnings for malformed XML
- Timeout and connection errors
- Date parsing fallbacks
