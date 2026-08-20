# Real LLM Setup (llama.cpp)

By default EAIStack runs against `FakeChatModel`, a canned-response stub used by the
unit tests. This guide switches local development over to real inference via
`llama-server`, the OpenAI-compatible server bundled with llama.cpp.

Unit tests are unaffected by everything here — they mock at the
`app.core.llm_client` boundary and always use the fake model.

## Prerequisites

- Docker and Docker Compose
- ~5 GB free disk space for the model
- ~8 GB RAM (16 GB recommended)

CPU-only inference on a 7B model takes roughly **5–15 seconds per response**. That
is expected, not a bug.

## 1. Download a model

From the repository root:

```bash
mkdir -p models
curl -L --fail -o models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf \
  "https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
```

This is Meta Llama 3.1 8B Instruct at Q4_K_M quantization (~4.9 GB). It's the
default because it has llama.cpp's *native* tool-calling template support — see
[Tool-calling support](#tool-calling-support) below for why that matters and what
else was tried.

To use a different model, change the filename in **both** `docker-compose.yml`
(the `-m` flag on `llama-server`) and `LLM_MODEL` in your `.env.local`. The two
must match.

## 2. Configure the backend

```bash
cp .env.local.example .env.local
```

The defaults in that file are already correct for the compose setup. The variable
that actually flips behavior is:

```bash
LLM_PROVIDER=llama-cpp   # "fake" uses the mocked model
```

Note that `LLM_URL` **must** end in `/v1`. The OpenAI-compatible client appends
paths like `/chat/completions` to it; without the suffix every request 404s.

## 3. Start the stack

```bash
docker compose --profile llm up -d
```

`llama-server` only starts with `--profile llm`, so the default
`docker compose up` stays fast and needs no model file.

Loading the weights takes ~30 seconds. Wait for readiness:

```bash
curl -f http://localhost:8000/health
```

## 4. Verify inference

Hit `llama-server` directly, bypassing the backend:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
       "messages": [{"role": "user", "content": "What is the capital of France?"}]}'
```

A real answer mentioning Paris confirms the model is live.

Then verify the backend is actually routed to it:

```bash
docker compose exec backend env | grep LLM_PROVIDER   # expect: llama-cpp
```

If this still prints `fake`, the backend picked up stale environment — recreate it
with `docker compose --profile llm up -d --force-recreate backend`.

## Ports

| Service | Host port | In-cluster address |
|---|---|---|
| `llama-server` | 8000 | `http://llama-server:8000` |
| `backend` | **8001** | `http://backend:8000` |
| `keycloak` | 8080 | `http://keycloak:8080` |
| `frontend` | 3000 | — |

The backend is published on **8001**, not 8000 — `llama-server` occupies 8000 on the
host. If you run `uvicorn` directly instead of in compose, give it an explicit
non-conflicting port and point `LLM_URL` at `http://localhost:8000/v1`:

```bash
uvicorn app.main:app --reload --port 8001
```

## Reverting to the mock

```bash
# In .env.local
LLM_PROVIDER=fake
```

Then `docker compose up -d --force-recreate backend`. No code changes are needed;
the provider switch is the only thing that selects the client.

## Troubleshooting

**Container exits immediately.** The model file is missing or the filename doesn't
match the `-m` flag. Check `docker compose --profile llm logs llama-server` and
confirm `ls models/`.

**Connection refused from the backend.** `llama-server` binds loopback unless
started with `--host 0.0.0.0`; the compose command sets this. If you run it
manually, pass the flag.

**Timeouts.** CPU inference on a long prompt can exceed the default. Raise
`LLM_TIMEOUT` in `.env.local` to 180 or more.

**Out of memory.** Use a smaller or more aggressively quantized model — a 3B model,
or Q4 instead of Q6. Lowering `--ctx-size` in `docker-compose.yml` also reduces the
memory footprint.

**Responses are still the canned fake string.** `LLM_PROVIDER` is not reaching the
backend process. Verify with the `docker compose exec` check in step 4.

## Tool-calling support

The chat agent (`app/agents/chat_agent.py`) binds a `search_knowledge_base` tool
to the LLM via `bind_tools` and expects the model to emit `tool_calls`, not just
prose. Not every GGUF chat template supports this, and llama.cpp needs the
`--jinja` flag (already set in `docker-compose.yml`) to use a template's native
tool-calling format at all. This was tested directly against `llama-server`,
outside the test suite (which always uses `FakeChatModel` and never depends on
this).

### Models tested

