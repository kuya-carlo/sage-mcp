from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class CMORecord(BaseModel):
    id: UUID
    program_code: str
    cmo_reference: Optional[str] = None
    academic_year: Optional[str] = None
    classification: Optional[str] = None # core_gened, shared_major, program_specific, elective
    year_level: Optional[int] = Field(None, ge=1, le=5)
    semester: Optional[int] = Field(None, ge=1, le=4)
    course_code: str
    course_title: str
    competency_tags: List[str] = Field(min_length=1, max_length=4)
    source: str = "ched_cmo"
    created_at: datetime
    embedding: Optional[List[float]] = None

class CMORecordCreate(BaseModel):
    program_code: str
    cmo_reference: Optional[str] = None
    academic_year: Optional[str] = None
    classification: Optional[str] = None 
    year_level: Optional[int] = Field(None, ge=1, le=5)
    semester: Optional[int] = Field(None, ge=1, le=4)
    course_code: str
    course_title: str
    competency_tags: List[str] = Field(min_length=1, max_length=4)
    source: str = "ched_cmo"
    embedding: None = None

class FailedExtraction(BaseModel):
    program_code: str
    raw_data: str
    error_message: str
    created_at: Optional[datetime] = None