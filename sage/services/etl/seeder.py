# sage/services/etl/seeder.py

from sage.database import get_db
from sage.models.cmo import CMORecordCreate, FailedExtraction
from sage.services.etl.gaffa import search_and_extract_cmo
from pydantic import ValidationError


PROGRAM_NAME_MAP = {
    "BSCPE": "BS Computer Engineering",
    "BSCS":  "BS Computer Science",
    "BSIT":  "BS Information Technology",
    "BSECE": "BS Electronics Engineering",
    "BSIE":  "BS Industrial Engineering",
}

UPSERT_SQL = """
    INSERT INTO cmo_records (
        program_code, cmo_reference, year_level,
        semester, course_code, course_title,
        competency_tags, source
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8
    )
    ON CONFLICT (program_code, cmo_reference, course_code)
    DO UPDATE SET
        course_title     = EXCLUDED.course_title,
        competency_tags  = EXCLUDED.competency_tags;
"""

FAILED_SQL = """
    INSERT INTO failed_extractions (program_code, raw_data, error_message)
    VALUES ($1, $2, $3);
"""


async def upsert_records(records: list[dict],
                         program_code: str) -> tuple[int, int]:
    inserted, failed = 0, 0
    async with get_db() as conn:
        for record in records:
            try:
                validated = CMORecordCreate(**record)
                await conn.execute(
                    UPSERT_SQL,
                    validated.program_code,
                    validated.cmo_reference,
                    validated.year_level,
                    validated.semester,
                    validated.course_code,
                    validated.course_title,
                    validated.competency_tags,
                    validated.source,
                )
                inserted += 1
            except (ValidationError, Exception) as e:
                await conn.execute(
                    FAILED_SQL,
                    program_code,
                    str(record),
                    str(e)
                )
                failed += 1

    return inserted, failed


async def seed_program(program_code: str) -> dict:
    program_name = PROGRAM_NAME_MAP.get(program_code)
    if not program_name:
        return {
            "status": "unknown_program",
            "program": program_code
        }

    try:
        raw_records = await search_and_extract_cmo(
            program_name, program_code
        )

        if not raw_records:
            return {
                "status": "no_source_found",
                "program": program_code
            }

        inserted, failed = await upsert_records(
            raw_records, program_code
        )

        return {
            "status": "done",
            "program": program_code,
            "inserted": inserted,
            "failed": failed
        }

    except Exception as e:
        print(f"[seeder] Error seeding {program_code}: {e}")
        return {
            "status": "error",
            "program": program_code,
            "message": str(e)
        }
