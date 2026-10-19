from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class QueryRequest(BaseModel):
    question: str = Field(..., description="The user query or question about the document")
    target_language: Optional[str] = Field("English", description="Target response language (e.g., English, Hindi, Tamil)")
    session_id: Optional[str] = Field("default", description="Optional conversation or session identifier")

class SourceCitation(BaseModel):
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

class SummaryResponse(BaseModel):
    summary: str
    filename: Optional[str] = None
    total_pages: Optional[int] = None
    model_used: Optional[str] = None
    status: str = "success"

class DocumentInfo(BaseModel):
    filename: str
    total_pages: int
    total_chars: int
    word_count: int
    is_loaded: bool
    status: str = "ready"

class UploadResponse(BaseModel):
    status: str = "success"
    filename: str
    total_pages: int
    word_count: int
    message: str