# EAIStack Frontend

React + TypeScript frontend with Keycloak OIDC authentication.

## Setup

```bash
npm install
npm run dev
```

## Testing

```bash
# Run tests
npm test

# Run tests with UI
npm run test:ui
```

## Building

```bash
npm run build
```

## Project Structure

- `src/` — React components and application logic
- `tests/` — Vitest test files
- `vite.config.ts` — Vite configuration
- `vitest.config.ts` — Vitest configuration

## Key Patterns

### Keycloak Authentication

In Phase 1, the app will initialize Keycloak for OIDC login. For now, tests mock the Keycloak provider.

See `tests/setup.ts` for the test mock.
