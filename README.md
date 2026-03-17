# Agent Template

A minimal, pluggable AI agent framework. Add your LLM provider API key, drop a Skill file in one directory, and you have a working agent with a Web UI.

```
┌──────────────┐       SSE stream       ┌──────────────┐
│  Next.js UI  │ ◄──────────────────── │ FastAPI back  │
│  (port 3000) │ ──── POST /api/chat ─► │  (port 8000) │
└──────────────┘                        └──────┬───────┘
                                               │
                                 ┌─────────────┼─────────────┐
                                 ▼             ▼             ▼
                             LLM SDK     Skill: calc    Skill: search
                          (openai/       (built-in)     (built-in)
                          anthropic)
```

---

## Quick Start

### 1 — Clone and install

```bash
git clone <this-repo>
cd agent-template
```

**Backend**

```bash
cd backend
pip install -r requirements.txt
```

**Frontend**

```bash
cd frontend
npm install
```

### 2 — Start the servers

**Backend** (in `backend/`)

```bash
uvicorn main:app --reload --port 8000
```

**Frontend** (in `frontend/`)

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### 3 — Add a provider

Click **Settings** in the top-right corner, then **Add Provider**. Fill in:

| Field | Example |
|---|---|
| Name | My OpenAI |
| Provider Type | openai |
| API Key | `sk-...` |
| Base URL | `https://api.openai.com/v1` (or leave blank for default) |
| Default Model | `gpt-4o-mini` |

Hit **Save** and go back to chat. You're ready.

**Supported provider types**

| Type | Description |
|---|---|
| `openai` | OpenAI or any OpenAI-compatible API (Moonshot, DeepSeek, Qwen, etc.) |
| `openai_compat` | Alias for openai — use for custom / self-hosted endpoints |
| `anthropic` | Anthropic Claude via the official SDK |

For OpenAI-compatible providers (Moonshot, DeepSeek, etc.) just set **Provider Type = openai** and provide the correct **Base URL** and model name.

---

## Adding a Custom Skill

1. Create a new Python file in `backend/skills/`, e.g. `my_skill.py`.
2. Inherit from `Skill` and implement `execute`.
3. Restart the backend — the skill is auto-discovered and available to the agent.

### Minimal example

```python
# backend/skills/my_skill.py
from skills.base import Skill

class GreetSkill(Skill):
    name = "greet"
    description = "Greet a person by name."
    parameters = {
        "type": "object",
        "properties": {
            "person_name": {
                "type": "string",
                "description": "The name of the person to greet.",
            }
        },
        "required": ["person_name"],
    }

    def execute(self, person_name: str) -> str:
        return f"Hello, {person_name}! Nice to meet you."
```

That's it. The LLM will call this skill automatically when it decides it's relevant.

### Skill interface reference

```python
class Skill(ABC):
    name: str           # Unique tool name (snake_case recommended)
    description: str    # Shown to the LLM — be clear and specific
    parameters: dict    # JSON Schema for the arguments

    def execute(self, **kwargs) -> str:
        # Receives the LLM's arguments as keyword args.
        # Must return a plain string (the tool result shown back to the LLM).
        ...
```

### Tips for writing good Skills

- Keep `description` clear and action-oriented: *"Search the web for current information"* not *"web search"*.
- Return concise string results — the LLM re-reads the output.
- For long outputs (e.g. file contents) truncate or summarize to avoid context overflow.
- Skills are synchronous — for async operations (HTTP requests, DB queries), use `asyncio.run()` or a sync wrapper inside `execute`.

---

## Built-in Skills

| Skill | Description | Requires |
|---|---|---|
| `calculator` | Safely evaluates math expressions | Nothing |
| `web_search` | DuckDuckGo text search | Network access |

---

## Project Structure

```
agent-template/
├── backend/
│   ├── main.py                 # FastAPI entry point
│   ├── requirements.txt
│   ├── core/
│   │   ├── agent.py            # ReAct agent loop (tool calls + streaming SSE)
│   │   ├── llm.py              # LLM provider factory
│   │   └── skill_loader.py     # Auto-discovers skills/ directory
│   ├── skills/
│   │   ├── base.py             # Skill base class ← extend this
│   │   ├── calculator.py       # Built-in: math evaluator
│   │   └── web_search.py       # Built-in: DuckDuckGo search
│   ├── api/
│   │   ├── chat.py             # POST /api/chat  (SSE)
│   │   ├── providers.py        # CRUD /api/providers
│   │   └── skills.py           # GET  /api/skills
│   └── db/
│       └── storage.py          # SQLite helpers (aiosqlite)
├── frontend/
│   ├── app/
│   │   ├── page.tsx            # Chat interface
│   │   └── settings/page.tsx   # Provider management
│   ├── components/
│   │   ├── ChatMessage.tsx     # Message renderer (Markdown + tool call blocks)
│   │   └── SkillBadge.tsx      # Skill pill with tooltip
│   └── lib/
│       └── api.ts              # Typed API client + SSE streaming
├── .env.example
└── README.md
```

---

## Environment Variables

Copy `.env.example` to `.env` (in `backend/`) for optional configuration:

```bash
cp .env.example backend/.env
```

| Variable | Default | Description |
|---|---|---|
| `DB_PATH` | `data/agent.db` | Path to the SQLite database file |
| `DEFAULT_PROVIDER_NAME` | — | Auto-seed a provider on first launch |
| `DEFAULT_PROVIDER_API_KEY` | — | API key for the auto-seeded provider |
| `DEFAULT_PROVIDER_TYPE` | `openai` | Provider type for auto-seeded provider |
| `DEFAULT_PROVIDER_BASE_URL` | — | Base URL for auto-seeded provider |
| `DEFAULT_PROVIDER_MODEL` | `gpt-4o-mini` | Model for auto-seeded provider |

---

## API Reference

### `POST /api/chat`

Request body:

```json
{
  "provider_id": 1,
  "messages": [{"role": "user", "content": "What is 2^10?"}],
  "system_prompt": "You are a helpful assistant."
}
```

Response: `text/event-stream` with events:

```
data: {"type": "token",      "content": "The answer is "}
data: {"type": "tool_start", "name": "calculator", "args": {"expression": "2**10"}}
data: {"type": "tool_end",   "name": "calculator", "result": "1024"}
data: {"type": "token",      "content": "1024."}
data: {"type": "done"}
```

### `GET /api/providers`

Returns list of configured providers (API keys masked).

### `POST /api/providers`

Create a new provider.

### `PATCH /api/providers/{id}`

Update a provider.

### `DELETE /api/providers/{id}`

Delete a provider.

### `GET /api/skills`

Returns list of all registered skills with their schemas.
