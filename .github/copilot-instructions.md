# GitHub Copilot Instructions for EAIStack

This repository uses a shared standards document: [AGENTS.md](../AGENTS.md) for coding standards, testing discipline, and development workflow.

For project architecture, constraints, and phase context, see [CLAUDE.md](../CLAUDE.md).

## Key Principles

**Code is built for a 10-year lifecycle. Every line should be clear, tested, and maintainable.**

- **TDD is mandatory**: Write tests first, then implementation. Tests are the specification. All unit tests must pass before pushing.
- **Test outcomes define correctness**: If a test passes, the feature works. If it fails, something is broken. No other source of truth.
- **Clear, intent-revealing code**: Names should reveal *what* and *why*. Clarity beats cleverness. Long functions (>50 lines) should be broken down.
- **Mock the LLM boundary only**: All LLM calls go through `app.core.llm_client`. Unit tests mock this, not higher-level business logic.
- **No premature abstractions**: Three similar lines is better than a shared utility. Extract functions only if you have multiple callers or a strong reason.
- **Descriptive commits**: Explain the *why*, not just what changed. Document decisions so future maintainers understand trade-offs.
- **One logical change per commit**: Squash before merge if needed.
- **Phase scope**: Don't add features outside the current phase — stick to thin vertical slices.

## Quick Links

- **Testing standards & commands**: [AGENTS.md#testing-tdd-enforced-by-ci](../AGENTS.md#testing-tdd-enforced-by-ci)
- **Coding standards**: [AGENTS.md#coding-standards](../AGENTS.md#coding-standards)
- **Code review checklist**: [AGENTS.md#code-review-checklist](../AGENTS.md#code-review-checklist)
- **Development workflow**: [AGENTS.md#development-workflow](../AGENTS.md#development-workflow)
- **Constraints**: [AGENTS.md#key-constraints](../AGENTS.md#key-constraints) and [CLAUDE.md#constraints--gotchas](../CLAUDE.md#constraints--gotchas)

## Architecture & Project Status

See [CLAUDE.md](../CLAUDE.md) for:
- Project overview and core stack
- Current phase status (Phase 2 complete)
- Architecture overview (Backend, Frontend, Data Flow)
- Helpful context (greenfield project, K8s assumptions, encryption requirements)

## Repository Structure

```
backend/          FastAPI + LangGraph backend
frontend/         React + TypeScript frontend
infra/            Kubernetes, Helm, deployment scripts
/mcp-servers      Custom MCP servers (Phase 3+)
tests/            Unit and integration tests
AGENTS.md         Coding standards & development process (this doc)
CLAUDE.md         Project overview & architecture
CONTRIBUTING.md   Setup & contribution quickstart
```

## Common Commands

**Backend setup & testing**:
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
pytest tests/unit/ -v      # Tests must pass before commit
black . && ruff check .     # Format and lint
```

**Frontend setup & testing**:
```bash
cd frontend
npm install
npm test                    # Tests must pass before commit
npm run lint && npm run build
```

**Full stack**:
```bash
docker-compose up           # All services
docker-compose up --profile llm  # Including LLM
```

Refer to [CLAUDE.md](../CLAUDE.md) for detailed command reference.
