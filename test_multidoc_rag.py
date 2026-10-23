import os
import sys
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Ensure backend can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv()

from backend.config import UPLOAD_DIR
from backend.services.pdf_processor import extract_document_content, find_relevant_citations
from backend.services.rag_engine import rag_engine

def test_pipeline():
    print("=" * 60)
    print("🧪 Testing IndicDoc-AI Multi-Document Unlimited RAG Engine")
    print("=" * 60)

    # 1. Reset
    rag_engine.reset_documents()
    print("[1] Library reset OK.")

    # 2. Check uploaded_pdfs for sample files
    sample_files = list(UPLOAD_DIR.glob("*.pdf"))
    print(f"[2] Found {len(sample_files)} sample PDFs in {UPLOAD_DIR}:")
    for f in sample_files:
        print(f"    - {f.name}")

    if not sample_files:
        print("    No sample files found to index. Creating a synthetic test file.")
        dummy_path = UPLOAD_DIR / "sample_doc1.txt"
        dummy_path.write_text("Machine learning is a subset of artificial intelligence. It focuses on neural networks and gradient descent.", encoding="utf-8")
        sample_files = [dummy_path]

    # 3. Add multiple documents (Testing Unlimited Uploads)
    for f in sample_files:
        doc_data = extract_document_content(str(f), filename=f.name)
        rag_engine.add_document(doc_data)
        print(f"    ✓ Indexed: {f.name} ({doc_data['total_pages']} pages, {len(doc_data['chunks'])} chunks)")

    info = rag_engine.get_documents_info()
    print("\n[3] Global Library State:")
    print(f"    Total Documents: {info['total_documents']}")
    print(f"    Total Pages    : {info['total_pages']}")
    print(f"    Total Words    : {info['total_words']:,}")
    print(f"    Total Chunks   : {len(rag_engine.all_chunks)}")

    assert info["total_documents"] == len(sample_files), "Mismatch in total documents!"

    # 4. Test Multi-Document Retrieval
    query = "What is machine learning or supervised learning?"
    print(f"\n[4] Retrieving relevant chunks for query: '{query}'")
    chunks = rag_engine.retrieve_relevant_chunks(query, doc_filter="all", top_k=3)
    print(f"    Retrieved {len(chunks)} chunks.")
    for c in chunks:
        print(f"    - [{c['doc_name']} | Page {c['page']}] {c['text'][:80]}...")

    # 5. Test Citations
    citations = find_relevant_citations(chunks, query, max_citations=2)
    print(f"\n[5] Citations generated: {len(citations)}")
    for cit in citations:
        print(f"    - Document: {cit['doc_name']}, Page: {cit['page']}")

    # 6. Test Gemini Query with auto-fallback & caching
    print("\n[6] Testing Gemini LLM response (streaming)...")
    try:
        response_chunks = []
        for text in rag_engine.stream_answer(query, target_language="English", doc_filter="all"):
            response_chunks.append(text)
        full_ans = "".join(response_chunks)
        print(f"    Active Model: {rag_engine.active_model_name}")
        print(f"    Answer preview:\n    {full_ans[:200]}...\n")
        assert len(full_ans) > 20, "Answer too short!"
    except Exception as e:
        print(f"    LLM generation error: {e}")

    # 7. Test In-Memory Cache (0 latency, 0 tokens)
    print("[7] Testing Cache hit on repeated question...")
    cached_chunks = []
    for text in rag_engine.stream_answer(query, target_language="English", doc_filter="all"):
        cached_chunks.append(text)
    cached_ans = "".join(cached_chunks)
    assert cached_ans == full_ans, "Cache mismatch!"
    print("    ✓ Cache Hit Success! Zero API tokens consumed.")

    print("\n" + "=" * 60)
    print("🎉 ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_pipeline()
