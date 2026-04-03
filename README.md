# StudyRAG — AI Study Assistant

> Upload any PDF. Ask anything. Get answers grounded in your own documents.

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-blue?logo=postgresql)](https://neon.tech)
[![Azure](https://img.shields.io/badge/Azure-Container%20Apps-0078D4?logo=microsoftazure)](https://azure.microsoft.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 🌐 Live Demo

**[https://studyrag-app.prouddune-47b5fd2b.australiaeast.azurecontainerapps.io](https://studyrag-app.prouddune-47b5fd2b.australiaeast.azurecontainerapps.io)**

Register a free account → Upload a PDF → Start asking questions.

---

## What is StudyRAG?

StudyRAG is a production-grade **Retrieval-Augmented Generation (RAG)** web application where students upload PDF documents and chat with the content in real time using AI.

Instead of reading 200 pages, just ask:
- *"What are the key concepts in Chapter 3?"*
- *"Explain the difference between X and Y"*
- *"Give me 10 quiz questions on this topic"*
- *"Summarise this document for my exam"*

The AI answers **only from your uploaded documents** — no hallucinations, with sources cited.

---

## Features

### Core RAG Pipeline
- **PDF Upload** → text extraction → chunking → embedding → vector storage
- **Semantic Search** — finds the most relevant chunks using cosine similarity
- **Cross-Encoder Reranking** — re-scores top candidates for higher precision
- **Streaming Responses** — tokens appear word-by-word like ChatGPT
- **Source Citations** — every answer shows which part of your document it came from

### Study Tools
- **Quiz Generator** — auto-generates MCQ questions from your documents
- **Document Summariser** — key concepts, definitions, and exam topics
- **Follow-up Suggester** — 3 related questions after every answer
- **Confidence Scorer** — shows how well the answer is grounded in your docs

### Platform
- **JWT Authentication** — secure register/login with 8-hour sessions
- **Per-User Document Spaces** — each user's PDFs are completely private
- **Chat History** — all sessions saved and reloadable from sidebar
- **Admin Dashboard** — manage users, view stats, promote/demote admins
- **Rate Limiting** — prevents abuse (register: 5/min, chat: 30/min)
- **45 Unit Tests** — across auth, CRUD, documents, and chat endpoints

---

## Architecture

```
Refer below diagram -
..\student-rag\Documents\StudyRAG-Architectures.png
..\student-rag\Documents\Study_RAG_UI.pdf
```

### RAG Pipeline

```
UPLOAD PHASE
────────────────────────────────────────
PDF → PyPDFLoader → TextSplitter (800 chars, 100 overlap)
    → MiniLM embeddings (384-dim) → ChromaDB (per-user collection)

CHAT PHASE
────────────────────────────────────────
Question → MiniLM embedding → ChromaDB (top 10 chunks)
         → CrossEncoder reranker (keep top 4)
         → Groq LLaMA (stream=True)
         → SSE → Browser (typewriter effect)
         → PostgreSQL (save full answer + sources)
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Web Framework | FastAPI | REST API + SSE streaming |
| LLM | Groq (LLaMA 3.1/3.3) | Answer generation |
| Embeddings | HuggingFace MiniLM-L6-v2 | Text → 384-dim vectors (local, free) |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 | Precision re-scoring |
| Vector Store | ChromaDB | Semantic similarity search |
| Database | PostgreSQL (Neon) | Users, sessions, messages |
| Auth | JWT (python-jose) | Stateless authentication |
| Password | bcrypt | Secure password hashing |
| Rate Limiting | slowapi | Prevent API abuse |
| Testing | pytest + httpx | 45 unit + integration tests |
| Frontend | Vanilla JS + SSE | No framework needed |
| Container | Docker | Portable deployment |
| Cloud | Azure Container Apps | Production hosting |

---

## Project Structure

```
..\student-rag\Documents\Project_Structure.png
..\student-rag\Documents\SProject_Structure.html
```
---

##  Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- [Groq API key](https://console.groq.com) (free)

### 1. Clone and setup

```bash
git clone https://github.com/sanjay4221/AI_StudyRAG_Assistant.git
cd studyrag
```

### 2. Create virtual environment

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
# Copy the example env file
cp .env.example .env

# Edit .env and add your keys
GROQ_API_KEY=gsk_your_key_here
JWT_SECRET_KEY=your_random_secret_here
```

### 5. Run the app

```bash
uvicorn main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000)

---

## 🐳 Docker (Local)

```bash
# Build and run with docker-compose
docker-compose up --build

# App available at http://localhost:8000
```

---

##  Running Tests

```bash
cd backend
pytest                          # all 45 tests
pytest -v                       # verbose
pytest tests/test_security.py   # one file
pytest -k "test_login"          # by name
pytest --tb=long                # full tracebacks
```

---

## ☁️ Cloud Deployment (Azure)

See [DEPLOYMENT.md](DEPLOYMENT.md) for the complete step-by-step Azure deployment guide covering:
- Azure Container Registry setup
- Docker build and push
- Azure Container Apps environment
- Neon PostgreSQL integration
- Persistent storage configuration
- Environment variables reference

---

##  Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Your Groq API key from console.groq.com |
| `JWT_SECRET_KEY` | Yes | Random secret for JWT signing (keep fixed in production) |
| `DATABASE_URL` | Cloud only | PostgreSQL connection string (Neon or other) |
| `DATA_DIR` | Cloud only | Base directory for data storage (default: project root) |
| `UPLOAD_DIR` | Optional | Override upload directory path |
| `VECTORSTORE_DIR` | Optional | Override ChromaDB directory path |
| `LOG_DIR` | Optional | Override logs directory path |

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/register` | No | Create account |
| POST | `/auth/login` | No | Get JWT token |
| GET | `/auth/me` | Yes | Current user info |
| POST | `/upload` | Yes | Upload PDF |
| GET | `/documents` | Yes | List uploaded docs |
| DELETE | `/reset` | Yes | Clear all docs |
| POST | `/chat` | Yes | Chat (SSE stream) |
| GET | `/sessions` | Yes | Chat history |
| GET | `/health` | No | Health check |
| GET | `/admin/users` | Admin | All users |
| GET | `/admin/stats` | Admin | Platform stats |

Full API docs available at `/docs` (Swagger UI) when running locally.

---

##  Roadmap

- [x] Phase 1 — Simple RAG Foundation
- [x] Phase 2 — Proper Engineering Structure
- [x] Phase 3 — Auth + Chat History
- [x] Phase 4 — Per-User Document Spaces
- [x] Phase 5 — Streaming Responses
- [x] Phase 6 — Rate Limiting
- [x] Phase 7 — Admin Dashboard
- [x] Phase 8 — pytest Unit Tests
- [x] Phase 9 — Azure Cloud Deployment
- [x] Phase 10 — PostgreSQL (Neon) Integration
- [ ] Phase 11 — Pinecone/Qdrant for scalable vector storage
- [ ] Phase 12 — Multi-document support per session
- [ ] Phase 13 — Mobile-responsive UI
- [ ] Phase 14 — OAuth (Google login)

---

##  Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Author

Built with love as a learning project to explore RAG, FastAPI, and cloud deployment.

*Feedback and suggestions welcome — open an issue or reach out directly.*
