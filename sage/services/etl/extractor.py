# sage/services/etl/extractor.py
# Handles text→schema extraction for user-uploaded syllabi only.
# CMO extraction is done inline in gaffa.py via parse_json action.

import json
import httpx
from sage.config import settings

EXTRACTION_SYSTEM_PROMPT = """
You are a structured data extractor for Philippine university
curriculum documents. You receive text extracted from a syllabus PDF.
You respond ONLY with valid JSON. No preamble, no markdown code fences.

Output schema (array of objects):
[{
  "program_code": string,
  "cmo_reference": string,
  "year_level": integer,
  "semester": integer,
  "course_code": string,
  "course_title": string,
  "competency_tags": string[]
}]

Rules:
- Extract every course listed. Do not summarize or skip.
- year_level must be integer 1-4.
- semester must be integer 1 or 2.
- competency_tags must be lowercase, 1-3 words each, max 4 tags.
- If a field cannot be determined, use null — never guess.
"""


def chunk_text_blocks(blocks: list[str],
                      max_chars: int = 24000) -> list[str]:
    chunks, current, count = [], [], 0
    for block in blocks:
        if count + len(block) > max_chars:
            chunks.append("\n".join(current))
            current, count = [], 0
        current.append(block)
        count += len(block)
    if current:
        chunks.append("\n".join(current))
    return chunks


async def extract_records(chunk: str,
                          program_code: str) -> list[dict]:
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "HTTP-Referer": settings.or_site_url,
        "X-Title": settings.or_app_name,
        "Content-Type": "application/json"
    }
    payload = {
        "model": "google/gemini-flash-1.5",
        "messages": [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": chunk}
        ]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=60.0
        )
        response.raise_for_status()

    text = response.json()["choices"][0]["message"]["content"]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Retry once with stricter prompt
        retry_payload = {
            **payload,
            "messages": payload["messages"] + [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": (
                        "Your previous response was not valid JSON. "
                        "Return only the JSON array, no other text."
                    )
                }
            ]
        }
        async with httpx.AsyncClient() as client:
            retry = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=retry_payload,
                headers=headers,
                timeout=60.0
            )
            retry.raise_for_status()

        try:
            return json.loads(
                retry.json()["choices"][0]["message"]["content"]
            )
        except json.JSONDecodeError:
            print(f"[extractor] Double failure on chunk for {program_code}")
            return []


async def extract_all_chunks(chunks: list[str],
                             program_code: str) -> list[dict]:
    results = []
    for chunk in chunks:
        records = await extract_records(chunk, program_code)
        results.extend(records)
    return results
