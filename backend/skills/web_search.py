"""
web_search.py — built-in Skill

Provides two search modes via DuckDuckGo (no API key required):
  - "search" (default): general web search
  - "news": dedicated news search — returns articles from news sources
    with publication dates, much better for recent/latest information

Requires: duckduckgo-search (already in requirements.txt)
"""

from skills.base import Skill


class WebSearchSkill(Skill):
    name = "web_search"
    description = (
        "Search the web using DuckDuckGo. Supports two modes:\n"
        "- mode='search': General web search for facts, documentation, tutorials, etc.\n"
        "- mode='news': Search recent news articles from news sources, "
        "returns results with publication dates. Best for current events and latest information.\n"
        "Use the timelimit parameter ('d'=day, 'w'=week, 'm'=month) to filter by recency."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query. Be specific for better results.",
            },
            "mode": {
                "type": "string",
                "description": (
                    "'search' for general web search, 'news' for news articles. "
                    "Use 'news' when the user asks about latest/recent events or news."
                ),
                "enum": ["search", "news"],
                "default": "search",
            },
            "timelimit": {
                "type": "string",
                "description": (
                    "Time filter: 'd'=last 24 hours, 'w'=last week, 'm'=last month. "
                    "Highly recommended for news queries to get fresh results."
                ),
                "enum": ["", "d", "w", "m"],
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default 5, max 10).",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    def execute(
        self,
        query: str,
        mode: str = "search",
        timelimit: str = "",
        max_results: int = 5,
    ) -> str:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return "Error: duckduckgo-search is not installed. Run: pip install duckduckgo-search"

        max_results = min(max(max_results, 1), 10)
        timelimit = (timelimit or "").strip().lower()
        if timelimit not in ("d", "w", "m"):
            timelimit = ""

        if mode == "news":
            return self._search_news(query, max_results, timelimit)
        return self._search_web(query, max_results, timelimit)

    @staticmethod
    def _search_web(query: str, max_results: int, timelimit: str) -> str:
        from duckduckgo_search import DDGS

        try:
            with DDGS() as ddgs:
                kwargs: dict = {"max_results": max_results}
                if timelimit:
                    kwargs["timelimit"] = timelimit
                results = list(ddgs.text(query, **kwargs))
        except Exception as exc:
            return f"Web search failed: {exc}"

        if not results:
            return f"No web results found for: {query}"

        time_label = {"d": "24 hours", "w": "week", "m": "month"}.get(timelimit, "")
        note = f" (last {time_label})" if time_label else ""
        lines = [f"Web search results for: {query}{note}\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            url = r.get("href", "")
            body = r.get("body", "")
            lines.append(f"{i}. {title}\n   URL: {url}\n   {body}\n")

        return "\n".join(lines)

    @staticmethod
    def _search_news(query: str, max_results: int, timelimit: str) -> str:
        from duckduckgo_search import DDGS

        try:
            with DDGS() as ddgs:
                kwargs: dict = {"max_results": max_results}
                if timelimit:
                    kwargs["timelimit"] = timelimit
                results = list(ddgs.news(query, **kwargs))
        except Exception as exc:
            return f"News search failed: {exc}"

        if not results:
            return f"No news found for: {query}"

        time_label = {"d": "24 hours", "w": "week", "m": "month"}.get(timelimit, "")
        note = f" (last {time_label})" if time_label else ""
        lines = [f"News results for: {query}{note}\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            url = r.get("url", r.get("href", ""))
            body = r.get("body", "")
            source = r.get("source", "")
            date = r.get("date", "")
            source_info = f" — {source}" if source else ""
            date_info = f" [{date}]" if date else ""
            lines.append(
                f"{i}. {title}{source_info}{date_info}\n"
                f"   URL: {url}\n"
                f"   {body}\n"
            )

        return "\n".join(lines)
