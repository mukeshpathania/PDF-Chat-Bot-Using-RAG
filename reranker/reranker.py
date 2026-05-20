"""
reranker.py
-----------
Takes the candidate chunks returned by the retriever and re-scores them
with a cross-encoder model so that only the *most semantically relevant*
chunks are forwarded to the LLM.

Why do we need a reranker?
  The vector store uses bi-encoder embeddings which are fast but imprecise –
  the query and each document are embedded independently.  A cross-encoder
  reads the (query, document) pair *together*, giving a much more accurate
  relevance score at the cost of speed.  By combining both steps we get
  the best of both worlds:
    1. Retriever  → fast broad recall  (fetch top-k candidates)
    2. Reranker   → precise re-scoring (keep top-n best candidates)

Cross-encoder model used:
  "cross-encoder/ms-marco-MiniLM-L-6-v2"
  - Trained on MS-MARCO passage ranking
  - Very small (~22 MB), fast on CPU
  - Replace with a larger model for higher accuracy
"""

from sentence_transformers import CrossEncoder

# ---------------------------------------------------------------------------
# Module-level singleton – loaded once and reused for every request
# ---------------------------------------------------------------------------
_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_cross_encoder: CrossEncoder | None = None


def _get_cross_encoder() -> CrossEncoder:
    """Lazy-load the cross-encoder so it is only downloaded on first use."""
    global _cross_encoder
    if _cross_encoder is None:
        print(f"[Reranker] Loading cross-encoder: {_CROSS_ENCODER_MODEL}")
        _cross_encoder = CrossEncoder(_CROSS_ENCODER_MODEL)
    return _cross_encoder


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rerank_documents(query: str, docs: list, top_n: int = 3) -> list:
    """
    Re-score and re-order a list of LangChain Document objects using a
    cross-encoder model, then return only the top-n most relevant ones.

    Parameters
    ----------
    query : str
        The user's original question.
    docs : list[Document]
        Candidate documents from the retriever step.
    top_n : int
        How many documents to keep after reranking. Must be <= len(docs).

    Returns
    -------
    list[Document]
        Documents sorted from most to least relevant, limited to top_n.
    """
    if not docs:
        return []

    top_n = min(top_n, len(docs))

    cross_encoder = _get_cross_encoder()

    # Build (query, passage) pairs for the cross-encoder
    pairs = [(query, doc.page_content) for doc in docs]

    # Predict relevance scores – higher score = more relevant
    scores = cross_encoder.predict(pairs)

    # Attach scores to documents and sort descending
    scored_docs = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)

    # Return only the top_n documents (without the score)
    reranked = [doc for _, doc in scored_docs[:top_n]]
    return reranked


def rerank_context(query: str, docs: list, top_n: int = 3) -> str:
    """
    Convenience wrapper used directly by query.py.
    Reranks the docs and returns a single formatted context string ready
    to be injected into the LLM prompt.

    Parameters
    ----------
    query : str
        The user's question.
    docs : list[Document]
        Candidate documents returned by the retriever.
    top_n : int
        Number of top-ranked chunks to include in the final context.

    Returns
    -------
    str
        Newline-separated, labeled chunk texts.
    """
    reranked_docs = rerank_documents(query, docs, top_n=top_n)

    if not reranked_docs:
        return "No relevant context found after reranking."

    context = "\n\n".join(
        [doc.page_content for doc in reranked_docs]
    )
    return context
