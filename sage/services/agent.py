import json

import httpx

from sage.config import settings
from sage.services.mcp_tools import commons, sensor, tasks, workspace

SAGE_SYSTEM_PROMPT = """
You are SAGE, an academic co-pilot for Filipino university
students. You have access to tools that read curriculum data
and build Notion workspaces.

Your behavior:
- Always call get_commons_tree before create_semester_tree.
- If get_commons_tree returns seeding_in_progress, tell the
  user their curriculum is being fetched and to try again
  in 30 seconds. Do not call create_semester_tree yet.
- Build the full workspace in one session once data is ready.
- After create_semester_tree completes, summarize what was
  built in plain language. Be encouraging, not clinical.
- Never mention token limits, API calls, or errors to user.
- Use "we" language: "We built your semester" not "I created".
- Always use UPPERCASE for program_code values: BSCPE, BSIT, BSCS, BSECE, BSIE

Tone: supportive, direct, peer-level. Senior student helping
a junior — not a chatbot, not a professor.
"""

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_commons_tree",
            "description": "Fetch curriculum from Ghost Commons for a program",
            "parameters": {
                "type": "object",
                "properties": {
                    "program_code": {"type": "string"},
                    "year_level": {"type": "integer"},
                    "semester": {"type": "integer"},
                },
                "required": ["program_code", "year_level", "semester"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_semester_tree",
            "description": "Build Notion workspace for a semester",
            "parameters": {
                "type": "object",
                "properties": {
                    "program_code": {"type": "string"},
                    "year_level": {"type": "integer"},
                    "semester": {"type": "integer"},
                },
                "required": ["program_code", "year_level", "semester"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "breakdown_task",
            "description": "Split an overwhelming task into micro-steps",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "task_title": {"type": "string"},
                    "task_notes": {"type": "string"},
                },
                "required": ["task_id", "task_title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weekly_load",
            "description": "Calculate current week cognitive load score",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "week_start_date": {"type": "string"},
                },
                "required": ["workspace_id", "week_start_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "block_calendar_slot",
            "description": "Create protected recovery block on Notion calendar",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "date": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["workspace_id", "date", "label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dismissed_blocks",
            "description": "Check if user dismissed a burnout block this week",
            "parameters": {
                "type": "object",
                "properties": {"workspace_id": {"type": "string"}, "week": {"type": "string"}},
                "required": ["workspace_id", "week"],
            },
        },
    },
]


async def call_tool(tool_name: str, parameters: dict, workspace_id: str) -> dict:
    try:
        if tool_name == "get_commons_tree":
            return await commons.get_commons_tree(
                program_code=parameters["program_code"],
                year_level=parameters["year_level"],
                semester=parameters["semester"],
            )
        elif tool_name == "create_semester_tree":
            return await workspace.create_semester_tree(
                program_code=parameters["program_code"],
                year_level=parameters["year_level"],
                semester=parameters["semester"],
                workspace_id=workspace_id,
            )
        elif tool_name == "breakdown_task":
            return await tasks.breakdown_task(
                task_id=parameters["task_id"],
                task_title=parameters["task_title"],
                task_notes=parameters.get("task_notes", "none"),
                workspace_id=workspace_id,
            )
        elif tool_name == "get_weekly_load":
            return await sensor.get_weekly_load(
                workspace_id=workspace_id, week_start_date=parameters["week_start_date"]
            )
        elif tool_name == "block_calendar_slot":
            return await sensor.block_calendar_slot(
                workspace_id=workspace_id, date=parameters["date"], label=parameters["label"]
            )
        elif tool_name == "get_dismissed_blocks":
            return await sensor.get_dismissed_blocks(
                workspace_id=workspace_id, week=parameters["week"]
            )
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        return {"error": str(e)}


async def run_agent_loop(message: str, workspace_id: str, max_iterations: int = 10) -> dict:
    messages = [{"role": "user", "content": message}]

    injected_system_prompt = SAGE_SYSTEM_PROMPT + f"\nUser workspace_id: {workspace_id}"

    url = f"{settings.vultr_inference_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.vultr_inference_key}",
        "HTTP-Referer": settings.or_site_url or "http://localhost:8000",
        "X-Title": settings.or_app_name or "SAGE",
    }

    try:
        async with httpx.AsyncClient() as client:
            for iteration in range(max_iterations):
                payload = {
                    "model": "Qwen2.5-Coder-32B-Instruct",
                    "messages": [{"role": "system", "content": injected_system_prompt}] + messages,
                    "tools": TOOLS_SCHEMA,
                    "max_tokens": 1000,
                }

                response = await client.post(url, headers=headers, json=payload, timeout=60.0)
                if response.status_code != 200:
                    return {
                        "error": f"Vultr Inference API error: {response.text}",
                        "response": "I'm having trouble connecting to my inference brain (Vultr). Please check my API key or network.",
                    }

                resp_data = response.json()
                assistant_message = resp_data["choices"][0]["message"]

                # The structure of assistant_message directly from OpenRouter usually matches OpenAI API schema
                tool_calls = assistant_message.get("tool_calls", [])
                content = assistant_message.get("content")

                # Append the assistant's entire message back to the array for context matching
                messages.append(assistant_message)

                if tool_calls:
                    for tool_call in tool_calls:
                        call_id = tool_call["id"]
                        func_name = tool_call["function"]["name"]

                        try:
                            func_args = json.loads(tool_call["function"]["arguments"])
                        except json.JSONDecodeError:
                            func_args = {}

                        tool_result = await call_tool(func_name, func_args, workspace_id)

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": json.dumps(tool_result),
                            }
                        )
                    # Continue loop after handling all tool calls
                else:
                    # Text only response -> Finish
                    return {
                        "response": content or "",
                        "tool_calls_made": sum(
                            "tool_calls" in m
                            for (idx, m) in enumerate(messages)
                            if "tool_calls" in m
                        ),
                        "iterations": iteration + 1,
                    }
    except Exception as e:
        return {
            "error": str(e),
            "response": f"System error during agent execution: {e}. Let's try that again, something might have timed out.",
        }

    return {
        "response": "I ran into a problem completing that. I might have hit an iteration limit.",
        "tool_calls_made": max_iterations,
        "iterations": max_iterations,
    }
