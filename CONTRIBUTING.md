# Contributing to EAIStack

## Before You Start

Read [CLAUDE.md](CLAUDE.md) for project overview, development standards, and testing discipline.

## Development Setup

### Prerequisites

- Python 3.10+
- Node.js 20 (LTS) — matches CI and `frontend/.nvmrc`; run `nvm use` in `frontend/` if you use nvm
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

**Write tests first, implementation second.** Every commit should have corresponding tests. See [AGENTS.md#testing-tdd-enforced-by-ci](AGENTS.md#testing-tdd-enforced-by-ci) for detailed testing standards, commands, and CI requirements.

## Commit Workflow

See [AGENTS.md#development-workflow](AGENTS.md#development-workflow) and [AGENTS.md#commit-standards](AGENTS.md#commit-standards) for detailed workflow, commit format, and pre-push checklist.

## Code Review Checklist

See [AGENTS.md#code-review-checklist](AGENTS.md#code-review-checklist) for the full checklist.

## Reporting Issues

If you find a bug or have a question:
1. Check current [plan files](.claude/plans/) for context
2. Open an issue with reproduction steps and expected vs. actual behavior
3. Reference relevant code locations

## Questions?

Refer to [CLAUDE.md](CLAUDE.md) for architectural decisions and trade-offs. If something isn't documented, it's probably worth adding.
