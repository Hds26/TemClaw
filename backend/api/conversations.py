"""
conversations.py — /api/conversations CRUD routes
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import storage

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str = "New Chat"


class ConversationRename(BaseModel):
    title: str


@router.get("")
async def list_conversations():
    return await storage.list_conversations()


@router.post("", status_code=201)
async def create_conversation(body: ConversationCreate):
    return await storage.create_conversation(body.title)


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: int):
    conv = await storage.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return conv


@router.patch("/{conversation_id}")
async def rename_conversation(conversation_id: int, body: ConversationRename):
    updated = await storage.rename_conversation(conversation_id, body.title)
    if not updated:
        raise HTTPException(404, "Conversation not found")
    return updated


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: int):
    deleted = await storage.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(404, "Conversation not found")
