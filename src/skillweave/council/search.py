"""Web Search integration for SkillWeave Council.

4 search providers: DuckDuckGo (free, no key), Serper, Tavily, Brave.
Includes: hybrid web+news, relevance reranking, full content fetching via Jina Reader.
"""

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote_plus


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str       # "web" or "news"
    date: str = ""    # ISO date string from result
    full_content: str = ""


@dataclass
class SearchConfig:
    provider: str = "duckduckgo"      # "duckduckgo" | "serper" | "tavily" | "brave"
    time_range: str = "any"           # "30d" | "quarter" | "6mo" | "1yr" | "any"
    max_results: int = 10
    full_content_results: int = 3     # how many results to fetch full content for
    hybrid_search: bool = True        # web + news for DuckDuckGo
    api_key: str | None = None        # for Serper/Tavily/Brave


class WebSearch:
    """Multi-provider web search with time-range support."""

    TIME_RANGE_DAYS = {
        "30d": 30,
        "quarter": 90,
        "6mo": 180,
        "1yr": 365,
        "any": None,
    }

    async def search(self, query: str, config: SearchConfig | None = None) -> str:
        """Execute search and return formatted context string for council prompts."""
        if config is None:
            config = SearchConfig()
        config = self._apply_defaults(config)

        try:
            results = await asyncio.wait_for(
                self._search_provider(query, config),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            return "SEARCH ERROR: Search timed out after 60 seconds."

        if not results:
            return "No search results found for this query."

        # Time-range filter (post-hoc for providers without native support)
        if config.time_range != "any":
            results = self._filter_by_time_range(results, config.time_range)

        # Relevance reranking
        results = self._rerank(results, query)

        # Fetch full content for top N
        if config.full_content_results > 0:
            results = await self._fetch_full_content(results[:config.full_content_results]) + results[config.full_content_results:]

        return self._format_context(results, config.time_range)

    async def _search_provider(self, query: str, config: SearchConfig) -> list[SearchResult]:
        """Dispatch to the configured search provider."""
        provider = config.provider.lower()
        if provider == "duckduckgo":
            return await self._search_duckduckgo(query, config)
        elif provider == "serper":
            return await self._search_serper(query, config)
        elif provider == "tavily":
            return await self._search_tavily(query, config)
        elif provider == "brave":
            return await self._search_brave(query, config)
        else:
            return await self._search_duckduckgo(query, config)  # fallback

    async def _search_duckduckgo(self, query: str, config: SearchConfig) -> list[SearchResult]:
        """DuckDuckGo search — free, no API key needed."""
        results = []
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                # Time limit mapping for DDG
                timelimit_map = {"30d": "m", "quarter": "m", "6mo": "w", "1yr": "y", "any": None}
                timelimit = timelimit_map.get(config.time_range)

                # Web search
                loop = asyncio.get_event_loop()
                web_results = await loop.run_in_executor(
                    None,
                    lambda: list(ddgs.text(query, max_results=config.max_results, timelimit=timelimit))
                )
                for r in web_results:
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        snippet=r.get("body", ""),
                        source="web",
                        date=r.get("date", ""),
                    ))

                # News search (hybrid)
                if config.hybrid_search:
                    news_results = await loop.run_in_executor(
                        None,
                        lambda: list(ddgs.news(query, max_results=config.max_results, timelimit=timelimit))
                    )
                    for r in news_results:
                        results.append(SearchResult(
                            title=r.get("title", ""),
                            url=r.get("url", ""),
                            snippet=r.get("body", r.get("excerpt", "")),
                            source="news",
                            date=r.get("date", ""),
                        ))

        except ImportError:
            results.append(SearchResult(
                title="DuckDuckGo Search Unavailable",
                url="",
                snippet="Install duckduckgo_search: pip install duckduckgo-search",
                source="error",
            ))
        except Exception as e:
            results.append(SearchResult(
                title="Search Error",
                url="",
                snippet=str(e),
                source="error",
            ))

        return results

    async def _search_serper(self, query: str, config: SearchConfig) -> list[SearchResult]:
        """Serper.dev — Google search results. Requires API key."""
        if not config.api_key:
            return [SearchResult(title="Serper Error", url="", snippet="API key required. Set in config or SERPER_API_KEY env.", source="error")]

        import json, urllib.request
        results = []
        try:
            body = json.dumps({"q": query, "num": config.max_results}).encode()
            req = urllib.request.Request(
                "https://google.serper.dev/search",
                data=body,
                headers={"X-API-KEY": config.api_key, "Content-Type": "application/json"}
            )
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=15))
            data = json.loads(resp.read())

            for r in data.get("organic", []):
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("link", ""),
                    snippet=r.get("snippet", ""),
                    source="web",
                    date=r.get("date", ""),
                ))
        except Exception as e:
            results.append(SearchResult(title="Serper Error", url="", snippet=str(e), source="error"))
        return results

    async def _search_tavily(self, query: str, config: SearchConfig) -> list[SearchResult]:
        """Tavily — purpose-built for LLMs. Requires API key."""
        if not config.api_key:
            return [SearchResult(title="Tavily Error", url="", snippet="API key required.", source="error")]

        import json, urllib.request
        results = []
        try:
            body = json.dumps({
                "query": query,
                "max_results": config.max_results,
                "search_depth": "advanced",
                "include_raw_content": False,
            }).encode()
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=body,
                headers={"Content-Type": "application/json", "api-key": config.api_key} if "api-key" in config.api_key else {"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"}
            )
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=15))
            data = json.loads(resp.read())

            for r in data.get("results", []):
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", ""),
                    source="web",
                ))
        except Exception as e:
            results.append(SearchResult(title="Tavily Error", url="", snippet=str(e), source="error"))
        return results

    async def _search_brave(self, query: str, config: SearchConfig) -> list[SearchResult]:
        """Brave Search — privacy-focused. Requires API key."""
        if not config.api_key:
            return [SearchResult(title="Brave Error", url="", snippet="API key required.", source="error")]

        import json, urllib.request
        results = []
        try:
            url = f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(query)}&count={config.max_results}"
            req = urllib.request.Request(url, headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": config.api_key,
            })
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=15))
            data = json.loads(resp.read())

            for r in data.get("web", {}).get("results", []):
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("description", ""),
                    source="web",
                    date=r.get("page_age", ""),
                ))
        except Exception as e:
            results.append(SearchResult(title="Brave Error", url="", snippet=str(e), source="error"))
        return results

    def _filter_by_time_range(self, results: list[SearchResult], time_range: str) -> list[SearchResult]:
        """Post-hoc date filter for providers without native time range support."""
        days = self.TIME_RANGE_DAYS.get(time_range)
        if days is None:
            return results

        cutoff = datetime.now() - timedelta(days=days)
        filtered = []
        for r in results:
            if r.date:
                try:
                    # Try ISO format or "X days ago" etc.
                    date_str = r.date.strip()
                    if "ago" in date_str.lower():
                        # "3 days ago", "1 month ago" — assume recent enough
                        filtered.append(r)
                        continue
                    # Try common date formats
                    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%b %d, %Y", "%B %d, %Y"]:
                        try:
                            parsed = datetime.strptime(date_str[:10] if len(date_str) >= 10 else date_str, fmt)
                            if parsed >= cutoff:
                                filtered.append(r)
                            break
                        except ValueError:
                            continue
                except Exception:
                    filtered.append(r)  # can't parse → include by default
            else:
                filtered.append(r)  # no date → include (assume recent)
        return filtered

    def _rerank(self, results: list[SearchResult], query: str) -> list[SearchResult]:
        """Relevance reranking by token overlap scoring."""
        query_tokens = set(query.lower().split())

        def score(r: SearchResult) -> float:
            title_tokens = set(r.title.lower().split())
            snippet_tokens = set(r.snippet.lower().split())

            title_overlap = len(title_tokens & query_tokens) / max(len(title_tokens), 1)
            snippet_overlap = len(snippet_tokens & query_tokens) / max(len(snippet_tokens), 1)

            # URL authority bonus
            url_bonus = 0.0
            if any(domain in r.url for domain in [".gov", ".edu", ".org", "wikipedia.org", "github.com"]):
                url_bonus = 0.15

            # Freshness bonus for news
            freshness = 0.0
            if r.source == "news":
                freshness = 0.1

            return (title_overlap * 0.4) + (snippet_overlap * 0.35) + url_bonus + freshness

        scored = [(score(r), r) for r in results]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored]

    async def _fetch_full_content(self, results: list[SearchResult]) -> list[SearchResult]:
        """Fetch full article content via Jina Reader."""
        import urllib.request

        async def fetch_one(r: SearchResult) -> SearchResult:
            if not r.url:
                return r
            try:
                jina_url = f"https://r.jina.ai/{r.url}"
                req = urllib.request.Request(jina_url, headers={"Accept": "text/plain"})
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=25))
                content = resp.read().decode("utf-8", errors="replace")
                if len(content) > 500:
                    r.full_content = content[:2000]
            except Exception:
                pass
            return r

        tasks = [fetch_one(r) for r in results]
        return await asyncio.gather(*tasks)

    def _format_context(self, results: list[SearchResult], time_range: str) -> str:
        """Format search results as context string for council prompts."""
        lines = [f"Web Search Results (time range: {time_range}):\n"]
        for i, r in enumerate(results[:10], 1):
            content = r.full_content if r.full_content else r.snippet
            if len(content) > 500:
                content = content[:500] + "..."
            date_info = f" [{r.date}]" if r.date else ""
            lines.append(f"Result {i}: {r.title} | {r.url}{date_info}\n  {content}\n")
        return "\n".join(lines)

    def _apply_defaults(self, config: SearchConfig) -> SearchConfig:
        """Apply defaults from environment if not set."""
        import os
        if not config.api_key:
            if config.provider == "serper":
                config.api_key = os.environ.get("SERPER_API_KEY")
            elif config.provider == "tavily":
                config.api_key = os.environ.get("TAVILY_API_KEY")
            elif config.provider == "brave":
                config.api_key = os.environ.get("BRAVE_API_KEY")
        return config
