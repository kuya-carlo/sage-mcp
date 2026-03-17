from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class MCPRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any]

class MCPResponse(BaseModel):
    result: Any
    error: Optional[str] = None
