import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from '../src/App'

vi.mock('../src/context/AuthContext', () => ({
  useAuth: () => ({
    token: 'fake-token-123',
    isAuthenticated: true,
    isLoading: false,
    login: () => {},
    logout: () => {},
    refreshAccessToken: async () => false,
    user: {
      name: 'Test User',
      username: 'testuser',
    },
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}))

describe('App Component', () => {
  it('should render the App title', () => {
    render(<App />)
    expect(screen.getByText('EAIStack')).toBeInTheDocument()
  })

  it('should display Phase 2 status', () => {
    render(<App />)
    expect(screen.getByText(/Phase 2.*Agent Chat/i)).toBeInTheDocument()
  })
})
