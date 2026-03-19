"""
url_reader.py — Fetch and extract readable text from a web page.

Complements web_search: search finds URLs, url_reader reads the content.
"""

import urllib.request
import urllib.error
import re
import html
from skills.base import Skill


class UrlReaderSkill(Skill):
    name = "url_reader"
    description = (
        "Fetch a web page URL and return its main text content. "
        "Use this when you need to read the actual content of a specific web page, "
        "article, or documentation URL. Complements web_search: first search to "
        "find relevant URLs, then use this tool to read the full content."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full URL to fetch (must start with http:// or https://)",
            },
        },
        "required": ["url"],
    }

    def execute(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            return "Error: URL must start with http:// or https://"

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AgentBot/1.0)",
                    "Accept": "text/html,application/xhtml+xml,*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "text" not in content_type and "html" not in content_type and "json" not in content_type:
                    return f"Error: Non-text content type: {content_type}"

                charset = "utf-8"
                if "charset=" in content_type:
                    charset = content_type.split("charset=")[-1].strip().split(";")[0]

                raw = resp.read(500_000)
                text = raw.decode(charset, errors="replace")

        except urllib.error.HTTPError as e:
            return f"HTTP Error {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            return f"URL Error: {e.reason}"
        except Exception as e:
            return f"Error fetching URL: {e}"

        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<nav[^>]*>.*?</nav>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<footer[^>]*>.*?</footer>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n", "\n\n", text)
        text = text.strip()

        if len(text) > 3000:
            text = text[:3000] + "\n\n... [content truncated]"

        return text if text else "(page returned no readable text)"
