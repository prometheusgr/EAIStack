import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from '../src/App'

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
