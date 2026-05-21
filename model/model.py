from pydantic import BaseModel
from typing import List, Dict


class QueryRequest(BaseModel):
    question: str
    filename: str = ""
    chat_history: List[Dict[str, str]] = []
    # Model settings (sent from the frontend settings panel)
    llm_model:    str   = "llama-3.3-70b-versatile"
    temperature:  float = 0.7
    max_tokens:   int   = 512
    retrieval_k:  int   = 8
    rerank_top_n: int   = 3