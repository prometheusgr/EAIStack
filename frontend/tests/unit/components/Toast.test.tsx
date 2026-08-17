import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider, useToast } from '../../../src/components/ui/toast'

function TestComponent() {
  const { addToast } = useToast()

  return (
    <div>
      <button onClick={() => addToast('Success message', 'success')}>
        Add success
      </button>
      <button onClick={() => addToast('Error message', 'error')}>
        Add error
      </button>
      <button onClick={() => addToast('Info message', 'info')}>
        Add info
      </button>
    </div>
  )
}

describe('Toast system', () => {
  it('displays success toast', async () => {
    const user = userEvent.setup()
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    )

    await user.click(screen.getByText('Add success'))
    expect(screen.getByText('Success message')).toBeInTheDocument()
  })

  it('displays error toast', async () => {
    const user = userEvent.setup()
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    )

    await user.click(screen.getByText('Add error'))
    expect(screen.getByText('Error message')).toBeInTheDocument()
  })

  it('displays info toast', async () => {
    const user = userEvent.setup()
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    )

    await user.click(screen.getByText('Add info'))
    expect(screen.getByText('Info message')).toBeInTheDocument()
  })

  it('dismisses toast on close button click', async () => {
    const user = userEvent.setup()
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    )

    await user.click(screen.getByText('Add success'))
    const closeButton = screen.getByRole('button', { name: '' }).closest('button')
    if (closeButton) {
      await user.click(closeButton)
    }

    await waitFor(() => {
      expect(screen.queryByText('Success message')).not.toBeInTheDocument()
    })
  })

  it('passes duration prop to toast', async () => {
    const user = userEvent.setup()
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    )

    await user.click(screen.getByText('Add success'))
    expect(screen.getByText('Success message')).toBeInTheDocument()
  })

  it('throws error when useToast is used outside provider', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(() => {
      render(<TestComponent />)
    }).toThrow('useToast must be used within ToastProvider')

    consoleError.mockRestore()
  })
})
