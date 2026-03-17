"""
skills.py — /api/skills routes (list, upload, toggle, delete)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from core.skill_loader import (
    get_registry,
    get_all_skills,
    reload_skills,
    validate_skill_file,
    SKILLS_DIR,
    BUILTIN_FILES,
)
from db import storage

router = APIRouter(prefix="/api/skills", tags=["skills"])


class ToggleBody(BaseModel):
    enabled: bool


@router.get("")
async def list_skills():
    """Return metadata for all skills with enabled/builtin status."""
    db_config = {s["name"]: s for s in await storage.list_skills_config()}
    all_skills = get_all_skills()
    result = []
    for name, skill in all_skills.items():
        cfg = db_config.get(name, {})
        result.append({
            **skill.to_info(),
            "enabled": cfg.get("enabled", True),
            "is_builtin": cfg.get("is_builtin", True),
            "filename": cfg.get("filename", ""),
        })

    for name, cfg in db_config.items():
        if name not in all_skills:
            result.append({
                "name": name,
                "description": "(failed to load)",
                "parameters": {},
                "enabled": cfg["enabled"],
                "is_builtin": cfg["is_builtin"],
                "filename": cfg.get("filename", ""),
            })
    return result


@router.post("/upload", status_code=201)
async def upload_skill(file: UploadFile = File(...)):
    """Upload a .py skill file, validate it, save to skills/ and register."""
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(400, "Only .py files are accepted")
    if file.filename in BUILTIN_FILES:
        raise HTTPException(400, f"Cannot overwrite built-in file '{file.filename}'")

    content_bytes = await file.read()
    try:
        source = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be valid UTF-8 text")

    validation = validate_skill_file(source)
    if not validation["valid"]:
        raise HTTPException(422, validation["error"])

    skill_name = validation["name"]

    existing = await storage.get_skill_config(skill_name)
    if existing and existing["is_builtin"]:
        raise HTTPException(409, f"Cannot overwrite built-in skill '{skill_name}'")

    dest = SKILLS_DIR / file.filename
    dest.write_text(source, encoding="utf-8")

    await storage.upsert_skill_config(skill_name, file.filename, is_builtin=False, enabled=True)
    await reload_skills()

    all_skills = get_all_skills()
    skill = all_skills.get(skill_name)
    if not skill:
        raise HTTPException(500, "Skill file saved but failed to load. Check for import errors.")

    return {
        **skill.to_info(),
        "enabled": True,
        "is_builtin": False,
        "filename": file.filename,
    }


@router.patch("/{skill_name}")
async def toggle_skill(skill_name: str, body: ToggleBody):
    """Enable or disable a skill."""
    updated = await storage.set_skill_enabled(skill_name, body.enabled)
    if not updated:
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    await reload_skills()
    return updated


@router.delete("/{skill_name}", status_code=204)
async def delete_skill(skill_name: str):
    """Delete a user-uploaded skill (built-in skills cannot be deleted)."""
    cfg = await storage.get_skill_config(skill_name)
    if not cfg:
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    if cfg["is_builtin"]:
        raise HTTPException(403, "Cannot delete built-in skills")

    filepath = SKILLS_DIR / cfg["filename"]
    if filepath.exists():
        filepath.unlink()

    await storage.delete_skill_config(skill_name)
    await reload_skills()
