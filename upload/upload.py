from fastapi import APIRouter, UploadFile
import shutil
import os
import sqlite3
import re

from rag.rag import process_pdf
from db.db import vector_db

router = APIRouter()

# 1. Ensure uploads directory exists
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 2. Setup simple SQLite table (run this once when the app starts)
conn = sqlite3.connect('db/files.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS uploaded_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE,
        filepath TEXT
    )
''')
conn.commit()

@router.post("/upload")
async def upload_pdf(file: UploadFile):
    # Clean multiple spaces to single spaces to prevent HTML innerText vs backend mismatch
    clean_filename = re.sub(r'\s+', ' ', file.filename)
    
    # Save permanently in uploads folder
    file_path = os.path.join(UPLOAD_DIR, clean_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    total_chunks = process_pdf(file_path)

    # Save metadata to SQLite
    try:
        cursor.execute("INSERT INTO uploaded_files (filename, filepath) VALUES (?, ?)", 
                       (clean_filename, file_path))
        conn.commit()
    except sqlite3.IntegrityError:
        pass # File already exists in DB

    return {
        "message": "PDF uploaded and indexed successfully",
        "chunks": total_chunks,
        "filename": clean_filename,
    }
@router.get("/files")
async def list_files():
    cursor.execute("SELECT filename FROM uploaded_files")
    files = [row[0] for row in cursor.fetchall()]
    return {"files": files}

@router.delete("/files")
async def delete_all_files():
    # 1. Clear SQLite DB
    cursor.execute("DELETE FROM uploaded_files")
    conn.commit()

    # 2. Clear Uploads Folder
    for filename in os.listdir(UPLOAD_DIR):
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except:
                pass

    # 3. Clear ChromaDB
    try:
        all_docs = vector_db.get()
        if all_docs and all_docs.get("ids"):
            vector_db.delete(ids=all_docs["ids"])
    except Exception as e:
        print(f"Error clearing ChromaDB: {e}")

    return {"message": "All documents cleared successfully"}
