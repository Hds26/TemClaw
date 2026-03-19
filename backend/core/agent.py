"""
agent.py
--------
ReAct-style agent loop with streaming SSE output.

Flow per turn:
1. Send the full message history + available tools to the LLM.
2. If the LLM returns tool_calls -> execute the corresponding Skills,
   append the results to history, and loop back to step 1.
3. If the LLM returns a text response -> stream it token-by-token via SSE
   and break the loop.

Key design: when tool results contain rich content (images, etc.),
the agent streams them directly to the frontend instead of relying
on the LLM to echo them back. This ensures images always display
regardless of the LLM's behavior.
"""

from __future__ import annotations

import json
import logging
import re
from typing import AsyncGenerator

from core.llm import get_client, is_anthropic
from core.skill_loader import execute_skill, get_tool_schemas

logger = logging.getLogger("agent")

MAX_ITERATIONS = 8
MAX_CONSECUTIVE_SAME_TOOL = 2

_IMAGE_PATTERN = re.compile(r"!\[.*?\]\(.*?\)")


def _extract_rich_content(tool_results: list[dict]) -> str:
    """Extract markdown images and other rich content from tool results
    that should be shown to the user directly (not filtered through the LLM)."""
    parts = []
    for tr in tool_results:
        result = tr.get("result", "")
        if _IMAGE_PATTERN.search(result):
            parts.append(result)
    return "\n\n".join(parts)


async def run_agent(
    messages: list[dict],
    provider: dict,
) -> AsyncGenerator[str, None]:
    client = get_client(provider)
    model = provider.get("default_model", "gpt-4o-mini")
    tools = get_tool_schemas()

    history = list(messages)
    recent_tool_calls: list[str] = []
    last_tool_results: list[dict] = []
    rich_content_pending = ""

    for iteration in range(MAX_ITERATIONS):
        logger.info(f"[iter {iteration}] tools={len(tools)}, history={len(history)} msgs")

        if is_anthropic(provider):
            try:
                async for event in _call_anthropic(client, model, history, tools):
                    yield event
            except Exception as exc:
                yield _sse({"type": "error", "message": str(exc)})
                yield _sse({"type": "done"})
            return
        else:
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
                logger.error(f"[iter {iteration}] LLM call failed: {exc}")
                yield _sse({"type": "error", "message": str(exc)})
                yield _sse({"type": "done"})
                return

            try:
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta is None:
                        continue

                    if delta.content:
                        # Before first LLM token, inject any pending rich content
                        if rich_content_pending and not accumulated_text:
                            yield _sse({"type": "token", "content": rich_content_pending + "\n\n"})
                            accumulated_text += rich_content_pending + "\n\n"
                            rich_content_pending = ""

                        accumulated_text += delta.content
                        yield _sse({"type": "token", "content": delta.content})

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
                                    tool_calls_buffer[idx]["arguments"] += tc.function.arguments

                    if chunk.choices[0].finish_reason:
                        finish_reason = chunk.choices[0].finish_reason
            except Exception as exc:
                logger.error(f"[iter {iteration}] Stream error: {exc}")
                yield _sse({"type": "error", "message": str(exc)})
                yield _sse({"type": "done"})
                return

            logger.info(
                f"[iter {iteration}] finish_reason={finish_reason}, "
                f"text_len={len(accumulated_text)}, "
                f"tool_calls={len(tool_calls_buffer)}"
            )

            # ---- Handle tool calls ----
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
                        "content": "\n\n[Agent stopped: repeated identical tool calls detected.]\n\n",
                    })
                    async for event in _force_final_answer(client, model, history):
                        yield event
                    return

                tool_calls_list = [
                    {
                        "id": v["id"],
                        "type": "function",
                        "function": {"name": v["name"], "arguments": v["arguments"]},
                    }
                    for v in tool_calls_buffer.values()
                ]
                history.append({"role": "assistant", "tool_calls": tool_calls_list})

                last_tool_results = []
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

                    last_tool_results.append({"name": name, "result": result})
                    history.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })

                rich_content_pending = _extract_rich_content(last_tool_results)
                continue

            # ---- Normal text response ----
            if accumulated_text:
                # Rich content was already injected before LLM tokens
                history.append({"role": "assistant", "content": accumulated_text})
                yield _sse({"type": "done"})
                return

            # ---- Empty LLM response: surface tool results directly ----
            if rich_content_pending:
                yield _sse({"type": "token", "content": rich_content_pending})
                yield _sse({"type": "done"})
                return

            if last_tool_results:
                logger.warning(f"[iter {iteration}] LLM returned empty after tool calls.")
                fallback = _build_fallback_response(last_tool_results)
                yield _sse({"type": "token", "content": fallback})
                yield _sse({"type": "done"})
                return

            logger.warning(f"[iter {iteration}] Completely empty response.")
            yield _sse({"type": "done"})
            return

    # Exceeded MAX_ITERATIONS
    yield _sse({
        "type": "token",
        "content": "\n\n[Reached maximum iterations. Synthesizing answer.]\n\n",
    })
    async for event in _force_final_answer(client, model, history):
        yield event


def _build_fallback_response(tool_results: list[dict]) -> str:
    """Build a user-facing response from raw tool results."""
    parts = []
    for tr in tool_results:
        result = tr["result"]
        if result and not result.startswith("Error"):
            parts.append(result)
        elif result:
            parts.append(f"**{tr['name']}:** {result}")
    return "\n\n".join(parts) if parts else "(Tool executed but returned no content.)"


async def _force_final_answer(
    client, model: str, history: list[dict]
) -> AsyncGenerator[str, None]:
    """Ask the LLM to synthesize a final answer without tools."""
    history.append({
        "role": "system",
        "content": (
            "STOP calling tools. Based on all tool results gathered, "
            "provide your best answer now."
        ),
    })
    try:
        final_stream = await client.chat.completions.create(
            model=model, messages=history, stream=True,
        )
        async for chunk in final_stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield _sse({"type": "token", "content": delta.content})
    except Exception as exc:
        yield _sse({"type": "error", "message": str(exc)})
    yield _sse({"type": "done"})


async def _call_anthropic(
    client, model: str, history: list[dict], tools: list[dict],
) -> AsyncGenerator[str, None]:
    """Anthropic streaming with tool use."""
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
        "model": model, "max_tokens": 4096,
        "messages": anthropic_messages, "stream": True,
    }
    if system_content:
        kwargs["system"] = system_content
    if anthropic_tools:
        kwargs["tools"] = anthropic_tools

    async with client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield _sse({"type": "token", "content": text})
    yield _sse({"type": "done"})


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
