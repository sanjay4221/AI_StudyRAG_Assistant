"""
core/limiter.py
---------------
Centralized rate limiter using slowapi (built on limits library).

How slowapi works:
  1. A Limiter instance is created once here
  2. Attached to the FastAPI app in main.py
  3. Each route decorates with @limiter.limit("N/period")
  4. slowapi tracks requests by IP address (or custom key)
  5. When limit exceeded → HTTP 429 Too Many Requests

Rate limit strings:
  "5/minute"   → max 5 requests per minute per IP
  "100/hour"   → max 100 requests per hour per IP
  "1000/day"   → max 1000 requests per day per IP

Why per-IP and not per-user?
  - Auth endpoints are hit BEFORE we know who the user is
  - Per-IP is the standard defence for login/register brute force
  - For /chat we could do per-user-id later (enterprise upgrade)

Storage backend:
  We use in-memory storage (default) — fine for a single server.
  Enterprise upgrade: switch to Redis storage so limits persist
  across server restarts and work with multiple server instances.

Limits chosen for a student laptop / small deployment:
  /auth/register  →  5/minute   (prevent mass fake account creation)
  /auth/login     →  10/minute  (prevent password brute force)
  /upload         →  10/minute  (prevent storage flooding)
  /chat           →  30/minute  (generous for real students, blocks bots)
  /health         →  60/minute  (monitoring tools ping often)
  default         →  100/minute (all other endpoints)
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# get_remote_address extracts the client IP from the request
# In production behind a proxy, use get_real_ip instead
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    headers_enabled=False,  # disabled — avoids Response injection requirement
                            # in enterprise, enable this and add Response param to each route
)
