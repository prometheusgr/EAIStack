# Time Injection Pattern

## Overview

The **time injection pattern** makes time-dependent functions deterministic without mocking global state. Instead of calling `datetime.now()` inside a function, accept `now: datetime` as a parameter.

This approach:
- ✓ Eliminates non-determinism in tests (no randomness, no freezegun needed)
- ✓ Makes function dependencies explicit (the signature shows it depends on time)
- ✓ Passes the same "now" value to all callees (consistent reference point)
- ✓ Works seamlessly with production code (callers inject the current time)

## Pattern

### Function Definition

Every time-dependent function should accept `now: datetime` as a parameter:

```python
from datetime import datetime, timedelta, timezone

def calculate_token_expiry(
    issued_at: datetime,
    ttl_seconds: int,
    now: datetime  # <-- Accept now as parameter
) -> datetime:
    """Calculate when a token expires.
    
    Args:
        issued_at: When the token was issued.
        ttl_seconds: Time-to-live in seconds.
        now: Current time (for testability; use datetime.now(timezone.utc) in production).
    
    Returns:
        The expiry datetime.
    """
    return now + timedelta(seconds=ttl_seconds)
```

### Testing

Pass a fixed `now` value in tests. Use pytest fixtures for standard test times:

```python
def test_token_expires_after_ttl(now_fixed):
    issued = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
    ttl = 3600  # 1 hour
    
    expiry = calculate_token_expiry(issued, ttl, now=now_fixed)
    
    expected = datetime(2026, 8, 21, 13, 0, 0, tzinfo=timezone.utc)
    assert expiry == expected
```

No mocking, no freezegun — just pass the fixed time.

### Production Code

In production, callers inject the current time:

```python
@app.post("/tokens")
def issue_token():
    now = datetime.now(timezone.utc)
    expiry = calculate_token_expiry(issued_at=now, ttl_seconds=3600, now=now)
    return {"token": "...", "expires_at": expiry}
```

Or wrap the injection in a service/helper:

```python
class TokenService:
    def calculate_expiry(self, issued_at: datetime, ttl_seconds: int) -> datetime:
        now = datetime.now(timezone.utc)
        return calculate_token_expiry(issued_at, ttl_seconds, now=now)
```

## Available Fixtures

### `now_fixed`
Provides a fixed UTC datetime: `datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)`.

```python
def test_something(now_fixed):
    result = my_function(now=now_fixed)
    assert result is not None
```

### `now_fixed_naive`
Provides a fixed naive datetime (no timezone): `datetime(2026, 8, 21, 12, 0, 0)`.

Use only when testing code that expects naive datetimes. Prefer `now_fixed` for new code.

```python
def test_legacy_function(now_fixed_naive):
    result = legacy_function(now=now_fixed_naive)
    assert result is not None
```

## Linter

The linter `python tools/lint_time_injection.py` flags functions that call `datetime.now()` without accepting a `now` parameter.

**Output modes:**
- **Error**: Parse syntax errors (always fail CI)
- **Warning**: Functions calling `datetime.now()` without `now` parameter (informational, non-blocking)

Run it locally:
```bash
cd backend
python tools/lint_time_injection.py
```

Runs automatically in CI pipeline.

## When to Use This Pattern

✓ Use time injection when:
- Function behavior depends on the current time
- You want deterministic unit tests
- The function is called from multiple places (consistency matters)

✗ Don't use it for:
- Logging timestamps (log library handles injection)
- Heartbeat/status endpoints (non-determinism is fine here)
- Code that doesn't depend on time

## Edge Cases

### Multiple `now` parameters?

If a function needs multiple time values, pass them all explicitly:

```python
def calculate_session_age(
    started_at: datetime,
    last_activity_at: datetime,
    now: datetime  # Single "current time" reference
) -> timedelta:
    """Calculate how old a session is."""
    return now - started_at
```

Don't call `datetime.now()` multiple times in one function; use one injected value.

### Chaining functions

All functions in a call chain use the same `now`:

```python
def outer(user_id: str, now: datetime) -> str:
    return inner(user_id, now=now)

def inner(user_id: str, now: datetime) -> str:
    expiry = calculate_expiry(now=now)
    return expiry.isoformat()
```

### Async functions

Same pattern applies:

```python
async def async_function(data: str, now: datetime) -> str:
    result = await process(data)
    return f"{result} at {now}"
```

## Examples

See `backend/tests/unit/` for tested examples of the pattern.

## Rationale: Why Not Mock?

Mocking `datetime.now()` works but is fragile:
- Global state affects all tests (mutations bleed between tests)
- Mock setup is verbose and easy to get wrong
- Future developers might forget to mock
- The function signature doesn't document the time dependency

Injection is simpler, clearer, and keeps functions pure.

## References

- [AGENTS.md: Time-Dependent Functions](../AGENTS.md#time-dependent-functions)
- [Dependency Injection Pattern](https://en.wikipedia.org/wiki/Dependency_injection)
