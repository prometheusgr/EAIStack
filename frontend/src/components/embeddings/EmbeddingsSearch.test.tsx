import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EmbeddingsSearch } from './EmbeddingsSearch'
import type { SemanticSearchResult } from '@/types/embeddings'

vi.mock('@/context/AuthContext', () => ({
  useAuth: () => ({
    token: 'test-token-123',
    isAuthenticated: true,
    user: { name: 'Test User' },
    refreshAccessToken: async () => false,
  }),
}))

const mockSearch = vi.fn()
const mockDelete = vi.fn()

vi.mock('@/hooks/useEmbeddingsService', () => ({
  useEmbeddingsService: () => ({
    search: {
      mutateAsync: mockSearch,
      isPending: false,
      error: null,
      data: null,
    },
    delete: {
      mutateAsync: mockDelete,
      isPending: false,
      error: null,
      data: null,
    },
  }),
}))

describe('EmbeddingsSearch', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render search input and button', () => {
    render(<EmbeddingsSearch />)
    expect(screen.getByPlaceholderText(/search by topic or content/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /search/i })).toBeInTheDocument()
  })

  it('should show empty state when no query is entered', () => {
    render(<EmbeddingsSearch />)
    expect(screen.getByText(/enter a query to search/i)).toBeInTheDocument()
  })

  it.skip('should disable submit button while loading', async () => {
    const user = userEvent.setup()
    mockSearch.mockImplementation(() => new Promise(() => {}))
    render(<EmbeddingsSearch />)
    const input = screen.getByPlaceholderText(/search by topic or content/i)
    const button = screen.getByRole('button', { name: /search/i })
    await user.type(input, 'test query')
    await user.click(button)
    expect(button).toBeDisabled()
    expect(screen.getByRole('button', { name: /searching/i })).toBeInTheDocument()
  })

  it('should call semanticSearch with query text on form submit', async () => {
    const user = userEvent.setup()
    mockSearch.mockResolvedValue([])
    render(<EmbeddingsSearch />)
    const input = screen.getByPlaceholderText(/search by topic or content/i)
    const button = screen.getByRole('button', { name: /search/i })
    await user.type(input, 'machine learning')
    await user.click(button)
    await waitFor(() => {
      expect(mockSearch).toHaveBeenCalled()
    })
  })

  it('should display search results after successful search', async () => {
    const user = userEvent.setup()
    const mockResults: SemanticSearchResult[] = [
      {
        id: 'emb-1',
        doc_id: 'doc-1',
        title: 'AI Basics',
        content: 'AI content',
        preview: 'AI content',
        similarity_score: 0.95,
        created_at: '2024-01-15T10:00:00Z',
      },
    ]
    mockSearch.mockResolvedValue(mockResults)
    render(<EmbeddingsSearch />)
    const input = screen.getByPlaceholderText(/search by topic or content/i)
    const button = screen.getByRole('button', { name: /search/i })
    await user.type(input, 'machine learning')
    await user.click(button)
    await waitFor(() => {
      expect(screen.getByText('AI Basics')).toBeInTheDocument()
    })
  })

  it('should display "no results found" when search returns empty', async () => {
    const user = userEvent.setup()
    mockSearch.mockResolvedValue([])
    render(<EmbeddingsSearch />)
    const input = screen.getByPlaceholderText(/search by topic or content/i)
    const button = screen.getByRole('button', { name: /search/i })
    await user.type(input, 'nonexistent')
    await user.click(button)
    await waitFor(() => {
      expect(screen.getByText(/no results found/i)).toBeInTheDocument()
    })
  })

  it.skip('should handle search errors', async () => {
    const user = userEvent.setup()
    mockSearch.mockRejectedValue(new Error('Network error'))
    render(<EmbeddingsSearch />)
    const input = screen.getByPlaceholderText(/search by topic or content/i)
    const button = screen.getByRole('button', { name: /search/i })
    await user.type(input, 'test')
    await user.click(button)
    await waitFor(() => {
      expect(screen.getByText(/network error/i)).toBeInTheDocument()
    })
  })

  it('should display similarity score as percentage', async () => {
    const user = userEvent.setup()
    const mockResults: SemanticSearchResult[] = [
      {
        id: 'emb-1',
        doc_id: 'doc-1',
        title: 'Result',
        content: 'Content',
        preview: 'Content',
        similarity_score: 0.856,
        created_at: '2024-01-15T10:00:00Z',
      },
    ]
    mockSearch.mockResolvedValue(mockResults)
    render(<EmbeddingsSearch />)
    const input = screen.getByPlaceholderText(/search by topic or content/i)
    const button = screen.getByRole('button', { name: /search/i })
    await user.type(input, 'test')
    await user.click(button)
    await waitFor(() => {
      expect(screen.getByText(/85\.6%/)).toBeInTheDocument()
    })
  })

  it('should not search if query is empty or whitespace only', async () => {
    const user = userEvent.setup()
    render(<EmbeddingsSearch />)
    const input = screen.getByPlaceholderText(/search by topic or content/i)
    const button = screen.getByRole('button', { name: /search/i })
    await user.type(input, '   ')
    await user.click(button)
    expect(mockSearch).not.toHaveBeenCalled()
  })
})
