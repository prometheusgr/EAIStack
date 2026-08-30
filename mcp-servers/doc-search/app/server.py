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

import anyio.to_thread
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp

import app.db as app_db
from app.auth import TokenVerificationError, verify_bearer_token
from app.search import search_knowledge_base_with_sources as _search_knowledge_base_with_sources

_current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_user_id")

# Paths a Kubernetes/docker-compose health probe must be able to reach
# without a Keycloak token. Kept to exactly the synthetic liveness/readiness
# path — every other route, including the MCP endpoint itself, still goes
# through verify_bearer_token below. Exposing "the process is up" costs
# nothing security-wise; it reveals no data and no user identity.
UNAUTHENTICATED_PATHS = frozenset({"/healthz"})


async def healthz(request: Request) -> JSONResponse:
    """Liveness/readiness endpoint. Deliberately excluded from
    BearerTokenMiddleware (see UNAUTHENTICATED_PATHS) so kubelet's readiness
    probe gets a real 200 instead of the 401 every other route returns
    without a bearer token — kubelet only treats HTTP 200-399 as a passing
    probe, so a 401 here would keep this pod out of the Service's endpoints
    forever even though the process is healthy.
    """
    return JSONResponse({"status": "ok"})


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Verifies the Authorization header against Keycloak's JWKS on every
    request, independently of whatever the backend claims about the caller.
    Rejects before the request reaches MCP's tool dispatch.

    Exempts UNAUTHENTICATED_PATHS (currently just the health probe) from
    this check; every other path, including /mcp, is unaffected.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if request.url.path in UNAUTHENTICATED_PATHS:
            return await call_next(request)

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
    # The MCP SDK's DNS-rebinding protection validates the Host header
    # against an explicit allowlist -- a guard against a malicious webpage
    # in someone's browser making a request that lands on a server it
    # believes is same-origin. That threat model doesn't fully evaporate
    # just because this server is normally reached by the backend's
    # server-side HTTP client: docker-compose.yml publishes this port to the
    # host ("8100:8100", for curl/direct debugging), which also makes
    # http://localhost:8100 directly reachable from any browser tab. So the
    # fix is to allowlist every real Host value this server is legitimately
    # reached under, not to disable the check:
    #   - "doc-search:8100"            docker-compose service DNS name
    #   - "eaistack-doc-search"        K8s Service short name (in-namespace)
    #   - "eaistack-doc-search:8100"   K8s Service short name with port
    #   - "127.0.0.1"/"localhost"/"::1" (with wildcard port) local/dev access
    #     via the published host port -- these mirror FastMCP's own default
    #     allowlist for a localhost-bound server (see
    #     mcp.server.fastmcp.server.FastMCP.__init__), which we must restate
    #     explicitly here because supplying our own TransportSecuritySettings
    #     replaces that default rather than extending it (confirmed against
    #     mcp.server.transport_security.TransportSecurityMiddleware._validate_host,
    #     which only ever consults self.settings.allowed_hosts).
    # allowed_hosts supports a ":*" suffix to match any port for a given
    # host (see _validate_host's wildcard-port branch), which is why the
    # docker-compose/K8s entries below are listed both bare and with the
    # concrete port: DNS-name Host headers are sent with the port already
    # attached by an HTTP client talking to a non-default port, but the
    # wildcard form keeps this working if the port ever changes.
    mcp = FastMCP(
        name="doc-search",
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                "doc-search",
                "doc-search:*",
                "eaistack-doc-search",
                "eaistack-doc-search:*",
                "127.0.0.1",
                "127.0.0.1:*",
                "localhost",
                "localhost:*",
                "[::1]",
                "[::1]:*",
            ],
        ),
    )

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
    async def search_knowledge_base(query: str, top_k: int = 5) -> CallToolResult:
        """Search the calling user's knowledge base.

        user_id is never a parameter here — it comes only from the verified
        token the BearerTokenMiddleware already checked for this request,
        mirroring the same closure-binding guarantee
        backend/app/agents/tools.py relied on before this was a separate
        service: the model (or an MCP client) can never supply user_id.

        FastMCP's tool dispatch calls a sync tool function directly on the
        request's own async task (no thread offload of its own — unlike
        LangChain's tool-calling layer on the backend side), so the blocking
        SQLAlchemy queries and (for the llama-cpp embedding provider) the
        synchronous httpx call inside _search_knowledge_base_with_sources
        would otherwise block this server's single ASGI event loop for every
        concurrent request. anyio.to_thread.run_sync moves that blocking work
        onto a worker thread, matching how any other blocking-I/O call is
        bridged into async code in this codebase (see
        backend/app/agents/checkpointer.py's a* methods for the same
        pattern).

        Returns a CallToolResult built by hand, rather than a bare str,
        so the tool result carries structuredContent (each matching
        document's knowledge_base_id/title/heading_path, for issue #19)
        alongside the unchanged prose text block the LLM reads. Returning
        CallToolResult directly (rather than a Pydantic model) opts out of
        FastMCP's automatic content conversion, which would otherwise
        replace the hand-formatted prose text block with a JSON dump of the
        return value — see mcp.server.fastmcp.utilities.func_metadata.
        FuncMetadata.convert_result's isinstance(result, CallToolResult)
        branch, which returns such a result unmodified.
        """
        user_id = _current_user_id.get()

        def run_search():
            db = app_db.SessionLocal()
            try:
                return _search_knowledge_base_with_sources(
                    db, user_id=user_id, query=query, top_k=top_k
                )
            finally:
                db.close()

        result = await anyio.to_thread.run_sync(run_search)

        return CallToolResult(
            content=[TextContent(type="text", text=result.text)],
            structuredContent={
                "sources": [
                    {
                        "knowledge_base_id": source.knowledge_base_id,
                        "title": source.title,
                        "heading_path": source.heading_path,
                    }
                    for source in result.sources
                ]
            },
        )

    return mcp


def build_app() -> Starlette:
    """Build the Streamable HTTP ASGI app, wrapped with bearer-token verification."""
    mcp = _build_mcp()
    inner_app = mcp.streamable_http_app()
    inner_app.router.routes.insert(0, Route("/healthz", healthz, methods=["GET"]))
    inner_app.user_middleware.insert(0, Middleware(BearerTokenMiddleware))
    return inner_app
