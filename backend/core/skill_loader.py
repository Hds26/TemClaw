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
  - convert_clawhub_zip(data)   → parse ClawHub .zip and generate .py source
  - convert_clawhub_json(data, md) → parse ClawHub JSON+MD and generate .py source
"""

from __future__ import annotations

import ast
import importlib
import inspect
import io
import json
import pkgutil
import re
import sys
import textwrap
import zipfile
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


# ---------------------------------------------------------------------------
# ClawHub format conversion
# ---------------------------------------------------------------------------

def convert_clawhub_zip(zip_bytes: bytes) -> dict:
    """Parse a ClawHub .zip archive and return conversion result.

    Returns {"valid": True, "name": ..., "filename": ..., "source": ...}
    or      {"valid": False, "error": ...}.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return {"valid": False, "error": "Invalid ZIP file"}

    names = zf.namelist()

    json_data = None
    md_content = ""
    tools_data = None

    json_candidates = ["claw.json", "skill.json"]
    md_candidates = ["instructions.md", "SKILL.md", "README.md"]
    tools_candidates = ["tools.json"]

    def _find(candidates: list[str]) -> str | None:
        for n in names:
            basename = n.rsplit("/", 1)[-1] if "/" in n else n
            if basename in candidates:
                return n
        return None

    json_path = _find(json_candidates)
    if json_path:
        try:
            json_data = json.loads(zf.read(json_path).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return {"valid": False, "error": f"Failed to parse {json_path}: {e}"}

    md_path = _find(md_candidates)
    if md_path:
        try:
            md_content = zf.read(md_path).decode("utf-8")
        except UnicodeDecodeError:
            md_content = ""

    tools_path = _find(tools_candidates)
    if tools_path:
        try:
            tools_data = json.loads(zf.read(tools_path).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            tools_data = None

    py_path = _find_py_in_zip(names)
    if py_path and not json_data:
        source = zf.read(py_path).decode("utf-8", errors="replace")
        validation = validate_skill_file(source)
        if validation["valid"]:
            return {"valid": True, "name": validation["name"], "filename": py_path.rsplit("/", 1)[-1], "source": source}

    if not json_data and not md_content:
        return {"valid": False, "error": "ZIP does not contain claw.json, skill.json, SKILL.md, or any .py skill file"}

    return convert_clawhub_json(json_data or {}, md_content, tools_data)


def _find_py_in_zip(names: list[str]) -> str | None:
    for n in names:
        basename = n.rsplit("/", 1)[-1] if "/" in n else n
        if basename.endswith(".py") and basename not in ("__init__.py", "base.py", "setup.py"):
            return n
    return None


def convert_clawhub_json(
    json_data: dict, md_content: str = "", tools_data: dict | list | None = None
) -> dict:
    """Convert ClawHub JSON + MD + optional tools.json into a Python Skill source.

    Returns {"valid": True, "name": ..., "filename": ..., "source": ...}
    or      {"valid": False, "error": ...}.
    """
    skill_name = json_data.get("name", "")
    description = json_data.get("description", "")

    if not skill_name and md_content:
        match = re.search(r"^name:\s*(.+)$", md_content, re.MULTILINE)
        if match:
            skill_name = match.group(1).strip()
        match = re.search(r"^description:\s*(.+)$", md_content, re.MULTILINE)
        if match and not description:
            description = match.group(1).strip()

    if not skill_name:
        return {"valid": False, "error": "Cannot determine skill name from JSON or MD"}

    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", skill_name).strip("_").lower()
    if not safe_name:
        return {"valid": False, "error": f"Cannot create valid Python identifier from name '{skill_name}'"}

    class_name = "".join(w.capitalize() for w in safe_name.split("_")) + "Skill"

    tools = _parse_tools(tools_data)

    if tools:
        source = _generate_tool_skill(safe_name, class_name, description, md_content, tools[0])
    else:
        source = _generate_instruction_skill(safe_name, class_name, description, md_content)

    validation = validate_skill_file(source)
    if not validation["valid"]:
        return {"valid": False, "error": f"Generated code failed validation: {validation['error']}"}

    filename = f"clawhub_{safe_name}.py"
    return {"valid": True, "name": safe_name, "filename": filename, "source": source}


def _parse_tools(tools_data) -> list[dict]:
    """Normalize tools.json into a list of tool dicts."""
    if not tools_data:
        return []
    if isinstance(tools_data, dict):
        if "tools" in tools_data:
            return tools_data["tools"] if isinstance(tools_data["tools"], list) else [tools_data["tools"]]
        if "name" in tools_data:
            return [tools_data]
        return list(tools_data.values()) if tools_data else []
    if isinstance(tools_data, list):
        return tools_data
    return []


def _escape_triple_quotes(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def _generate_tool_skill(
    safe_name: str, class_name: str, description: str, md_content: str, tool: dict
) -> str:
    """Generate a Skill with parameters from tools.json tool definition."""
    tool_desc = tool.get("description", description)
    executor = tool.get("executor", "")
    command = tool.get("command", "")

    params = tool.get("parameters", {})
    if not params.get("properties"):
        params = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Input for the skill"}
            },
            "required": ["query"],
        }

    properties = params.get("properties", {})
    param_names = list(properties.keys())
    func_args = ", ".join(f"{p}: str = ''" for p in param_names)

    params_json = json.dumps(params, indent=4, ensure_ascii=False)
    params_indented = params_json.replace("\n", "\n    ")

    if executor == "http" and command:
        execute_body = _generate_http_executor(command, param_names)
    elif executor == "bash" and command:
        execute_body = _generate_bash_executor(command, param_names)
    else:
        execute_body = _generate_instruction_executor(md_content, param_names)

    desc_escaped = _escape_triple_quotes(tool_desc or description)
    body_indented = textwrap.indent(execute_body, "        ")

    lines = [
        f'"""Auto-generated from ClawHub skill: {safe_name}"""',
        "from skills.base import Skill",
        "",
        "",
        f"class {class_name}(Skill):",
        f'    name = "{safe_name}"',
        f'    description = """{desc_escaped}"""',
        f"    parameters = {params_indented}",
        "",
        f"    def execute(self, {func_args}) -> str:",
        body_indented,
    ]
    return "\n".join(lines) + "\n"


def _generate_http_executor(command: str, param_names: list[str]) -> str:
    lines = [
        "import urllib.request, urllib.error, json",
        f'url = "{command}"',
    ]
    for p in param_names:
        placeholder = "{{" + p + "}}"
        lines.append(f'url = url.replace("{placeholder}", str({p}))')
    lines += [
        "try:",
        '    req = urllib.request.Request(url, headers={"User-Agent": "AgentBot/1.0"})',
        "    with urllib.request.urlopen(req, timeout=15) as resp:",
        '        return resp.read(10000).decode("utf-8", errors="replace")',
        "except Exception as e:",
        '    return f"HTTP error: {e}"',
    ]
    return "\n".join(lines)


def _generate_bash_executor(command: str, param_names: list[str]) -> str:
    lines = [
        "import subprocess",
        f'cmd = """{command}"""',
    ]
    for p in param_names:
        placeholder = "{{" + p + "}}"
        lines.append(f'cmd = cmd.replace("{placeholder}", str({p}))')
    lines += [
        "try:",
        "    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)",
        "    out = r.stdout + r.stderr",
        '    return out.strip() or "(no output)"',
        "except Exception as e:",
        '    return f"Execution error: {e}"',
    ]
    return "\n".join(lines)


def _generate_instruction_executor(md_content: str, param_names: list[str]) -> str:
    escaped = _escape_triple_quotes(md_content[:3000]) if md_content else "No instructions provided."
    if param_names:
        query_param = param_names[0]
        return (
            f'instructions = """{escaped}"""\n'
            f'return f"[Skill Instructions]\\n{{instructions}}\\n\\n[User Input] {{{query_param}}}"'
        )
    return f'return """{escaped}"""'


def _generate_instruction_skill(
    safe_name: str, class_name: str, description: str, md_content: str
) -> str:
    """Generate a Skill from pure instructions (no tools.json)."""
    desc_escaped = _escape_triple_quotes(description or "A ClawHub imported skill.")
    inst_escaped = _escape_triple_quotes(md_content[:3000]) if md_content else "No instructions."

    lines = [
        f'"""Auto-generated from ClawHub skill: {safe_name}"""',
        "from skills.base import Skill",
        "",
        "",
        f"class {class_name}(Skill):",
        f'    name = "{safe_name}"',
        f'    description = """{desc_escaped}"""',
        "    parameters = {",
        '        "type": "object",',
        '        "properties": {',
        '            "query": {',
        '                "type": "string",',
        '                "description": "The user query or topic to apply this skill to"',
        "            }",
        "        },",
        '        "required": ["query"],',
        "    }",
        "",
        "    def execute(self, query: str = '') -> str:",
        f'        instructions = """{inst_escaped}"""',
        f'        return f"[Skill: {safe_name}]\\nInstructions:\\n{{instructions}}\\n\\nUser query: {{query}}"',
    ]
    return "\n".join(lines) + "\n"
