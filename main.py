import os
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from backend.config import UPLOAD_DIR, HOST, PORT
from backend.models import (
    QueryRequest,
    QueryResponse,
    SummaryRequest,
    SummaryResponse,
    DocumentInfo,
    LibraryInfo,
    DocumentMeta,
    UploadResponse,
    SourceCitation
)
from backend.services.pdf_processor import extract_document_content
from backend.services.rag_engine import rag_engine

# Initialize FastAPI app
app = FastAPI(
    title="OmniDoc AI | Enterprise Multi-Document Intelligence API",
    description="High-performance Multi-PDF RAG and Document Intelligence engine powered by Google Gemini with regional language localization and infinite querying.",
    version="2.5.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def preload_existing_documents():
    """Automatically load existing documents from the upload directory on startup."""
    try:
        if UPLOAD_DIR.exists():
            for p in UPLOAD_DIR.iterdir():
                if p.is_file() and p.suffix.lower() in [".pdf", ".txt", ".md"]:
                    try:
                        doc_data = extract_document_content(str(p), filename=p.name)
                        rag_engine.add_document(doc_data)
                        print(f"[*] Preloaded document: {p.name} ({doc_data['total_pages']} pages)")
                    except Exception as e:
                        print(f"[!] Warning: Failed to preload {p.name}: {e}")
    except Exception as e:
        print(f"[!] Startup preload error: {e}")

@app.get("/", tags=["Health"])
def health_check():
    info = rag_engine.get_documents_info()
    return {
        "status": "healthy",
        "service": "OmniDoc AI",
        "active_model": rag_engine.active_model_name,
        "total_documents": info["total_documents"],
        "total_pages": info["total_pages"],
        "total_words": info["total_words"],
        "documents": [d["filename"] for d in info["documents"]],
        "docs_url": "/docs"
    }

@app.post("/api/v1/upload", response_model=UploadResponse, tags=["Document"])
@app.post("/api/upload", response_model=UploadResponse, tags=["Document"])
async def upload_document(
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None)
):
    """
    Upload and parse single or multiple PDF / text documents.
    Adds them to the multi-document index without deleting existing ones.
    """
    to_process: List[UploadFile] = []
    if files:
        to_process.extend(files)
    if file and file.filename:
        to_process.append(file)

    if not to_process:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    processed_names = []
    try:
        for f in to_process:
            if not f.filename:
                continue
            save_path = os.path.join(str(UPLOAD_DIR), f.filename)
            file_bytes = await f.read()

            with open(save_path, "wb") as out_file:
                out_file.write(file_bytes)

            # Parse document and extract pages + semantic chunks
            doc_data = extract_document_content(save_path, filename=f.filename)
            rag_engine.add_document(doc_data)
            processed_names.append(f.filename)

        info = rag_engine.get_documents_info()
        return UploadResponse(
            status="success",
            filename=processed_names[0] if processed_names else "none",
            uploaded_files=processed_names,
            total_documents=info["total_documents"],
            total_pages=info["total_pages"],
            word_count=info["total_words"],
            message=f"Successfully indexed {len(processed_names)} document(s). Library now contains {info['total_documents']} documents ({info['total_pages']} pages)."
        )
    except Exception as e:
        print(f"[Upload Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process documents: {str(e)}")

@app.get("/api/v1/documents", response_model=LibraryInfo, tags=["Document"])
def list_documents():
    """Returns metadata for all currently indexed documents."""
    info = rag_engine.get_documents_info()
    return LibraryInfo(
        documents=[DocumentMeta(**d) for d in info["documents"]],
        total_documents=info["total_documents"],
        total_pages=info["total_pages"],
        total_words=info["total_words"],
        is_loaded=info["is_loaded"],
        status="ready"
    )

