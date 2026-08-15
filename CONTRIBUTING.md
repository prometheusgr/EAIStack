# Contributing to EAIStack

## Before You Start

Read [CLAUDE.md](CLAUDE.md) for project overview, development standards, and testing discipline.

## Development Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker & Docker Compose
- Git

### Local Dev Environment

1. **Clone and initialize**:
   ```bash
   git clone <repo>
   cd EAIStack
   ```

2. **Backend**:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   pip install -e ".[dev]"
   pytest
   ```

3. **Frontend**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. **Full stack (docker-compose)**:
   ```bash
   docker-compose up
   # Navigate to http://localhost:3000 (frontend)
   ```

## Testing Discipline (TDD)

**Write tests first, implementation second.** Every commit should have corresponding tests.

### Backend
```bash
# Unit tests (must pass before commit)
pytest tests/unit/

# Integration tests (smoke check, non-blocking)
pytest tests/integration/
```

### Frontend
```bash
npm run test
```

### Pre-commit
```bash
# Run linters
npm run lint
pytest --cov
```

## Commit Workflow

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Write a failing test
3. Implement to make it pass
4. Run full test suite locally
5. Commit with a descriptive message:
   ```
   Brief one-line summary

   Longer explanation of why this change matters. Reference the plan or
   issue if applicable. Focus on the decision, not the implementation.
   ```
6. Push and open a PR

## Code Review Checklist

- [ ] Tests written first (TDD), all passing
- [ ] No mocking of LLM at the wrong boundary (should only mock at the LLM service boundary, not in business logic)
- [ ] No unnecessary abstractions
- [ ] Clear variable/function names (code documents itself)
- [ ] No feature flags or backwards-compat shims
- [ ] Follows the phase scope (don't add features outside the current phase)

## Reporting Issues

If you find a bug or have a question:
1. Check the [plan file](/.claude/plans/indexed-tinkering-babbage.md) for context
2. Open an issue with reproduction steps and expected vs. actual behavior
3. Reference relevant code locations

## Questions?

Refer to [CLAUDE.md](CLAUDE.md) for architectural decisions and trade-offs. If something isn't documented, it's probably worth adding.
