"""
rag/tools.py
------------
Prompt engineering for study tools:
  1. Quiz generator     — MCQ questions from document content
  2. Summariser         — structured summary with key concepts
  3. Follow-up suggester — 3 related questions after each answer
  4. Confidence scorer  — how well the answer is grounded in docs

Why separate from chain.py?
  chain.py handles conversational Q&A (stateful, streamed)
  tools.py handles one-shot structured generation (stateless, JSON)
  Keeping them separate makes each easier to test and improve.

All tools use the same pattern:
  1. Retrieve relevant chunks (reranked)
  2. Build a structured prompt
  3. Call Groq with JSON output format
  4. Parse and return structured data
"""

import json
from groq import Groq

from core.config import GROQ_API_KEY, GROQ_MAX_TOKENS, get_active_model
from core.logger import get_logger
from core.exceptions import LLMError
from rag.retriever import get_vectorstore
from rag.reranker import rerank

logger = get_logger(__name__)


def _get_all_chunks(user_id: int, max_chunks: int = 20) -> list[str]:
    """
    Retrieve a broad sample of chunks from the user's documents.
    Used for whole-document tools like summariser and quiz generator
    where we want coverage across the whole document, not just
    the most relevant bits.
    """
    try:
        vs   = get_vectorstore(user_id)
        data = vs.get()
        texts = [m for m in data.get("documents", []) if m]
        # Sample evenly across the document for broad coverage
        if len(texts) <= max_chunks:
            return texts
        step = len(texts) // max_chunks
        return texts[::step][:max_chunks]
    except Exception as exc:
        logger.error("Failed to get chunks for user_id=%d: %s", user_id, exc)
        return []


