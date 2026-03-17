"""
agent.py
--------
ReAct-style agent loop with streaming SSE output.

Flow per turn:
1. Send the full message history + available tools to the LLM.
2. If the LLM returns tool_calls → execute the corresponding Skills,
   append the results to history, and loop back to step 1.
3. If the LLM returns a text response → stream it token-by-token via SSE
   and break the loop.

SSE event types sent to the frontend
-------------------------------------
  {"type": "token",      "content": "..."}   — incremental text chunk
  {"type": "tool_start", "name": "...", "args": {...}}  — skill about to run
  {"type": "tool_end",   "name": "...", "result": "..."}  — skill result
  {"type": "done"}                            — generation complete
  {"type": "error",      "message": "..."}   — unrecoverable error
"""

from __future__ import annotations

import json
from typing import AsyncGenerator

from core.llm import get_client, is_anthropic
from core.skill_loader import execute_skill, get_tool_schemas

MAX_ITERATIONS = 5
MAX_CONSECUTIVE_SAME_TOOL = 2


async def run_agent(
    messages: list[dict],
    provider: dict,
) -> AsyncGenerator[str, None]:
    """
    Async generator — yields SSE-formatted strings.

    `messages` is the full conversation history in OpenAI format:
        [{"role": "user"/"assistant"/"system", "content": "..."}]
    `provider` is a provider config dict (see core/llm.py).
    """
    client = get_client(provider)
    model = provider.get("default_model", "gpt-4o-mini")
    tools = get_tool_schemas()

    history = list(messages)
    recent_tool_calls: list[str] = []

    for iteration in range(MAX_ITERATIONS):
        if is_anthropic(provider):
            try:
                async for event in _call_anthropic(client, model, history, tools):
                    yield event
            except Exception as exc:
                yield _sse({"type": "error", "message": str(exc)})
                yield _sse({"type": "done"})
            return
        else:
            # Collect the full stream; we need to detect tool_calls mid-stream
            accumulated_text = ""
            tool_calls_buffer: dict[int, dict] = {}
            finish_reason = None

            try:
                stream = await client.chat.completions.create(
                    model=model,
                    messages=history,
                    tools=tools if tools else None,
                    tool_choice="auto" if tools else None,
                    stream=True,
                )
            except Exception as exc:
                yield _sse({"type": "error", "message": str(exc)})
                yield _sse({"type": "done"})
                return

            try:
              async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                # Stream text tokens
                if delta.content:
                    accumulated_text += delta.content
                    yield _sse({"type": "token", "content": delta.content})

                # Accumulate tool call fragments
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc.id:
                            tool_calls_buffer[idx]["id"] += tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_buffer[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_buffer[idx]["arguments"] += (
                                    tc.function.arguments
                                )

                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason
            except Exception as exc:
                yield _sse({"type": "error", "message": str(exc)})
                yield _sse({"type": "done"})
                return

            # ---- After stream ends ----
            if finish_reason == "tool_calls" and tool_calls_buffer:
                call_signature = "|".join(
                    f"{v['name']}:{v['arguments']}" for v in tool_calls_buffer.values()
                )
                recent_tool_calls.append(call_signature)

                consecutive_same = 0
                if len(recent_tool_calls) >= 2:
                    for prev in reversed(recent_tool_calls[:-1]):
                        if prev == call_signature:
                            consecutive_same += 1
                        else:
                            break
                if consecutive_same >= MAX_CONSECUTIVE_SAME_TOOL:
                    yield _sse({
                        "type": "token",
                        "content": "\n\n[Agent stopped: repeated identical tool calls detected. "
                                   "Answering based on information already gathered.]\n\n",
                    })
                    history.append({
                        "role": "system",
                        "content": (
                            "STOP calling tools. You have already called the same tool with "
                            "the same arguments multiple times. Provide your best answer now "
                            "based on the tool results you already have. If you don't have "
                            "enough information, say so."
                        ),
                    })
                    try:
                        final_stream = await client.chat.completions.create(
                            model=model,
                            messages=history,
                            stream=True,
                        )
                        async for chunk in final_stream:
                            delta = chunk.choices[0].delta if chunk.choices else None
                            if delta and delta.content:
                                yield _sse({"type": "token", "content": delta.content})
                    except Exception as exc:
                        yield _sse({"type": "error", "message": str(exc)})
                    yield _sse({"type": "done"})
                    return

                # Add assistant message with tool_calls to history
                tool_calls_list = [
                    {
                        "id": v["id"],
                        "type": "function",
                        "function": {"name": v["name"], "arguments": v["arguments"]},
                    }
                    for v in tool_calls_buffer.values()
                ]
                history.append({"role": "assistant", "tool_calls": tool_calls_list})

                # Execute each tool call and add results
                for tc in tool_calls_buffer.values():
                    name = tc["name"]
                    raw_args = tc["arguments"]
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        args = {}

                    yield _sse({"type": "tool_start", "name": name, "args": args})
                    result = execute_skill(name, args)
                    yield _sse({"type": "tool_end", "name": name, "result": result})

                    history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        }
                    )
                # Loop continues → call LLM again with tool results
                continue

            # Normal text response — we're done
            if accumulated_text:
                history.append({"role": "assistant", "content": accumulated_text})
            yield _sse({"type": "done"})
            return

    # Exceeded MAX_ITERATIONS
    yield _sse({"type": "error", "message": "Max tool-call iterations reached."})
    yield _sse({"type": "done"})


async def _call_anthropic(
    client,
    model: str,
    history: list[dict],
    tools: list[dict],
) -> AsyncGenerator[str, None]:
    """Anthropic streaming with tool use."""
    # Convert OpenAI-style history to Anthropic format
    system_content = ""
    anthropic_messages = []
    for msg in history:
        role = msg["role"]
        if role == "system":
            system_content = msg.get("content", "")
        elif role in ("user", "assistant"):
            anthropic_messages.append({"role": role, "content": msg.get("content", "")})

    anthropic_tools = [
        {
            "name": t["function"]["name"],
            "description": t["function"]["description"],
            "input_schema": t["function"]["parameters"],
        }
        for t in tools
    ]

    kwargs = {
        "model": model,
        "max_tokens": 4096,
        "messages": anthropic_messages,
        "stream": True,
    }
    if system_content:
        kwargs["system"] = system_content
    if anthropic_tools:
        kwargs["tools"] = anthropic_tools

    accumulated_text = ""
    async with client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            accumulated_text += text
            yield _sse({"type": "token", "content": text})

    yield _sse({"type": "done"})


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
