"""
image_generate.py - Find or generate images based on a text prompt.

Strategy (in order):
1. If IMAGE_API_KEY is set, use SiliconFlow/OpenAI-compatible image generation API
2. Try DuckDuckGo image search
3. Fallback: try Pollinations.ai direct URL
4. Fallback: use DuckDuckGo text search to find image-hosting URLs

All paths download the image to backend/static/images/ and serve locally,
ensuring instant and reliable display in the chat.
"""

import os
import re
import time
import urllib.parse
from pathlib import Path

import requests

from skills.base import Skill

STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "images"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

BACKEND_BASE = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
IMAGE_API_KEY = os.environ.get("IMAGE_API_KEY", "")
IMAGE_API_BASE = os.environ.get("IMAGE_API_BASE", "https://api.siliconflow.cn/v1")

_http = requests.Session()
_http.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})


class ImageGenerateSkill(Skill):
    name = "image_generate"
    description = (
        "Generate or find an image based on a text description. "
        "ALWAYS call this tool when the user asks to generate, draw, create, "
        "paint, or make any image. Do NOT describe the image in text - "
        "actually call this tool to produce a real image. "
        "The image will display directly in the chat."
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Image description in English. Be concise but descriptive. "
                    "Examples: 'cute anime schoolgirl sunny campus', "
                    "'sunset mountains golden light', 'fluffy cat sleeping'"
                ),
            },
        },
        "required": ["prompt"],
    }

    def execute(self, prompt: str, **kwargs) -> str:
        if not prompt.strip():
            return "Error: prompt cannot be empty."

        if IMAGE_API_KEY:
            result = self._generate_via_api(prompt)
            if not result.startswith("Error"):
                return result

        result = self._find_via_ddg_images(prompt)
        if not result.startswith("Error"):
            return result

        result = self._try_pollinations(prompt)
        if not result.startswith("Error"):
            return result

        result = self._find_via_bing(prompt)
        if not result.startswith("Error"):
            return result

        result = self._find_via_ddg_text(prompt)
        if not result.startswith("Error"):
            return result

        return "Error: All image sources failed. Please try again later or configure IMAGE_API_KEY in .env for reliable AI image generation."

    def _generate_via_api(self, prompt: str) -> str:
        """Use OpenAI-compatible image generation API (SiliconFlow, etc.)."""
        try:
            resp = _http.post(
                f"{IMAGE_API_BASE}/images/generations",
                json={
                    "model": "black-forest-labs/FLUX.1-schnell",
                    "prompt": prompt,
                    "image_size": "1024x1024",
                },
                headers={"Authorization": f"Bearer {IMAGE_API_KEY}"},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            img_url = data["data"][0].get("url", "")
            if not img_url:
                return "Error: API returned no image URL."
            return self._download_and_serve(img_url, prompt, "AI-generated")
        except Exception as e:
            return f"Error: Image API failed - {e}"

    def _find_via_ddg_images(self, prompt: str) -> str:
        """Use DuckDuckGo image search."""
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.images(prompt, max_results=5))
        except Exception:
            return "Error: DDG image search unavailable"

        for r in results:
            img_url = r.get("image", "")
            if img_url:
                result = self._download_and_serve(img_url, prompt, "found via search")
                if not result.startswith("Error"):
                    return result
        return "Error: No downloadable images from DDG"

    def _try_pollinations(self, prompt: str) -> str:
        """Try Pollinations.ai as fallback (works for short/cached prompts)."""
        short_prompt = prompt.strip()[:60]
        encoded = urllib.parse.quote(short_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}"
        try:
            resp = _http.get(url, timeout=30)
            resp.raise_for_status()
            if len(resp.content) >= 1000 and "image" in resp.headers.get("content-type", ""):
                filename = f"gen_{int(time.time() * 1000)}.jpg"
                save_path = STATIC_DIR / filename
                save_path.write_bytes(resp.content)
                local_url = f"{BACKEND_BASE}/static/images/{filename}"
                short = prompt[:60] + "..." if len(prompt) > 60 else prompt
                return f"![{short}]({local_url})\n\n*Image AI-generated via Pollinations*"
        except Exception:
            pass
        return "Error: Pollinations unavailable"

    def _find_via_bing(self, prompt: str) -> str:
        """Scrape Bing Image Search results directly (no API key needed)."""
        try:
            encoded = urllib.parse.quote(prompt)
            url = f"https://www.bing.com/images/search?q={encoded}&first=1&count=10"
            resp = _http.get(url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html",
            })
            resp.raise_for_status()

            img_urls = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', resp.text)
            if not img_urls:
                img_urls = re.findall(
                    r'src2?="(https?://[^\s"]+\.(?:jpg|jpeg|png|webp))',
                    resp.text,
                    re.IGNORECASE,
                )

            for img_url in img_urls[:5]:
                result = self._download_and_serve(img_url, prompt, "found via Bing")
                if not result.startswith("Error"):
                    return result
        except Exception:
            pass
        return "Error: Bing image search unavailable"

    def _find_via_ddg_text(self, prompt: str) -> str:
        """Last resort: use DDG text search to find pages with images."""
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                query = f"{prompt} site:unsplash.com OR site:pexels.com OR site:pixabay.com"
                results = list(ddgs.text(query, max_results=5))
        except Exception:
            return "Error: DDG text search unavailable"

        for r in results:
            page_url = r.get("href", "")
            if not page_url:
                continue
            img_url = self._extract_image_from_page(page_url)
            if img_url:
                result = self._download_and_serve(img_url, prompt, "found online")
                if not result.startswith("Error"):
                    return result
        return "Error: No images found via text search"

    def _extract_image_from_page(self, page_url: str) -> str:
        """Try to extract a direct image URL from a page."""
        try:
            resp = _http.get(page_url, timeout=10)
            resp.raise_for_status()
            # Find image URLs in the HTML
            img_urls = re.findall(
                r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)',
                resp.text,
                re.IGNORECASE,
            )
            # Prefer larger images (URLs often contain size hints)
            for url in img_urls:
                if any(s in url for s in ["1200", "1024", "large", "original", "full"]):
                    return url
            return img_urls[0] if img_urls else ""
        except Exception:
            return ""

    def _download_and_serve(self, img_url: str, prompt: str, source: str) -> str:
        """Download an image from URL, save locally, return markdown."""
        filename = f"gen_{int(time.time() * 1000)}.jpg"
        save_path = STATIC_DIR / filename

        try:
            resp = _http.get(img_url, timeout=15, allow_redirects=True)
            resp.raise_for_status()

            ct = resp.headers.get("content-type", "")
            if "image" not in ct and "octet" not in ct:
                return f"Error: non-image content ({ct})"

            if len(resp.content) < 1000:
                return f"Error: image too small ({len(resp.content)} bytes)"

            save_path.write_bytes(resp.content)
        except Exception as e:
            return f"Error: download failed - {e}"

        local_url = f"{BACKEND_BASE}/static/images/{filename}"
        short = prompt[:60] + "..." if len(prompt) > 60 else prompt
        return (
            f"![{short}]({local_url})\n\n"
            f"*Image {source}*"
        )
