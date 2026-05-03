"""Web Search integration for SkillWeave Council.

5 search providers:
- DuckDuckGo Lite (free, no key, requests-based HTML parsing)
- Serper (Google results via API key)
- Tavily (LLM-optimized search via API key)
- Brave (privacy-focused via API key)
- Perplexity (AI-powered search with recency filter via API key)

Includes: relevance reranking, full content fetching via Jina Reader.
"""

import asyncio
import json
import os
import re
import time
import urllib.request
import urllib.error
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
    provider: str = "duckduckgo"      # "duckduckgo" | "serper" | "tavily" | "brave" | "perplexity"
    time_range: str = "any"           # "30d" | "quarter" | "6mo" | "1yr" | "any"
    max_results: int = 10
    full_content_results: int = 3     # how many results to fetch full content for
    hybrid_search: bool = True        # web + news for DuckDuckGo
    api_key: str | None = None


class WebSearch:
    """Multi-provider web search with time-range support."""

    TIME_RANGE_DAYS = {
        "30d": 30,
        "quarter": 90,
        "6mo": 180,
        "1yr": 365,
        "any": None,
    }

    PERPLEXITY_TIME_MAP = {
        "30d": "month",
        "quarter": "month",
        "6mo": "week",     # Perplexity only supports day/week/month/year
        "1yr": "year",
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
        elif provider == "perplexity":
            return await self._search_perplexity(query, config)
        else:
            return await self._search_duckduckgo(query, config)

    # ── DuckDuckGo Lite (requests-based, no duckduckgo_search package) ───

    async def _search_duckduckgo(self, query: str, config: SearchConfig) -> list[SearchResult]:
        """DuckDuckGo via HTML instant answer API — free, no API key, no external package."""
        results = []
        try:
            loop = asyncio.get_event_loop()
            # Use DuckDuckGo Lite HTML endpoint
            encoded = quote_plus(query)
            url = f"https://lite.duckduckgo.com/lite/?q={encoded}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "SkillWeave-Council/0.8 (https://github.com/typelicious/SkillWeave)"
            })
            resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=15))
            html = resp.read().decode("utf-8", errors="replace")

            # Parse HTML results
            results = self._parse_duckduckgo_lite(html)

        except urllib.error.HTTPError as e:
            results.append(SearchResult(
                title=f"DuckDuckGo Error: HTTP {e.code}",
                url="",
                snippet=str(e),
                source="error",
            ))
        except Exception as e:
            results.append(SearchResult(
                title="DuckDuckGo Search Failed",
                url="",
                snippet=f"DuckDuckGo search unavailable: {e}",
                source="error",
            ))

        return results if results else [SearchResult(
            title="DuckDuckGo Search Failed",
            url="",
            snippet="DuckDuckGo returned no results. Try another provider or rephrase query.",
            source="error",
        )]

    def _parse_duckduckgo_lite(self, html: str) -> list[SearchResult]:
        """Parse DuckDuckGo Lite HTML results."""
        results = []
        # DDG Lite: result blocks are <a class="result-link"> with sibling <td class="result-snippet">
        # Pattern: <a[^>]*class="[^"]*result-link[^"]*"[^>]*href="([^"]*)"[^>]*>(.*?)</a>
        links = re.findall(
            r'<a[^>]*class="[^"]*result-link[^"]*"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )
        snippets = re.findall(
            r'<td[^>]*class="[^"]*result-snippet[^"]*"[^>]*>(.*?)</td>',
            html, re.DOTALL
        )
        for i, (href, title_html) in enumerate(links):
            url = href
            if "uddg=" in url:
                from urllib.parse import unquote
                real_match = re.search(r'uddg=([^&]+)', url)
                if real_match:
                    url = unquote(real_match.group(1))
            title = re.sub(r'<[^>]+>', '', title_html).strip()
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            if title:
                results.append(SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet[:500],
                    source="web",
                ))
        return results

    # ── Serper ────────────────────────────────────────────────────────

    async def _search_serper(self, query: str, config: SearchConfig) -> list[SearchResult]:
        """Serper.dev — Google search results. Requires API key."""
        if not config.api_key:
            return [SearchResult(title="Serper Error", url="", snippet="SERPER_API_KEY not set.", source="error")]

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

    # ── Tavily ────────────────────────────────────────────────────────

    async def _search_tavily(self, query: str, config: SearchConfig) -> list[SearchResult]:
        """Tavily — purpose-built for LLMs. Requires API key."""
        if not config.api_key:
            return [SearchResult(title="Tavily Error", url="", snippet="TAVILY_API_KEY not set.", source="error")]

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
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"}
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

    # ── Brave ─────────────────────────────────────────────────────────

    async def _search_brave(self, query: str, config: SearchConfig) -> list[SearchResult]:
        """Brave Search — privacy-focused. Requires API key."""
        if not config.api_key:
            return [SearchResult(title="Brave Error", url="", snippet="BRAVE_API_KEY not set.", source="error")]

        results = []
        try:
            url = f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(query)}&count={config.max_results}"
            req = urllib.request.Request(url, headers={
                "Accept": "application/json",
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

    # ── Perplexity ────────────────────────────────────────────────────

    async def _search_perplexity(self, query: str, config: SearchConfig) -> list[SearchResult]:
        """Perplexity AI — search-enabled chat completions. Requires PERPLEXITY_API_KEY."""
        if not config.api_key:
            return [SearchResult(title="Perplexity Error", url="", snippet="PERPLEXITY_API_KEY not set.", source="error")]

        results = []
        try:
            body = {
                "model": "sonar-pro",
                "messages": [
                    {"role": "system", "content": "Search the web and provide results. Return concise summaries with URLs."},
                    {"role": "user", "content": query},
                ],
                "search_recency_filter": self.PERPLEXITY_TIME_MAP.get(config.time_range),
                "max_tokens": 2000,
                "temperature": 0.2,
                "return_related_questions": False,
            }
            # Remove None values
            body = {k: v for k, v in body.items() if v is not None}

            data = json.dumps(body).encode()
            req = urllib.request.Request(
                "https://api.perplexity.ai/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config.api_key}",
                }
            )
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=30))
            result = json.loads(resp.read())

            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            citations = result.get("citations", [])

            # Parse citations into SearchResults
            for i, citation in enumerate(citations[:config.max_results]):
                results.append(SearchResult(
                    title=f"Source {i+1}",
                    url=citation,
                    snippet=f"Referenced in Perplexity search results",
                    source="web",
                ))

            # Add the synthesized answer as a primary result
            if content:
                results.insert(0, SearchResult(
                    title=f"Perplexity: {query[:80]}",
                    url="",
                    snippet=content[:1000],
                    source="web",
                ))

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            results.append(SearchResult(
                title=f"Perplexity Error: HTTP {e.code}",
                url="",
                snippet=f"Perplexity API returned {e.code}: {error_body}",
                source="error",
            ))
        except Exception as e:
            results.append(SearchResult(
                title="Perplexity Error",
                url="",
                snippet=str(e),
                source="error",
            ))
        return results

    # ── Helpers ───────────────────────────────────────────────────────

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
                    date_str = r.date.strip()
                    if "ago" in date_str.lower():
                        filtered.append(r)
                        continue
                    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%b %d, %Y", "%B %d, %Y"]:
                        try:
                            parsed = datetime.strptime(date_str[:10] if len(date_str) >= 10 else date_str, fmt)
                            if parsed >= cutoff:
                                filtered.append(r)
                            break
                        except ValueError:
                            continue
                except Exception:
                    filtered.append(r)
            else:
                filtered.append(r)
        return filtered

    def _rerank(self, results: list[SearchResult], query: str) -> list[SearchResult]:
        """Relevance reranking by token overlap scoring."""
        query_tokens = set(query.lower().split())

        def score(r: SearchResult) -> float:
            title_tokens = set(r.title.lower().split())
            snippet_tokens = set(r.snippet.lower().split())

            title_overlap = len(title_tokens & query_tokens) / max(len(title_tokens), 1)
            snippet_overlap = len(snippet_tokens & query_tokens) / max(len(snippet_tokens), 1)

            url_bonus = 0.0
            if any(domain in r.url for domain in [".gov", ".edu", ".org", "wikipedia.org", "github.com"]):
                url_bonus = 0.15

            freshness = 0.1 if r.source == "news" else 0.0

            return (title_overlap * 0.4) + (snippet_overlap * 0.35) + url_bonus + freshness

        scored = [(score(r), r) for r in results]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored]

    async def _fetch_full_content(self, results: list[SearchResult]) -> list[SearchResult]:
        """Fetch full article content via Jina Reader."""
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
        env_map = {
            "serper": "SERPER_API_KEY",
            "tavily": "TAVILY_API_KEY",
            "brave": "BRAVE_API_KEY",
            "perplexity": "PERPLEXITY_API_KEY",
        }
        if not config.api_key and config.provider in env_map:
            config.api_key = os.environ.get(env_map[config.provider])
        return config
