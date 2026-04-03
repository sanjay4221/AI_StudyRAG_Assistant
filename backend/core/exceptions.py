"""
core/exceptions.py
------------------
Custom exception hierarchy for the RAG application.

Why a custom hierarchy?
  - Catching `Exception` everywhere is lazy and hides bugs.
  - With typed exceptions, each layer of the app can catch ONLY what it owns
    and let everything else bubble up to a top-level handler.
  - FastAPI's exception handlers map each type to the right HTTP status code,
    so your API always returns meaningful errors to the frontend.
  - When we go enterprise, we can add error codes, i18n messages, and
    structured error payloads here without touching any other file.

Hierarchy (read top → bottom = general → specific):

    StudyRAGError                  ← base for ALL custom errors
    ├── ConfigurationError         ← missing env vars, bad settings
    ├── VectorStoreError           ← ChromaDB read/write failures
    │   └── VectorStoreEmptyError  ← no documents indexed yet
    ├── IngestionError             ← PDF load / chunk / embed failures
    │   └── UnsupportedFileError   ← wrong file type
    └── LLMError                   ← Groq API / chain failures
        └── LLMRateLimitError      ← 429 from Groq free tier
"""


# ── Base ──────────────────────────────────────────────────────────────────────
class StudyRAGError(Exception):
    """
    Base exception for all application errors.
    Carry an optional human-readable message and HTTP status hint.
    """
    def __init__(self, message: str = "An unexpected error occurred.", status_code: int = 500):
        super().__init__(message)
        self.message     = message
        self.status_code = status_code

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(status={self.status_code}, msg={self.message!r})"


# ── Config layer ──────────────────────────────────────────────────────────────
class ConfigurationError(StudyRAGError):
    """
    Raised when required configuration (env vars, settings) is missing or invalid.
    Fail fast at startup — don't let the app limp along with bad config.

    Example:
        if not os.environ.get("GROQ_API_KEY"):
            raise ConfigurationError("GROQ_API_KEY is not set in .env")
    """
    def __init__(self, message: str = "Application is misconfigured."):
        super().__init__(message, status_code=500)


# ── Vector store layer ─────────────────────────────────────────────────────────
class VectorStoreError(StudyRAGError):
    """
    Raised when ChromaDB operations fail (read, write, delete).

    Example:
        raise VectorStoreError("Failed to persist embeddings to disk.")
    """
    def __init__(self, message: str = "Vector store operation failed."):
        super().__init__(message, status_code=500)


class VectorStoreEmptyError(VectorStoreError):
    """
    Raised when the user asks a question but no PDFs have been indexed yet.
    Maps to HTTP 400 — it's a client mistake, not a server crash.

    Example:
        if not list_indexed_files():
            raise VectorStoreEmptyError()
    """
    def __init__(self, message: str = "No documents indexed yet. Please upload a PDF first."):
        # Call grandparent StudyRAGError directly to override status_code
        StudyRAGError.__init__(self, message, status_code=400)


# ── Ingestion layer ───────────────────────────────────────────────────────────
class IngestionError(StudyRAGError):
    """
    Raised when PDF loading, splitting, or embedding fails.

    Example:
        raise IngestionError(f"Could not parse '{filename}'. It may be corrupted.")
    """
    def __init__(self, message: str = "Failed to ingest document."):
        super().__init__(message, status_code=422)


class UnsupportedFileError(IngestionError):
    """
    Raised when a non-PDF file is uploaded.
    HTTP 415 = Unsupported Media Type.

    Example:
        raise UnsupportedFileError("Only PDF files are supported. Got: .docx")
    """
    def __init__(self, message: str = "Unsupported file type. Only PDF files are accepted."):
        StudyRAGError.__init__(self, message, status_code=415)


# ── LLM layer ─────────────────────────────────────────────────────────────────
class LLMError(StudyRAGError):
    """
    Raised when the Groq API call or LangChain chain execution fails.

    Example:
        raise LLMError("Groq returned an empty response.")
    """
    def __init__(self, message: str = "LLM inference failed."):
        super().__init__(message, status_code=502)   # 502 = Bad Gateway (upstream failed)


class LLMRateLimitError(LLMError):
    """
    Raised when Groq free-tier rate limit (429) is hit.
    HTTP 429 = Too Many Requests — client should back off and retry.

    Example:
        raise LLMRateLimitError("Groq free tier limit reached. Wait 60 seconds.")
    """
    def __init__(self, message: str = "Rate limit reached. Please wait a moment and try again."):
        StudyRAGError.__init__(self, message, status_code=429)


# ── Auth layer ────────────────────────────────────────────────────────────────
class AuthError(StudyRAGError):
    """
    Raised for any authentication or authorisation failure:
      - Invalid or expired JWT token
      - Wrong password
      - Token missing from request

    HTTP 401 = Unauthorized — client must log in first.

    Example:
        raise AuthError("Token is invalid or expired. Please log in again.")
    """
    def __init__(self, message: str = "Authentication failed. Please log in."):
        super().__init__(message, status_code=401)


class UserAlreadyExistsError(StudyRAGError):
    """
    Raised when a student tries to register with an email already in use.
    HTTP 409 = Conflict.

    Example:
        raise UserAlreadyExistsError("An account with this email already exists.")
    """
    def __init__(self, message: str = "An account with this email already exists."):
        super().__init__(message, status_code=409)
