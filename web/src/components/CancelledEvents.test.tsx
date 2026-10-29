import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import type { CancelledEvent } from '../api/eventCancellation'
import { formatSingaporeTime } from '../api/venueCalendar'
import { AuthProvider } from '../auth/context'
import CancelledEvents from './CancelledEvents'

// SCRUM-88 AC6: the API decides which cancelled events each viewer may see; these tests
// prove the section asks for the right list, shows the record and opens the history.

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const CANCELLED_AT = '2026-11-02T03:00:00Z'
const OPEN_DAY: CancelledEvent = {
  id: 'ev-1',
  name: 'Open Day',
  start_at: '2026-12-01T02:00:00Z',
  cancelled_at: CANCELLED_AT,
  cancellation_reason: 'Speaker withdrew',
}

function renderAs(roles: string[], rows: CancelledEvent[]) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'u-1', roles }),
  )
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url === '/api/event-requests/assigned-cancelled' || url === '/api/event-requests/cancelled')
      return new Response(JSON.stringify(rows), { status: 200 })
    if (url === '/api/event-requests/ev-1/history')
      return new Response(JSON.stringify([]), { status: 200 })
    throw new Error(`unexpected request ${url}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <CancelledEvents />
      </AuthProvider>
    </QueryClientProvider>,
  )
  const urls = () => fetchMock.mock.calls.map(([input]) => String(input))
  return { ...view, urls }
}

describe('SCRUM-88 cancelled events offer the event history (frontend unit)', () => {
  test('a cancelled event shows its name, cancelled time and reason', async () => {
    renderAs(['coordinator'], [OPEN_DAY])

    const card = await screen.findByRole('article')

    expect(card).toHaveTextContent('Open Day')
    expect(card).toHaveTextContent(`Cancelled ${formatSingaporeTime(CANCELLED_AT)}.`)
    expect(card).toHaveTextContent('Reason: Speaker withdrew')
    expect(screen.queryByRole('button', { name: /cancel/i })).not.toBeInTheDocument()
  })

  test('the toggle opens that event history', async () => {
    const { urls } = renderAs(['coordinator'], [OPEN_DAY])

    fireEvent.click(await screen.findByRole('button', { name: 'View event history' }))

    expect(await screen.findByText('No history you can see for Open Day yet.')).toBeInTheDocument()
    expect(urls()).toContain('/api/event-requests/ev-1/history')
  })

  test('a Coordinator asks for their own cancelled events', async () => {
    const { urls } = renderAs(['coordinator'], [OPEN_DAY])

    await screen.findByRole('article')

    expect(urls()).toEqual(['/api/event-requests/assigned-cancelled'])
  })

  test('a Lead who is also a Coordinator asks only for every cancelled event', async () => {
    const { urls } = renderAs(['coordinator', 'coordinator_lead'], [OPEN_DAY])

    await screen.findByRole('article')

    expect(urls()).toEqual(['/api/event-requests/cancelled'])
  })

  test('with no cancelled events the section is not shown', async () => {
    const { urls, container } = renderAs(['coordinator_lead'], [])

    await waitFor(() => expect(urls()).toEqual(['/api/event-requests/cancelled']))

    expect(container).toBeEmptyDOMElement()
  })
})
