import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { EmbeddingDetail } from '../EmbeddingDetail'
import { useEmbeddingsService } from '@/hooks/useEmbeddingsService'

vi.mock('@/hooks/useEmbeddingsService')

describe('EmbeddingDetail', () => {
  const mockEmbedding = {
    id: 'emb-123',
    doc_id: 'doc-456', // The knowledge base ID
    title: 'Test Embedding',
    content: 'Test content here',
    embedding: [0.1, 0.2],
    embed_metadata: {},
    doc_metadata: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    deleted_at: null,
  }

  const mockDeleteDocumentMutation = {
    mutateAsync: vi.fn(),
    isPending: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    const mockService = {
      getEmbedding: {
        execute: vi.fn(),
        data: mockEmbedding,
        isLoading: false,
        error: null,
      },
      deleteDocument: mockDeleteDocumentMutation,
    }
    ;(useEmbeddingsService as unknown as ReturnType<typeof vi.fn>).mockReturnValue(mockService)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('should call delete mutation with doc_id (knowledge base id), not embedding id', async () => {
    mockDeleteDocumentMutation.mutateAsync.mockResolvedValue(undefined)
    global.confirm = vi.fn(() => true)

    render(<EmbeddingDetail id={mockEmbedding.id} />)

    await waitFor(() => {
      expect(screen.getByText('Delete Document')).toBeInTheDocument()
    })

    const deleteButton = screen.getByText('Delete Document')
    fireEvent.click(deleteButton)

    await waitFor(() => {
      // The mutation should be called with doc_id (knowledge base id), not embedding id
      expect(mockDeleteDocumentMutation.mutateAsync).toHaveBeenCalledWith(mockEmbedding.doc_id)
      expect(mockDeleteDocumentMutation.mutateAsync).not.toHaveBeenCalledWith(mockEmbedding.id)
    })
  })

  it('should display error message if document delete fails', async () => {
    const errorMessage = 'Failed to delete document'
    mockDeleteDocumentMutation.mutateAsync.mockRejectedValue(new Error(errorMessage))
    global.confirm = vi.fn(() => true)

    render(<EmbeddingDetail id={mockEmbedding.id} />)

    await waitFor(() => {
      expect(screen.getByText('Delete Document')).toBeInTheDocument()
    })

    const deleteButton = screen.getByText('Delete Document')
    fireEvent.click(deleteButton)

    await waitFor(() => {
      expect(screen.getByText(errorMessage)).toBeInTheDocument()
    })
  })

  it('should call onBack callback after successful deletion', async () => {
    mockDeleteDocumentMutation.mutateAsync.mockResolvedValue(undefined)
    global.confirm = vi.fn(() => true)
    const onBack = vi.fn()

    render(<EmbeddingDetail id={mockEmbedding.id} onBack={onBack} />)

    await waitFor(() => {
      expect(screen.getByText('Delete Document')).toBeInTheDocument()
    })

    const deleteButton = screen.getByText('Delete Document')
    fireEvent.click(deleteButton)

    await waitFor(() => {
      expect(onBack).toHaveBeenCalled()
    })
  })

  it('should not call delete mutation when user cancels confirmation', async () => {
    global.confirm = vi.fn(() => false)

    render(<EmbeddingDetail id={mockEmbedding.id} />)

    await waitFor(() => {
      expect(screen.getByText('Delete Document')).toBeInTheDocument()
    })

    const deleteButton = screen.getByText('Delete Document')
    fireEvent.click(deleteButton)

    await waitFor(() => {
      expect(mockDeleteDocumentMutation.mutateAsync).not.toHaveBeenCalled()
    })
  })
})
