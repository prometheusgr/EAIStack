# LLM Observability (Tracing)

**Status**: base tracing implemented (issue #4). Trace clustering/search
([#29](../../../issues/29)), evaluation hooks ([#30](../../../issues/30)),
and cost-per-span ([#31](../../../issues/31)) are deliberately out of scope
for this slice — see those issues.

## What's captured

Every chat agent run (`app.agents.chat_agent`) is traced as a tree: the
LangGraph run itself, each `call_agent`/LLM invocation, each tool call
(`search_knowledge_base`), and the routing decisions between them — with
latency (span start/end time), token counts (prompt/completion/total, read
from the LLM response's usage metadata), and the exact prompt and response
content for every LLM call.

**Verified by hand** (not assumed) by running a real LangGraph tool-call
turn through the instrumented agent and inspecting the captured spans via
Phoenix's own API:

```
LangGraph (CHAIN)
└─ call_agent (AGENT)
   └─ FakeChatModel (LLM)          <- first LLM call, returns a tool call
└─ call_tool (CHAIN)
   └─ fake_search (TOOL)
└─ call_agent (AGENT)
   └─ FakeChatModel (LLM)          <- second LLM call, returns the final answer
```

Node names are legible and match the actual LangGraph node/tool names from
the code (`call_agent`, `call_tool`, the tool's own name) — **not** generic
`RunnableSequence` spans, which was the least-certain part of this
integration going in. Each LLM span's attributes include the full input
message list (including the tool call and tool result that were fed back to
the model) and the full output message content, satisfying issue #4's
"click into any trace and see the exact prompt sent to llama-server, what
came back" requirement.

Token-count capture (`llm.token_count.prompt/completion/total`) was
confirmed to be a supported OpenInference span attribute, populated
automatically from `ChatOpenAI`'s (the real llama-server client's)
`usage_metadata` — the fake-provider smoke test above doesn't populate
token counts itself (`FakeChatModel` is a test double with no token
accounting), so this specific detail rests on standard LangChain/OpenAI SDK
behavior rather than a from-scratch observation. If you're validating this
slice locally with `--profile llm`, confirm real token counts appear on the
LLM span as an easy last check.

## How to view traces locally

```bash
# Optional: real chat provider, needed to exercise a real tool-call turn
# (FakeChatModel never emits a tool call at all)
TRACING_ENABLED=true docker-compose up --profile llm
```

or, with the default fake provider (still traces the agent graph, just
without a real tool call):

```bash
TRACING_ENABLED=true docker-compose up
```

Then open `http://localhost:6006`. Traces appear under the
`eaistack-chat-agent` project.

`TRACING_ENABLED` defaults to `false` — tracing is opt-in. When disabled,
`app.core.tracing.configure_tracing` never runs, so no `TracerProvider` or
OTLP exporter is ever constructed; this is also what every unit test and
every default `docker-compose up` gets.

## Design notes

- **Storage**: Phoenix keeps its own SQLite file on a dedicated
  `phoenix_data` volume, not the shared `eaistack` Postgres database. This
  repo's Postgres has no multi-database provisioning mechanism (a single
  `POSTGRES_DB`), and Phoenix's trace schema isn't part of this repo's
  Alembic-owned application schema — keeping it separate avoids inventing
  new DB-provisioning machinery for one consumer and keeps Alembic the sole
  authority over `eaistack`'s own schema.
- **Batching**: the OTel exporter is configured with `batch=True`
  (`BatchSpanProcessor`, not Phoenix's default `SimpleSpanProcessor`). This
  was found by hand, not assumed: the default synchronously exports (and
  retries) each span inline, which measurably blocked the request path for
  several seconds per span when Phoenix was unreachable. `BatchSpanProcessor`
  exports on a background thread, so a slow or down Phoenix instance cannot
  add latency to, or block, a live chat response — confirmed span creation
  drops to sub-millisecond with this setting even while Phoenix is
  unreachable.
- **Health check**: the vendored `arizephoenix/phoenix` image has no
  `curl`/`wget`/`which` binary (confirmed by hand — it's a from-scratch
  Python 3.13 image), so `docker-compose.yml`'s healthcheck uses
  `python3 -c "import urllib.request; ..."` instead of the `curl`-based
  healthcheck every other service in this file uses. `/healthz` on port
  `6006` returns `200` once the container is ready (confirmed against the
  real image).
- **Ports**: `6006` serves both the UI and the OTLP HTTP trace-ingest
  endpoint (`/v1/traces`); `4317` is OTLP gRPC ingest (published for parity,
  unused by the backend today, which exports over HTTP).

## Known gaps

### No retention policy yet — traces accumulate indefinitely

Every other persisted, content-bearing store in this repo has an explicit
retention window (see `docs/SECURITY.md`'s Data Retention Policy table) —
`conversation_threads` defaults to 24h, for example. **Trace data has no
such policy yet.** Traces capture the exact prompt and response content for
every chat turn, by design — the same sensitivity class as
`conversation_threads` — but currently accumulate forever in Phoenix's
`phoenix_data` volume with no purge mechanism.

This is deliberately out of scope for this slice (see
[#32](../../../issues/32)): Phoenix's trace store lives outside the
`eaistack` Postgres database this repo's `retention_sweep` owns and purges
via direct SQL `DELETE`, so purging traces needs a call into Phoenix's own
deletion surface instead — different enough machinery to warrant its own
issue rather than a guess in this one. #32 is prioritized to land
immediately after this slice, ahead of #29/#30/#31, precisely because this
gap starts accumulating sensitive data the moment `TRACING_ENABLED=true` is
first set. **Anyone enabling tracing before #32 ships should know this front
and understand it as an explicit, temporary gap, not an oversight.**

### No TLS on the Phoenix service yet (Helm/production path)

Every other Helm chart in `infra/helm/charts/` defaults `tls.enabled: true`
and terminates TLS itself (doc-search does this via its own
`docker-entrypoint.sh`, adding `--ssl-certfile`/`--ssl-keyfile` to its
`uvicorn` invocation). Phoenix is an unmodified upstream image — this repo
doesn't control its entrypoint the way it does doc-search's — and this
project is air-gapped, so this slice's implementation had no way to verify
whether the real vendored image supports native TLS termination without
guessing at flags/env vars that might not match. `infra/helm/charts/phoenix`
ships with `tls.enabled: false`, a deliberate, documented exception, not an
oversight. See [#33](../../../issues/33) for the follow-up: verify against
the real image, then either wire native TLS support in (if it exists) or
add a TLS-terminating sidecar.

Local `docker-compose` traffic to Phoenix is plaintext, same as every other
service in that file today — tracked generally by
[#17](../../../issues/17) (docker-compose TLS-by-default), which now also
covers the `phoenix` service.
