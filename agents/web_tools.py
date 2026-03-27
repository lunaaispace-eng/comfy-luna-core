"""Web access tools for Luna Core agents.

Provides web_search and web_fetch tools that require user approval
before each execution. Uses DuckDuckGo for search and aiohttp for fetching.
"""

import json
import logging
import re
from typing import List
from urllib.parse import quote_plus

from .tools import ToolDefinition, ToolParameter

logger = logging.getLogger("luna_core.web_tools")


def setup_web_tools() -> List[ToolDefinition]:
    """Create web access tools. All require user approval."""
    return [
        _make_web_search(),
        _make_web_fetch(),
    ]


# ---------------------------------------------------------------------------
# Tool: web_search
# ---------------------------------------------------------------------------

def _make_web_search() -> ToolDefinition:
    async def handler(query: str, max_results: int = 5) -> str:
        import aiohttp

        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return json.dumps({"error": f"Search failed with status {resp.status}"})
                    html = await resp.text()
        except Exception as e:
            return json.dumps({"error": f"Search request failed: {e}"})

        # Parse results from DuckDuckGo HTML
        results = _parse_ddg_results(html, max_results)

        if not results:
            return json.dumps({
                "query": query,
                "results": [],
                "note": "No results found. Try different search terms.",
            })

        return json.dumps({
            "query": query,
            "count": len(results),
            "results": results,
        })

    return ToolDefinition(
        name="web_search",
        description="Search the web for information. Useful for finding ComfyUI node documentation, workflow guides, model details, or troubleshooting specific errors. Requires user approval before each search.",
        parameters=[
            ToolParameter(name="query", type="string",
                          description="Search query (e.g. 'ComfyUI WAN video workflow setup', 'FLUX model recommended settings').",
                          required=True),
            ToolParameter(name="max_results", type="integer",
                          description="Maximum number of results to return (default 5, max 10).",
                          required=False),
        ],
        handler=handler,
        requires_approval=True,
    )


def _parse_ddg_results(html: str, max_results: int) -> list:
    """Parse search results from DuckDuckGo HTML response."""
    results = []

    # Find result blocks — DuckDuckGo wraps each in <div class="result...">
    # Extract title, URL, and snippet
    result_pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL
    )

    for match in result_pattern.finditer(html):
        if len(results) >= min(max_results, 10):
            break

        url = match.group(1)
        title = _strip_html(match.group(2))
        snippet = _strip_html(match.group(3))

        # DuckDuckGo redirects through uddg param
        if "uddg=" in url:
            from urllib.parse import unquote, parse_qs, urlparse
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if "uddg" in params:
                url = unquote(params["uddg"][0])

        if title and url:
            results.append({
                "title": title.strip(),
                "url": url.strip(),
                "snippet": snippet.strip() if snippet else "",
            })

    return results


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r'<[^>]+>', '', text).strip()


# ---------------------------------------------------------------------------
# Tool: web_fetch
# ---------------------------------------------------------------------------

def _make_web_fetch() -> ToolDefinition:
    async def handler(url: str, extract_text: bool = True) -> str:
        import aiohttp

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        return json.dumps({"error": f"Fetch failed with status {resp.status}", "url": url})

                    content_type = resp.headers.get("Content-Type", "")

                    # Handle JSON responses directly
                    if "application/json" in content_type:
                        try:
                            data = await resp.json()
                            text = json.dumps(data, indent=2)
                            # Cap size
                            if len(text) > 8000:
                                text = text[:8000] + "\n... (truncated)"
                            return json.dumps({"url": url, "type": "json", "content": text})
                        except Exception:
                            pass

                    # Only fetch text content
                    if not any(t in content_type for t in ("text/", "application/json", "application/xml")):
                        return json.dumps({
                            "error": f"Non-text content type: {content_type}",
                            "url": url,
                        })

                    html = await resp.text()

        except Exception as e:
            return json.dumps({"error": f"Fetch failed: {e}", "url": url})

        if extract_text:
            text = _extract_readable_text(html)
        else:
            text = html

        # Cap response size
        MAX_CHARS = 6000
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + "\n... (truncated)"

        return json.dumps({
            "url": url,
            "length": len(text),
            "content": text,
        })

    return ToolDefinition(
        name="web_fetch",
        description="Fetch and read a web page. Returns the text content of the page. Use web_search first to find relevant URLs, then web_fetch to read specific pages. Requires user approval before each fetch.",
        parameters=[
            ToolParameter(name="url", type="string",
                          description="The full URL to fetch (e.g. 'https://docs.comfy.org/...').",
                          required=True),
            ToolParameter(name="extract_text", type="boolean",
                          description="If true (default), strips HTML and returns readable text. If false, returns raw HTML.",
                          required=False),
        ],
        handler=handler,
        requires_approval=True,
    )


def _extract_readable_text(html: str) -> str:
    """Extract readable text from HTML, removing scripts, styles, and nav."""
    # Remove script and style blocks
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<header[^>]*>.*?</header>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Convert common elements to readable format
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?p[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?div[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n## \1\n', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<pre[^>]*>(.*?)</pre>', r'\n```\n\1\n```\n', text, flags=re.DOTALL | re.IGNORECASE)

    # Strip remaining tags
    text = re.sub(r'<[^>]+>', '', text)

    # Clean up whitespace
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'&#39;', "'", text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)

    lines = [line.strip() for line in text.split('\n')]
    # Remove very short lines (likely navigation remnants)
    lines = [line for line in lines if len(line) > 2 or line == '']

    return '\n'.join(lines).strip()
