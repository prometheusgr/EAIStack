import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from '../src/App'

describe('Phase 0 Scaffold', () => {
  it('should render the App component', () => {
    render(<App />)
    expect(screen.getByText('EAIStack Frontend')).toBeInTheDocument()
  })

  it('should display the phase 0 message', () => {
    render(<App />)
    expect(screen.getByText(/Phase 0 scaffold/i)).toBeInTheDocument()
  })
})
