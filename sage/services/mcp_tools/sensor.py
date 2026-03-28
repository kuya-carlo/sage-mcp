from datetime import datetime, timedelta

from sage.config import settings
from sage.database import get_db_pool
from sage.routers.notion_auth import get_notion_token
from sage.services.notion import NotionService


async def get_weekly_load(
    workspace_id: str, week_start_date: str, notion_service: NotionService | None = None
) -> dict:
    if notion_service is None:
        access_token = await get_notion_token(workspace_id)
        async with NotionService(access_token=access_token) as ns:
            return await _get_weekly_load_impl(ns, week_start_date)
    return await _get_weekly_load_impl(notion_service, week_start_date)


async def _get_weekly_load_impl(notion_service: NotionService, week_start_date: str) -> dict:
    start_dt = datetime.fromisoformat(week_start_date)
    week_end_dt = start_dt + timedelta(days=6)
    week_start = start_dt.strftime("%Y-%m-%d")
    week_end = week_end_dt.strftime("%Y-%m-%d")

    # 2. Get Tasks databases
    databases = await notion_service.search_databases(query="Tasks")

    async def get_tasks_count_for_week(db_list: list, w_start: str, w_end: str) -> int:
        count = 0
        for db in db_list:
            db_id = db["id"]
            tasks = await notion_service.query_tasks_due_this_week(db_id, w_start, w_end)
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
            databases, past_w_start_dt.strftime("%Y-%m-%d"), past_w_end_dt.strftime("%Y-%m-%d")
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
        "threshold_exceeded": score > 80,
    }


async def block_calendar_slot(
    workspace_id: str, date: str, label: str, notion_service: NotionService | None = None
) -> dict:
    if notion_service is None:
        access_token = await get_notion_token(workspace_id)
        async with NotionService(access_token=access_token) as ns:
            return await _block_calendar_slot_impl(workspace_id, date, label, ns)
    return await _block_calendar_slot_impl(workspace_id, date, label, notion_service)


async def _block_calendar_slot_impl(
    workspace_id: str, date: str, label: str, notion_service: NotionService
) -> dict:
    databases = await notion_service.search_databases(query="SAGE Calendar")

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
        # 1. Use Config -> Saved DB ID -> Search Fallback
        parent_page_id = settings.notion_root_page_id

        if not parent_page_id:
            # Create a new root page if none exists
            res = await notion_service.create_root_page("SAGE Workspace Root")
            parent_page_id = res["id"]

            # Save this page as the user's preferred root for future use
            pool = await get_db_pool()
            save_query = "UPDATE user_tokens SET root_page_id = $1 WHERE workspace_id = $2"
            async with pool.acquire() as connection:
                await connection.execute(save_query, parent_page_id, workspace_id)

        db_properties = {"Name": {"title": {}}, "Date": {"date": {}}, "Protected": {"checkbox": {}}}
        db_res = await notion_service.create_database(
            parent_page_id=parent_page_id,
            title="SAGE Calendar",
            properties=db_properties,
        )
        calendar_db_id = db_res["id"]

    entry_res = await notion_service.create_calendar_entry(
        calendar_db_id=calendar_db_id,
        title=label,
        date=date,
        protected=True,
    )

    pool = await get_db_pool()
    query = """
        INSERT INTO dismissed_blocks (workspace_id, week_start, dismissed)
        VALUES ($1, $2, False)
        ON CONFLICT DO NOTHING
    """
    async with pool.acquire() as connection:
        await connection.execute(query, workspace_id, date)

    return {"created": True, "entry_id": entry_res["id"], "date": date, "label": label}


async def get_dismissed_blocks(workspace_id: str, week: str) -> dict:
    pool = await get_db_pool()
    query = """
        SELECT * FROM dismissed_blocks
        WHERE workspace_id = $1 AND week_start = $2
    """
    async with pool.acquire() as connection:
        records = await connection.fetch(query, workspace_id, week)

    return {"dismissed": len(records) > 0, "count": len(records)}
