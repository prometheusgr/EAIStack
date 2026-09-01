import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InfoTooltip } from './info-tooltip'

describe('InfoTooltip', () => {
  it('is hidden until the info icon receives hover or focus', async () => {
    const user = userEvent.setup()
    render(<InfoTooltip>Rejects input longer than this.</InfoTooltip>)

    expect(screen.queryByText('Rejects input longer than this.')).not.toBeInTheDocument()

    const trigger = screen.getByRole('button', { name: 'Show help' })
    await user.hover(trigger)

    expect(await screen.findByText('Rejects input longer than this.')).toBeInTheDocument()
  })

  it('is reachable and shows its content via keyboard focus, for non-mouse users', async () => {
    const user = userEvent.setup()
    render(<InfoTooltip>Keep forever if left empty.</InfoTooltip>)

    await user.tab()
    expect(screen.getByRole('button', { name: 'Show help' })).toHaveFocus()
    expect(await screen.findByText('Keep forever if left empty.')).toBeInTheDocument()
  })
})
