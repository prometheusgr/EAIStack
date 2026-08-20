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
curl -L --fail -o models/mistral-7b-instruct-v0.2.Q4_K_M.gguf \
  "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
```

This is Mistral 7B Instruct at Q4_K_M quantization (~4.1 GB) — a reasonable balance
of quality and CPU speed. `models/` and `*.gguf` are gitignored; model weights are
never committed.

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
  -d '{"model": "mistral-7b-instruct-v0.2.Q4_K_M.gguf",
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

## Air-gapped deployment

Downloading from Hugging Face is a local-development convenience only. For
air-gapped targets the model must be vendored into the image at build time or
mounted from a pre-seeded volume — there is no network at runtime. See
[AIRGAP_SETUP.md](AIRGAP_SETUP.md).
