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

  const mockDeleteMutation = {
    mutateAsync: vi.fn(),
    isPending: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    ;(useEmbeddingsService as any).mockReturnValue({
      getEmbedding: {
        execute: vi.fn(),
        data: mockEmbedding,
        isLoading: false,
        error: null,
      },
      delete: mockDeleteMutation,
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('should call delete mutation with doc_id (knowledge base id), not embedding id', async () => {
    mockDeleteMutation.mutateAsync.mockResolvedValue(undefined)
    global.confirm = vi.fn(() => true)

    render(<EmbeddingDetail id={mockEmbedding.id} />)

    await waitFor(() => {
      expect(screen.getByText('Delete Embedding')).toBeInTheDocument()
    })

    const deleteButton = screen.getByText('Delete Embedding')
    fireEvent.click(deleteButton)

    await waitFor(() => {
      // The mutation should be called with doc_id (knowledge base id), not embedding id
      expect(mockDeleteMutation.mutateAsync).toHaveBeenCalledWith(mockEmbedding.doc_id)
      expect(mockDeleteMutation.mutateAsync).not.toHaveBeenCalledWith(mockEmbedding.id)
    })
  })

  it('should not delete if user cancels confirmation', async () => {
    global.confirm = vi.fn(() => false)

    render(<EmbeddingDetail id={mockEmbedding.id} />)

    await waitFor(() => {
      expect(screen.getByText('Delete Embedding')).toBeInTheDocument()
    })

    const deleteButton = screen.getByText('Delete Embedding')
    fireEvent.click(deleteButton)

    await waitFor(() => {
      expect(mockDeleteMutation.mutateAsync).not.toHaveBeenCalled()
    })
  })

  it('should display error message if delete fails', async () => {
    const errorMessage = 'Failed to delete embedding'
    mockDeleteMutation.mutateAsync.mockRejectedValue(new Error(errorMessage))
    global.confirm = vi.fn(() => true)

    render(<EmbeddingDetail id={mockEmbedding.id} />)

    await waitFor(() => {
      expect(screen.getByText('Delete Embedding')).toBeInTheDocument()
    })

    const deleteButton = screen.getByText('Delete Embedding')
    fireEvent.click(deleteButton)

    await waitFor(() => {
      expect(screen.getByText(errorMessage)).toBeInTheDocument()
    })
  })
})
