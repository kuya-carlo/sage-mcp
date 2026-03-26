# sage/services/etl/local_parser.py
# In-house PDF processing using PyMuPDF (fitz) + Tesseract OCR
# This is Option C: Zero cloud costs, but requires more CPU juice.

import io

import fitz  # PyMuPDF
import pytesseract
from PIL import Image


async def process_pdf_locally(pdf_bytes: bytes) -> list[str]:
    """
    Accepts raw PDF bytes (from user upload).
    Returns list of page text strings using local PyMuPDF extraction.
    Falls back to Tesseract OCR if the page contains no digital text layer.
    """
    pages = []
    
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # 1. Try digital text extraction first (fastest)
            text = page.get_text("text").strip()
            
            if not text:
                # 2. Page is likely an image. Perform OCR.
                # Generate high-res image for OCR (300 DPI for better detection)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                
                # Perform OCR using Tesseract
                ocr_text = pytesseract.image_to_string(img, lang="eng")
                pages.append(ocr_text)
                
                print(f"[local_parser] OCR'd page {page_num + 1}/{len(doc)}")
            else:
                # Digital text exists. Use block-level extraction for better structure.
                blocks = page.get_text("blocks")
                sorted_blocks = sorted(blocks, key=lambda b: (b[1], b[0]))
                
                page_text = ""
                for b in sorted_blocks:
                    page_text += b[4] + "\n"
                pages.append(page_text)
                
    return pages
