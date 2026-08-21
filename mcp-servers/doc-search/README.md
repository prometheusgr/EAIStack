# doc-search

Standalone MCP server exposing pgvector-backed knowledge base search
(`search_knowledge_base`) as an MCP tool over **Streamable HTTP**, so it
can run as its own K8s pod rather than in-process in the backend. See
[docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md)'s "MCP Transport" section
for why Streamable HTTP (not stdio) is a hard requirement.

## Security model

This service is reached over the network — by the backend today, and
potentially other callers in the future — so it never trusts a bare
`user_id` handed to it by a caller. Every tool call must carry a Keycloak
access token as a `Bearer` header; a Starlette middleware
(`app/server.py::BearerTokenMiddleware`) independently verifies that token
against Keycloak's JWKS (`app/auth.py`, mirroring
`backend/app/core/auth.py`'s verification logic) before the request ever
reaches the MCP tool dispatch. The verified `sub` claim, not any
caller-supplied value, is what scopes the search.

## Schema ownership

Alembic in `backend/` remains the sole schema authority for
`knowledge_base`, `embeddings`, and `system_settings`. `app/models.py` is a
read-mostly mirror of those tables (column-for-column) — this service never
runs migrations and never writes to any of them; it only reads.

## Local development

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Testing (all tests here need real Postgres via testcontainers)
pytest tests/ -m "unit or integration" -v

# Run standalone (requires DATABASE_URL and KEYCLOAK_URL to point at real services)
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/eaistack` | Same Postgres instance the backend uses |
| `KEYCLOAK_URL` | `http://localhost:8080` | JWKS fetched from `{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs` |
| `KEYCLOAK_REALM` | `eaistack` | |
| `KEYCLOAK_CLIENT_ID` | `eaistack-api` | Accepted token audience (service-to-service) |
| `KEYCLOAK_WEB_CLIENT_ID` | `eaistack-web` | Accepted token audience (forwarded user session) |
| `EMBEDDING_PROVIDER` | `fake` | `fake` \| `llama-cpp` — must match the backend's env default; an admin's runtime override in the Settings screen (stored in `system_settings`) wins over this for both services identically |
| `EMBEDDING_URL` | `http://localhost:8002/v1` | |
| `EMBEDDING_MODEL` | `nomic-embed-text-v1.5.Q4_K_M.gguf` | |

## Why doc-search generates its own query embeddings

`search_knowledge_base` takes a natural-language `query`, not a
pre-computed vector — this service resolves the embedding provider itself
(reading the same `system_settings` row the backend's indexing path
reads) and calls the same standalone embedding-server pod the backend
uses. Both services independently depend on that shared infrastructure,
not on each other's process — the same relationship this service already
has with Keycloak's JWKS endpoint.
