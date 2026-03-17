from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class CMORecord(BaseModel):
    id: UUID
    program_code: str
    cmo_reference: str
    year_level: int = Field(ge=1, le=5)
    semester: int = Field(ge=1, le=4)
    course_code: str
    course_title: str
    competency_tags: List[str] = Field(min_length=1, max_length=4)
    source: str = "ched_cmo"
    created_at: datetime
    embedding: Optional[List[float]] = None
