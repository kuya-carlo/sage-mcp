import httpx
from datetime import datetime, timedelta
from typing import Dict, Any

from sage.config import settings
from sage.database import get_db_pool
from sage.services.notion import NotionService
from sage.services.mcp_tools.workspace import get_decrypted_token

notion_service = NotionService()

async def get_weekly_load(workspace_id: str, week_start_date: str) -> dict:
    access_token = await get_decrypted_token(workspace_id)
    
    start_dt = datetime.fromisoformat(week_start_date)
    week_end_dt = start_dt + timedelta(days=6)
    week_start = start_dt.strftime("%Y-%m-%d")
    week_end = week_end_dt.strftime("%Y-%m-%d")
    
    # 2. Get Tasks databases
    databases = await notion_service.search_databases(access_token, query="Tasks")

    async def get_tasks_count_for_week(db_list: list, w_start: str, w_end: str) -> int:
        count = 0
        for db in db_list:
            db_id = db["id"]
            tasks = await notion_service.query_tasks_due_this_week(access_token, db_id, w_start, w_end)
            count += len(tasks)
        return count

    # Count total tasks_this_week
    tasks_this_week = await get_tasks_count_for_week(databases, week_start, week_end)
    
    # Repeat for past 3 weeks
    past_counts = []
    for i in range(1, 4):
        past_w_start_dt = start_dt - timedelta(days=7 * i)
        past_w_end_dt = past_w_start_dt + timedelta(days=6)
        
        past_count = await get_tasks_count_for_week(
            databases, 
            past_w_start_dt.strftime("%Y-%m-%d"), 
            past_w_end_dt.strftime("%Y-%m-%d")
        )
        past_counts.append(past_count)
        
    avg_past_3_weeks = sum(past_counts) / 3.0 if past_counts else None
    
    # Calculate load_score
    if avg_past_3_weeks is not None and avg_past_3_weeks > 0:
        score = (tasks_this_week / avg_past_3_weeks) * 100
    else:
        score = (tasks_this_week / 12.0) * 100
        
    return {
        "tasks_this_week": tasks_this_week,
        "avg_past_3_weeks": round(avg_past_3_weeks, 1) if avg_past_3_weeks is not None else None,
        "load_score": round(score, 1),
        "threshold_exceeded": score > 80
    }

async def block_calendar_slot(workspace_id: str, date: str, label: str) -> dict:
    access_token = await get_decrypted_token(workspace_id)
    
    databases = await notion_service.search_databases(access_token, query="SAGE Calendar")
        
    calendar_db_id = None
    for db in databases:
        title_prop = db.get("title", [])
        title_text = "".join(t.get("plain_text", "") for t in title_prop)
        if title_text == "SAGE Calendar":
            calendar_db_id = db["id"]
            break
            
    if not calendar_db_id and databases:
        calendar_db_id = databases[0]["id"]
        
    if not calendar_db_id:
        # Fallback parent ID usually comes from configuration
        parent_page_id = settings.notion_root_page_id
        if not parent_page_id:
            # If not configured, we try to find ONE page to act as parent
            pages = await notion_service.search_pages(access_token, query="")
            if not pages:
                 raise ValueError("Could not find any pages to host the SAGE Calendar. Grant access to a page!")
            parent_page_id = pages[0]["id"]
            
        db_properties = {
            "Name": {"title": {}},
            "Date": {"date": {}},
            "Protected": {"checkbox": {}}
        }
        db_res = await notion_service.create_database(
            access_token=access_token,
            parent_page_id=parent_page_id,
            title="SAGE Calendar",
            properties=db_properties
        )
        calendar_db_id = db_res["id"]
        
    entry_res = await notion_service.create_calendar_entry(
        access_token=access_token,
        calendar_db_id=calendar_db_id,
        title=label,
        date=date,
        protected=True
    )
    
    pool = await get_db_pool()
    query = """
        INSERT INTO dismissed_blocks (workspace_id, week_start, dismissed)
        VALUES ($1, $2, False)
        ON CONFLICT DO NOTHING
    """
    async with pool.acquire() as connection:
        await connection.execute(query, workspace_id, date)
        
    return {
        "created": True,
        "entry_id": entry_res["id"],
        "date": date,
        "label": label
    }

async def get_dismissed_blocks(workspace_id: str, week: str) -> dict:
    pool = await get_db_pool()
    query = """
        SELECT * FROM dismissed_blocks
        WHERE workspace_id = $1 AND week_start = $2
    """
    async with pool.acquire() as connection:
        records = await connection.fetch(query, workspace_id, week)
        
    return {
        "dismissed": len(records) > 0,
        "count": len(records)
    }
