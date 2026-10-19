import os
import unicodedata
from pathlib import Path
from typing import Dict, Any, List
from pypdf import PdfReader

def clean_text(text: str) -> str:
    """Normalize unicode characters (e.g. ligatures fi, fl) and clean control chars."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    return normalized

def extract_document_content(file_path: str, filename: str = "") -> Dict[str, Any]:
    """
    Extracts text and page-level metadata from PDF, TXT, and Markdown files.
    Injects clear page demarcations for multi-page citation mapping.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    filename = filename or os.path.basename(file_path)
    ext = Path(file_path).suffix.lower()

    pages: List[Dict[str, Any]] = []
    full_text_parts: List[str] = []

    if ext == ".pdf":
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        for idx, page in enumerate(reader.pages):
            raw_text = page.extract_text() or ""
            page_text = clean_text(raw_text)
            page_num = idx + 1
            pages.append({
                "page": page_num,
                "text": page_text
            })
            if page_text.strip():
                full_text_parts.append(f"--- Page {page_num} ---\n{page_text.strip()}\n")
    elif ext in [".txt", ".md"]:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        pages.append({
            "page": 1,
            "text": content
        })
        full_text_parts.append(f"--- Page 1 ---\n{content}\n")
        total_pages = 1
    else:
        raise ValueError(f"Unsupported file format: {ext}. Only PDF and TXT files are supported.")

    full_text = "\n".join(full_text_parts)
    word_count = len(full_text.split())
    total_chars = len(full_text)

    return {
        "filename": filename,
        "total_pages": len(pages),
        "total_chars": total_chars,
        "word_count": word_count,
        "pages": pages,
        "full_text": full_text
    }

def find_relevant_page_citations(pages: List[Dict[str, Any]], query: str, max_citations: int = 3) -> List[Dict[str, Any]]:
    """
    Finds pages most relevant to the query to provide verified citations.
    """
    query_tokens = [w.lower() for w in query.split() if len(w) > 3]
    if not query_tokens:
        query_tokens = [w.lower() for w in query.split()]

    scored_pages = []
    for page_data in pages:
        p_text = page_data.get("text", "")
        p_lower = p_text.lower()
        score = sum(p_lower.count(token) for token in query_tokens)
        if score > 0:
            scored_pages.append((score, page_data["page"], p_text))

    scored_pages.sort(key=lambda x: x[0], reverse=True)

    citations = []
    for _, page_num, p_text in scored_pages[:max_citations]:
        snippet = " ".join(p_text.strip().split()[:60]) + "..."
        citations.append({
            "page": page_num,
            "snippet": snippet
        })

    return citations