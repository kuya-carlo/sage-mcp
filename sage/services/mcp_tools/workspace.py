import json
import re

import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException

from sage.config import settings
from sage.database import get_db_pool
from sage.services.notion import NotionService

# Note: In an MCP tool context, these might be called directly by the agent
# and might not need to throw HTTP exceptions if the agent is expected to handle them.
# However, instructed to use HTTPException here.
notion_service = NotionService()


async def get_decrypted_token(workspace_id: str) -> tuple[str, str | None]:
    """Query user_tokens table for workspace_id and decrypt the token."""
    pool = await get_db_pool()
    query = "SELECT encrypted_token, root_page_id FROM user_tokens WHERE workspace_id = $1"
    async with pool.acquire() as connection:
        record = await connection.fetchrow(query, workspace_id)

    if not record:
        raise HTTPException(status_code=401, detail="Workspace ID not found or unauthorized")

    encrypted_token = record["encrypted_token"]
    root_page_id = record.get("root_page_id")
    fernet = Fernet(settings.fernet_key.encode())
    decrypted_token = fernet.decrypt(encrypted_token.encode()).decode()
    return decrypted_token, root_page_id


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


async def expand_topics_for_course(course_title: str, competency_tags: list[str]) -> list:
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
        print(f"Error expanding topics: {e}")

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
    workspace_root_id: str = "",
) -> dict:
    """Read curriculum from Supabase then build a Notion workspace hierarchy."""
    # 1. get_decrypted_token
    access_token, saved_root_id = await get_decrypted_token(workspace_id)

    # Use explicitly passed ID, or saved ID, or fallback to search
    if not workspace_root_id:
        if saved_root_id:
            workspace_root_id = saved_root_id
        else:
            pages = await notion_service.search_pages(access_token, query="")
            if not pages:
                return {
                    "status": "error",
                    "message": "No accessible pages found! SAGE needs access to at least one Notion page to build under.",
                }
            workspace_root_id = pages[0]["id"]

            # Save the derived root ID back to the database
            pool = await get_db_pool()
            save_query = "UPDATE user_tokens SET root_page_id = $1 WHERE workspace_id = $2"
            async with pool.acquire() as connection:
                await connection.execute(save_query, workspace_root_id, workspace_id)

    # 2. get_commons_for_program
    commons = await get_commons_for_program(program_code, year_level, semester)

    # 3. Search for existing page
    page_title = f"{program_code} — Year {year_level} Sem {semester}"
    search_results = await notion_service.search_pages(access_token, query=page_title)

    # Check if a matching page already exists within the current root
    for result in search_results:
        # Check if title strictly matches (Notion search can be fuzzy)
        title_prop = result.get("properties", {}).get("title", {}).get("title", [])
        extracted_title = "".join(t.get("plain_text", "") for t in title_prop) if title_prop else ""

        # Check parent constraint (Ensure we're not false-flagging identically named pages elsewhere)
        parent_id = result.get("parent", {}).get("page_id", "").replace("-", "")
        formatted_root_id = workspace_root_id.replace("-", "")

        if extracted_title == page_title and parent_id == formatted_root_id:
            return {"status": "already_exists", "root_page_id": result["id"]}

    # 4. Create root page titled "{program_code} — Year {year_level} Sem {semester}" under workspace_root_id with icon 🎓
    root_page_response = await notion_service.create_page(
        access_token=access_token, parent_id=workspace_root_id, title=page_title, icon_emoji="🎓"
    )
    new_root_page_id = root_page_response["id"]

    created_pages = 0
    created_databases = 0

    # 5. For each course in commons
    for course in commons:
        course_title = course.get("course_title", "Unknown Course")
        competency_tags = course.get("competency_tags", [])

        # a. Create sub-page titled course_title under root page with icon 📖
        sub_page_response = await notion_service.create_page(
            access_token=access_token,
            parent_id=new_root_page_id,
            title=course_title,
            icon_emoji="📖",
        )
        sub_page_id = sub_page_response["id"]
        created_pages += 1

        # b. Create Tasks database inside sub-page
        db_properties = {
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
        }

        await notion_service.create_database(
            access_token=access_token,
            parent_page_id=sub_page_id,
            title="Tasks",
            properties=db_properties,
        )
        created_databases += 1

        # c. Create Topics Database inside sub-page
        if competency_tags:
            topics_db_properties = {
                "Topic": {"title": {}},
                "Competency": {
                    "select": {
                        "options": [{"name": str(tag), "color": "blue"} for tag in competency_tags]
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
            }

            topics_db_response = await notion_service.create_database(
                access_token=access_token,
                parent_page_id=sub_page_id,
                title="Topics & Competencies",
                properties=topics_db_properties,
            )
            created_databases += 1
            topics_db_id = topics_db_response["id"]

            # Expand competency tags into actual topics via AI
            expanded_topics = await expand_topics_for_course(course_title, competency_tags)

            for topic_item in expanded_topics:
                # Create database entry
                entry = await notion_service.create_database_entry(
                    access_token=access_token,
                    database_id=topics_db_id,
                    properties={
                        "Topic": {"title": [{"text": {"content": topic_item["topic"]}}]},
                        "Competency": {"select": {"name": topic_item["competency"]}},
                        "Status": {"select": {"name": "Not Started"}},
                    },
                )

                # Add summary and study prompt as page content
                if topic_item.get("summary") or topic_item.get("study_prompt"):
                    children = [
                        {
                            "object": "block",
                            "type": "heading_2",
                            "heading_2": {
                                "rich_text": [{"type": "text", "text": {"content": "Summary"}}]
                            },
                        },
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {"content": topic_item.get("summary", "")},
                                    }
                                ]
                            },
                        },
                        {
                            "object": "block",
                            "type": "heading_2",
                            "heading_2": {
                                "rich_text": [{"type": "text", "text": {"content": "Study Prompt"}}]
                            },
                        },
                        {
                            "object": "block",
                            "type": "callout",
                            "callout": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {"content": topic_item.get("study_prompt", "")},
                                    }
                                ],
                                "icon": {"emoji": "🎯"},
                            },
                        },
                    ]

                    await notion_service.append_block_children(
                        access_token=access_token, page_id=entry["id"], children=children
                    )

    # 6. Return response
    return {
        "status": "created",
        "root_page_id": new_root_page_id,
        "program_code": program_code,
        "year_level": year_level,
        "semester": semester,
        "created_pages": created_pages,
        "created_databases": created_databases,
    }
