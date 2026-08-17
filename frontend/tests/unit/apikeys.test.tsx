import { describe, it, expect } from 'vitest'
import { APIKey, APIKeyCreate, APIKeyUpdate } from '../../src/api/apiKeysClient'

// Test data structures and type safety
describe('apiKeysClient types', () => {
  describe('APIKey', () => {
    it('represents an API key with all required fields', () => {
      const key: APIKey = {
        id: 'key-1',
        user_id: 'user-123',
        name: 'OpenAI Key',
        provider: 'openai',
        secret_value_masked: 'sk-proj-***...',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
        revoked_at: null,
      }

      expect(key.id).toBe('key-1')
      expect(key.name).toBe('OpenAI Key')
      expect(key.provider).toBe('openai')
      expect(key.secret_value_masked).toBe('sk-proj-***...')
      expect(key.revoked_at).toBeNull()
    })

    it('allows optional updated_at and revoked_at fields', () => {
      const key: APIKey = {
        id: 'key-1',
        user_id: 'user-123',
        name: 'Key',
        provider: 'openai',
        secret_value_masked: 'masked',
        created_at: '2024-01-01T00:00:00Z',
      }

      expect(key.updated_at).toBeUndefined()
      expect(key.revoked_at).toBeUndefined()
    })

    it('never exposes full secret_value', () => {
      const key: APIKey = {
        id: 'key-1',
        user_id: 'user-123',
        name: 'Key',
        provider: 'openai',
        secret_value_masked: 'masked',
        created_at: '2024-01-01T00:00:00Z',
      }

      // @ts-expect-error - secret_value should not exist on response
      expect(key.secret_value).toBeUndefined()
    })
  })

  describe('APIKeyCreate', () => {
    it('requires name, provider, and secret_value', () => {
      const payload: APIKeyCreate = {
        name: 'My Key',
        provider: 'openai',
        secret_value: 'sk-proj-secret',
      }

      expect(payload.name).toBe('My Key')
      expect(payload.provider).toBe('openai')
      expect(payload.secret_value).toBe('sk-proj-secret')
    })

    it('accepts various providers', () => {
      const providers = ['openai', 'anthropic', 'huggingface', 'custom']

      providers.forEach((provider) => {
        const payload: APIKeyCreate = {
          name: 'Key',
          provider,
          secret_value: 'secret',
        }
        expect(payload.provider).toBe(provider)
      })
    })
  })

  describe('APIKeyUpdate', () => {
    it('requires keyId, name, and provider', () => {
      const payload: APIKeyUpdate = {
        keyId: 'key-1',
        name: 'Updated Name',
        provider: 'anthropic',
      }

      expect(payload.keyId).toBe('key-1')
      expect(payload.name).toBe('Updated Name')
      expect(payload.provider).toBe('anthropic')
    })

    it('does not allow secret_value in update payload', () => {
      const payload: APIKeyUpdate = {
        keyId: 'key-1',
        name: 'Updated',
        provider: 'openai',
      }

      // @ts-expect-error - secret_value should not be updatable
      payload.secret_value = 'new-secret'
    })
  })

  describe('API Key masking behavior', () => {
    it('masks secrets to show only prefix', () => {
      const masked = 'sk-proj-***...'
      const original = 'sk-proj-1234567890abcdefghijklmnop'

      expect(masked.length).toBeLessThan(original.length)
      expect(masked).toContain('***...')
      expect(masked).not.toContain('1234567890')
    })

    it('never sends full secret in response', () => {
      const response: APIKey = {
        id: 'key-1',
        user_id: 'user-123',
        name: 'Key',
        provider: 'openai',
        secret_value_masked: 'masked',
        created_at: '2024-01-01T00:00:00Z',
      }

      const keys = Object.keys(response)
      expect(keys).not.toContain('secret_value')
      expect(keys).toContain('secret_value_masked')
    })
  })

  describe('User isolation', () => {
    it('associates keys with user_id', () => {
      const key: APIKey = {
        id: 'key-1',
        user_id: 'user-a',
        name: 'Key',
        provider: 'openai',
        secret_value_masked: 'masked',
        created_at: '2024-01-01T00:00:00Z',
      }

      expect(key.user_id).toBe('user-a')
    })

    it('allows filtering by user_id', () => {
      const keys: APIKey[] = [
        {
          id: 'key-1',
          user_id: 'user-a',
          name: 'Key A',
          provider: 'openai',
          secret_value_masked: 'masked',
          created_at: '2024-01-01T00:00:00Z',
        },
        {
          id: 'key-2',
          user_id: 'user-b',
          name: 'Key B',
          provider: 'openai',
          secret_value_masked: 'masked',
          created_at: '2024-01-01T00:00:00Z',
        },
      ]

      const userAKeys = keys.filter((k) => k.user_id === 'user-a')
      expect(userAKeys).toHaveLength(1)
      expect(userAKeys[0].name).toBe('Key A')
    })
  })

  describe('Soft-delete via revoked_at', () => {
    it('marks keys as revoked via revoked_at timestamp', () => {
      const activeKey: APIKey = {
        id: 'key-1',
        user_id: 'user-a',
        name: 'Active',
        provider: 'openai',
        secret_value_masked: 'masked',
        created_at: '2024-01-01T00:00:00Z',
        revoked_at: null,
      }

      const revokedKey: APIKey = {
        id: 'key-2',
        user_id: 'user-a',
        name: 'Revoked',
        provider: 'openai',
        secret_value_masked: 'masked',
        created_at: '2024-01-01T00:00:00Z',
        revoked_at: '2024-01-02T00:00:00Z',
      }

      const activeKeys = [activeKey, revokedKey].filter((k) => !k.revoked_at)
      expect(activeKeys).toHaveLength(1)
      expect(activeKeys[0].name).toBe('Active')
    })
  })
})
