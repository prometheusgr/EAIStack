"""Rate-limiting primitives: pure token-bucket math, no DB/IO.

Mirrors app.guardrails' package shape -- submodules are imported directly
by callers (see app.services.rate_limiter_service), no re-export surface
here.
"""
