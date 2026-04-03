"""
rag/reranker.py
---------------
Cross-encoder reranker — the quality upgrade over pure embedding search.

How it works:
  Embedding search (what we had before):
    - Encodes question → vector A
    - Encodes each chunk → vector B
    - Computes cosine similarity between A and each B
    - Returns top-K by similarity score
    - Problem: vectors are created INDEPENDENTLY — the model never
      sees the question and chunk TOGETHER

  Cross-encoder reranking (what we add now):
    - Takes (question, chunk) as a PAIR
    - Runs both through a transformer TOGETHER
    - Outputs a single relevance score (0.0 to 1.0)
    - "Does this specific chunk actually answer this specific question?"
    - Much more accurate but slower (runs once per chunk)

Performance trade-off:
  Embedding search:   O(1) — vectors pre-computed, just a dot product
  Cross-encoder:      O(n) — runs inference for each (question, chunk) pair
  That's why we retrieve 10 with embeddings (fast) then rerank (accurate).
  We pay the cross-encoder cost for only 10 chunks, not the whole DB.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2
  - Trained on MS MARCO (Microsoft MAchine Reading COmprehension)
  - 22M parameters — small and fast
  - ~80MB download, runs on CPU
  - Scores relevance of (query, passage) pairs
"""

from sentence_transformers import CrossEncoder
from langchain.schema import Document

from core.config import RERANKER_MODEL, RERANKER_TOP_K, RERANKER_ENABLED
from core.logger import get_logger
from core.exceptions import VectorStoreError

logger = get_logger(__name__)

# Module-level cache — loaded once, reused for the process lifetime
_reranker: CrossEncoder | None = None


def get_reranker() -> CrossEncoder:
    """
    Return the cross-encoder model, loading it on first call.
    Same lazy-load pattern as embeddings.py.
    """
    global _reranker

    if _reranker is not None:
        return _reranker

    logger.info(
        "Loading reranker model: %s (first call — downloads ~80MB if not cached)",
        RERANKER_MODEL,
    )
    try:
        _reranker = CrossEncoder(RERANKER_MODEL, max_length=512)
        logger.info("Reranker model loaded ✓")
    except Exception as exc:
        logger.error("Failed to load reranker: %s", exc, exc_info=True)
        raise VectorStoreError(f"Could not load reranker model: {exc}") from exc

    return _reranker


def rerank(question: str, docs: list[Document]) -> list[Document]:
    """
    Rerank a list of retrieved documents by relevance to the question.

    Steps:
      1. Build (question, chunk_text) pairs for every doc
      2. Run all pairs through the cross-encoder in one batch
      3. Attach scores to docs
      4. Sort by score descending
      5. Return top RERANKER_TOP_K docs

    Args:
      question: the student's original question
      docs:     candidate chunks from ChromaDB (typically 10)

    Returns:
      Top RERANKER_TOP_K docs sorted by relevance score (best first)
    """
    if not docs:
        logger.debug("Rerank called with empty docs — returning empty")
        return []

    if not RERANKER_ENABLED:
        logger.debug("Reranker disabled — returning first %d docs as-is", RERANKER_TOP_K)
        return docs[:RERANKER_TOP_K]

    reranker = get_reranker()

    # Build input pairs: [(question, chunk1_text), (question, chunk2_text), ...]
    pairs = [(question, doc.page_content) for doc in docs]

    logger.debug(
        "Reranking %d chunks for question: %r",
        len(docs), question[:60],
    )

    try:
        # predict() returns a numpy array of scores
        # Higher score = more relevant to the question
        scores = reranker.predict(pairs)
    except Exception as exc:
        logger.error("Reranker prediction failed: %s", exc, exc_info=True)
        # Graceful fallback — return top-K without reranking
        logger.warning("Falling back to top-%d without reranking", RERANKER_TOP_K)
        return docs[:RERANKER_TOP_K]

    # Attach scores to docs for sorting
    # zip() pairs each score with its corresponding doc
    scored_docs = list(zip(scores, docs))

    # Sort by score descending (highest relevance first)
    scored_docs.sort(key=lambda x: x[0], reverse=True)

    # Log the scores so you can see how reranking changed the order
    for i, (score, doc) in enumerate(scored_docs[:RERANKER_TOP_K]):
        logger.debug(
            "  Rank %d | score=%.4f | source=%s | page=%s | preview=%r",
            i + 1,
            float(score),
            doc.metadata.get("source_file", "?"),
            doc.metadata.get("page", "?"),
            doc.page_content[:60],
        )

    # Return only the top-K docs (drop the scores, LLM just needs the text)
    top_docs = [doc for _, doc in scored_docs[:RERANKER_TOP_K]]

    logger.info(
        "Reranking complete: %d → %d chunks  best_score=%.4f",
        len(docs), len(top_docs), float(scored_docs[0][0]),
    )

    return top_docs