| Model | Native tool_calls via `--jinja`? | Notes |
|---|---|---|
| Mistral 7B Instruct v0.2 (Q4_K_M) | **No** | `bind_tools(...).invoke(...)` always returns `tool_calls: []`, even with `--jinja`. The v0.2 chat template has no tool-call syntax. The model instead answers in prose, confidently and plausibly, with no indication it should have deferred to a tool. This is the failure mode CLAUDE.md's "known rough edge" note refers to — it fails silently, not loudly. |
| **Meta Llama 3.1 8B Instruct (Q4_K_M), `bartowski/Meta-Llama-3.1-8B-Instruct-GGUF`** | **Yes** | Current default. Emits real `tool_calls` out of the box with just `--jinja` — no `--chat-template-file` override needed, unlike Hermes-family models, which use an XML-tagged `<tool_call>` format that needs an external template file most quantizers don't bundle in the GGUF. |

Hermes 2/3 Pro (also acceptable under the no-Chinese-origin constraint) was not
downloaded or tested — Llama 3.1 8B Instruct's *native*, no-extra-file template
support was preferred for a smaller air-gap vendoring footprint (one file, no
companion Jinja template to also mirror into the offline model bundle).

**Follow-up to try**: `Llama-3-Groq-8B-Tool-Use` (Groq/Meta-Llama-3-based,
purpose-tuned for tool calling) — not yet evaluated, noted for a future pass.

### What "working" looks like

With Llama 3.1 8B Instruct, a question that can only be answered from a seeded
knowledge-base document produces a message trace like:

```
HumanMessage:  "What snack does the office serve on Friday afternoons?"
AIMessage:     tool_calls=[{"name": "search_knowledge_base", "args": {"query": "..."}}]
ToolMessage:   "Title: EAIStack Office Snack Policy\n...verbatim seeded content..."
AIMessage:     "According to the EAIStack Office Snack Policy, the office serves ..."
```

The final answer contains facts only present in the seeded document (verified
manually; there's no automated end-to-end test against a real model — the graph
logic itself is covered by `tests/unit/test_chat_agent.py` against
`FakeChatModel` with scripted tool-call responses).

### Verification command

From inside the `backend` container, with `LLM_PROVIDER=llama-cpp` and a
knowledge-base document seeded for some `user_id`:

```python
from app.db.database import SessionLocal
from app.agents.chat_agent import create_chat_agent
from langchain_core.messages import HumanMessage

db = SessionLocal()
agent = create_chat_agent(db=db, user_id="<seeded-user-id>")
result = agent.invoke({
    "messages": [HumanMessage(content="<a question only the seeded doc can answer>")],
    "thread_id": "verify",
    "user_id": "<seeded-user-id>",
})
for m in result["messages"]:
    print(type(m).__name__, getattr(m, "tool_calls", None), m.content[:200])
```

Look for an `AIMessage` with a non-empty `tool_calls` list, a `ToolMessage`
containing the seeded document's content, and a final `AIMessage` whose answer
reflects that content.

### Two follow-up findings from live testing (not blockers, but worth knowing)

- **Without a system prompt, Llama 3.1 8B sometimes describes the tool call
  instead of answering from its result** — e.g. "This response is a JSON object
  with the function name and its parameters..." instead of the actual answer.
  `chat_agent.py` now prepends a short `SystemMessage` (`SYSTEM_PROMPT` in that
  file) on every `call_agent` invocation specifically to prevent this. This was
  necessary for reliable grounding, not optional polish.
- **The model can be tool-happy**: with only one tool available, it sometimes
  calls `search_knowledge_base` even for questions the tool can't help with
  (e.g. "What is 7 times 8?"). It still answered correctly in testing, and the
  `MAX_TOOL_CALL_ROUNDS` guard in `chat_agent.py` bounds the worst case, but this
  is a real behavior to be aware of, not a bug in the graph.

### Retrieval quality caveat

Retrieval quality is limited by `generate_embedding` (`app/services/embedding_service.py`),
which is a **deterministic mock** (seeded RNG over the query text), not a real
embedding model — this is intentional for Phase 3a (keeps tests deterministic)
and is a known Phase 4 item. If a live query returns weak or irrelevant matches,
that's the mock embedding, not a tool-calling failure — the pgvector ranking and
tool-call plumbing around it are real.

## Air-gapped deployment

Downloading from Hugging Face is a local-development convenience only. For
air-gapped targets the model must be vendored into the image at build time or
mounted from a pre-seeded volume — there is no network at runtime. See
[AIRGAP_SETUP.md](AIRGAP_SETUP.md).
