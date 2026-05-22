"""
Web Search MCP Server — Web search and page fetching for the agent.

Supports multiple search backends (configurable via env var):
  - Exa (recommended — semantic search designed for AI agents)
  - Tavily (good for agent use)
  - Brave Search API
  - SerpAPI (Google)

Registered in mcp_config.json as "WebSearchMCP".
"""

import os
import sys
import json

import _env_bridge  # noqa: F401 — load env vars from parent process bridge file

from mcp.server.fastmcp import FastMCP

# Fix UTF-8 encoding for Windows
if sys.platform == "win32":
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

mcp = FastMCP("WebSearchMCP")

# Search provider config
SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "exa")  # exa | tavily | brave | serpapi
EXA_API_KEY = os.getenv("EXA_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")


@mcp.tool()
def web_search(query: str, num_results: int = 5) -> dict:
    """
    Search the web for information.

    Args:
        query: The search query string
        num_results: Number of results to return (default 5, max 10)
    """
    num_results = min(max(num_results, 1), 10)

    try:
        if SEARCH_PROVIDER == "exa" and EXA_API_KEY:
            return _search_exa(query, num_results)
        elif SEARCH_PROVIDER == "tavily" and TAVILY_API_KEY:
            return _search_tavily(query, num_results)
        elif SEARCH_PROVIDER == "brave" and BRAVE_API_KEY:
            return _search_brave(query, num_results)
        elif SEARCH_PROVIDER == "serpapi" and SERPAPI_KEY:
            return _search_serpapi(query, num_results)
        else:
            # Auto-detect: try whichever key is available
            if EXA_API_KEY:
                return _search_exa(query, num_results)
            elif TAVILY_API_KEY:
                return _search_tavily(query, num_results)
            elif BRAVE_API_KEY:
                return _search_brave(query, num_results)
            elif SERPAPI_KEY:
                return _search_serpapi(query, num_results)
            return {
                "success": False,
                "error": "No search provider configured. Set one of: EXA_API_KEY, TAVILY_API_KEY, BRAVE_SEARCH_API_KEY, SERPAPI_KEY",
            }
    except Exception as e:
        return {"success": False, "error": f"Search failed: {str(e)}"}


@mcp.tool()
def fetch_webpage(url: str, max_chars: int = 10000) -> dict:
    """
    Fetch a webpage and extract its text content.

    Args:
        url: The URL to fetch
        max_chars: Maximum characters to return (default 10000)
    """
    import httpx

    try:
        max_chars = min(max(max_chars, 500), 50000)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ClingySOCKs-Agent/1.0)"
        }
        
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        
        if "text/html" in content_type:
            text = _extract_text_from_html(resp.text)
        else:
            text = resp.text

        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[Content truncated...]"

        return {
            "success": True,
            "url": url,
            "content": text,
            "length": len(text),
        }
    except Exception as e:
        return {"success": False, "error": f"Fetch failed: {str(e)}", "url": url}


# ─── Search Provider Implementations ─────────────────

def _search_exa(query: str, num_results: int) -> dict:
    """Search using Exa API (semantic search, best for AI agents)."""
    import httpx

    with httpx.Client(timeout=15) as client:
        resp = client.post(
            "https://api.exa.ai/search",
            headers={
                "x-api-key": EXA_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "num_results": num_results,
                "type": "auto",  # auto-detect: keyword vs neural
                "contents": {
                    "text": {"max_characters": 1000},
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()

    results = []
    for r in data.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("text", "")[:500],
            "published_date": r.get("publishedDate", ""),
            "score": r.get("score", 0),
        })

    return {
        "success": True,
        "query": query,
        "results": results,
        "count": len(results),
        "provider": "exa",
    }


def _search_tavily(query: str, num_results: int) -> dict:
    """Search using Tavily API (best for AI agents)."""
    import httpx

    with httpx.Client(timeout=15) as client:
        resp = client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": num_results,
                "search_depth": "basic",
                "include_answer": True,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    results = []
    for r in data.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", "")[:500],
        })

    return {
        "success": True,
        "query": query,
        "answer": data.get("answer", ""),
        "results": results,
        "count": len(results),
    }


def _search_brave(query: str, num_results: int) -> dict:
    """Search using Brave Search API."""
    import httpx

    with httpx.Client(timeout=15) as client:
        resp = client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_API_KEY,
            },
            params={"q": query, "count": num_results},
        )
        resp.raise_for_status()
        data = resp.json()

    results = []
    for r in data.get("web", {}).get("results", []):
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("description", "")[:500],
        })

    return {
        "success": True,
        "query": query,
        "results": results,
        "count": len(results),
    }


def _search_serpapi(query: str, num_results: int) -> dict:
    """Search using SerpAPI (Google results)."""
    import httpx

    with httpx.Client(timeout=15) as client:
        resp = client.get(
            "https://serpapi.com/search",
            params={
                "api_key": SERPAPI_KEY,
                "q": query,
                "num": num_results,
                "engine": "google",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    results = []
    for r in data.get("organic_results", []):
        results.append({
            "title": r.get("title", ""),
            "url": r.get("link", ""),
            "snippet": r.get("snippet", "")[:500],
        })

    return {
        "success": True,
        "query": query,
        "results": results,
        "count": len(results),
    }


# ─── HTML Text Extraction ────────────────────────────

def _extract_text_from_html(html: str) -> str:
    """Extract readable text from HTML, removing scripts/styles."""
    import re

    # Remove script and style elements
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<footer[^>]*>.*?</footer>", "", html, flags=re.DOTALL | re.IGNORECASE)

    # Replace common block elements with newlines
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</(p|div|h[1-6]|li|tr|blockquote)>", "\n", html, flags=re.IGNORECASE)

    # Strip remaining tags
    text = re.sub(r"<[^>]+>", " ", html)

    # Decode common HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")

    # Clean up whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    return text.strip()


if __name__ == "__main__":
    mcp.run()
