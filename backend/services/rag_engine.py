import os
import json
import time
import re
from typing import Generator, Dict, Any, Optional, Tuple, List
from collections import OrderedDict
from google import genai
from google.genai.errors import ServerError, ClientError

from backend.config import GOOGLE_API_KEY, GOOGLE_API_KEYS, MODEL_CANDIDATES, DEFAULT_MODEL
from backend.services.pdf_processor import find_relevant_citations

class MultiDocumentRAGEngine:
    def __init__(self):
        # Key pool for automatic key rotation on quota exhaustion
        self.api_keys = list(GOOGLE_API_KEYS) if GOOGLE_API_KEYS else ([GOOGLE_API_KEY] if GOOGLE_API_KEY else [])
        self.active_key_idx = 0
        self.active_model_name = DEFAULT_MODEL
        
        # Document Registry: { filename: doc_data }
        self.documents: Dict[str, Dict[str, Any]] = {}
        # Global chunk index across all documents
        self.all_chunks: List[Dict[str, Any]] = []
        
        # In-memory LRU Response Cache (prevents consuming API quota for repeated/similar queries)
        self.cache: OrderedDict[str, str] = OrderedDict()
        self.cache_max_size = 500
        
        # Persistent client cache: { api_key: Client }
        self._clients: Dict[str, genai.Client] = {}

    def get_client(self, custom_key: Optional[str] = None) -> genai.Client:
        """Returns a persistent configured Google GenAI client with key rotation support."""
        if custom_key and custom_key.strip():
            key = custom_key.strip()
        elif self.api_keys:
            key = self.api_keys[self.active_key_idx % len(self.api_keys)]
        else:
            raise ValueError("No Gemini API key configured. Please set GOOGLE_API_KEY in .env or provide one in UI.")
        
        if key not in self._clients:
            self._clients[key] = genai.Client(api_key=key)
        return self._clients[key]

    def rotate_key(self):
        """Rotates to the next available API key in the pool."""
        if len(self.api_keys) > 1:
            self.active_key_idx = (self.active_key_idx + 1) % len(self.api_keys)
            print(f"[RAG Engine] Switched to API Key #{self.active_key_idx + 1}")

    def add_document(self, doc_data: Dict[str, Any]):
        """Adds or updates a document in the library and rebuilds the chunk index."""
        filename = doc_data["filename"]
        self.documents[filename] = doc_data
        self._rebuild_chunks_index()
        # Invalidate response cache when document library changes
        self.cache.clear()

    def remove_document(self, filename: str) -> bool:
        """Removes a document and its chunks from the registry."""
        if filename in self.documents:
            del self.documents[filename]
            self._rebuild_chunks_index()
            self.cache.clear()
            return True
        return False

    def reset_documents(self):
        """Clears all documents, chunks, and cache."""
        self.documents.clear()
        self.all_chunks.clear()
        self.cache.clear()

    # Legacy alias for backward compatibility
    def set_document(self, doc_data: Dict[str, Any]):
        self.add_document(doc_data)

    def reset_document(self):
        self.reset_documents()

    def get_document(self, filename: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Returns a specific document or the first active document."""
        if not self.documents:
            return None
        if filename and filename in self.documents:
            return self.documents[filename]
        return next(iter(self.documents.values()))

    def get_documents_info(self) -> Dict[str, Any]:
        """Returns high-level statistics across all uploaded documents."""
        docs_list = []
        total_pages = 0
        total_words = 0
        total_chars = 0

        for name, doc in self.documents.items():
            total_pages += doc.get("total_pages", 0)
            total_words += doc.get("word_count", 0)
            total_chars += doc.get("total_chars", 0)
            docs_list.append({
                "filename": name,
                "total_pages": doc.get("total_pages", 0),
                "total_chars": doc.get("total_chars", 0),
                "word_count": doc.get("word_count", 0),
                "chunks_count": len(doc.get("chunks", []))
            })

        return {
            "documents": docs_list,
            "total_documents": len(docs_list),
            "total_pages": total_pages,
            "total_words": total_words,
            "total_chars": total_chars,
            "is_loaded": len(docs_list) > 0
        }

    def _rebuild_chunks_index(self):
        """Consolidates all chunks from all documents into a single search index."""
        combined = []
        for doc in self.documents.values():
            combined.extend(doc.get("chunks", []))
        self.all_chunks = combined

    def retrieve_relevant_chunks(self, query: str, doc_filter: str = "all", top_k: int = 8) -> List[Dict[str, Any]]:
        """
        Retrieves top relevant passages using keyword, frequency, and exact-match scoring.
        Limits token size to prevent exceeding LLM context limits across unlimited documents.
        """
        pool = self.all_chunks
        if doc_filter and doc_filter != "all":
            pool = [c for c in pool if c["doc_name"] == doc_filter]

        if not pool:
            return []

        tokens = [w.lower() for w in re.findall(r'\b\w{3,}\b', query)]
        if not tokens:
            tokens = [w.lower() for w in query.split()]

        scored_chunks = []
        q_lower = query.lower().strip()

        for chunk in pool:
            text_lower = chunk.get("clean_lower", "")
            score = 0

            # Match exact question phrase
            if len(q_lower) > 4 and q_lower in text_lower:
                score += 25

            # Match individual keyword tokens
            for token in tokens:
                count = text_lower.count(token)
                if count > 0:
                    score += 2 + min(count, 4)

            # Match document name if mentioned in question
            doc_base = chunk["doc_name"].lower()
            if doc_base in q_lower:
                score += 5

            scored_chunks.append((score, chunk))

        # Sort by relevance
        scored_chunks.sort(key=lambda x: x[0], reverse=True)

        # Select top chunks while ensuring multi-page diversity
        results = []
        for score, ch in scored_chunks:
            if score > 0 or len(results) < 3:
                results.append(ch)
            if len(results) >= top_k:
                break

        # Fallback if no keywords matched (e.g., broad query like 'What is this?')
        if not results:
            results = pool[:top_k]

        return results

    def _call_with_fallback(self, func, custom_key: Optional[str] = None):
        """
        Executes Gemini call with automated failover:
        1. Tries primary model (gemini-3.5-flash-lite)
        2. Tries candidate models on 503 (high demand) or 404 (not found)
        3. Rotates API key or applies backoff on 429 (quota exceeded)
        """
        candidates = [self.active_model_name] + [m for m in MODEL_CANDIDATES if m != self.active_model_name]
        last_error = None

        for model_name in candidates:
            # Try up to 2 key attempts per model if multiple keys are configured
            attempts = min(len(self.api_keys), 2) if self.api_keys else 1
            for _ in range(attempts):
                try:
                    client = self.get_client(custom_key)
                    result = func(client, model_name)
                    self.active_model_name = model_name
                    return result, model_name
                except (ServerError, ClientError, Exception) as e:
                    err_str = str(e)
                    print(f"[RAG Engine] Model {model_name} error: {err_str[:120]}. Falling back...")
                    last_error = e

                    # Check for quota limit (429) -> Rotate API key
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        self.rotate_key()
                        time.sleep(1.0)
                    elif "503" in err_str or "UNAVAILABLE" in err_str:
                        # Model overloaded -> immediately try next model candidate
                        break
                    elif "404" in err_str or "NOT_FOUND" in err_str:
                        # Model retired/unavailable -> immediately try next model
                        break
                    else:
                        break

        raise RuntimeError(f"All Gemini models & keys failed. Last error: {last_error}")

    def build_prompt(self, question: str, target_language: str = "English", doc_filter: str = "all") -> Tuple[str, List[Dict[str, Any]]]:
        if not self.documents:
            raise ValueError("No documents uploaded yet. Please upload one or more PDFs first.")

        relevant_chunks = self.retrieve_relevant_chunks(question, doc_filter=doc_filter, top_k=8)
        
        context_blocks = []
        for idx, ch in enumerate(relevant_chunks):
            context_blocks.append(
                f"[Source Document: {ch['doc_name']} | Page: {ch['page']}]\n{ch['text']}"
            )
        
        context_text = "\n\n---\n\n".join(context_blocks)

        language_instruction = ""
        if target_language and target_language.lower() != "english":
            language_instruction = (
                f"\nCRITICAL LOCALIZATION REQUIREMENT: The user requests the answer in {target_language}.\n"
                f"Respond fully, accurately, and fluently in {target_language}. Keep key technical or legal terms clear."
            )

        prompt = f"""You are OmniDoc AI, an enterprise document intelligence and multi-PDF analytics assistant.
Analyze the provided excerpts across uploaded documents to answer the user's question accurately.

CORE INSTRUCTIONS:
1. Base your answer strictly on the provided Document Excerpts below. Do not fabricate or speculate.
2. CITATION REQUIREMENT: For every fact, statistic, or policy stated, explicitly cite the document and page number, e.g. "[Machine Learning Notes.pdf - Page 4]" or "[Invoice.pdf - Page 1]".
3. If the answer cannot be found in the provided contexts, explicitly state that the uploaded documents do not contain this information.
4. Format your answer with clean markdown bullet points, bold headers, and structured paragraphs.{language_instruction}

=== VERIFIED DOCUMENT EXCERPTS ===
{context_text}
=== END OF EXCERPTS ===

USER QUESTION:
{question}

ACCURATE MULTI-DOC ANSWER WITH CITATIONS:"""

        return prompt, relevant_chunks

    def stream_answer(
        self,
        question: str,
        target_language: str = "English",
        doc_filter: str = "all",
        api_key: Optional[str] = None
    ) -> Generator[str, None, None]:
        """
        Streams generated answers chunk by chunk for ultra-responsive UI experience.
        Utilizes LRU caching for instant responses on repeated questions.
        """
        if not self.documents:
            yield "⚠️ Please upload one or more PDF documents before asking questions."
            return

        cache_key = f"{question.strip().lower()}::{target_language}::{doc_filter}"
        if cache_key in self.cache:
            yield self.cache[cache_key]
            return

        prompt, _ = self.build_prompt(question, target_language, doc_filter)

        def do_stream(client, model_name):
            return client.models.generate_content_stream(
                model=model_name,
                contents=prompt
            )

        full_answer = []
        try:
            stream_result, model_used = self._call_with_fallback(do_stream, custom_key=api_key)
            for chunk in stream_result:
                if chunk.text:
                    full_answer.append(chunk.text)
                    yield chunk.text

            complete_text = "".join(full_answer)
            # Store in LRU cache
            if len(self.cache) >= self.cache_max_size:
                self.cache.popitem(last=False)
            self.cache[cache_key] = complete_text
        except Exception as e:
            yield f"\n[Error generating response: {str(e)}]"

    def stream_sse_answer(
        self,
        question: str,
        target_language: str = "English",
        doc_filter: str = "all",
        api_key: Optional[str] = None
    ) -> Generator[str, None, None]:
        """Streams answers formatted as Server-Sent Events (SSE)."""
        if not self.documents:
            yield f"data: {json.dumps({'text': '⚠️ Please upload at least one document first!'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        for text_chunk in self.stream_answer(question, target_language, doc_filter, api_key):
            yield f"data: {json.dumps({'text': text_chunk})}\n\n"
        yield "data: [DONE]\n\n"

    def generate_answer(
        self,
        question: str,
        target_language: str = "English",
        doc_filter: str = "all",
        api_key: Optional[str] = None
    ) -> Tuple[str, str, List[Dict[str, Any]]]:
        """Returns non-streamed full answer, model name used, and page citations."""
        if not self.documents:
            raise ValueError("No documents uploaded yet.")

        prompt, relevant_chunks = self.build_prompt(question, target_language, doc_filter)

        def do_generate(client, model_name):
            return client.models.generate_content(
                model=model_name,
                contents=prompt
            )

        res, model_used = self._call_with_fallback(do_generate, custom_key=api_key)
        answer_text = res.text if res else "No response generated."

        # Extract verified source citations from relevant chunks
        citations = find_relevant_citations(relevant_chunks, question, max_citations=4)

        return answer_text, model_used, citations

    def generate_summary(
        self,
        target_language: str = "English",
        summary_type: str = "executive",
        doc_filter: str = "all",
        api_key: Optional[str] = None
    ) -> Tuple[str, str, int]:
        """
        Generates structured Executive Summary for all uploaded documents or a specific document.
        """
        if not self.documents:
            raise ValueError("No documents uploaded yet.")

        lang_instr = ""
        if target_language and target_language.lower() != "english":
            lang_instr = f"\nPlease write the entire summary in {target_language}."

        if doc_filter and doc_filter != "all" and doc_filter in self.documents:
            doc = self.documents[doc_filter]
            context = doc["full_text"][:250000]
            header = f"Executive Summary for Document: '{doc['filename']}' ({doc['total_pages']} pages)"
            total_pages = doc["total_pages"]
        else:
            # Multi-document consolidated summary
            summary_parts = []
            total_pages = 0
            for name, doc in self.documents.items():
                total_pages += doc["total_pages"]
                summary_parts.append(f"=== Document: {name} ({doc['total_pages']} pages) ===\n{doc['full_text'][:70000]}")
            context = "\n\n".join(summary_parts)[:300000]
            header = f"Consolidated Executive Summary across {len(self.documents)} Documents ({total_pages} total pages)"

        prompt = f"""You are OmniDoc AI, an expert enterprise document intelligence and research analyst.
Generate a structured, professional Executive Summary based on the provided document content.
Title: {header}

Provide a structured markdown report with the following sections:
1. **Executive Overview**: High-level synthesis of the uploaded documents, their purpose, and key subjects covered.
2. **Key Findings & Core Points**: Bullet points detailing the most critical information, metrics, facts, and conclusions from each document.
3. **Important Clauses, Risks & Obligations**: Specific liabilities, dates, deadlines, financial figures, or risk factors cited with document names and page numbers.
4. **Strategic Takeaways & Conclusion**: Final assessment or actionable next steps.{lang_instr}

=== DOCUMENT REPOSITORY CONTENT ===
{context}
=== END OF CONTENT ===

PROFESSIONAL EXECUTIVE SUMMARY:"""

        def do_summary(client, model_name):
            return client.models.generate_content(
                model=model_name,
                contents=prompt
            )

        res, model_used = self._call_with_fallback(do_summary, custom_key=api_key)
        summary_text = res.text if res else "Could not generate summary."
        return summary_text, model_used, total_pages

# Global RAG Engine singleton
rag_engine = MultiDocumentRAGEngine()
