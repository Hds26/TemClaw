"""
skill_loader.py
---------------
Auto-discovers Skill subclasses from the skills/ package and maintains a
runtime registry. Respects the skills_config DB table for enabled state.

Public API:
  - get_registry()       → dict of active (enabled) skills
  - get_tool_schemas()   → OpenAI tool list for enabled skills
  - execute_skill(name, args)
  - reload_skills()      → re-scan files + DB, rebuild registry
  - sync_skills_to_db()  → ensure every .py skill file has a DB row
  - validate_skill_file(source) → check if a string is a valid Skill .py file
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import sys
from pathlib import Path
from typing import Dict

import skills as skills_pkg
from skills.base import Skill

_registry: Dict[str, Skill] = {}
_all_skills: Dict[str, Skill] = {}

BUILTIN_FILES = {"base.py", "__init__.py"}
SKILLS_DIR = Path(skills_pkg.__file__).parent


def _discover_all() -> Dict[str, Skill]:
    """Scan skills/ directory, import every Skill subclass, return name->instance."""
    found: Dict[str, Skill] = {}
    for finder, module_name, _ in pkgutil.iter_modules([str(SKILLS_DIR)]):
        if module_name == "base":
            continue
        full_name = f"skills.{module_name}"
        try:
            if full_name in sys.modules:
                module = importlib.reload(sys.modules[full_name])
            else:
                module = importlib.import_module(full_name)
        except Exception as exc:
            print(f"[skill_loader] WARNING: could not import {full_name}: {exc}")
            continue

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Skill) and obj is not Skill and getattr(obj, "name", ""):
                found[obj.name] = obj()
    return found


async def sync_skills_to_db() -> None:
    """Ensure every discovered skill has a row in skills_config.
    Builtin skills (already on disk at startup) get is_builtin=True."""
    from db.storage import upsert_skill_config, list_skills_config

    all_skills = _discover_all()
    existing = {s["name"] for s in await list_skills_config()}

    for skill_name, skill_instance in all_skills.items():
        module = type(skill_instance).__module__
        filename = module.replace("skills.", "") + ".py"
        if skill_name not in existing:
            await upsert_skill_config(skill_name, filename, is_builtin=True, enabled=True)


async def reload_skills() -> None:
    """Rebuild the active registry based on DB enabled state."""
    from db.storage import list_skills_config

    global _registry, _all_skills

    _all_skills = _discover_all()
    db_config = {s["name"]: s for s in await list_skills_config()}

    _registry = {}
    for name, instance in _all_skills.items():
        cfg = db_config.get(name)
        if cfg is None or cfg["enabled"]:
            _registry[name] = instance


def get_registry() -> Dict[str, Skill]:
    return _registry


def get_all_skills() -> Dict[str, Skill]:
    return _all_skills


def get_tool_schemas() -> list[dict]:
    return [skill.to_tool_schema() for skill in _registry.values()]


def execute_skill(name: str, arguments: dict) -> str:
    if name not in _registry:
        return f"Error: skill '{name}' not found. Available: {list(_registry.keys())}"
    try:
        return _registry[name].execute(**arguments)
    except Exception as exc:
        return f"Error executing skill '{name}': {exc}"


def validate_skill_file(source: str) -> dict:
    """Parse a Python source string and check it defines a valid Skill subclass.
    Returns {"valid": True, "name": "...", "description": "..."} or
            {"valid": False, "error": "..."}.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"valid": False, "error": f"Syntax error: {e}"}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [_get_name(b) for b in node.bases]
            if "Skill" in bases:
                skill_name = ""
                description = ""
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == "name":
                                if isinstance(item.value, ast.Constant):
                                    skill_name = item.value.value
                            if isinstance(target, ast.Name) and target.id == "description":
                                if isinstance(item.value, ast.Constant):
                                    description = item.value.value
                if not skill_name:
                    return {"valid": False, "error": f"Class '{node.name}' has no 'name' attribute"}
                return {"valid": True, "name": skill_name, "description": description, "class_name": node.name}

    return {"valid": False, "error": "No Skill subclass found in file"}


def _get_name(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
