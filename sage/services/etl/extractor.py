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
  "academic_year": string,
  "classification": string,
  "year_level": integer,
  "semester": integer,
  "course_code": string,
  "course_title": string,
  "competency_tags": string[]
}]

Rules:
- Extract every course listed. Do not summarize or skip.
- program_code and academic_year can often be found in the header: "(REVISED)POLICIES, STANDARDS AND GUIDELINES FOR THE {program} ({program_shorthand}) EFFECTIVE (AY) {ay}."
- classification must be one of: [core_gened, shared_major, program_specific, elective].
    * core_gened: General Education (English, Math, History, etc.)
    * shared_major: Technical courses shared between IT/CS/IS (e.g., Intro to Computing, Programming 1/2).
    * program_specific: Courses specific to this degree (e.g., Operating Systems, VLSI, Network Admin).
    * elective: Any elective course.
- academic_year should be in format "AY YYYY-YYYY" or simply the year found.
- year_level must be integer 1-5.
- semester must be integer 1 or 2.
- competency_tags must be lowercase, 1-3 words each, max 4 tags.
- IMPORTANT: If year_level or semester are not explicitly in the course row, infer them from the section headers (e.g., "First Year", "Second Semester") found earlier in the text.
- If a field genuinely cannot be determined even with context, use null.
"""


def chunk_text_blocks(
    blocks: list[str], max_chars: int = 15000, overlap_pages: int = 2
) -> list[str]:
    """
    Chunks text blocks with overlap to ensure context (like year/sem headers)
    isn't lost between chunks.
    """
    chunks = []
    # We'll use a sliding window of pages
    for i in range(0, len(blocks), max(1, len(blocks) // 5)):  # Ensure at least 5 chunks
        window = blocks[i : i + 8]  # Try to take 8 pages at a time
        text = "\n".join(window)
        if len(text) > max_chars * 2:  # Keep them reasonable
            text = text[: max_chars * 2]
        chunks.append(text)
        if i + 8 >= len(blocks):
            break

    return chunks


async def extract_records(chunk: str, program_code: str) -> list[dict]:
    url = f"{settings.vultr_inference_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.vultr_inference_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "Qwen2.5-Coder-32B-Instruct",
        "messages": [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": chunk},
        ],
        "temperature": 0.1,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers, timeout=180.0)
        response.raise_for_status()

    text = response.json()["choices"][0]["message"]["content"]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Retry once with stricter prompt
        retry_payload = {
            **payload,
            "messages": payload["messages"]
            + [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": (
                        "Your previous response was not valid JSON. "
                        "Return only the JSON array, no other text."
                    ),
                },
            ],
        }
        async with httpx.AsyncClient() as client:
            retry = await client.post(url, json=retry_payload, headers=headers, timeout=180.0)
            retry.raise_for_status()

        try:
            return json.loads(retry.json()["choices"][0]["message"]["content"])
        except json.JSONDecodeError:
            print(f"[extractor] Double failure on chunk for {program_code}")
            return []


async def extract_all_chunks(chunks: list[str], program_code: str) -> list[dict]:
    results = []
    for chunk in chunks:
        records = await extract_records(chunk, program_code)
        results.extend(records)
    return results
