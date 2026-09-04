import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { EmbeddingsList } from '../EmbeddingsList'
import { useEmbeddingsService } from '@/hooks/useEmbeddingsService'

vi.mock('@/hooks/useEmbeddingsService')

describe('EmbeddingsList', () => {
  const mockEmbeddings = [
    {
      id: 'emb-1',
      doc_id: 'doc-1',
      title: 'First Document',
      content: 'Content of the first document',
      embedding: [0.1, 0.2],
      embed_metadata: {},
      doc_metadata: {},
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      deleted_at: null,
    },
    {
      id: 'emb-2',
      doc_id: 'doc-2',
      title: 'Second Document',
      content: 'Content of the second document',
      embedding: [0.3, 0.4],
      embed_metadata: {},
      doc_metadata: {},
      created_at: '2026-01-02T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
      deleted_at: null,
    },
  ]

  const mockListQuery = {
    execute: vi.fn(),
    data: mockEmbeddings,
    isLoading: false,
    error: null,
  }

  const mockDeleteDocumentMutation = {
    mutateAsync: vi.fn(),
    isPending: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    const mockService = {
      list: mockListQuery,
      getEmbedding: {
        execute: vi.fn(),
        data: mockEmbeddings[0],
        isLoading: false,
        error: null,
      },
      deleteDocument: mockDeleteDocumentMutation,
      upload: { mutateAsync: vi.fn(), isPending: false },
      uploadFile: { mutateAsync: vi.fn(), isPending: false },
    }
    ;(useEmbeddingsService as unknown as ReturnType<typeof vi.fn>).mockReturnValue(mockService)
  })

  it('renders each document title as a clickable link', async () => {
    render(<EmbeddingsList />)

    const titleLink = await screen.findByRole('button', { name: 'First Document' })
    expect(titleLink).toBeInTheDocument()
  })

  it('shows the document content when its title is clicked', async () => {
    render(<EmbeddingsList />)

    const titleLink = await screen.findByRole('button', { name: 'First Document' })
    fireEvent.click(titleLink)

    await waitFor(() => {
      expect(screen.getByText('Content of the first document')).toBeInTheDocument()
    })
  })

  it('returns to the list when back is pressed from the detail view', async () => {
    render(<EmbeddingsList />)

    const titleLink = await screen.findByRole('button', { name: 'First Document' })
    fireEvent.click(titleLink)

    await waitFor(() => {
      expect(screen.getByText('Content of the first document')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /back/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'First Document' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Second Document' })).toBeInTheDocument()
    })
  })

  it('removes the document from the list after it is deleted from the detail view', async () => {
    mockDeleteDocumentMutation.mutateAsync.mockResolvedValue(undefined)
    global.confirm = vi.fn(() => true)

    render(<EmbeddingsList />)

    const titleLink = await screen.findByRole('button', { name: 'First Document' })
    fireEvent.click(titleLink)

    await waitFor(() => {
      expect(screen.getByText('Content of the first document')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Delete Document'))

    await waitFor(() => {
      expect(mockDeleteDocumentMutation.mutateAsync).toHaveBeenCalledWith('doc-1')
    })

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'First Document' })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Second Document' })).toBeInTheDocument()
    })
  })
})
