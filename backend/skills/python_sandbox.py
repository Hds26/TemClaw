"""
python_sandbox.py — Execute Python code in a restricted subprocess.

This is the killer skill that differentiates an Agent from a plain chat model:
the LLM can write code, run it, see the output, and iterate.
"""

import subprocess
import sys
import tempfile
import os
from skills.base import Skill

_AVAILABLE_PACKAGES: list[str] | None = None


def _detect_packages() -> list[str]:
    """Detect commonly used packages available in the current Python env."""
    global _AVAILABLE_PACKAGES
    if _AVAILABLE_PACKAGES is not None:
        return _AVAILABLE_PACKAGES

    candidates = [
        "requests", "numpy", "pandas", "matplotlib",
        "bs4", "lxml", "PIL", "scipy", "sympy",
        "httpx", "aiohttp", "pydantic", "yaml",
    ]
    available = []
    for pkg in candidates:
        try:
            __import__(pkg)
            available.append(pkg)
        except ImportError:
            pass
    _AVAILABLE_PACKAGES = available
    return available


class PythonSandboxSkill(Skill):
    name = "python_execute"
    description = (
        "Execute a Python code snippet and return its stdout/stderr output. "
        "Use this when you need to: run calculations, process data, fetch URLs, "
        "test code, or perform any programmatic task. "
        "The code runs in a real Python interpreter. "
        "Always use print() to produce output that you can see. "
        "IMPORTANT: Prefer using standard library modules (urllib.request, json, math, etc.) "
        "which are always available. If you need HTTP requests, use urllib.request instead of requests."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The Python code to execute. Use print() for output. "
                               "Prefer stdlib (urllib.request, json, etc.) over third-party packages.",
            },
        },
        "required": ["code"],
    }

    def execute(self, code: str) -> str:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        try:
            result = subprocess.run(
                [sys.executable, "-u", tmp_path],
                capture_output=True,
                timeout=30,
                cwd=tempfile.gettempdir(),
                env=env,
                encoding="utf-8",
                errors="replace",
            )
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                stderr_clean = result.stderr
                if output:
                    output += "\n--- stderr ---\n" + stderr_clean
                else:
                    output = stderr_clean
            if not output.strip():
                output = "(no output)"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"

                if "ModuleNotFoundError" in output:
                    pkgs = _detect_packages()
                    hint = (
                        f"\n[Hint: available third-party packages: {', '.join(pkgs) if pkgs else 'none'}. "
                        "Use stdlib (urllib.request, json, etc.) for HTTP requests.]"
                    )
                    output += hint

            return output[:4000]
        except subprocess.TimeoutExpired:
            return "Error: code execution timed out (30s limit)"
        except Exception as e:
            return f"Error: {e}"
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
