# Frontend Service Layer & API Clients

This is the canonical worked example for the frontend's three-layer architecture. Follow this pattern exactly — new API integrations should look like this one, not invent a new shape.

Governing standards live in [AGENTS.md](../AGENTS.md); this doc is the how-to.

**Frontend API calls must follow a strict three-layer pattern: Components → Services → API Clients → HTTP.** This pattern centralizes API logic, enables testing, and prevents scattered fetch() calls across components.

## Architecture Overview

**Three layers, each with a clear responsibility:**

```
Components (React)
  ↓ (uses)
Services (business logic, token passing)
  ↓ (uses)
API Clients (HTTP-only, no business logic)
  ↓ (uses)
HTTP (fetch, headers, response parsing)
```

**Layer responsibilities:**

1. **API Clients** (`src/api/`) — HTTP-only, no business logic
   - Take `token` as an explicit parameter
   - Handle fetch(), headers, status codes
   - Parse JSON responses and throw errors
   - Export typed interfaces for request/response shapes

2. **Services** (`src/services/`) — Business logic layer
   - Take `token` in constructor
   - Delegate HTTP work to API clients
   - Add retry logic, error handling, business rules
   - Optional: auth refresh callbacks

3. **Components** (React) — UI layer only
   - Get token from `useAuth()` hook
   - Create service instance: `const service = new MyService(token)`
   - Call service methods, update state, render
   - No direct fetch() calls, no auth header logic

## When to Add New API Endpoints

**Workflow for adding a new API endpoint to the frontend:**

1. **Create the API Client** (`src/api/newFeatureClient.ts`)
   ```typescript
   // src/api/newFeatureClient.ts
   export interface NewFeatureRequest {
     name: string
     value: string
   }

   export interface NewFeatureResponse {
     id: string
     user_id: string
     name: string
     value: string
     created_at: string
   }

   async function authorizedFetch(
     url: string,
     token: string,
     options?: RequestInit
   ): Promise<Response> {
     const headers = {
       ...options?.headers,
       Authorization: `Bearer ${token}`,
     } as Record<string, string>

     return fetch(url, { ...options, headers })
   }

   export const newFeatureClient = {
     async create(name: string, value: string, token: string): Promise<NewFeatureResponse> {
       const response = await authorizedFetch('/api/new-feature', token, {
         method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         body: JSON.stringify({ name, value }),
       })
       if (!response.ok) throw new Error(`Create failed: ${response.statusText}`)
       return response.json()
     },

     async get(id: string, token: string): Promise<NewFeatureResponse> {
       const response = await authorizedFetch(`/api/new-feature/${id}`, token, {
         method: 'GET',
       })
       if (!response.ok) throw new Error(`Fetch failed: ${response.statusText}`)
       return response.json()
     },

     async list(token: string): Promise<NewFeatureResponse[]> {
       const response = await authorizedFetch('/api/new-feature', token, {
         method: 'GET',
       })
       if (!response.ok) throw new Error(`List failed: ${response.statusText}`)
       return response.json()
     },
   }
   ```

   **Key principles:**
   - Take `token` as explicit parameter (last argument)
   - No business logic, only HTTP concerns
   - Use `authorizedFetch()` helper to handle Authorization header
   - Throw on non-ok response
   - Export response type interfaces

2. **Create the Service** (`src/services/newFeatureService.ts`)
   ```typescript
   // src/services/newFeatureService.ts
   import { newFeatureClient, type NewFeatureResponse } from '@/api/newFeatureClient'

   export class NewFeatureService {
     constructor(private token: string) {}

     async create(name: string, value: string): Promise<NewFeatureResponse> {
       if (!this.token) throw new Error('No auth token available')
       return newFeatureClient.create(name, value, this.token)
     }

     async get(id: string): Promise<NewFeatureResponse> {
       if (!this.token) throw new Error('No auth token available')
       return newFeatureClient.get(id, this.token)
     }

     async list(): Promise<NewFeatureResponse[]> {
       if (!this.token) throw new Error('No auth token available')
       return newFeatureClient.list(this.token)
     }
   }
   ```

   **Key principles:**
   - Wrap the API client, passing token automatically
   - Token is checked when methods are called (not in constructor)
   - Add business logic here (retries, validation, transformations)
   - Methods don't take token—it's in constructor