@app.delete("/api/v1/documents/{filename}", tags=["Document"])
def delete_document(filename: str):
    """Removes a specific document from the index."""
    removed = rag_engine.remove_document(filename)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Document '{filename}' not found.")
    
    # Optionally remove local file from uploaded_pdfs
    file_path = UPLOAD_DIR / filename
    if file_path.exists():
        try:
            file_path.unlink()
        except Exception:
            pass

    info = rag_engine.get_documents_info()
    return {
        "status": "success",
        "message": f"Document '{filename}' removed successfully.",
        "remaining_documents": info["total_documents"]
    }

@app.post("/api/v1/stream-query", tags=["Query"])
async def stream_query(request: QueryRequest):
    """
    Streams generated answers in real time as plain text chunks.
    Compatible with multi-document retrieval and custom user API keys.
    """
    info = rag_engine.get_documents_info()
    if not info["is_loaded"]:
        return StreamingResponse(
            iter(["⚠️ Please upload one or more PDF documents before asking questions."]),
            media_type="text/plain"
        )

    return StreamingResponse(
        rag_engine.stream_answer(
            question=request.question,
            target_language=request.target_language,
            doc_filter=request.doc_filter or "all",
            api_key=request.api_key
        ),
        media_type="text/plain"
    )

@app.post("/api/v1/query", tags=["Query"])
@app.post("/api/query", tags=["Query"])
@app.post("/chat", tags=["Query"])
async def query_document(request: QueryRequest, raw_req: Request):
    """
    Query the document repository. Supports both Server-Sent Events (SSE) and structured JSON with citations.
    """
    info = rag_engine.get_documents_info()
    if not info["is_loaded"]:
        raise HTTPException(status_code=400, detail="No documents loaded. Please upload at least one PDF first.")

    accept_header = raw_req.headers.get("accept", "")
    if "text/event-stream" in accept_header:
        return StreamingResponse(
            rag_engine.stream_sse_answer(
                question=request.question,
                target_language=request.target_language,
                doc_filter=request.doc_filter or "all",
                api_key=request.api_key
            ),
            media_type="text/event-stream"
        )

    try:
        answer, model_used, citations = rag_engine.generate_answer(
            question=request.question,
            target_language=request.target_language,
            doc_filter=request.doc_filter or "all",
            api_key=request.api_key
        )
        return QueryResponse(
            answer=answer,
            sources=[SourceCitation(**c) for c in citations],
            model_used=model_used,
            status="success"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/summarize", response_model=SummaryResponse, tags=["Analysis"])
@app.post("/api/summarize", response_model=SummaryResponse, tags=["Analysis"])
async def summarize_document(request: Optional[SummaryRequest] = None):
    """
    Generates a structured Executive Summary across all loaded documents or a specific document.
    """
    info = rag_engine.get_documents_info()
    if not info["is_loaded"]:
        raise HTTPException(status_code=400, detail="Please upload at least one document to generate a summary.")

    req = request or SummaryRequest()
    try:
        summary_text, model_used, total_pages = rag_engine.generate_summary(
            target_language=req.target_language,
            summary_type=req.summary_type,
            doc_filter=req.doc_filter or "all",
            api_key=req.api_key
        )
        return SummaryResponse(
            summary=summary_text,
            target_doc=req.doc_filter or "all",
            total_pages=total_pages,
            model_used=model_used,
            status="success"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")

@app.get("/api/v1/document", response_model=DocumentInfo, tags=["Document"])
def get_current_document():
    """Backward compatibility endpoint for single document metadata."""
    doc = rag_engine.get_document()
    if not doc:
        return DocumentInfo(
            filename="None",
            total_pages=0,
            total_chars=0,
            word_count=0,
            is_loaded=False,
            status="no_document"
        )
    return DocumentInfo(
        filename=doc["filename"],
        total_pages=doc["total_pages"],
        total_chars=doc["total_chars"],
        word_count=doc["word_count"],
        is_loaded=True,
        status="ready"
    )

@app.post("/api/v1/reset", tags=["Document"])
def reset_document():
    """Clears all loaded documents and index from memory."""
    rag_engine.reset_documents()
    return {"status": "success", "message": "All documents cleared from memory"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
