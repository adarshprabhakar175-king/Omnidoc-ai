import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

def process_pdf_file(file_path: str):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Load PDF with page metadata
    loader = PyPDFLoader(file_path)
    docs = loader.load()

    # Split into chunks while preserving metadata (including page number)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=150
    )
    chunks = text_splitter.split_documents(docs)

    # Format page content so model easily spots page numbers
    for chunk in chunks:
        page_num = chunk.metadata.get("page", 0) + 1
        chunk.page_content = f"[Page {page_num}]\n{chunk.page_content}"

    return chunks