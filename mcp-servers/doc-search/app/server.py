"""FastMCP app exposing search_knowledge_base over Streamable HTTP.

Transport is Streamable HTTP, not stdio — a hard constraint (see
CLAUDE.md/AGENTS.md's MCP transport note): this server runs as its own K8s
pod, reached over the network by the backend, not spawned as a co-located
subprocess.

Every call must carry a Keycloak access token; a small Starlette middleware
verifies it (via app.auth.verify_bearer_token) before the request ever
reaches MCP's tool dispatch, and rejects with 401 if verification fails.
The verified user_id is handed to the tool via a contextvar set by the
middleware — this server never trusts a user_id supplied any other way
(never a tool argument, never a header taken at face value).
"""

import contextvars

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

import app.db as app_db
from app.auth import TokenVerificationError, verify_bearer_token
from app.search import search_knowledge_base as _search_knowledge_base

_current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_user_id")


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Verifies the Authorization header against Keycloak's JWKS on every
    request, independently of whatever the backend claims about the caller.
    Rejects before the request reaches MCP's tool dispatch.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return JSONResponse({"error": "Missing bearer token"}, status_code=401)

        token = auth_header[len("bearer ") :].strip()
        try:
            user_id = await verify_bearer_token(token)
        except TokenVerificationError as e:
            return JSONResponse({"error": f"Invalid token: {e}"}, status_code=401)

        context_token = _current_user_id.set(user_id)
        try:
            return await call_next(request)
        finally:
            _current_user_id.reset(context_token)


def _build_mcp() -> FastMCP:
    mcp = FastMCP(name="doc-search", stateless_http=True)

    @mcp.tool(
        name="search_knowledge_base",
        description=(
            "Search the user's personal knowledge base for documents relevant to a "
            "query. Use this whenever answering the question requires specific facts, "
            "policies, or content that may have been uploaded by the user rather than "
            "general knowledge. Returns the title and a content excerpt for each "
            "matching document, or a message saying nothing matched."
        ),
    )
    def search_knowledge_base(query: str, top_k: int = 5) -> str:
        """Search the calling user's knowledge base.

        user_id is never a parameter here — it comes only from the verified
        token the BearerTokenMiddleware already checked for this request,
        mirroring the same closure-binding guarantee
        backend/app/agents/tools.py relied on before this was a separate
        service: the model (or an MCP client) can never supply user_id.
        """
        user_id = _current_user_id.get()
        db = app_db.SessionLocal()
        try:
            return _search_knowledge_base(db, user_id=user_id, query=query, top_k=top_k)
        finally:
            db.close()

    return mcp


def build_app() -> Starlette:
    """Build the Streamable HTTP ASGI app, wrapped with bearer-token verification."""
    mcp = _build_mcp()
    inner_app = mcp.streamable_http_app()
    inner_app.user_middleware.insert(0, Middleware(BearerTokenMiddleware))
    return inner_app
