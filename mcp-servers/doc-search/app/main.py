"""ASGI entrypoint: `uvicorn app.main:app`.

Separate from app/server.py's build_app() so the module-level `app` object
uses settings resolved at process start (env vars / .env), matching how
backend/app/main.py is the thin entrypoint over its own app package.
"""

from app.server import build_app

app = build_app()
