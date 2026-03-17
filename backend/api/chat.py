"""
chat.py — /api/chat SSE streaming endpoint with conversation persistence
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.agent import run_agent
from db.storage import (
    get_provider,
    list_providers,
    create_conversation,
    append_message,
    rename_conversation,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    provider_id: int | None = None
    messages: list[Message]
    system_prompt: str | None = None
    conversation_id: int | None = None


@router.post("")
async def chat(body: ChatRequest):
    if body.provider_id is not None:
        provider = await get_provider(body.provider_id)
        if not provider:
            raise HTTPException(404, f"Provider {body.provider_id} not found")
    else:
        all_providers = await list_providers()
        enabled = [p for p in all_providers if p.get("enabled")]
        if not enabled:
            raise HTTPException(400, "No enabled providers found. Add a provider in Settings first.")
        provider = enabled[0]

    history: list[dict] = []
    if body.system_prompt:
        history.append({"role": "system", "content": body.system_prompt})
    history.extend([m.model_dump() for m in body.messages])

    conv_id = body.conversation_id

    async def event_stream():
        nonlocal conv_id

        if conv_id is None and body.messages:
            first_msg = body.messages[-1].content[:30].strip() or "New Chat"
            conv = await create_conversation(first_msg)
            conv_id = conv["id"]
            yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conv_id})}\n\n"

        if conv_id is not None and body.messages:
            last_user = body.messages[-1]
            await append_message(conv_id, last_user.role, last_user.content)

        assistant_content = ""

        async for chunk in run_agent(history, provider):
            yield chunk
            if chunk.startswith("data:"):
                try:
                    evt = json.loads(chunk[5:].strip())
                    if evt.get("type") == "token":
                        assistant_content += evt.get("content", "")
                except (json.JSONDecodeError, KeyError):
                    pass

        if conv_id is not None and assistant_content:
            await append_message(conv_id, "assistant", assistant_content)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
