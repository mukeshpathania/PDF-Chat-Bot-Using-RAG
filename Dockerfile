# ── Base Image ────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# ── System Dependencies ───────────────────────────────────────────────────────
# gcc/g++ needed to compile some Python packages (e.g. chromadb, hnswlib)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# ── Working Directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Install Python Dependencies ───────────────────────────────────────────────
# Copy requirements first for better Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Copy Application Code ─────────────────────────────────────────────────────
COPY . .

# ── Create Required Runtime Directories ──────────────────────────────────────
# These are created at build time so the app starts without errors
RUN mkdir -p uploads chroma_db db

# ── Expose Port ───────────────────────────────────────────────────────────────
# Hugging Face Spaces requires port 7860
EXPOSE 7860

# ── Launch Server ─────────────────────────────────────────────────────────────
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
