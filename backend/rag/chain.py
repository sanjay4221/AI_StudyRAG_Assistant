"""
rag/chain.py
------------
LLM chain — now supports:
  1. Per-user retriever  (each user searches only their docs)
  2. Streaming responses (tokens sent to browser as they arrive)

Two public functions:
  build_qa_chain(user_id)   → standard chain for non-streaming (history sessions)
  stream_answer(question, user_id, chat_history)  → generator that yields tokens

Why two functions?
  LangChain's ConversationalRetrievalChain doesn't stream easily with memory.
  For streaming we use a simpler direct approach:
    1. Retrieve chunks with the retriever
    2. Build the prompt manually
    3. Call Groq with stream=True
    4. Yield each token as a Server-Sent Event
  This gives us full control and real word-by-word streaming.
"""

import json
from groq import RateLimitError as GroqRateLimitError
from groq import Groq

from langchain_groq import ChatGroq
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)

from core.config import (
    GROQ_API_KEY,
    GROQ_TEMPERATURE,
    GROQ_MAX_TOKENS,
    get_active_model,
)
from core.logger import get_logger
from core.exceptions import LLMError, LLMRateLimitError
from rag.retriever import get_retriever
from rag.reranker import rerank

logger = get_logger(__name__)

# ── Shared system prompt ───────────────────────────────────────────────────────
_SYSTEM = """You are StudyRAG, a friendly and knowledgeable AI study assistant.
Your job is to help students understand their course material clearly and accurately.

Rules you must always follow:
1. Answer ONLY using information from the provided document context below.
2. If the answer is not in the context, respond with:
   "I couldn't find that in your documents. Try rephrasing your question or uploading a more relevant PDF."
3. Never invent facts, statistics, or references that are not in the context.
4. Be clear and student-friendly — explain concepts simply, use examples where helpful.
5. Use bullet points or numbered steps when it improves clarity.
6. When you cite information, mention the source file name naturally in your answer.

Document context:
{context}

Conversation history:
{chat_history}"""

_HUMAN = "{question}"

QA_PROMPT = ChatPromptTemplate.from_messages([
    SystemMessagePromptTemplate.from_template(_SYSTEM),
    HumanMessagePromptTemplate.from_template(_HUMAN),
])


# ── 1. Standard chain (used for loading past sessions) ────────────────────────
def build_qa_chain(user_id: int) -> ConversationalRetrievalChain:
    """
    Build a ConversationalRetrievalChain for this specific user.
    Uses user's private ChromaDB collection.
    """
    active_model = get_active_model()
    logger.info("Building QA chain for user_id=%d model=%s", user_id, active_model)

    llm = ChatGroq(
        model=active_model,
        temperature=GROQ_TEMPERATURE,
        max_tokens=GROQ_MAX_TOKENS,
        groq_api_key=GROQ_API_KEY,
    )

    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        output_key="answer",
    )

    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=get_retriever(user_id),       # ← user-scoped retriever
        memory=memory,
        combine_docs_chain_kwargs={"prompt": QA_PROMPT},
        return_source_documents=True,
        verbose=False,
    )

    logger.info("QA chain ready for user_id=%d ✓", user_id)
    return chain


