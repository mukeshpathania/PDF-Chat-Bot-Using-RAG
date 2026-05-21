from fastapi import APIRouter
# pyrefly: ignore [missing-import]
from groq import Groq
from dotenv import load_dotenv
import os
import re

from model.model import QueryRequest
from retriever.retriever import retrieve_documents   # Step 1 - broad candidate fetch
from reranker.reranker import rerank_context        # Step 2 - precise re-scoring


load_dotenv()

router = APIRouter()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

SYSTEM_PROMPT = """You are a helpful AI assistant that answers questions using ONLY the provided document context.

Rules you MUST follow:
1. Write a clear, natural language answer. Do NOT copy or repeat raw text from the context.
2. Do NOT include any separators, labels, or formatting markers from the context (such as "---", numbers in parentheses like "(1)", or slide numbers).
3. Synthesize the information into a coherent, human-readable response.
4. If the context does not contain the answer, say: "I couldn't find that in the uploaded document."
5. Keep your answer concise and well-structured."""

FOLLOWUP_SYSTEM_PROMPT = """You are a helpful AI assistant engaged in a conversation with the user.
The user is asking a follow-up question about your PREVIOUS answer — they want you to rephrase, shorten, expand, or reformat it.
Use ONLY your previous answer as the source. Do NOT make up new information.
Respond naturally and concisely."""

# Patterns that signal a follow-up / reformatting request rather than a new document question
FOLLOWUP_PATTERNS = re.compile(
    r"""
    \b(
      give\s*me | gimme | make\s*it | rewrite | summarize\s*(it|that|above|this) |
      shorten | shorter | brief(er|ly)? | condense | simplify | expand |
      explain\s*(more|it|that|further) | in\s*\d+\s*(lines?|sentences?|words?|points?) |
      \d+\s*(lines?|sentences?|words?|points?) | more\s*detail | again | repeat |
      rephrase | reformat | bullet\s*points? | list\s*(it|them)
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_followup(question: str, has_history: bool) -> bool:
    """Return True if the question looks like a reformatting/follow-up request."""
    if not has_history:
        return False
    # Short questions (≤ 12 words) that match a follow-up pattern are very likely follow-ups
    word_count = len(question.split())
    return bool(FOLLOWUP_PATTERNS.search(question)) and word_count <= 12


@router.post("/query")
async def query_rag(data: QueryRequest):

    print(f"[DEBUG] Received query for filename: '{data.filename}'")

    history_messages = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in data.chat_history
        if msg.get("role") in ("user", "assistant") and msg.get("content")
    ]

    # ── Follow-up path: rephrase / shorten / expand the PREVIOUS answer ──────
    if is_followup(data.question, bool(history_messages)):
        print(f"[DEBUG] Detected follow-up question — skipping RAG retrieval")

        # Find the last assistant answer to use as the source
        last_answer = ""
        for msg in reversed(data.chat_history):
            if msg.get("role") == "assistant":
                last_answer = msg["content"]
                break

        followup_user_msg = (
            f"Here is your previous answer:\n\n{last_answer}\n\n"
            f"User follow-up: {data.question}"
        )

        response = client.chat.completions.create(
            model=data.llm_model,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            messages=[
                {"role": "system", "content": FOLLOWUP_SYSTEM_PROMPT},
                *history_messages,
                {"role": "user",   "content": followup_user_msg},
            ]
        )
        return {"answer": response.choices[0].message.content}

    # ── Normal RAG path ───────────────────────────────────────────────────────
    # 1. Retrieve candidates using the user-chosen k
    candidate_docs = retrieve_documents(
        data.question, search_type="mmr", k=data.retrieval_k, filename=data.filename
    )

    print(f"[DEBUG] Retrieved {len(candidate_docs)} candidates")

    # HARD GUARD: if no chunks found, never call the LLM — it would hallucinate
    if not candidate_docs:
        return {
            "answer": (
                f"⚠️ No content found for **{data.filename}** in the document index.\n\n"
                "This usually means:\n"
                "• The file hasn't been uploaded/indexed yet — please upload it again.\n"
                "• The PDF is image-based (scanned) and contains no extractable text."
            )
        }

    # 2. Rerank and keep only the top_n most relevant chunks (user-chosen)
    context = rerank_context(data.question, candidate_docs, top_n=data.rerank_top_n)

    user_message = f"""Here is the relevant context from the document:

{context}

Question: {data.question}"""

    response = client.chat.completions.create(
        model=data.llm_model,
        temperature=data.temperature,
        max_tokens=data.max_tokens,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            *history_messages,
            {
                "role": "user",
                "content": user_message
            }
        ]
    )

    answer = response.choices[0].message.content

    return {
        "answer": answer,
    }