from typing import Any

from pydantic import BaseModel


class MCPRequest(BaseModel):
    tool: str
    arguments: dict[str, Any]


class MCPResponse(BaseModel):
    result: Any
    error: str | None = None