# ── 2. Streaming answer (used for new chat messages) ─────────────────────────
def stream_answer(question: str, user_id: int, chat_history: list[dict]):
    """
    Generator that yields Server-Sent Event strings for real-time streaming.

    Flow:
      1. Retrieve top-K chunks from user's collection
      2. Format context + history into the prompt
      3. Call Groq with stream=True
      4. Yield each token as:  data: {"token": "..."}\n\n
      5. At end yield sources: data: {"sources": [...], "done": true}\n\n

    Why SSE (Server-Sent Events)?
      Simple one-way stream from server to browser.
      Browser uses EventSource or fetch with ReadableStream.
      No WebSocket complexity needed for this use case.
    """
    active_model = get_active_model()
    logger.info("Streaming answer for user_id=%d model=%s question=%r",
                user_id, active_model, question[:80])

    # Step 1 — Retrieve top-K candidate chunks (wide net — returns 10)
    try:
        retriever = get_retriever(user_id)
        docs      = retriever.invoke(question)
    except Exception as exc:
        logger.error("Retrieval failed for user_id=%d: %s", user_id, exc)
        yield f"data: {json.dumps({'error': 'Failed to search your documents.'})}\n\n"
        return

    # Step 2 — Rerank: cross-encoder scores each (question, chunk) pair
    #           keeps only the top 4 most relevant chunks
    #           This is the quality upgrade over pure embedding search
    try:
        docs = rerank(question, docs)
    except Exception as exc:
        logger.warning("Reranking failed, using raw retrieval: %s", exc)
        # Non-fatal — fall back to first 4 chunks from embedding search
        docs = docs[:4]

    # Step 3 — Build context string from reranked chunks
    context = "\n\n".join(doc.page_content for doc in docs)

    # Step 3 — Format chat history for the prompt
    history_text = ""
    for msg in chat_history[-6:]:   # last 3 turns (6 messages) to stay within token limit
        role    = "Student" if msg["role"] == "user" else "StudyRAG"
        history_text += f"{role}: {msg['content']}\n"

    # Step 4 — Build the final prompt
    system_msg = _SYSTEM.format(context=context, chat_history=history_text)

    # Step 5 — Call Groq with stream=True using the raw Groq client
    groq_client = Groq(api_key=GROQ_API_KEY)

    try:
        stream = groq_client.chat.completions.create(
            model=active_model,
            messages=[
                {"role": "system",  "content": system_msg},
                {"role": "user",    "content": question},
            ],
            temperature=GROQ_TEMPERATURE,
            max_tokens=GROQ_MAX_TOKENS,
            stream=True,    # ← this is what makes it stream token by token
        )
    except GroqRateLimitError:
        logger.warning("Groq rate limit hit for user_id=%d", user_id)
        yield f"data: {json.dumps({'error': 'Rate limit reached. Please wait a moment.'})}\n\n"
        return
    except Exception as exc:
        logger.error("Groq API error for user_id=%d: %s", user_id, exc)
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        return

    # Step 6 — Yield each token as it arrives
    full_answer = ""
    for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            full_answer += token
            # Each SSE message: "data: {...}\n\n"
            yield f"data: {json.dumps({'token': token})}\n\n"

    # Step 7 — After streaming completes, send sources + confidence + followups + done signal
    seen, sources = set(), []
    for doc in docs:
        ref = (doc.metadata.get("source_file", "unknown"), doc.metadata.get("page", "?"))
        if ref not in seen:
            seen.add(ref)
            sources.append({"file": ref[0], "page": ref[1]})

    # Confidence score
    try:
        from rag.tools import score_confidence, suggest_followups
        confidence = score_confidence(question, full_answer, docs)
        followups  = suggest_followups(question, full_answer, user_id)
    except Exception as exc:
        logger.warning("Tools failed (non-fatal): %s", exc)
        confidence = {"level": "medium", "score": 0.5, "label": "🟡 Medium confidence",
                      "message": "Verify with your source material."}
        followups  = []

    logger.info("Stream complete for user_id=%d  length=%d chars  sources=%d",
                user_id, len(full_answer), len(sources))

    yield f"data: {json.dumps({'sources': sources, 'model': active_model, 'confidence': confidence, 'followups': followups, 'done': True})}\n\n"


# ── 3. Non-streaming ask (kept for loading past session messages) ─────────────
def ask_question(chain: ConversationalRetrievalChain, question: str) -> dict:
    """Non-streaming invoke — used when replaying session history."""
    logger.info("Non-stream question: %r", question[:120])
    try:
        result = chain.invoke({"question": question})
    except GroqRateLimitError as exc:
        raise LLMRateLimitError() from exc
    except Exception as exc:
        logger.error("Chain invocation failed: %s", exc, exc_info=True)
        raise LLMError(f"LLM failed: {exc}") from exc

    answer = result.get("answer", "").strip()
    if not answer:
        raise LLMError("LLM returned an empty response.")

    seen, sources = set(), []
    for doc in result.get("source_documents", []):
        ref = (doc.metadata.get("source_file", "unknown"), doc.metadata.get("page", "?"))
        if ref not in seen:
            seen.add(ref)
            sources.append({"file": ref[0], "page": ref[1]})

    return {"answer": answer, "sources": sources, "model": get_active_model()}
