import fitz

def extract_text(file_path:str) -> tuple[str,int]:
    doc = fitz.open(file_path)
    try:
        pages=[page.get_text() for page in doc]
        return "\n\n".join(pages),doc.page_count
    finally:
        doc.close()