3. **Create a Hook** (optional, for use with React Query)
   ```typescript
   // src/hooks/useNewFeatureService.ts
   import { useAuth } from '@/context/AuthContext'
   import { newFeatureClient } from '@/api/newFeatureClient'
   import { useApiMutation } from './useApiMutation'

   export function useNewFeatureService() {
     const { token } = useAuth()

     const create = useApiMutation<
       { name: string; value: string },
       NewFeatureResponse
     >(async ({ name, value }) => {
       if (!token) throw new Error('No auth token available')
       return newFeatureClient.create(name, value, token)
     })

     // ... other mutations

     return { create }
   }
   ```

4. **Use in Components**
   ```typescript
   // src/components/NewFeatureForm.tsx
   import { useAuth } from '@/context/AuthContext'
   import { NewFeatureService } from '@/services/newFeatureService'

   export function NewFeatureForm() {
     const { token } = useAuth()
     const [loading, setLoading] = useState(false)
     const [error, setError] = useState<string | null>(null)

     const handleSubmit = async (name: string, value: string) => {
       if (!token) {
         setError('Not authenticated')
         return
       }

       setLoading(true)
       setError(null)

       try {
         const service = new NewFeatureService(token)
         const result = await service.create(name, value)
         console.log('Created:', result)
       } catch (err) {
         setError(err instanceof Error ? err.message : 'Create failed')
       } finally {
         setLoading(false)
       }
     }

     return (
       // JSX...
     )
   }
   ```

   **Key principles:**
   - Get token from `useAuth()`
   - Create service instance: `new NewFeatureService(token)`
   - Call service methods, handle errors, update state
   - No fetch(), no auth headers, no API logic in component

## Updating Existing Endpoints

**If an API endpoint changes:**

1. **Update the API Client** (`src/api/existingClient.ts`)
   - Add/update request/response interfaces
   - Update the method signature
   - Update error handling if response format changes

2. **Update the Service** (`src/services/existingService.ts`)
   - Update method signature to match client
   - Update any business logic if needed

3. **Update Components**
   - Update calls to match new service signature
   - Update state/UI if response shape changed

4. **Update Tests**
   - Update API client mocks
   - Update service tests
   - Update component tests

## Testing the Service Layer

**API Client tests** (mock fetch):
```typescript
// src/api/__tests__/newFeatureClient.test.ts
import { vi } from 'vitest'
import { newFeatureClient } from '../newFeatureClient'

vi.stubGlobal('fetch', vi.fn())

describe('newFeatureClient', () => {
  it('creates a new feature', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ id: '1', name: 'test', value: 'value', user_id: 'user-1', created_at: '2024-01-01' }),
      })
    )

    const result = await newFeatureClient.create('test', 'value', 'token')
    expect(result.id).toBe('1')
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/new-feature',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token' }),
      })
    )
  })
})
```

**Service tests** (mock API client):
```typescript
// src/services/__tests__/newFeatureService.test.ts
import { vi } from 'vitest'
import { NewFeatureService } from '../newFeatureService'
import * as newFeatureClientModule from '@/api/newFeatureClient'

vi.spyOn(newFeatureClientModule, 'newFeatureClient', 'get').mockReturnValue({
  create: vi.fn(() =>
    Promise.resolve({ id: '1', name: 'test', value: 'value', user_id: 'user-1', created_at: '2024-01-01' })
  ),
  // ... other methods
})

describe('NewFeatureService', () => {
  it('creates a feature with token', async () => {
    const service = new NewFeatureService('token-123')
    const result = await service.create('test', 'value')
    expect(result.id).toBe('1')
  })

  it('throws if no token', async () => {
    const service = new NewFeatureService('')
    await expect(service.create('test', 'value')).rejects.toThrow('No auth token')
  })
})
```

**Component tests** (mock service):
```typescript
// src/components/__tests__/NewFeatureForm.test.tsx
import { vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { NewFeatureForm } from '../NewFeatureForm'

vi.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ token: 'test-token' }),
}))

vi.mock('@/services/newFeatureService', () => ({
  NewFeatureService: vi.fn().mockImplementation(() => ({
    create: vi.fn(() =>
      Promise.resolve({ id: '1', name: 'test', value: 'value', user_id: 'user-1', created_at: '2024-01-01' })
    ),
  })),
}))

describe('NewFeatureForm', () => {
  it('submits form with service', async () => {
    render(<NewFeatureForm />)
    // ... test form submission
  })
})
```

## Frontend Custom Hooks for State & API Management

**All component state management and API calls must use custom hooks** (`src/hooks/`). Hooks reduce duplication, centralize error handling, and simplify components.

