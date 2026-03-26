import json

import httpx

from sage.config import settings
from sage.services.mcp_tools.workspace import get_decrypted_token
from sage.services.notion import NotionService

notion_service = NotionService()

BREAKDOWN_SYSTEM_PROMPT = """
You are SAGE. You receive a task title and optional notes.
You respond ONLY with valid JSON. No preamble, no markdown.

Output schema:
{
  "micro_steps": [
    {
      "order": integer,
      "action": string,
      "is_micro_start": boolean
    }
  ]
}

Rules:
- Always return exactly 3-5 steps. Never fewer, never more.
- Each action starts with an imperative verb.
- Each step completable in under 2 minutes.
- Specific to this task — never generic.
- No clinical language. No ADHD references.
- Infer steps from title if notes empty.
"""

async def call_breakdown_model(task_title: str, task_notes: str) -> dict:
    url = f"{settings.vultr_inference_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.vultr_inference_key}",
        "HTTP-Referer": settings.or_site_url or "http://localhost:8000",
        "X-Title": settings.or_app_name or "SAGE"
    }
    payload = {
        "model": "Qwen2.5-Coder-32B-Instruct",
        "messages": [
            {"role": "system", "content": BREAKDOWN_SYSTEM_PROMPT},
            {"role": "user", "content": f"Task: {task_title}\nNotes: {task_notes}"}
        ]
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload, timeout=60.0)
        response.raise_for_status()
        json_resp = response.json()
        
    content = json_resp["choices"][0]["message"]["content"].strip()
    
    # Strip markdown formatting just in case
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
        
    try:
        parsed_dict = json.loads(content.strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON response: {content}") from e
        
    micro_steps = parsed_dict.get("micro_steps", [])
    if not (3 <= len(micro_steps) <= 5):
        raise ValueError(f"Validation failed: Expected 3-5 micro_steps, got {len(micro_steps)}")
        
    return parsed_dict

async def breakdown_task(task_id: str, task_title: str, task_notes: str, workspace_id: str) -> dict:
    access_token = await get_decrypted_token(workspace_id)
    
    breakdown_res = await call_breakdown_model(task_title, task_notes or "none")
    micro_steps = breakdown_res.get("micro_steps", [])
    
    micro_start_step_action = None
    
    for step in micro_steps:
        action = step.get("action", "Unknown Action")
        is_micro_start = step.get("is_micro_start", False)
        
        icon = "⚡" if is_micro_start else "▪️"
        
        if is_micro_start and micro_start_step_action is None:
            micro_start_step_action = action
            
        await notion_service.create_page(
            access_token=access_token,
            parent_id=task_id,
            title=action,
            icon_emoji=icon
        )
        
    await notion_service.update_page_property(
        access_token=access_token,
        page_id=task_id,
        property_name="Needs Breakdown",
        value={"checkbox": False}
    )
    
    return {
        "task_id": task_id,
        "steps_created": len(micro_steps),
        "micro_start_step": micro_start_step_action
    }