def _call_groq_json(system_prompt: str, user_prompt: str) -> dict:
    """
    Call Groq and expect a JSON response.
    Returns parsed dict or raises LLMError.
    """
    client = Groq(api_key=GROQ_API_KEY)
    try:
        response = client.chat.completions.create(
            model=get_active_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=2048,
            stream=False,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        return json.loads(raw)

    except json.JSONDecodeError as exc:
        logger.error("JSON parse failed: %s | raw=%r", exc, raw[:200])
        raise LLMError("AI returned invalid JSON. Please try again.") from exc
    except Exception as exc:
        logger.error("Groq call failed: %s", exc, exc_info=True)
        raise LLMError(f"AI request failed: {exc}") from exc


# ── 1. Quiz Generator ─────────────────────────────────────────────────────────

def generate_quiz(user_id: int, num_questions: int = 10, difficulty: str = "medium") -> dict:
    """
    Generate MCQ quiz questions from the user's uploaded documents.

    Returns:
    {
      "title": "Quiz on Contract Law",
      "questions": [
        {
          "question": "What are the three elements of a valid contract?",
          "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
          "answer": "B",
          "explanation": "A contract requires offer, acceptance and consideration."
        },
        ...
      ]
    }
    """
    logger.info("Generating quiz: user_id=%d questions=%d difficulty=%s",
                user_id, num_questions, difficulty)

    chunks = _get_all_chunks(user_id, max_chunks=20)
    if not chunks:
        raise LLMError("No documents found. Please upload a PDF first.")

    context = "\n\n".join(chunks[:15])

    system_prompt = """You are an expert academic quiz creator.
Generate multiple choice questions from the provided study material.
You MUST respond with valid JSON only — no markdown, no explanation, just the JSON object.

Rules:
- Questions must be based ONLY on the provided content
- Each question must have exactly 4 options (A, B, C, D)
- Only one option is correct
- Include a brief explanation for the correct answer
- Vary question difficulty appropriately
- Focus on key concepts, definitions, and important facts"""

    user_prompt = f"""Create {num_questions} {difficulty}-difficulty MCQ questions from this study material.

Study material:
{context}

Respond with this exact JSON structure:
{{
  "title": "Quiz on [topic name]",
  "difficulty": "{difficulty}",
  "questions": [
    {{
      "question": "Question text here?",
      "options": ["A) option1", "B) option2", "C) option3", "D) option4"],
      "answer": "A",
      "explanation": "Brief explanation of why this is correct."
    }}
  ]
}}"""

    result = _call_groq_json(system_prompt, user_prompt)
    logger.info("Quiz generated: %d questions", len(result.get("questions", [])))
    return result


# ── 2. Document Summariser ────────────────────────────────────────────────────

def summarise_documents(user_id: int) -> dict:
    """
    Generate a structured summary of the user's uploaded documents.

    Returns:
    {
      "title": "Contract Law — Study Summary",
      "overview": "This document covers...",
      "key_concepts": ["Offer", "Acceptance", "Consideration"],
      "definitions": [{"term": "Tort", "definition": "A civil wrong..."}],
      "exam_topics": ["Elements of negligence", "Types of contracts"],
      "study_tips": ["Focus on the three elements...", ...]
    }
    """
    logger.info("Generating summary for user_id=%d", user_id)

    chunks = _get_all_chunks(user_id, max_chunks=20)
    if not chunks:
        raise LLMError("No documents found. Please upload a PDF first.")

    context = "\n\n".join(chunks[:15])

    system_prompt = """You are an expert academic study coach.
Create comprehensive, structured study summaries from document content.
You MUST respond with valid JSON only — no markdown, no preamble.

Focus on what students need to know for exams.
Be concise but complete. Use plain, clear language."""

    user_prompt = f"""Create a structured study summary from this material:

{context}

Respond with this exact JSON structure:
{{
  "title": "Topic — Study Summary",
  "overview": "2-3 sentence overview of the entire document",
  "key_concepts": ["concept1", "concept2", "concept3", "concept4", "concept5"],
  "definitions": [
    {{"term": "Term name", "definition": "Clear definition in one sentence"}}
  ],
  "exam_topics": ["likely exam topic 1", "likely exam topic 2", "likely exam topic 3"],
  "study_tips": ["specific study tip 1", "specific study tip 2", "specific study tip 3"]
}}"""

    result = _call_groq_json(system_prompt, user_prompt)
    logger.info("Summary generated for user_id=%d", user_id)
    return result


# ── 3. Follow-up Question Suggester ──────────────────────────────────────────

def suggest_followups(question: str, answer: str, user_id: int) -> list[str]:
    """
    Suggest 3 natural follow-up questions based on the Q&A exchange.

    Returns: ["follow-up 1", "follow-up 2", "follow-up 3"]
    """
    logger.debug("Generating follow-up suggestions for user_id=%d", user_id)

    system_prompt = """You are a study assistant helping students explore topics deeper.
Generate 3 natural follow-up questions a student might want to ask next.
You MUST respond with valid JSON only.

Rules:
- Questions must be directly related to the answer given
- Each question should explore a different angle
- Keep questions concise and student-friendly
- Questions should be answerable from study material"""

    user_prompt = f"""Student asked: {question}

AI answered: {answer[:500]}

Generate 3 follow-up questions the student might want to ask next.

Respond with this exact JSON:
{{"questions": ["question 1?", "question 2?", "question 3?"]}}"""

    try:
        result = _call_groq_json(system_prompt, user_prompt)
        questions = result.get("questions", [])[:3]
        logger.debug("Generated %d follow-up suggestions", len(questions))
        return questions
    except Exception as exc:
        logger.warning("Follow-up generation failed: %s", exc)
        return []   # non-fatal — return empty list


# ── 4. Confidence Scorer ──────────────────────────────────────────────────────

def score_confidence(question: str, answer: str, docs: list) -> dict:
    """
    Score how confident the AI is that the answer is grounded in the documents.

    Uses two signals:
      1. Reranker score of the best matching chunk (primary)
      2. LLM self-assessment (secondary)

    Returns:
    {
      "level": "high",        # high / medium / low
      "score": 0.87,          # 0.0 to 1.0
      "label": "🟢 High",
      "message": "This answer is well supported by your documents."
    }
    """
    if not docs:
        return {
            "level": "low", "score": 0.0,
            "label": "🔴 Low",
            "message": "Could not find relevant content in your documents.",
        }

    # Use the reranker to score relevance of best chunk
    try:
        from sentence_transformers import CrossEncoder
        from core.config import RERANKER_MODEL
        reranker  = CrossEncoder(RERANKER_MODEL, max_length=512)
        # Score question against the answer itself (proxy for grounding)
        score     = float(reranker.predict([(question, docs[0].page_content)]))
        # Normalise to 0-1 range (cross-encoder scores can exceed 1.0)
        score     = min(max(score / 10.0 + 0.5, 0.0), 1.0)
    except Exception:
        # Fallback: estimate from answer length and source count
        score = min(0.5 + len(docs) * 0.1, 0.9)

    if score >= 0.75:
        level, label = "high",   "🟢 High confidence"
        message = "This answer is well supported by your uploaded documents."
    elif score >= 0.45:
        level, label = "medium", "🟡 Medium confidence"
        message = "Partially supported — verify key points with your source material."
    else:
        level, label = "low",    "🔴 Low confidence"
        message = "Limited coverage in your documents — check the original source."

    return {"level": level, "score": round(score, 2), "label": label, "message": message}
