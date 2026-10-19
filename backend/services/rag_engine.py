import os
import json
from typing import Generator, Dict, Any, Optional, Tuple, List
import google.generativeai as genai

from backend.config import GOOGLE_API_KEY, MODEL_CANDIDATES, DEFAULT_MODEL
from backend.services.pdf_processor import find_relevant_page_citations

class DocumentRAGEngine:
    def __init__(self):
        self.api_key = GOOGLE_API_KEY
        if self.api_key:
            genai.configure(api_key=self.api_key)
        self.active_model_name = DEFAULT_MODEL
        self.current_doc: Optional[Dict[str, Any]] = None

    def set_document(self, doc_data: Dict[str, Any]):
        """Sets the currently active document in memory."""
        self.current_doc = doc_data

    def get_document(self) -> Optional[Dict[str, Any]]:
        """Returns the current document metadata or None."""
        return self.current_doc

    def reset_document(self):
        """Clears the loaded document."""
        self.current_doc = None

    def _get_model(self, model_name: Optional[str] = None) -> genai.GenerativeModel:
        name = model_name or self.active_model_name
        return genai.GenerativeModel(name)

    def _call_with_fallback(self, func):
        """
        Executes a Gemini call with automatic model fallback in case of 404/503 errors.
        """
        last_error = None
        candidates = [self.active_model_name] + [m for m in MODEL_CANDIDATES if m != self.active_model_name]

        for model_name in candidates:
            try:
                model = self._get_model(model_name)
                result = func(model)
                self.active_model_name = model_name
                return result, model_name
            except Exception as e:
                err_msg = str(e)
                print(f"[RAG Engine] Model {model_name} failed: {err_msg}. Attempting fallback...")
                last_error = e

        raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")

    def build_prompt(self, question: str, target_language: str = "English") -> str:
        if not self.current_doc or not self.current_doc.get("full_text"):
            raise ValueError("No document uploaded yet. Please upload a document first.")

        doc_text = self.current_doc["full_text"]
        # Limit text safely within context window (Gemini can comfortably take 500k+ chars)
        context_slice = doc_text[:400000]

        language_instruction = ""
        if target_language and target_language.lower() != "english":
            language_instruction = (
                f"\nCRITICAL LOCALIZATION REQUIREMENT: The user requests the answer in {target_language}.\n"
                f"Respond fully and fluently in {target_language}, while keeping important technical/legal terms clear."
            )

        prompt = f"""You are IndicDoc-AI, a world-class enterprise document intelligence assistant.
Analyze the provided document text carefully to answer the user's question accurately.

GUIDELINES:
1. Base your answer strictly on the provided Document Context. Do not hallucinate or extrapolate beyond the text.
2. Whenever you reference facts, rules, numbers, or statements from the document, explicitly cite the page number (e.g. "[Page 2]" or "[Page 5]").
3. If the answer cannot be found in the document, politely state that the uploaded document does not contain this information.
4. Provide structured, clear formatting using bolding, bullet points, or sections where appropriate.{language_instruction}

=== DOCUMENT CONTEXT BEGINS ===
{context_slice}
=== DOCUMENT CONTEXT ENDS ===

USER QUESTION:
{question}

ACCURATE ANSWER:"""
        return prompt

    def stream_answer(self, question: str, target_language: str = "English") -> Generator[str, None, None]:
        """
        Yields raw string chunks for smooth real-time token streaming.
        """
        if not self.current_doc or not self.current_doc.get("full_text"):
            yield "⚠️ Please upload a document first before querying."
            return

        prompt = self.build_prompt(question, target_language)

        def do_stream(model):
            return model.generate_content(prompt, stream=True)

        try:
            response, model_used = self._call_with_fallback(do_stream)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"\n[Error generating response: {str(e)}]"

    def stream_sse_answer(self, question: str, target_language: str = "English") -> Generator[str, None, None]:
        """
        Yields Server-Sent Events (SSE) formatted chunks: 'data: {...}\n\n'
        """
        if not self.current_doc or not self.current_doc.get("full_text"):
            yield f"data: {json.dumps({'text': '⚠️ Please upload a document first!'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        for text_chunk in self.stream_answer(question, target_language):
            yield f"data: {json.dumps({'text': text_chunk})}\n\n"
        yield "data: [DONE]\n\n"

    def generate_answer(self, question: str, target_language: str = "English") -> Tuple[str, str, List[Dict[str, Any]]]:
        """
        Returns full answer text, model name used, and page citations.
        """
        if not self.current_doc or not self.current_doc.get("full_text"):
            raise ValueError("No document uploaded yet.")

        prompt = self.build_prompt(question, target_language)

        def do_generate(model):
            return model.generate_content(prompt)

        res, model_used = self._call_with_fallback(do_generate)
        answer_text = res.text if res else "No response generated."

        # Extract citations
        citations = find_relevant_page_citations(
            self.current_doc.get("pages", []),
            question,
            max_citations=3
        )

        return answer_text, model_used, citations

    def generate_summary(self, target_language: str = "English", summary_type: str = "executive") -> Tuple[str, str]:
        """
        Generates an executive summary of the currently loaded document.
        """
        if not self.current_doc or not self.current_doc.get("full_text"):
            raise ValueError("No document uploaded yet.")

        doc_text = self.current_doc["full_text"][:300000]
        filename = self.current_doc.get("filename", "Document")
        total_pages = self.current_doc.get("total_pages", 1)

        lang_instr = ""
        if target_language and target_language.lower() != "english":
            lang_instr = f"\nPlease write the executive summary completely in {target_language}."

        prompt = f"""You are IndicDoc-AI, an expert enterprise analyst.
Generate a high-level, structured Executive Summary for the document titled '{filename}' ({total_pages} pages).

Format the summary with the following clear markdown sections:
1. **Executive Overview**: A 2-3 sentence high-level synthesis of what this document is about.
2. **Key Highlights & Core Points**: Bulleted list of the top 4-6 most important facts, metrics, or arguments.
3. **Important Clauses / Obligations / Risks**: Key stipulations, dates, obligations, or takeaways.
4. **Conclusion & Recommendations**: Final verdict or next steps.{lang_instr}

=== DOCUMENT CONTENT ===
{doc_text}
=== END DOCUMENT CONTENT ===

EXECUTIVE SUMMARY:"""

        def do_summary(model):
            return model.generate_content(prompt)

        res, model_used = self._call_with_fallback(do_summary)
        summary_text = res.text if res else "Could not generate summary."
        return summary_text, model_used

# Global RAG Engine singleton
rag_engine = DocumentRAGEngine()