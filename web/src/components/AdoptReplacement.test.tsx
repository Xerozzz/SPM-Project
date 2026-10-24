import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import type { EventRequest } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import VenueBookingRequest from './VenueBookingRequest'

// SCRUM-133: the Coordinator adopts an approved replacement from the booking list.

const event = {
  id: 'req-1',
  name: 'Careers Fair',
  status: 'approved',
  start_at: '2030-01-01T01:00:00Z',
  end_at: '2030-01-01T07:00:00Z',
} as unknown as EventRequest

const original = {
  id: 'booking-1',
  venue_id: 'venue-1',
  session_label: 'Keynote',
  start_at: '2030-01-01T01:00:00Z',
  end_at: '2030-01-01T03:00:00Z',
  status: 'confirmed',
  conflict: null,
  replaces_booking_id: null,
}

const replacement = {
  ...original,
  id: 'booking-2',
  venue_id: 'venue-2',
  status: 'tentative',
  expires_at: '2029-12-30T01:00:00Z',
  replaces_booking_id: 'booking-1',
  adopted_at: null,
}

const venues = [
  { id: 'venue-1', name: 'Hall A', is_active: true },
  { id: 'venue-2', name: 'Hall B', is_active: true },
]

beforeEach(() => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'coord-1', roles: ['coordinator'] }),
  )
})

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderList(bookings: unknown[], adoptResponse?: () => Response) {
  let listed = bookings
  const adopted: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (init?.method === 'POST' && url.endsWith('/adopt')) {
      adopted.push(url)
      if (adoptResponse) return adoptResponse()
      const done = { ...replacement, adopted_at: '2029-12-02T02:00:00Z', adopted_by_id: 'coord-1' }
      listed = [{ ...original, status: 'cancelled' }, done]
      return json(done)
    }
    if (url.endsWith('/venue-bookings')) return json(listed)
    if (url === '/api/venues') return json(venues)
    throw new Error(`unexpected request ${url}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <VenueBookingRequest event={event} />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return adopted
}

describe('SCRUM-133 adopt a replacement', () => {
  test('AC1: adopting an approved replacement shows it adopted and the original cancelled', async () => {
    const adopted = renderList([original, replacement])

    fireEvent.click(
      await screen.findByRole('button', { name: 'Adopt this replacement for Keynote' }),
    )

    expect(await screen.findByText(/Adopted on/)).toHaveTextContent(
      'The original booking was cancelled.',
    )
    expect(adopted).toEqual(['/api/event-requests/req-1/venue-bookings/booking-2/adopt'])
    expect(screen.getByText('cancelled')).toBeInTheDocument()
  })

  test('AC2: a replacement Venue Staff have not approved offers no adoption', async () => {
    renderList([original, { ...replacement, status: 'pending' }])

    expect(await screen.findByText(/Replacement for Keynote at Hall A/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Adopt this replacement/ })).not.toBeInTheDocument()
  })

  test('AC4: a refused adoption says why and changes nothing on screen', async () => {
    renderList([original, replacement], () =>
      json({ detail: 'This arrangement has already been cancelled' }, 409),
    )

    fireEvent.click(
      await screen.findByRole('button', { name: 'Adopt this replacement for Keynote' }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This arrangement has already been cancelled',
    )
    expect(screen.queryByText(/Adopted on/)).not.toBeInTheDocument()
  })
})
