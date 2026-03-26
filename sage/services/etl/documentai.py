# sage/services/etl/documentai.py
# Used ONLY for user-uploaded syllabus PDFs (v1.4 roadmap)
# CMO seeding uses gaffa.py instead

import base64
import json

from google.cloud import documentai
from google.oauth2 import service_account

from sage.config import settings


def _load_credentials() -> service_account.Credentials | None:
    if not settings.google_credentials_base64:
        print("[documentai] GOOGLE_CREDENTIALS_BASE64 is missing.")
        return None

    credentials_json = base64.b64decode(settings.google_credentials_base64).decode("utf-8")
    credentials_dict = json.loads(credentials_json)
    return service_account.Credentials.from_service_account_info(
        credentials_dict, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )


# Instantiated once at module load — not per call
_credentials = _load_credentials()


async def process_pdf_bytes(pdf_bytes: bytes) -> list[str]:
    """
    Accepts raw PDF bytes (from user upload).
    Returns list of page text strings.
    Used by: routers/admin.py user syllabus upload endpoint (v1.4)
    """
    if not _credentials:
        raise ValueError("Google Cloud credentials are not configured. Cannot use Document AI.")

    client = documentai.DocumentProcessorServiceAsyncClient(credentials=_credentials)

    processor_name = (
        f"projects/{settings.google_cloud_project}"
        f"/locations/{settings.google_cloud_location}"
        f"/processors/{settings.document_ai_processor_id}"
    )

    raw_document = documentai.RawDocument(content=pdf_bytes, mime_type="application/pdf")

    request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)

    result = await client.process_document(request=request)
    document = result.document

    pages = []
    full_text = document.text
    for page in document.pages:
        segments = page.layout.text_anchor.text_segments
        page_text = "".join(
            full_text[int(seg.start_index) : int(seg.end_index)] for seg in segments
        )
        pages.append(page_text)

    return pages
