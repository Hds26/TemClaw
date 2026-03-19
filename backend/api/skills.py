"""
skills.py — /api/skills routes (list, upload, toggle, delete)

Supports uploading:
  - .py  — Native Skill file (validated directly)
  - .zip — ClawHub package (claw.json + instructions.md + optional tools.json)
  - .json — ClawHub claw.json / skill.json (standalone)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from core.skill_loader import (
    get_registry,
    get_all_skills,
    reload_skills,
    validate_skill_file,
    convert_clawhub_zip,
    convert_clawhub_json,
    SKILLS_DIR,
    BUILTIN_FILES,
)
from db import storage

router = APIRouter(prefix="/api/skills", tags=["skills"])

ALLOWED_EXTENSIONS = (".py", ".zip", ".json")


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
    """Upload a skill file (.py / .zip / .json), validate, save and register."""
    fname = file.filename or ""
    ext = ""
    for e in ALLOWED_EXTENSIONS:
        if fname.lower().endswith(e):
            ext = e
            break

    if not ext:
        raise HTTPException(
            400,
            f"Unsupported file type. Accepted formats: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    content_bytes = await file.read()

    if ext == ".py":
        return await _handle_py_upload(fname, content_bytes)
    elif ext == ".zip":
        return await _handle_zip_upload(content_bytes)
    elif ext == ".json":
        return await _handle_json_upload(content_bytes)


async def _handle_py_upload(filename: str, content_bytes: bytes) -> dict:
    """Process a native .py Skill upload."""
    if filename in BUILTIN_FILES:
        raise HTTPException(400, f"Cannot overwrite built-in file '{filename}'")

    try:
        source = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be valid UTF-8 text")

    validation = validate_skill_file(source)
    if not validation["valid"]:
        raise HTTPException(422, validation["error"])

    return await _save_and_register(validation["name"], filename, source)


async def _handle_zip_upload(content_bytes: bytes) -> dict:
    """Process a ClawHub .zip package."""
    result = convert_clawhub_zip(content_bytes)
    if not result["valid"]:
        raise HTTPException(422, result["error"])

    return await _save_and_register(result["name"], result["filename"], result["source"])


async def _handle_json_upload(content_bytes: bytes) -> dict:
    """Process a standalone ClawHub claw.json / skill.json."""
    try:
        json_data = __import__("json").loads(content_bytes.decode("utf-8"))
    except Exception as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    result = convert_clawhub_json(json_data)
    if not result["valid"]:
        raise HTTPException(422, result["error"])

    return await _save_and_register(result["name"], result["filename"], result["source"])


async def _save_and_register(skill_name: str, filename: str, source: str) -> dict:
    """Write .py to disk, update DB, reload, return skill info."""
    existing = await storage.get_skill_config(skill_name)
    if existing and existing["is_builtin"]:
        raise HTTPException(409, f"Cannot overwrite built-in skill '{skill_name}'")

    dest = SKILLS_DIR / filename
    dest.write_text(source, encoding="utf-8")

    await storage.upsert_skill_config(skill_name, filename, is_builtin=False, enabled=True)
    await reload_skills()

    all_skills = get_all_skills()
    skill = all_skills.get(skill_name)
    if not skill:
        raise HTTPException(
            500,
            "Skill file saved but failed to load. Check for import errors in the generated code."
        )

    return {
        **skill.to_info(),
        "enabled": True,
        "is_builtin": False,
        "filename": filename,
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
