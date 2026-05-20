"""
retriever.py
------------
Responsible for fetching the most relevant document chunks from the
ChromaDB vector store for a given user query.

Two search strategies are available:
  - "similarity" : pure cosine-similarity search (fast, default)
  - "mmr"        : Maximal Marginal Relevance – balances relevance with
                   diversity so the LLM receives varied evidence rather
                   than near-duplicate chunks.

Filtering strategy (two layers):
  1. ChromaDB metadata filter  — passed directly to similarity_search /
     max_marginal_relevance_search so the DB only scans the right file.
  2. Python post-filter        — verifies the `source` metadata of every
     returned chunk. Guarantees correctness even if the DB filter is
     silently ignored by a particular ChromaDB/LangChain version.
"""

import os
from db.db import vector_db


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_where_filter(filename: str) -> dict | None:
    """
    Build the ChromaDB `where` dict for a given filename.
    Normalises path separators to forward-slashes for cross-platform safety.
    Returns None when no filename is provided (no filtering).
    """
    if not filename:
        return None
    full_path = os.path.join("uploads", filename).replace("\\", "/")
    return {"source": full_path}


def _post_filter(docs: list, filename: str) -> list:
    """
    Safety-net: keep only docs whose `source` metadata contains the
    expected filename.  Runs after the DB query so wrong-document chunks
    can never leak through regardless of ChromaDB filter behaviour.
    """
    if not filename:
        return docs
    return [
        doc for doc in docs
        if filename in doc.metadata.get("source", "").replace("\\", "/")
    ]


def _filter_chunks(docs: list) -> list:
    """
    Remove low-quality chunks — slide numbers, bare digits, very short
    strings — that add noise to the LLM context.
    """
    MIN_CHARS = 60
    return [doc for doc in docs if len(doc.page_content.strip()) >= MIN_CHARS]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve_documents(
    query: str,
    search_type: str = "similarity",
    k: int = 5,
    filename: str = "",
) -> list:
    """
    Retrieve the top-k most relevant Document objects for a query.

    Parameters
    ----------
    query : str
        The user's question or search string.
    search_type : str
        "similarity" or "mmr".
    k : int
        How many chunks to retrieve.
    filename : str
        Restrict retrieval to chunks from this file only.

    Returns
    -------
    list[Document]
        LangChain Document objects, each with .page_content and .metadata.
    """
    where = _build_where_filter(filename)

    print(f"[Retriever] search_type={search_type!r}  filename={filename!r}")
    print(f"[Retriever] where filter = {where!r}")

    # Use as_retriever — it correctly propagates the filter in langchain-chroma
    # 1.1 / chromadb 1.5, whereas calling max_marginal_relevance_search /
    # similarity_search with filter= can silently return 0 docs.
    search_kwargs = {"k": k}
    if where:
        search_kwargs["filter"] = where
    if search_type == "mmr":
        search_kwargs["fetch_k"] = max(k * 3, 20)

    try:
        retriever = vector_db.as_retriever(
            search_type=search_type if search_type == "mmr" else "similarity",
            search_kwargs=search_kwargs,
        )
        docs = retriever.invoke(query)
        print(f"[Retriever] as_retriever returned {len(docs)} docs")
    except Exception as e:
        print(f"[Retriever] as_retriever failed ({e}), falling back to direct search")
        docs = []

    # Fallback: if filtered retriever returned nothing, try unfiltered and let
    # the Python post-filter do the job (bulletproof safety net).
    if not docs:
        print("[Retriever] Zero docs from filtered retriever — trying unfiltered fallback")
        try:
            fallback_kwargs = {"k": k * 4}
            if search_type == "mmr":
                fallback_kwargs["fetch_k"] = k * 8
            fallback_retriever = vector_db.as_retriever(
                search_type=search_type if search_type == "mmr" else "similarity",
                search_kwargs=fallback_kwargs,
            )
            docs = fallback_retriever.invoke(query)
            print(f"[Retriever] Fallback returned {len(docs)} docs (pre-post-filter)")
        except Exception as e2:
            print(f"[Retriever] Fallback also failed ({e2})")
            docs = []

    # Layer 2: Python-level source guard (bulletproof safety net)
    docs = _post_filter(docs, filename)
    print(f"[Retriever] After post-filter : {len(docs)} docs")

    # Layer 3: quality filter (drop very short / junk chunks)
    docs = _filter_chunks(docs)
    print(f"[Retriever] After quality filter: {len(docs)} docs")

    return docs


def retrieve_context(
    query: str,
    search_type: str = "similarity",
    k: int = 5,
    filename: str = "",
) -> str:
    """
    High-level helper — retrieve and return a single context string
    ready to inject into the LLM prompt.
    """
    docs = retrieve_documents(query, search_type=search_type, k=k, filename=filename)

    if not docs:
        return "No relevant context found in the uploaded documents."

    return "\n\n".join(doc.page_content for doc in docs)
