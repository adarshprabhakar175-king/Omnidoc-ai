from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class QueryRequest(BaseModel):
    question: str = Field(..., description="The user query or question about the documents")
    target_language: Optional[str] = Field("English", description="Target response language (e.g., English, Hindi, Tamil)")
    session_id: Optional[str] = Field("default", description="Optional conversation or session identifier")
    doc_filter: Optional[str] = Field("all", description="Document filter: 'all' for entire library or a specific filename")
    api_key: Optional[str] = Field(None, description="Optional custom Gemini API key provided by user for unlimited requests")

class SourceCitation(BaseModel):
    doc_name: str = Field(..., description="Source document filename")
    page: int = Field(..., description="Document page number (1-indexed)")
    snippet: str = Field(..., description="Relevant passage snippet from the page")

class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceCitation] = []
    model_used: Optional[str] = None
    status: str = "success"

class SummaryRequest(BaseModel):
    target_language: Optional[str] = Field("English", description="Target language for the summary")
    summary_type: Optional[str] = Field("executive", description="Type of summary (executive, bullet_points, comprehensive)")
    doc_filter: Optional[str] = Field("all", description="Filter summary to 'all' documents or a specific filename")
    api_key: Optional[str] = Field(None, description="Optional custom Gemini API key")

class SummaryResponse(BaseModel):
    summary: str
    target_doc: Optional[str] = "all"
    total_pages: Optional[int] = 0
    model_used: Optional[str] = None
    status: str = "success"

class DocumentMeta(BaseModel):
    filename: str
    total_pages: int
    total_chars: int
    word_count: int
    chunks_count: int

class LibraryInfo(BaseModel):
    documents: List[DocumentMeta] = []
    total_documents: int = 0
    total_pages: int = 0
    total_words: int = 0
    is_loaded: bool = False
    status: str = "ready"

class DocumentInfo(BaseModel):
    filename: str
    total_pages: int
    total_chars: int
    word_count: int
    is_loaded: bool
    status: str = "ready"

class UploadResponse(BaseModel):
    status: str = "success"
    filename: Optional[str] = None
    uploaded_files: List[str] = []
    total_documents: int = 0
    total_pages: int = 0
    word_count: int = 0
    message: str = ""
