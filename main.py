import os
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from backend.config import UPLOAD_DIR, GOOGLE_API_KEY, DEFAULT_MODEL
from backend.models import (
    QueryRequest,
    QueryResponse,
    SummaryRequest,
    SummaryResponse,
    DocumentInfo,
    UploadResponse,
    SourceCitation
)
from backend.services.pdf_processor import extract_document_content
from backend.services.rag_engine import rag_engine

# Initialize FastAPI app
app = FastAPI(
    title="IndicDoc-AI | Enterprise Document Intelligence API",
    description="High-performance RAG and document intelligence engine powered by Google Gemini with regional language localization.",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["Health"])
def health_check():
    doc = rag_engine.get_document()
    return {
        "status": "healthy",
        "service": "IndicDoc-AI",
        "active_model": rag_engine.active_model_name,
        "document_loaded": bool(doc),
        "loaded_filename": doc["filename"] if doc else None,
        "docs_url": "/docs"
    }

@app.post("/api/v1/upload", response_model=UploadResponse, tags=["Document"])
@app.post("/api/upload", response_model=UploadResponse, tags=["Document"])
async def upload_document(file: UploadFile = File(...)):
    """
    Upload and parse PDF or text document. Injects page markers and caches text for RAG.
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        save_path = os.path.join(str(UPLOAD_DIR), file.filename)
        file_bytes = await file.read()

        with open(save_path, "wb") as f:
            f.write(file_bytes)

        # Parse document and extract pages
        doc_data = extract_document_content(save_path, filename=file.filename)
        rag_engine.set_document(doc_data)

        return UploadResponse(
            status="success",
            filename=file.filename,
            total_pages=doc_data["total_pages"],
            word_count=doc_data["word_count"],
            message=f"Document '{file.filename}' processed successfully with {doc_data['total_pages']} pages."
        )
    except Exception as e:
        print(f"[Upload Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")

@app.post("/api/v1/stream-query", tags=["Query"])
async def stream_query(request: QueryRequest):
    """
    Streams generated answers in real time as plain text chunks.
    Directly compatible with frontend streaming consumption.
    """
    doc = rag_engine.get_document()
    if not doc:
        return StreamingResponse(
            iter(["⚠️ Please upload a PDF document before asking questions."]),
            media_type="text/plain"
        )

    return StreamingResponse(
        rag_engine.stream_answer(request.question, request.target_language),
        media_type="text/plain"
    )

@app.post("/api/v1/query", tags=["Query"])
@app.post("/api/query", tags=["Query"])
@app.post("/chat", tags=["Query"])
async def query_document(request: QueryRequest, raw_req: Request):
    """
    Query the document. Supports both Server-Sent Events (SSE) and structured JSON with citations.
    """
    doc = rag_engine.get_document()
    if not doc:
        raise HTTPException(status_code=400, detail="No document loaded. Please upload a document first.")

    # Check if SSE stream was explicitly requested via header or parameter
    accept_header = raw_req.headers.get("accept", "")
    if "text/event-stream" in accept_header:
        return StreamingResponse(
            rag_engine.stream_sse_answer(request.question, request.target_language),
            media_type="text/event-stream"
        )

    try:
        answer, model_used, citations = rag_engine.generate_answer(
            request.question,
            request.target_language
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
async def summarize_document(request: SummaryRequest = None):
    """
    Generates a structured Executive Summary of the uploaded document.
    """
    doc = rag_engine.get_document()
    if not doc:
        raise HTTPException(status_code=400, detail="Please upload a document to generate a summary.")

    req = request or SummaryRequest()
    try:
        summary_text, model_used = rag_engine.generate_summary(
            target_language=req.target_language,
            summary_type=req.summary_type
        )
        return SummaryResponse(
            summary=summary_text,
            filename=doc.get("filename"),
            total_pages=doc.get("total_pages"),
            model_used=model_used,
            status="success"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")

@app.get("/api/v1/document", response_model=DocumentInfo, tags=["Document"])
def get_current_document():
    """
    Returns metadata for the currently active document.
    """
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
    """
    Clears the loaded document from memory.
    """
    rag_engine.reset_document()
    return {"status": "success", "message": "Document cleared from memory"}

if __name__ == "__main__":
    import uvicorn
    from backend.config import HOST, PORT
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)