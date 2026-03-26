## sage/services/etl/gaffa.py

import httpx

from sage.config import settings

KNOWN_PH_UNIVERSITIES = [
    "university of the philippines", "up diliman",
    "mapua", "de la salle", "dlsu", "ateneo",
    "ust", "university of santo tomas",
    "feu", "far eastern university",
    "pup", "polytechnic university",
    "adamson", "letran", "benilde",
    "batangas state", "bulacan state", "bulsu",
    "technological university", "tup",
    "pamantasan ng lungsod", "plm",
    "mindanao state", "xavier university",
    "lyceum", "arellano", "national university",
    "perpetual help", "san beda",
    "southern luzon", "cavite state",
]

GAFFA_BASE_URL = "https://api.gaffa.dev/v1/browser/requests"


def _filter_university_result(results: list[dict]) -> str | None:
    # We skip official CHED CHOs as per user request to use university-specific curriculums
    for result in results:
        url = result.get("url", "").lower()
        if "ched.gov.ph" in url:
            continue
            
        text = ((result.get("title") or "") + " " + (result.get("snippet") or "")).lower()
        
        # Look for university-specific PDF links
        if any(uni in text for uni in KNOWN_PH_UNIVERSITIES):
            if ".pdf" in url:
                return result.get("url")

    # Secondary check for edu.ph domains
    for result in results:
        url = result.get("url", "").lower()
        if "ched.gov.ph" in url:
            continue
        if ".edu.ph" in url and ".pdf" in url:
            return result.get("url")

    return None


