from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CMORecord(BaseModel):
    id: UUID
    program_code: str
    cmo_reference: str | None = None
    academic_year: str | None = None
    classification: str | None = None  # core_gened, shared_major, program_specific, elective
    year_level: int | None = Field(None, ge=1, le=5)
    semester: int | None = Field(None, ge=1, le=4)
    course_code: str
    course_title: str
    competency_tags: list[str] = Field(min_length=1, max_length=4)
    source: str = "ched_cmo"
    created_at: datetime
    embedding: list[float] | None = None


class CMORecordCreate(BaseModel):
    program_code: str
    cmo_reference: str | None = None
    academic_year: str | None = None
    classification: str | None = None
    year_level: int | None = Field(None, ge=1, le=5)
    semester: int | None = Field(None, ge=1, le=4)
    course_code: str
    course_title: str
    competency_tags: list[str] = Field(min_length=1, max_length=4)
    source: str = "ched_cmo"
    embedding: None = None


class FailedExtraction(BaseModel):
    program_code: str
    raw_data: str
    error_message: str
    created_at: datetime | None = None
