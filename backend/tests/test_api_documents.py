"""
tests/test_api_documents.py
----------------------------
API tests for document management endpoints.

What we test:
  POST /upload     → auth required, PDF only, file saved & indexed
  GET  /documents  → auth required, returns user's own docs only
  DELETE /reset    → auth required, clears only this user's docs

Note on mocking:
  We mock ingest_pdf() because it requires ChromaDB + embedding model
  which are heavy external dependencies. Unit tests should be fast
  and not require GPU/disk setup.
  The mock lets us verify the HTTP layer works correctly in isolation.
"""

import pytest
from unittest.mock import patch, MagicMock


# ── Upload ────────────────────────────────────────────────────────────────────

class TestUpload:

    def test_upload_requires_auth(self, client, sample_pdf):
        """Upload without token returns 403."""
        with open(sample_pdf, "rb") as f:
            r = client.post("/upload", files={"file": ("test.pdf", f, "application/pdf")})
        assert r.status_code == 403

    def test_upload_rejects_non_pdf(self, client, auth_headers, tmp_path):
        """Non-PDF files are rejected with 415."""
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("This is a text file")
        with open(txt_file, "rb") as f:
            r = client.post(
                "/upload",
                files={"file": ("notes.txt", f, "text/plain")},
                headers=auth_headers,
            )
        assert r.status_code == 415

    def test_upload_pdf_success(self, client, auth_headers, sample_pdf):
        """
        Valid PDF upload returns 200 with indexing stats.
        We mock ingest_pdf to avoid needing ChromaDB in tests.
        """
        mock_result = {"filename": "test_document.pdf", "pages": 1, "chunks": 3}

        with patch("api.routes.documents.ingest_pdf", return_value=mock_result), \
             patch("api.routes.documents.list_indexed_files", return_value=[]), \
             patch("main.reset_chain"):

            with open(sample_pdf, "rb") as f:
                r = client.post(
                    "/upload",
                    files={"file": ("test_document.pdf", f, "application/pdf")},
                    headers=auth_headers,
                )

        assert r.status_code == 200
        data = r.json()
        assert "indexed successfully" in data["message"]
        assert data["details"]["chunks"] == 3
        assert data["details"]["pages"] == 1


# ── Documents list ────────────────────────────────────────────────────────────

class TestDocumentsList:

    def test_list_requires_auth(self, client):
        """GET /documents without token returns 403."""
        r = client.get("/documents")
        assert r.status_code == 403

    def test_list_returns_empty_initially(self, client, auth_headers):
        """New user with no uploads gets empty list."""
        with patch("api.routes.documents.list_indexed_files", return_value=[]):
            r = client.get("/documents", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["documents"] == []
        assert r.json()["count"] == 0

    def test_list_returns_user_docs(self, client, auth_headers):
        """Returns only this user's documents."""
        with patch("api.routes.documents.list_indexed_files",
                   return_value=["lecture_notes.pdf", "textbook.pdf"]):
            r = client.get("/documents", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data["documents"]) == 2
        assert "lecture_notes.pdf" in data["documents"]


# ── Reset ──────────────────────────────────────────────────────────────────────

class TestReset:

    def test_reset_requires_auth(self, client):
        """DELETE /reset without token returns 403."""
        r = client.delete("/reset")
        assert r.status_code == 403

    def test_reset_clears_user_docs(self, client, auth_headers):
        """DELETE /reset returns success message."""
        with patch("api.routes.documents.clear_user_vectorstore"), \
             patch("main.reset_chain"), \
             patch("api.routes.documents._user_upload_dir") as mock_dir:

            mock_dir.return_value = MagicMock()
            mock_dir.return_value.glob.return_value = []

            r = client.delete("/reset", headers=auth_headers)

        assert r.status_code == 200
        assert "cleared" in r.json()["message"].lower()
