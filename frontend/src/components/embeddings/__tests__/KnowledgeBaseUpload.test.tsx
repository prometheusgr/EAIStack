import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { KnowledgeBaseUpload } from '../KnowledgeBaseUpload'
import { useEmbeddingsService } from '@/hooks/useEmbeddingsService'

vi.mock('@/hooks/useEmbeddingsService')

describe('KnowledgeBaseUpload', () => {
  const mockUploadMutation = {
    mutateAsync: vi.fn(),
    isPending: false,
  }
  const mockUploadFileMutation = {
    mutateAsync: vi.fn(),
    isPending: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    const mockService = {
      upload: mockUploadMutation,
      uploadFile: mockUploadFileMutation,
    }
    ;(useEmbeddingsService as unknown as ReturnType<typeof vi.fn>).mockReturnValue(mockService)
  })

  it('defaults to the paste-text tab and submits via upload()', async () => {
    mockUploadMutation.mutateAsync.mockResolvedValue(undefined)
    render(<KnowledgeBaseUpload />)

    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: 'My Doc' } })
    fireEvent.change(screen.getByLabelText(/content/i), { target: { value: 'Body text' } })
    fireEvent.click(screen.getByRole('button', { name: /create entry/i }))

    await waitFor(() => {
      expect(mockUploadMutation.mutateAsync).toHaveBeenCalledWith({
        title: 'My Doc',
        content: 'Body text',
        metadata: {},
      })
    })
    expect(mockUploadFileMutation.mutateAsync).not.toHaveBeenCalled()
  })

  it('switches to the upload-file tab and submits the selected file via uploadFile()', async () => {
    mockUploadFileMutation.mutateAsync.mockResolvedValue({ id: 'kb-1' })
    render(<KnowledgeBaseUpload />)

    fireEvent.click(screen.getByRole('tab', { name: /upload file/i }))

    const file = new File(['file bytes'], 'spec.pdf', { type: 'application/pdf' })
    const input = screen.getByLabelText(/choose file/i) as HTMLInputElement
    await userEvent.upload(input, file)

    fireEvent.click(screen.getByRole('button', { name: /upload/i }))

    await waitFor(() => {
      expect(mockUploadFileMutation.mutateAsync).toHaveBeenCalledWith(file)
    })
    expect(mockUploadMutation.mutateAsync).not.toHaveBeenCalled()
  })

  it('clears paste-mode draft state when switching to the upload-file tab and back', async () => {
    render(<KnowledgeBaseUpload />)

    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: 'Draft title' } })
    fireEvent.change(screen.getByLabelText(/content/i), { target: { value: 'Draft body' } })

    fireEvent.click(screen.getByRole('tab', { name: /upload file/i }))
    fireEvent.click(screen.getByRole('tab', { name: /paste text/i }))

    expect(screen.getByLabelText(/title/i)).toHaveValue('')
    expect(screen.getByLabelText(/content/i)).toHaveValue('')
  })

  it('clears a selected file when switching away from the upload-file tab', async () => {
    render(<KnowledgeBaseUpload />)

    fireEvent.click(screen.getByRole('tab', { name: /upload file/i }))
    const file = new File(['bytes'], 'spec.pdf', { type: 'application/pdf' })
    const input = screen.getByLabelText(/choose file/i) as HTMLInputElement
    await userEvent.upload(input, file)

    fireEvent.click(screen.getByRole('tab', { name: /paste text/i }))
    fireEvent.click(screen.getByRole('tab', { name: /upload file/i }))

    expect(screen.getByRole('button', { name: /^upload$/i })).toBeDisabled()
  })

  it('disables both mode tabs while a file upload is pending', () => {
    mockUploadFileMutation.isPending = true
    render(<KnowledgeBaseUpload />)

    expect(screen.getByRole('tab', { name: /paste text/i })).toBeDisabled()
    expect(screen.getByRole('tab', { name: /upload file/i })).toBeDisabled()

    mockUploadFileMutation.isPending = false
  })

  it('disables both mode tabs while a paste-text create is pending', () => {
    mockUploadMutation.isPending = true
    render(<KnowledgeBaseUpload />)

    expect(screen.getByRole('tab', { name: /paste text/i })).toBeDisabled()
    expect(screen.getByRole('tab', { name: /upload file/i })).toBeDisabled()

    mockUploadMutation.isPending = false
  })

  it('disables the upload button until a file is chosen', () => {
    render(<KnowledgeBaseUpload />)

    fireEvent.click(screen.getByRole('tab', { name: /upload file/i }))

    expect(screen.getByRole('button', { name: /upload/i })).toBeDisabled()
  })

  it('calls onUploadSuccess after a successful file upload', async () => {
    mockUploadFileMutation.mutateAsync.mockResolvedValue({ id: 'kb-1' })
    const onUploadSuccess = vi.fn()
    render(<KnowledgeBaseUpload onUploadSuccess={onUploadSuccess} />)

    fireEvent.click(screen.getByRole('tab', { name: /upload file/i }))
    const file = new File(['file bytes'], 'spec.pdf', { type: 'application/pdf' })
    const input = screen.getByLabelText(/choose file/i) as HTMLInputElement
    await userEvent.upload(input, file)
    fireEvent.click(screen.getByRole('button', { name: /upload/i }))

    await waitFor(() => {
      expect(onUploadSuccess).toHaveBeenCalled()
    })
  })

  it('surfaces a rejected file upload as an error message via onUploadError', async () => {
    // The server, not the browser's file picker, is what rejects this file
    // (e.g. content sniffing disagrees with the declared type) - the input's
    // `accept` attribute already filters obviously-wrong extensions client
    // side, so this simulates the upload() call itself failing.
    mockUploadFileMutation.mutateAsync.mockRejectedValue(new Error('Unsupported file type'))
    const onUploadError = vi.fn()
    render(<KnowledgeBaseUpload onUploadError={onUploadError} />)

    fireEvent.click(screen.getByRole('tab', { name: /upload file/i }))
    const file = new File(['bytes'], 'spec.pdf', { type: 'application/pdf' })
    const input = screen.getByLabelText(/choose file/i) as HTMLInputElement
    await userEvent.upload(input, file)
    fireEvent.click(screen.getByRole('button', { name: /upload/i }))

    await waitFor(() => {
      expect(onUploadError).toHaveBeenCalledWith('Unsupported file type')
    })
    expect(screen.getByText('Unsupported file type')).toBeInTheDocument()
  })

  it('does not update state after unmounting mid-upload', async () => {
    let resolveUpload!: (value: { id: string }) => void
    mockUploadFileMutation.mutateAsync.mockReturnValue(
      new Promise((resolve) => {
        resolveUpload = resolve
      })
    )
    const onUploadSuccess = vi.fn()
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    const { unmount } = render(<KnowledgeBaseUpload onUploadSuccess={onUploadSuccess} />)

    fireEvent.click(screen.getByRole('tab', { name: /upload file/i }))
    const file = new File(['bytes'], 'spec.pdf', { type: 'application/pdf' })
    const input = screen.getByLabelText(/choose file/i) as HTMLInputElement
    await userEvent.upload(input, file)
    fireEvent.click(screen.getByRole('button', { name: /upload/i }))

    unmount()
    resolveUpload({ id: 'kb-1' })
    await Promise.resolve()
    await Promise.resolve()

    const unmountWarning = consoleError.mock.calls.some((call) =>
      String(call[0]).includes('unmounted component')
    )
    expect(unmountWarning).toBe(false)

    consoleError.mockRestore()
  })
})
