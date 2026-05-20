from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings


embedding_model = HuggingFaceEmbeddings(
model_name = "BAAI/bge-small-en"
)


vector_db = Chroma(
collection_name = "rag_collection",
embedding_function = embedding_model,
persist_directory = "./chroma_db"
)