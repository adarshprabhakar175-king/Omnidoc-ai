import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, Any, List
from pypdf import PdfReader

def clean_text(text: str) -> str:
    """Normalize unicode characters and clean whitespace/control chars."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    # Replace non-breaking spaces and excessive whitespace
    normalized = re.sub(r'[ \t]+', ' ', normalized)
    normalized = re.sub(r'\n{3,}', '\n\n', normalized)
    return normalized.strip()

def chunk_page_text(page_text: str, doc_name: str, page_num: int, chunk_size: int = 1000, overlap: int = 150) -> List[Dict[str, Any]]:
    """
    Splits page text into sliding-window chunks with page & doc metadata.
    Preserves paragraph and sentence boundaries wherever possible.
    """
    if not page_text:
        return []

    chunks = []
    start = 0
    text_len = len(page_text)
    chunk_idx = 1

    while start < text_len:
        end = start + chunk_size
        if end >= text_len:
            chunk_slice = page_text[start:text_len].strip()
            if chunk_slice:
                chunks.append({
                    "chunk_id": f"{doc_name}_p{page_num}_c{chunk_idx}",
                    "doc_name": doc_name,
                    "page": page_num,
                    "text": chunk_slice,
                    "clean_lower": chunk_slice.lower()
                })
            break

        # Try to break at a newline or period near the end
        boundary = page_text.rfind('\n', start + overlap, end)
        if boundary == -1:
            boundary = page_text.rfind('. ', start + overlap, end)
        if boundary != -1 and boundary > start:
            end = boundary + 1

        chunk_slice = page_text[start:end].strip()
        if chunk_slice:
            chunks.append({
                "chunk_id": f"{doc_name}_p{page_num}_c{chunk_idx}",
                "doc_name": doc_name,
                "page": page_num,
                "text": chunk_slice,
                "clean_lower": chunk_slice.lower()
            })
            chunk_idx += 1

        start = end - overlap
        if start < 0:
            start = 0

    return chunks

def extract_document_content(file_path: str, filename: str = "") -> Dict[str, Any]:
    """
    Extracts text, page-level metadata, and semantic chunks from PDF, TXT, and Markdown files.
    Injects clear page demarcations for multi-page citation mapping.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    filename = filename or os.path.basename(file_path)
    ext = Path(file_path).suffix.lower()

    pages: List[Dict[str, Any]] = []
    all_chunks: List[Dict[str, Any]] = []
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
            if page_text:
                full_text_parts.append(f"--- [{filename}] Page {page_num} ---\n{page_text}\n")
                chunks = chunk_page_text(page_text, filename, page_num)
                all_chunks.extend(chunks)
    elif ext in [".txt", ".md"]:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = clean_text(f.read())
        pages.append({
            "page": 1,
            "text": content
        })
        full_text_parts.append(f"--- [{filename}] Page 1 ---\n{content}\n")
        chunks = chunk_page_text(content, filename, 1)
        all_chunks.extend(chunks)
        total_pages = 1
    else:
        raise ValueError(f"Unsupported file format: {ext}. Only PDF, TXT, and Markdown files are supported.")

    full_text = "\n".join(full_text_parts)
    word_count = len(full_text.split())
    total_chars = len(full_text)

    return {
        "filename": filename,
        "total_pages": len(pages),
        "total_chars": total_chars,
        "word_count": word_count,
        "pages": pages,
        "chunks": all_chunks,
        "full_text": full_text
    }

def find_relevant_citations(chunks: List[Dict[str, Any]], query: str, max_citations: int = 4) -> List[Dict[str, Any]]:
    """
    Finds chunks most relevant to the query to provide verified citations with document and page numbers.
    """
    if not chunks:
        return []

    tokens = [w.lower() for w in re.findall(r'\b\w{3,}\b', query)]
    if not tokens:
        tokens = [w.lower() for w in query.split()]

    scored = []
    for chunk in chunks:
        c_text = chunk.get("clean_lower", "")
        # Score based on frequency and keyword occurrence
        score = sum(c_text.count(t) for t in tokens)
        # Bonus for exact query phrase match
        if query.lower() in c_text:
            score += 10
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)

    citations = []
    seen = set()
    for _, ch in scored:
        key = (ch["doc_name"], ch["page"])
        if key in seen:
            continue
        seen.add(key)
        snippet = " ".join(ch["text"].split()[:50]) + "..."
        citations.append({
            "doc_name": ch["doc_name"],
            "page": ch["page"],
            "snippet": snippet
        })
        if len(citations) >= max_citations:
            break

    return citations
