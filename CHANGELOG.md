# Changelog — StudyRAG

All notable changes to this project are documented here.

---

## [Phase 10] — Azure Cloud Deployment + PostgreSQL
- Deployed to Azure Container Apps (australiaeast region)
- Migrated database from SQLite to Neon PostgreSQL (free tier)
- Configured `DATABASE_URL` environment variable for cloud/local switching
- Added `psycopg2-binary` to requirements
- Fixed ChromaDB path to use local `/tmp` (avoids Azure Files SMB locking)
- Added `VECTORSTORE_DIR`, `UPLOAD_DIR`, `LOG_DIR` env var overrides in config
- Set min replicas = 0 (scale to zero), max replicas = 1
- Containerised with Docker and pushed to Azure Container Registry

---

## [Phase 8] — pytest Unit Tests
- 45 tests across 5 test files
- In-memory SQLite per test (never touches real DB)
- Mocked Groq API (tests don't call external services)
- `test_security.py` — 14 tests (password hashing + JWT)
- `test_crud.py` — 18 tests (DB operations)
- `test_api_auth.py` — 15 tests (register/login/me endpoints)
- `test_api_documents.py` — 6 tests (upload/list/reset)
- `test_api_chat.py` — 10 tests (chat/sessions)

---

## [Phase 7] — Admin Dashboard
- `is_admin` flag on User model
- `/admin` page — see all users, docs, sessions, messages
- Promote/demote admin, activate/deactivate accounts
- Delete user + all their data (cascade)
- Global platform stats (users, sessions, messages)

---

## [Phase 6] — Rate Limiting
- `slowapi` library — decorator per endpoint
- `/auth/register` → 5/minute (prevent fake accounts)
- `/auth/login` → 10/minute (prevent brute force)
- `/upload` → 10/minute (prevent storage flooding)
- `/chat` → 30/minute (generous for students, blocks bots)

---

## [Phase 5] — Streaming Responses
- Groq streams tokens one by one (`stream=True`)
- Server-Sent Events (SSE) → browser reads token by token
- Words appear as typed — ChatGPT typewriter effect
- Sources + model badge added after stream completes

---

## [Phase 4] — Per-User Document Spaces
- Each user gets a private ChromaDB collection (`user_1_docs`, `user_2_docs`)
- Uploads go to `uploads/user_1/` subfolder
- Clear docs → deletes ONLY this user's collection
- Other users completely unaffected

---

## [Phase 3] — Auth + Chat History
- JWT authentication (register → token → protected routes)
- SQLite/PostgreSQL database (users, sessions, messages)
- Chat history sidebar (all past sessions saved and reloadable)
- Login page (`login.html` → redirects to `/chat`)

---

## [Phase 2] — Proper Engineering Structure
- Layered folder architecture (core / rag / api / db)
- Centralized rotating logger (logs/app.log, 5MB × 3 backups)
- Custom exception hierarchy (6 typed exceptions)
- Single config file (core/config.py — all env vars)

---

## [Phase 1] — Simple RAG Foundation
- PDF upload → chunking → embedding → ChromaDB vector store
- Question → similarity search → top-4 chunks → Groq LLM → answer
- Basic frontend (upload zone + chat bubbles)

---

## Study Tools Added
- **Quiz Generator** — MCQ questions from document content
- **Document Summariser** — structured summary with key concepts
- **Follow-up Suggester** — 3 related questions after each answer
- **Confidence Scorer** — how well the answer is grounded in docs
- **Cross-Encoder Reranker** — `cross-encoder/ms-marco-MiniLM-L-6-v2`
