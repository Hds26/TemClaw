"""
llm.py
------
LLM provider factory.

Supports:
- openai        : OpenAI (https://api.openai.com/v1)
- anthropic     : Anthropic Claude via the official SDK
- moonshot      : Moonshot / Kimi (https://api.moonshot.cn/v1)
- deepseek      : DeepSeek (https://api.deepseek.com/v1)
- qwen          : Qwen / Alibaba Cloud (https://dashscope.aliyuncs.com/compatible-mode/v1)
- zhipu         : Zhipu AI / GLM (https://open.bigmodel.cn/api/paas/v4)
- yi            : 01.AI / Yi (https://api.lingyiwanwu.com/v1)
- baichuan      : Baichuan AI (https://api.baichuan-ai.com/v1)
- minimax       : MiniMax (https://api.minimax.chat/v1)
- groq          : Groq (https://api.groq.com/openai/v1)
- together      : Together AI (https://api.together.xyz/v1)
- ollama        : Ollama local (http://localhost:11434/v1)
- openai_compat : Generic OpenAI-compatible endpoint

All non-Anthropic types use the OpenAI SDK with the provider's base_url.
Provider configs come from the DB (see db/storage.py) and look like:
{
    "id": 1,
    "name": "My Provider",
    "provider_type": "moonshot",
    "api_key": "sk-...",
    "base_url": "https://api.moonshot.cn/v1",
    "default_model": "kimi-k2",
}
"""

from __future__ import annotations

from typing import Any


def build_openai_client(api_key: str, base_url: str | None = None) -> Any:
    """Return an openai.AsyncOpenAI client."""
    from openai import AsyncOpenAI

    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return AsyncOpenAI(**kwargs)


def build_anthropic_client(api_key: str, base_url: str | None = None) -> Any:
    """Return an anthropic.AsyncAnthropic client."""
    from anthropic import AsyncAnthropic

    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return AsyncAnthropic(**kwargs)


def get_client(provider: dict) -> Any:
    """
    Build and return the appropriate async LLM client for a provider config dict.
    """
    ptype = provider.get("provider_type", "openai")
    api_key = provider.get("api_key", "")
    base_url = provider.get("base_url") or None

    if ptype == "anthropic":
        return build_anthropic_client(api_key, base_url)
    # "openai" and "openai_compat" both use the OpenAI SDK
    return build_openai_client(api_key, base_url)


def is_anthropic(provider: dict) -> bool:
    return provider.get("provider_type") == "anthropic"
