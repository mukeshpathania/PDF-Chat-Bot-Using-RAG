from fastapi import APIRouter
# pyrefly: ignore [missing-import]
from groq import Groq
from dotenv import load_dotenv
import os

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


@router.post("/query")
async def query_rag(data: QueryRequest):

    print(f"[DEBUG] Received query for filename: '{data.filename}'")

    # --- Retrieval + Reranking pipeline ---
    # 1. Retrieve 8 broad candidates from the vector store
    candidate_docs = retrieve_documents(data.question, search_type="mmr", k=8, filename=data.filename)

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

    # 2. Rerank and keep only the 3 most relevant chunks
    context = rerank_context(data.question, candidate_docs, top_n=3)

    user_message = f"""Here is the relevant context from the document:

{context}

Question: {data.question}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
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