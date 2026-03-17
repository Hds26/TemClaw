"""
Skill base class — every custom Skill must inherit from this.

To add a new Skill:
1. Create a new .py file in this directory (e.g. my_skill.py).
2. Define a class that inherits from Skill.
3. Fill in `name`, `description`, and `parameters` (JSON Schema).
4. Implement the `execute` method.
5. Restart the backend — it will be auto-discovered.

Example
-------
from skills.base import Skill

class MySkill(Skill):
    name = "my_skill"
    description = "Does something useful."
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "The input text"}
        },
        "required": ["input"],
    }

    def execute(self, input: str) -> str:
        return f"You said: {input}"
"""

from abc import ABC, abstractmethod


class Skill(ABC):
    # -- Must override in subclass --
    name: str = ""
    description: str = ""
    # JSON Schema describing the arguments the LLM should pass to execute()
    parameters: dict = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """Run the skill and return a plain-text result."""

    # ------------------------------------------------------------------
    # Helpers used by skill_loader — no need to override
    # ------------------------------------------------------------------

    def to_tool_schema(self) -> dict:
        """Return the OpenAI function-calling tool schema for this skill."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_info(self) -> dict:
        """Return a JSON-serialisable summary for the /api/skills endpoint."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
