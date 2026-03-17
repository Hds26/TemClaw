"""
providers.py — /api/providers CRUD routes + connection test
"""

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.llm import get_client, is_anthropic
from db import storage

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProviderCreate(BaseModel):
    name: str
    provider_type: str = "openai"   # "openai" | "anthropic" | "openai_compat"
    api_key: str = ""
    base_url: str | None = None
    default_model: str = "gpt-4o-mini"
    enabled: bool = True


class ProviderUpdate(BaseModel):
    name: str | None = None
    provider_type: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    enabled: bool | None = None


@router.get("")
async def list_providers():
    providers = await storage.list_providers()
    # Mask api_key in list response
    return [_mask(p) for p in providers]


@router.get("/{provider_id}")
async def get_provider(provider_id: int):
    p = await storage.get_provider(provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")
    return _mask(p)


@router.post("", status_code=201)
async def create_provider(body: ProviderCreate):
    created = await storage.create_provider(body.model_dump())
    return _mask(created)


@router.patch("/{provider_id}")
async def update_provider(provider_id: int, body: ProviderUpdate):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if "api_key" in data and not data["api_key"]:
        del data["api_key"]
    updated = await storage.update_provider(provider_id, data)
    if not updated:
        raise HTTPException(404, "Provider not found")
    return _mask(updated)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: int):
    deleted = await storage.delete_provider(provider_id)
    if not deleted:
        raise HTTPException(404, "Provider not found")


@router.post("/{provider_id}/test")
async def test_provider_connection(provider_id: int):
    provider = await storage.get_provider(provider_id)
    if not provider:
        raise HTTPException(404, "Provider not found")

    model = provider["default_model"]
    try:
        t0 = time.time()
        if is_anthropic(provider):
            client = get_client(provider)
            msg = await client.messages.create(
                model=model,
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            latency_ms = int((time.time() - t0) * 1000)
            return {"status": "ok", "model": msg.model, "latency_ms": latency_ms}
        else:
            client = get_client(provider)
            resp = await client.chat.completions.create(
                model=model,
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            latency_ms = int((time.time() - t0) * 1000)
            return {"status": "ok", "model": resp.model, "latency_ms": latency_ms}
    except Exception as exc:
        raise HTTPException(502, f"Connection failed: {exc}")


def _mask(p: dict) -> dict:
    """Replace the actual api_key with a masked version in API responses."""
    out = dict(p)
    key = out.get("api_key", "")
    if key and len(key) > 8:
        out["api_key"] = key[:4] + "****" + key[-4:]
    elif key:
        out["api_key"] = "****"
    return out
