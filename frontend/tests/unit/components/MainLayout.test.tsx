import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MainLayout } from '../../../src/components/layout/MainLayout'
import { AuthProvider } from '../../../src/context/AuthContext'
import { ToastProvider } from '../../../src/components/ui/toast'

describe('MainLayout', () => {
  const defaultProps = {
    currentView: 'chat' as const,
    onViewChange: vi.fn(),
    children: <div>Test content</div>,
  }

  beforeEach(() => {
    localStorage.setItem('access_token', 'mock-token')
  })

  const renderWithProviders = (component: React.ReactElement) => {
    return render(
      <AuthProvider>
        <ToastProvider>
          {component}
        </ToastProvider>
      </AuthProvider>
    )
  }

  it('renders header with user name', () => {
    renderWithProviders(<MainLayout {...defaultProps} />)
    expect(screen.getByText(/Welcome/)).toBeInTheDocument()
  })

  it('renders navigation tabs', () => {
    renderWithProviders(<MainLayout {...defaultProps} />)
    expect(screen.getByRole('button', { name: /Chat/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /API Keys/i })).toBeInTheDocument()
  })

  it('calls onViewChange when tab is clicked', async () => {
    const onViewChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <MainLayout
        {...defaultProps}
        onViewChange={onViewChange}
      />
    )

    const apiKeysButton = screen.getByRole('button', { name: /API Keys/i })
    await user.click(apiKeysButton)
    expect(onViewChange).toHaveBeenCalledWith('apikeys')
  })

  it('renders children content', () => {
    renderWithProviders(
      <MainLayout {...defaultProps}>
        <div>Custom content</div>
      </MainLayout>
    )
    expect(screen.getByText('Custom content')).toBeInTheDocument()
  })

  it('renders footer', () => {
    renderWithProviders(<MainLayout {...defaultProps} />)
    expect(screen.getByText(/© 2024 Enterprise AI Stack/)).toBeInTheDocument()
  })

  it('has logout button', () => {
    renderWithProviders(<MainLayout {...defaultProps} />)
    expect(screen.getByRole('button', { name: /Logout/i })).toBeInTheDocument()
  })

  it('shows active tab indicator', () => {
    const { rerender } = renderWithProviders(
      <MainLayout currentView="chat" onViewChange={vi.fn()}>
        Content
      </MainLayout>
    )

    const chatButton = screen.getByRole('button', { name: /Chat/i })
    expect(chatButton).toHaveAttribute('data-active', 'true')

    rerender(
      <AuthProvider>
        <ToastProvider>
          <MainLayout currentView="apikeys" onViewChange={vi.fn()}>
            Content
          </MainLayout>
        </ToastProvider>
      </AuthProvider>
    )

    const apiKeysButton = screen.getByRole('button', { name: /API Keys/i })
    expect(apiKeysButton).toHaveAttribute('data-active', 'true')
  })
})
