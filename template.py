"""
template.py
-----------
Project scaffolding script for StudyRAG.
Run this once to create the complete folder and file structure.

Usage:
    python template.py

This script:
  - Creates all directories
  - Creates empty placeholder files
  - Skips files that already exist and have content
  - Safe to re-run at any time
"""

import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s]: %(message)s')

list_of_files = [

    # ── Backend: API 
    "backend/api/__init__.py",
    "backend/api/deps.py",
    "backend/api/routes/__init__.py",
    "backend/api/routes/auth.py",
    "backend/api/routes/chat.py",
    "backend/api/routes/documents.py",
    "backend/api/routes/health.py",
    "backend/api/routes/admin.py",

    # ── Backend: Core 
    "backend/core/__init__.py",
    "backend/core/config.py",
    "backend/core/exceptions.py",
    "backend/core/limiter.py",
    "backend/core/logger.py",
    "backend/core/security.py",

    # ── Backend: Database 
    "backend/db/__init__.py",
    "backend/db/crud.py",
    "backend/db/database.py",
    "backend/db/models.py",

    # ── Backend: RAG Pipeline
    "backend/rag/__init__.py",
    "backend/rag/chain.py",
    "backend/rag/embeddings.py",
    "backend/rag/ingestion.py",
    "backend/rag/reranker.py",
    "backend/rag/retriever.py",
    "backend/rag/tools.py",

    # ── Backend: Tests 
    "backend/tests/__init__.py",
    "backend/tests/conftest.py",
    "backend/tests/test_api_auth.py",
    "backend/tests/test_api_chat.py",
    "backend/tests/test_api_documents.py",
    "backend/tests/test_crud.py",
    "backend/tests/test_security.py",

    # ── Backend: Root files
    "backend/main.py",
    "backend/pytest.ini",
    "backend/requirements.txt",

    # ── Frontend: HTML pages 
    "frontend/index.html",
    "frontend/login.html",
    "frontend/admin.html",
    "frontend/privacy.html",
    "frontend/terms.html",

    # ── Frontend: CSS 
    "frontend/css/style.css",

    # ── Frontend: JavaScript 
    "frontend/js/app.js",
    "frontend/js/auth.js",
    "frontend/js/tools.js",

    # ── Data directories (gitkeep keeps them in git) 
    "logs/.gitkeep",
    "uploads/.gitkeep",
    "vectorstore/.gitkeep",

    # ── Root config files
    ".env.example",
    ".gitignore",
    ".dockerignore",
    "Dockerfile",
    "docker-compose.yml",
    "template.py",
    "checker_installLibrary.py",

    # ── GitHub documentation 
    "README.md",
    "DEPLOYMENT.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
]

for filepath in list_of_files:
    filepath = Path(filepath)
    filedir, filename = os.path.split(filepath)

    # Create directory if it doesn't exist
    if filedir != "":
        os.makedirs(filedir, exist_ok=True)
        logging.info(f"Creating directory: {filedir} for the file: {filename}")

    # Create empty file if it doesn't exist or is empty
    if (not os.path.exists(filepath)) or (os.path.getsize(filepath) == 0):
        with open(filepath, "w") as f:
            pass
        logging.info(f"Creating empty file: {filepath}")
    else:
        logging.info(f"Skipping (already exists): {filename}")

print("\n Project structure created successfully!")
print("Next steps:")
print("   1. Copy .env.example to .env and add your API keys")
print("   2. cd backend && pip install -r requirements.txt")
print("   3. uvicorn main:app --reload --port 8000")