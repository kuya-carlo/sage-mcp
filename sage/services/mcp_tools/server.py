# sage/services/mcp_tools/mcp_server.py

from fastmcp import FastMCP
from sage.services.mcp_tools import commons, workspace, tasks, sensor

mcp = FastMCP("SAGE")

@mcp.tool()
async def get_commons_tree(program_code: str,
                           year_level: int,
                           semester: int) -> dict:
    """Fetch curriculum from Ghost Commons for a program"""
    return await commons.get_commons_tree(
        program_code.upper(), year_level, semester
    )

@mcp.tool()
async def create_semester_tree(program_code: str,
                               year_level: int,
                               semester: int,
                               workspace_root_id: str,
                               workspace_id: str) -> dict:
    """Build Notion workspace for a semester"""
    return await workspace.create_semester_tree(
        program_code.upper(), year_level, semester,
        workspace_root_id, workspace_id
    )

@mcp.tool()
async def breakdown_task(task_id: str,
                         task_title: str,
                         workspace_id: str,
                         task_notes: str = "none") -> dict:
    """Split an overwhelming task into micro-steps"""
    return await tasks.breakdown_task(
        task_id, task_title, task_notes, workspace_id
    )

@mcp.tool()
async def get_weekly_load(workspace_id: str,
                          week_start_date: str) -> dict:
    """Calculate current week cognitive load score"""
    return await sensor.get_weekly_load(workspace_id, week_start_date)

@mcp.tool()
async def block_calendar_slot(workspace_id: str,
                              date: str,
                              label: str) -> dict:
    """Create protected recovery block on Notion calendar"""
    return await sensor.block_calendar_slot(workspace_id, date, label)

@mcp.tool()
async def get_dismissed_blocks(workspace_id: str,
                               week: str) -> dict:
    """Check if user dismissed a burnout block this week"""
    return await sensor.get_dismissed_blocks(workspace_id, week)