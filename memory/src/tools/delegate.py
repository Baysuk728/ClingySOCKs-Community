"""
delegate_task tool — enables companion agents to dispatch work to specialist subagents.

This is the bridge between the main companion (personality, memory, user-facing)
and functional subagents (content creation, social media, research, etc.).

The subagent runs a full ReAct agent loop with scoped tools, then returns
a structured result to the calling companion.
"""

import json
import uuid
import traceback
from datetime import datetime, timezone

import litellm

from src.agent.subagents import (
    get_subagent,
    list_subagents,
    filter_tools_by_scope,
    SubAgentConfig,
)
from src.integrations.mcp_client import mcp_manager


# ─── Constants ──────────────────────────────────────────

# Model to use for subagents (fast + capable, cost-effective)
# Falls back to env var or a sensible default
import os
SUBAGENT_MODEL = os.environ.get("SUBAGENT_MODEL", "gemini/gemini-2.5-flash")

MAX_SUBAGENT_STEPS = 25  # Hard cap


# ─── Main Entry Point ──────────────────────────────────

async def delegate_task(
    source_entity_id: str,
    subagent_id: str,
    goal: str,
    context: str = "",
    artifacts: list[str] | None = None,
) -> dict:
    """
    Delegate a task to a specialist subagent.

    Args:
        source_entity_id: The companion agent delegating the work
        subagent_id: ID of the subagent (e.g., "content_creator")
        goal: Clear description of what the subagent should accomplish
        context: Optional context/background from the companion
        artifacts: Optional list of file paths to pass to the subagent

    Returns:
        dict with 'result', 'files', 'subagent_name', 'steps_taken', etc.
    """
    # Resolve subagent config
    subagent = get_subagent(subagent_id)
    if not subagent:
        available = [f"{sa.id} ({sa.name}: {sa.description[:60]})" for sa in list_subagents()]
        return {
            "error": f"SubAgent '{subagent_id}' not found.",
            "available_subagents": available,
        }

    print(f"🤖 Delegating to SubAgent [{subagent.name}]: {goal[:100]}")

    # Gather and filter tools to this subagent's scope
    mcp_tools = await mcp_manager.get_all_tools()
    scoped_tools = filter_tools_by_scope(mcp_tools, subagent.tool_scope)

    if not scoped_tools:
        return {
            "error": f"SubAgent '{subagent.name}' has no tools available matching scope {subagent.tool_scope}. Check MCP server connections.",
        }

    print(f"  🔧 Tools available ({len(scoped_tools)}): {[t['function']['name'] for t in scoped_tools]}")

    # Build the subagent's system prompt
    artifact_section = ""
    if artifacts:
        artifact_section = f"\n\nARTIFACTS PROVIDED (file paths you can read/use):\n" + "\n".join(f"  - {a}" for a in artifacts)

    context_section = ""
    if context:
        context_section = f"\n\nCONTEXT FROM COMPANION:\n{context}"

    system_prompt = (
        f"{subagent.system_prompt}\n\n"
        f"You are the {subagent.name} subagent. You were delegated this task by a companion agent.\n"
        f"Focus on completing the goal efficiently. When done, clearly state what you accomplished "
        f"and list any output files."
        f"{context_section}"
        f"{artifact_section}"
    )

    max_steps = min(subagent.max_steps, MAX_SUBAGENT_STEPS)

    # Run the ReAct loop
    try:
        result = await _run_subagent_loop(
            model=SUBAGENT_MODEL,
            temperature=subagent.temperature,
            system_prompt=system_prompt,
            goal=goal,
            tools=scoped_tools,
            max_steps=max_steps,
        )
    except Exception as e:
        traceback.print_exc()
        return {
            "error": f"SubAgent execution failed: {str(e)}",
            "subagent_name": subagent.name,
        }

    return {
        "result": result.get("summary", ""),
        "files": result.get("files", []),
        "subagent_name": subagent.name,
        "subagent_id": subagent_id,
        "steps_taken": result.get("steps_taken", 0),
        "success": not result.get("error"),
    }


# ─── SubAgent ReAct Loop ───────────────────────────────

async def _run_subagent_loop(
    model: str,
    temperature: float,
    system_prompt: str,
    goal: str,
    tools: list[dict],
    max_steps: int,
) -> dict:
    """
    Run a simplified ReAct loop for a subagent.

    Lighter than the full agent loop — no warm memory, no reflection pauses,
    no DB task tracking. Just: think → act → observe → repeat.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"TASK: {goal}\n\nBegin working. Think step by step."},
    ]

    steps_taken = 0
    last_content = ""

    # Gemini safety settings
    safety_settings = None
    if "gemini" in model.lower():
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
        ]

    for step in range(1, max_steps + 1):
        steps_taken = step

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096,
            "tools": tools,
            "tool_choice": "auto",
            "stream": False,
        }
        if safety_settings:
            kwargs["safety_settings"] = safety_settings

        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as e:
            return {"summary": f"LLM call failed at step {step}: {e}", "error": True, "steps_taken": steps_taken}

        choice = response.choices[0]
        content = choice.message.content or ""
        last_content = content

        # No tool calls — subagent is done thinking/responding
        if not choice.message.tool_calls:
            print(f"  ✅ SubAgent completed at step {step}")
            break

        # Execute tool calls
        assistant_msg = {"role": "assistant", "content": content}
        assistant_msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in choice.message.tool_calls
        ]
        messages.append(assistant_msg)

        for tc in choice.message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            tool_name = tc.function.name
            print(f"  🔧 SubAgent step {step}: {tool_name}({json.dumps(args)[:80]})")

            result = await _execute_mcp_tool(tool_name, args)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str)[:4000],
            })

        # Nudge the subagent to continue or finish
        if step < max_steps:
            messages.append({
                "role": "user",
                "content": f"Step {step}/{max_steps} complete. Continue working or state your final result if done.",
            })

    # Extract file paths mentioned in the final response
    files = _extract_file_paths(last_content)

    return {
        "summary": last_content,
        "files": files,
        "steps_taken": steps_taken,
    }


async def _execute_mcp_tool(tool_name: str, args: dict) -> dict:
    """Execute an MCP tool call via the MCP manager."""
    try:
        result = await mcp_manager.call_tool(tool_name, args)
        return result
    except Exception as e:
        return {"error": f"Tool '{tool_name}' failed: {str(e)}"}


def _extract_file_paths(text: str) -> list[str]:
    """Extract file paths from the subagent's final response text."""
    import re
    paths = []
    # Match common file path patterns
    for match in re.finditer(r'(?:file[_\s]*path|output|saved|created|exported)[:\s]*[`"\']*([^\s`"\']+\.\w{2,5})', text, re.IGNORECASE):
        paths.append(match.group(1))
    # Also match explicit paths like /data/agent/...
    for match in re.finditer(r'(?:data/agent/[^\s`"\']+)', text):
        paths.append(match.group(0))
    return list(set(paths))  # dedupe
