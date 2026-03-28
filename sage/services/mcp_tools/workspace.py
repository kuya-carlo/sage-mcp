import asyncio
import json
import logging
import re

import httpx

from sage.config import settings
from sage.database import get_db_pool
from sage.routers.notion_auth import get_notion_token
from sage.services.notion import NotionService

logger = logging.getLogger("workspace")


async def get_commons_for_program(program_code: str, year_level: int, semester: int) -> list[dict]:
    """Query cmo_records WHERE program_code=$1 AND year_level=$2 AND semester=$3"""
    pool = await get_db_pool()
    query = """
        SELECT * FROM cmo_records
        WHERE program_code = $1 AND year_level = $2 AND semester = $3
    """
    async with pool.acquire() as connection:
        records = await connection.fetch(query, program_code, year_level, semester)
        return [dict(record) for record in records]


async def expand_topics_for_course(
    course_code: str, course_title: str, competency_tags: list[str]
) -> list:
    """Check DB for predefined topics first, then fallback to AI if missing."""
    pool = await get_db_pool()
    query = """
        SELECT topic_name as topic, competency, summary, study_prompt
        FROM curriculum_topics
        WHERE course_code = $1
        ORDER BY topic_order
    """

    async with pool.acquire() as connection:
        rows = await connection.fetch(query, course_code)
        if rows:
            logger.info(f"Using {len(rows)} predefined topics for {course_code}")
            return [dict(row) for row in rows]

    # Fallback to AI if no topics in DB
    logger.info(f"Expanding topics via AI for {course_title}")
    url = f"{settings.vultr_inference_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.vultr_inference_key}",
        "Content-Type": "application/json",
    }

    system_prompt = """You are a curriculum expert. Given a university course and its competency areas, generate specific study topics.
Respond ONLY with valid JSON. No markdown, no preamble.

Output schema:
[
  {
    "topic": "specific topic name",
    "competency": "which competency tag this belongs to",
    "summary": "2 sentence explanation of this topic",
    "study_prompt": "one focused question to guide studying"
  }
]

Rules:
- Generate 2-4 topics per competency tag
- Topics must be specific, not generic
- topic names should sound like actual lecture titles
- summary must be beginner-friendly
- study_prompt must be one actionable question"""

    user_message = f"Course: {course_title}\nCompetencies: {', '.join(competency_tags)}"

    payload = {
        "model": "Qwen2.5-Coder-32B-Instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.3,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]

            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                content = match.group(0)

            data = json.loads(content)
            if isinstance(data, list):
                valid_tags = [str(t) for t in competency_tags]
                for item in data:
                    if item.get("competency") not in valid_tags:
                        item["competency"] = valid_tags[0]
                return data
    except Exception as e:
        logger.error(f"Error expanding topics for {course_title}: {e}")

    # Fallback
    return [
        {"topic": str(tag), "competency": str(tag), "summary": "", "study_prompt": ""}
        for tag in competency_tags
    ]


async def create_semester_tree(
    program_code: str,
    year_level: int,
    semester: int,
    workspace_id: str,
) -> dict:
    access_token = await get_notion_token(workspace_id)
    async with NotionService(access_token=access_token) as notion_service:
        return await _create_semester_tree_impl(
            program_code, year_level, semester, workspace_id, notion_service
        )


async def _create_semester_tree_impl(
    program_code: str,
    year_level: int,
    semester: int,
    workspace_id: str,
    notion_service: NotionService,
) -> dict:
    # 1. Create Workspace root page
    root_title = f"SAGE — {program_code} Y{year_level}S{semester}"
    root_create_res = await notion_service.create_root_page(root_title)
    if "error" in root_create_res:
        return {
            "status": "error",
            "message": f"Failed to create root page: {root_create_res['error']}",
        }

    new_root_page_id = root_create_res["id"]

    # Save root ID
    pool = await get_db_pool()
    save_query = "UPDATE user_tokens SET root_page_id = $1 WHERE workspace_id = $2"
    async with pool.acquire() as connection:
        await connection.execute(save_query, new_root_page_id, workspace_id)

    # 2. Get Commons and parallelize course creation with a global semaphore
    commons = await get_commons_for_program(program_code, year_level, semester)

    global_sem = asyncio.Semaphore(2)  # Limit total courses being built concurrently

    async def create_course_with_dbs(course: dict):
        async with global_sem:
            course_title = course.get("course_title", "Unknown Course")
            competency_tags = course.get("competency_tags", [])
            course_code = course.get("course_code", "UNKNOWN")

            # Small delay between courses to let SSE settle
            await asyncio.sleep(0.5)

            # a. Create course page
            sub_page_response = await notion_service.create_page(
                parent_id=new_root_page_id,
                title=course_title,
                icon_emoji="📖",
            )
        if "error" in sub_page_response:
            return 0, 0

        sub_page_id = sub_page_response["id"]

        # b. Create Databases in parallel
        tasks_db_coro = notion_service.create_database(
            parent_page_id=sub_page_id,
            title="Tasks",
            properties={
                "Name": {"title": {}},
                "Status": {
                    "select": {
                        "options": [
                            {"name": "Todo", "color": "red"},
                            {"name": "In Progress", "color": "yellow"},
                            {"name": "Done", "color": "green"},
                        ]
                    }
                },
                "Due Date": {"date": {}},
                "Needs Breakdown": {"checkbox": {}},
            },
        )

        topics_db_coro = None
        if competency_tags:
            topics_db_coro = notion_service.create_database(
                parent_page_id=sub_page_id,
                title="topics",
                properties={
                    "Topic": {"title": {}},
                    "Competency": {
                        "select": {
                            "options": [
                                {"name": str(tag), "color": "blue"} for tag in competency_tags
                            ]
                        }
                    },
                    "Status": {
                        "select": {
                            "options": [
                                {"name": "Not Started", "color": "red"},
                                {"name": "In Progress", "color": "yellow"},
                                {"name": "Mastered", "color": "green"},
                            ]
                        }
                    },
                },
            )

        db_results = (
            await asyncio.gather(tasks_db_coro, topics_db_coro)
            if topics_db_coro
            else [await tasks_db_coro, None]
        )

        num_dbs = 1
        topics_db_response = db_results[1]
        if topics_db_response and "error" not in topics_db_response:
            num_dbs += 1
            topics_db_id = topics_db_response["id"]
            expanded_topics = await expand_topics_for_course(
                course_code, course_title, competency_tags
            )

            async def create_topic_with_content(topic_item: dict):
                entry = await notion_service.create_database_entry(
                    database_id=topics_db_id,
                    properties={
                        "Topic": {"title": [{"text": {"content": topic_item["topic"]}}]},
                        "Competency": {"select": {"name": topic_item["competency"]}},
                        "Status": {"select": {"name": "Not Started"}},
                    },
                )
                if "error" not in entry and (
                    topic_item.get("summary") or topic_item.get("study_prompt")
                ):
                    children = []
                    if topic_item.get("summary"):
                        children.extend(
                            [
                                {
                                    "object": "block",
                                    "type": "heading_2",
                                    "heading_2": {
                                        "rich_text": [
                                            {"type": "text", "text": {"content": "Summary"}}
                                        ]
                                    },
                                },
                                {
                                    "object": "block",
                                    "type": "paragraph",
                                    "paragraph": {
                                        "rich_text": [
                                            {
                                                "type": "text",
                                                "text": {"content": topic_item["summary"]},
                                            }
                                        ]
                                    },
                                },
                            ]
                        )
                    if topic_item.get("study_prompt"):
                        children.extend(
                            [
                                {
                                    "object": "block",
                                    "type": "heading_2",
                                    "heading_2": {
                                        "rich_text": [
                                            {"type": "text", "text": {"content": "Study Prompt"}}
                                        ]
                                    },
                                },
                                {
                                    "object": "block",
                                    "type": "callout",
                                    "callout": {
                                        "rich_text": [
                                            {
                                                "type": "text",
                                                "text": {"content": topic_item["study_prompt"]},
                                            }
                                        ],
                                        "icon": {"emoji": "🎯"},
                                    },
                                },
                            ]
                        )
                    await notion_service.append_block_children(
                        page_id=entry["id"], children=children
                    )

            sem = asyncio.Semaphore(2)

            async def create_topic_with_sem(t):
                async with sem:
                    await create_topic_with_content(t)
                    await asyncio.sleep(0.3)

            if expanded_topics:
                await asyncio.gather(*(create_topic_with_sem(t) for t in expanded_topics))

        return 1, num_dbs

    # 3. Parallelize Course Creation
    results = await asyncio.gather(*(create_course_with_dbs(c) for c in commons))

    return {
        "status": "created",
        "root_page_id": new_root_page_id,
        "program_code": program_code,
        "year_level": year_level,
        "semester": semester,
        "created_pages": sum(r[0] for r in results),
        "created_databases": sum(r[1] for r in results),
    }
