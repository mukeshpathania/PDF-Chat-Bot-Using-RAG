"""
rag.py
------
PDF ingestion pipeline.
Loads a PDF, splits it into chunks, and stores them in the ChromaDB
vector store.  Retrieval logic has been moved to retriever.py.
"""
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader

from db.db import vector_db


def process_pdf(file_path: str) -> int:
    """
    Load a PDF, split it into overlapping chunks, and index them.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the PDF file.

    Returns
    -------
    int
        Total number of chunks stored in the vector DB.
    """
    loader = PyPDFLoader(file_path)
    documents = loader.load()

    if not documents:
        print(f"[RAG] WARNING: No text extracted from {file_path}. "
              "The PDF may be image-based (scanned).")
        return 0

    # Normalise the source path to forward slashes so the metadata filter
    # works identically on Windows and Linux (avoids backslash mismatch).
    normalised_path = file_path.replace("\\", "/")
    for doc in documents:
        doc.metadata["source"] = normalised_path

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
    )

    chunks = splitter.split_documents(documents)
    print(f"[RAG] Indexed {len(chunks)} chunks from {len(documents)} pages")

    if chunks:
        vector_db.add_documents(chunks)
    else:
        print(f"[RAG] WARNING: No valid text chunks generated from {file_path}.")

    return len(chunks)