### Generic Hooks (Reusable)

**`useApiCall<T>`** — For fetching/reading data
```typescript
// src/hooks/useApiCall.ts
export function useApiCall<T>(
  apiFn: () => Promise<T>,
  options?: { immediate?: boolean; onSuccess?: (data: T) => void; onError?: (error: Error) => void }
): { data: T | null; isLoading: boolean; error: Error | null; execute: () => Promise<T | null> }
```

**When to use:**
- Reading data that doesn't change often (embeddings list, profile data)
- Defer loading with `immediate: false`, then call `execute()` manually
- Call `execute()` again to retry or refresh

**Example:**
```typescript
const { list, execute: refetch, isLoading, error } = useApiCall(
  async () => embeddingsClient.listEmbeddings(token),
  { immediate: false, onSuccess: (data) => console.log('Loaded:', data) }
);

// Trigger fetch manually
await refetch();
```

**`useApiMutation<T, R>`** — For mutations (POST/PUT/DELETE)
```typescript
// src/hooks/useApiMutation.ts
export function useApiMutation<T, R>(
  mutateFn: (args: T) => Promise<R>,
  options?: { onSuccess?: (data: R) => void; onError?: (error: Error) => void }
): {
  mutate: (args: T) => Promise<void>;
  mutateAsync: (args: T) => Promise<R>;
  isPending: boolean;
  error: Error | null;
  data: R | null;
}
```

**When to use:**
- Creating, updating, deleting data
- Fire-and-forget with `mutate()` or await with `mutateAsync()`
- Callbacks for success/error handling

**Example:**
```typescript
const { mutateAsync: create, isPending, error } = useApiMutation<
  { name: string; value: string },
  NewFeatureResponse
>(
  async ({ name, value }) => newFeatureClient.create(name, value, token),
  {
    onSuccess: () => {
      console.log('Created!');
      refetchList(); // Manually trigger list refresh
    },
    onError: (error) => setError(error.message),
  }
);

// Call mutation
try {
  const result = await create({ name: 'Test', value: 'Data' });
} catch (err) {
  // Error already in state
}
```

### Service-Specific Hooks (Built on Generic Hooks)

**`useChatService()`** — Chat operations
```typescript
// src/hooks/useChatService.ts
export function useChatService() {
  const { token, refreshAccessToken } = useAuth();
  return useApiMutation<{ message: string; threadId?: string }, ChatResponse>(
    async ({ message, threadId }) => {
      if (!token) throw new Error('No auth token available');
      return await sendChatMessage(message, threadId, token, refreshAccessToken);
    }
  );
}
```

**Usage:**
```typescript
const { mutateAsync: sendMessage, isPending } = useChatService();
const result = await sendMessage({ message: 'Hello', threadId });
setThreadId(result.threadId);
```

**`useEmbeddingsService()`** — Embeddings/knowledge base operations
```typescript
// src/hooks/useEmbeddingsService.ts
export function useEmbeddingsService() {
  const { token } = useAuth();
  return {
    list: useApiCall(async () => embeddingsClient.listEmbeddings(token), { immediate: false }),
    search: useApiMutation(async (queryText) => embeddingsClient.semanticSearch(queryText, token, 10)),
    upload: useApiMutation(async ({ title, content, metadata }) => knowledgeBaseClient.create(title, content, token, metadata)),
    delete: useApiMutation(async (docId) => knowledgeBaseClient.delete(docId, token)),
    update: useApiMutation(async ({ id, title, content, metadata }) => knowledgeBaseClient.update(id, title, content, token, metadata)),
  };
}
```

**Usage:**
```typescript
const { list, search, upload, delete: deleteEmbedding } = useEmbeddingsService();

// Fetch list
await list.execute();
if (!list.isLoading && list.data) {
  setEmbeddings(list.data);
}

// Search
const results = await search.mutateAsync('machine learning');

// Upload
await upload.mutateAsync({ title: 'Doc', content: '...', metadata: {} });

// Delete
await deleteEmbedding.mutateAsync(docId);
```

### Adding a New Service-Specific Hook

**When a new feature requires API calls:**