async def extract_cmo_from_pdf(pdf_url: str,
                                program_code: str) -> list[dict]:
    program_code = program_code.upper() # Ensure all-caps
    payload = {
        "url": pdf_url,
        "proxy_location": "us",
        "async": False,
        "max_cache_age": 604800,
        "settings": {
            "record_request": False,
            "actions": [
                {
                    "type": "download_file",
                    "timeout": 30000
                },
                {
                    "type": "parse_json",
                    "data_schema": {
                        "name": "CHEDCurriculum",
                        "description": "Extract curriculum data from CHED CMO PDF document",
                        "fields": [
                            {
                                "type": "string",
                                "name": "cmo_reference",
                                "description": "CMO reference e.g. CMO 24 s. 2008"
                            },
                            {
                                "type": "string",
                                "name": "program_name",
                                "description": "Full name of the degree program"
                            },
                            {
                                "type": "array",
                                "name": "courses",
                                "description": "All courses listed in the curriculum",
                                "fields": [
                                    {
                                        "type": "string",
                                        "name": "course_code",
                                        "description": "Course code e.g. ENGG101"
                                    },
                                    {
                                        "type": "string",
                                        "name": "course_title",
                                        "description": "Full course title"
                                    },
                                    {
                                        "type": "integer",
                                        "name": "year_level",
                                        "description": "Year level 1 to 4"
                                    },
                                    {
                                        "type": "integer",
                                        "name": "semester",
                                        "description": "Semester 1 or 2"
                                    },
                                    {
                                        "type": "string",
                                        "name": "classification",
                                        "description": "One of: core_gened, shared_major, program_specific, elective"
                                    },
                                    {
                                        "type": "array",
                                        "name": "competency_tags",
                                        "description": "2 to 4 short skill descriptors",
                                        "fields": [
                                            {
                                                "type": "string",
                                                "name": "tag",
                                                "description": "Single lowercase skill tag"
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    "instruction": (
                        "This is a Philippine CHED CMO curriculum document. "
                        "Extract every course in the curriculum table. "
                        "Identify the course classification: core_gened (minor subjects), "
                        "shared_major (ITE core), program_specific (majors), or elective. "
                        "Year level and semester must be integers. "
                        "competency_tags must be lowercase 1-3 word descriptors. "
                        "If year_level or semester cannot be determined, infer from context."
                    ),
                    "model": "gpt-4o-mini",
                    "output_type": "inline",
                    "max_pages": 50
                }
            ]
        }
    }

    headers = {
        "X-API-Key": settings.gaffa_api_key,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            GAFFA_BASE_URL,
            json=payload,
            headers=headers,
            timeout=300.0
        )
        response.raise_for_status()
        data = response.json()

    credit_usage = data["data"].get("credit_usage", 0)
    print(f"[gaffa] PDF extraction complete — credits used: {credit_usage}")

    parse_action = next(
        (a for a in data["data"]["actions"]
         if a["type"] == "parse_json"),
        None
    )
    if not parse_action or not parse_action.get("output"):
        print(f"[gaffa] No parse_json output for {pdf_url}")
        return []

    output = parse_action["output"]
    courses = output.get("courses", [])
    cmo_reference = output.get("cmo_reference", "unknown")

    records = []
    for course in courses:
        tags = [
            t["tag"] for t in course.get("competency_tags", [])
            if isinstance(t, dict) and t.get("tag")
        ]
        records.append({
            "program_code": program_code,
            "cmo_reference": cmo_reference,
            "classification": course.get("classification"),
            "year_level": course.get("year_level"),
            "semester": course.get("semester"),
            "course_code": course.get("course_code"),
            "course_title": course.get("course_title"),
            "competency_tags": tags[:4],
            "academic_year": None, # Will be filled by search context if needed
            "source": "ched_cmo",
            "embedding": None
        })

    return records


async def search_and_extract_cmo(program_name: str,
                                  program_code: str) -> list[dict]:
    program_code = program_code.upper()
    payload = {
        "url": (
            f"https://www.google.com/search"
            f"?q={program_name.replace(' ', '+')}+prospectus+curriculum+PH+PDF"
        ),
        "proxy_location": "us",
        "async": False,
        "max_cache_age": 86400,
        "settings": {
            "record_request": False,
            "max_media_bandwidth": 0,
            "actions": [
                {
                    "type": "wait",
                    "selector": "body",
                    "timeout": 5000,
                    "continue_on_fail": True
                },
                {
                    "type": "parse_json",
                    "data_schema": {
                        "name": "SearchResults",
                        "description": "Extract PDF links from Google search results",
                        "fields": [
                            {
                                "type": "array",
                                "name": "results",
                                "description": "Search result links",
                                "fields": [
                                    {
                                        "type": "string",
                                        "name": "url",
                                        "description": "Direct URL to PDF file"
                                    },
                                    {
                                        "type": "string",
                                        "name": "title",
                                        "description": "Title of the result"
                                    },
                                    {
                                        "type": "string",
                                        "name": "snippet",
                                        "description": "Description snippet"
                                    }
                                ]
                            }
                        ]
                    },
                    "instruction": (
                        "Extract only results that are direct links to PDF files. "
                        "Include the full URL, title, and snippet for each result."
                    ),
                    "model": "gpt-4o-mini",
                    "output_type": "inline"
                }
            ]
        }
    }

    headers = {
        "X-API-Key": settings.gaffa_api_key,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            GAFFA_BASE_URL,
            json=payload,
            headers=headers,
            timeout=60.0
        )
        response.raise_for_status()
        data = response.json()

    parse_action = next(
        (a for a in data["data"]["actions"]
         if a["type"] == "parse_json"),
        None
    )
    if not parse_action or not parse_action.get("output"):
        print(f"[gaffa] No search results for {program_name}")
        return []

    results = parse_action["output"].get("results", [])
    print(f"[gaffa] Discovered {len(results)} search results.")
    for r in results:
        print(f"  - {r.get('url')}")
    pdf_url = _filter_university_result(results)

    if not pdf_url:
        print(f"[gaffa] No university PDF found for {program_name}")
        return []

    print(f"[gaffa] Found PDF: {pdf_url}")
    return await extract_cmo_from_pdf(pdf_url, program_code)

