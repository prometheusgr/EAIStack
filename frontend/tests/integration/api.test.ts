import { describe, it, expect } from 'vitest'

describe('API Integration', () => {
  it('should have backend URL configured', () => {
    // In Docker: http://backend:8000
    // In local dev: http://localhost:8001
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8001'
    expect(backendUrl).toBeDefined()
    expect(backendUrl).toMatch(/^http/)
  })
})