1. **Create the hook** (`src/hooks/useNewFeatureService.ts`):
```typescript
import { useAuth } from '@/context/AuthContext';
import { newFeatureClient } from '@/api/newFeatureClient';
import { useApiCall } from './useApiCall';
import { useApiMutation } from './useApiMutation';

export function useNewFeatureService() {
  const { token } = useAuth();

  if (!token) {
    throw new Error('useNewFeatureService requires auth token');
  }

  return {
    list: useApiCall(
      async () => newFeatureClient.list(token),
      { immediate: false }
    ),
    create: useApiMutation(
      async ({ name, value }: { name: string; value: string }) =>
        newFeatureClient.create(name, value, token)
    ),
    delete: useApiMutation(async (id: string) => newFeatureClient.delete(id, token)),
  };
}
```

2. **Export from `src/hooks/index.ts`**:
```typescript
export { useNewFeatureService } from './useNewFeatureService';
```

3. **Use in components**:
```typescript
const { list, create, delete: deleteItem } = useNewFeatureService();

// Fetch data
useEffect(() => {
  list.execute();
}, []);

// Use results
if (list.isLoading) return <div>Loading...</div>;
if (list.error) return <div>Error: {list.error.message}</div>;

// Create item
const handleCreate = async (data: { name: string; value: string }) => {
  try {
    await create.mutateAsync(data);
    await list.execute(); // Refresh list
  } catch (err) {
    // Error already in create.error
  }
};
```

### Component Usage Pattern

**Keep components focused on UI, not API logic:**

```typescript
// ✓ GOOD: Uses custom hook, minimal state
export function MyComponent() {
  const { list, create } = useMyService();
  const [items, setItems] = useState([]);

  useEffect(() => {
    list.execute();
  }, []);

  useEffect(() => {
    if (list.data) setItems(list.data);
  }, [list.data]);

  const handleCreate = async (data: any) => {
    await create.mutateAsync(data);
    await list.execute(); // Refresh
  };

  if (list.isLoading) return <Skeleton />;
  if (list.error) return <Error message={list.error.message} />;

  return (
    <div>
      {items.map((item) => (
        <ItemCard key={item.id} item={item} />
      ))}
      <CreateForm onSubmit={handleCreate} isLoading={create.isPending} />
    </div>
  );
}

// ❌ BAD: Scattered fetch calls, manual state management
export function MyComponent() {
  const { token } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetch('/api/items', { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.json())
      .then((data) => setItems(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [token]);

  const handleCreate = async (data: any) => {
    setCreating(true);
    setCreateError(null);
    try {
      const response = await fetch('/api/items', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });
      if (!response.ok) throw new Error(`Failed: ${response.statusText}`);
      await handleCreate(data); // ❌ Duplicate load logic
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Create failed');
    } finally {
      setCreating(false);
    }
  };

  // ... rest of component
}
```

### Hook Testing

**Mock hooks in component tests:**

```typescript
// src/components/__tests__/MyComponent.test.tsx
import { vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MyComponent } from '../MyComponent';

vi.mock('@/hooks/useMyService', () => ({
  useMyService: () => ({
    list: {
      data: [{ id: '1', name: 'Item 1' }],
      isLoading: false,
      error: null,
      execute: vi.fn(),
    },
    create: {
      mutateAsync: vi.fn(() => Promise.resolve({ id: '2', name: 'Item 2' })),
      isPending: false,
      error: null,
      data: null,
    },
  }),
}));

describe('MyComponent', () => {
  it('renders items from hook', () => {
    render(<MyComponent />);
    expect(screen.getByText('Item 1')).toBeInTheDocument();
  });
});
```

## Code Review Checklist for Frontend APIs

- [ ] **API Client** (`src/api/newClient.ts`) exists and is HTTP-only
- [ ] **Service** (`src/services/newService.ts`) exists and wraps the client
- [ ] **Hook** (`src/hooks/useNewService.ts`) wraps API logic with state management
- [ ] API client takes `token` as explicit parameter (last argument)
- [ ] Service takes `token` in constructor
- [ ] Hook uses `useAuth()` to get token and creates service with it
- [ ] Hook returns mutation/call object with `mutateAsync()`, `isPending`, `error`, `data`
- [ ] Component gets hook: `const { list, create } = useMyService()`
- [ ] Component calls hook methods, updates state, renders
- [ ] **No fetch() calls in components** — all HTTP in API clients
- [ ] **No auth header logic in components** — all in API clients
- [ ] Request/response types exported from API client
- [ ] Hooks exported from `src/hooks/index.ts`
- [ ] API client tested with mocked fetch
- [ ] Service tested with mocked API client
- [ ] Component tested with mocked hook
- [ ] TypeScript compiles without errors
- [ ] Hook doesn't expose internal state (returns only what's needed)
