from cryptography.fernet import Fernet
from fastapi import HTTPException
from sage.config import settings
from sage.database import get_db_pool
from sage.services.notion import NotionService

# Note: In an MCP tool context, these might be called directly by the agent
# and might not need to throw HTTP exceptions if the agent is expected to handle them.
# However, instructed to use HTTPException here.
notion_service = NotionService()

async def get_decrypted_token(workspace_id: str) -> str:
    """Query user_tokens table for workspace_id and decrypt the token."""
    pool = await get_db_pool()
    query = "SELECT encrypted_token FROM user_tokens WHERE workspace_id = $1"
    async with pool.acquire() as connection:
        record = await connection.fetchrow(query, workspace_id)
        
    if not record:
        raise HTTPException(status_code=401, detail="Workspace ID not found or unauthorized")
        
    encrypted_token = record["encrypted_token"]
    fernet = Fernet(settings.fernet_key.encode())
    decrypted_token = fernet.decrypt(encrypted_token.encode()).decode()
    return decrypted_token

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

async def create_semester_tree(program_code: str, year_level: int, semester: int, workspace_root_id: str, workspace_id: str) -> dict:
    """Read curriculum from Supabase then build a Notion workspace hierarchy."""
    # 1. get_decrypted_token
    access_token = await get_decrypted_token(workspace_id)
    
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
            return {
                "status": "already_exists",
                "root_page_id": result["id"]
            }

    # 4. Create root page titled "{program_code} — Year {year_level} Sem {semester}" under workspace_root_id with icon 🎓
    root_page_response = await notion_service.create_page(
        access_token=access_token,
        parent_id=workspace_root_id,
        title=page_title,
        icon_emoji="🎓"
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
            icon_emoji="📖"
        )
        sub_page_id = sub_page_response["id"]
        created_pages += 1
        
        # b. Create Tasks database inside sub-page
        db_properties = {
            "Name": {"title": {}},
            "Status": {"select": {"options": [
                {"name": "Todo", "color": "red"}, 
                {"name": "In Progress", "color": "yellow"},
                {"name": "Done", "color": "green"}
            ]}},
            "Due Date": {"date": {}},
            "Needs Breakdown": {"checkbox": {}}
        }
        
        await notion_service.create_database(
            access_token=access_token,
            parent_page_id=sub_page_id,
            title="Tasks",
            properties=db_properties
        )
        created_databases += 1
        
        # c. Append competency_tags as a bulleted list block to the sub-page
        if competency_tags:
            children_blocks = []
            for tag in competency_tags:
                children_blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": str(tag)}}]
                    }
                })
            
            await notion_service.append_block_children(
                access_token=access_token,
                page_id=sub_page_id,
                children=children_blocks
            )
            
    # 6. Return response
    return {
        "status": "created",
        "root_page_id": new_root_page_id,
        "program_code": program_code,
        "year_level": year_level,
        "semester": semester,
        "created_pages": created_pages,
        "created_databases": created_databases
    }
