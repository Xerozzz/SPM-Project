import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import type { EventRequest } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import VenueBookingRequest from './VenueBookingRequest'

// SCRUM-116: the Coordinator starts a replacement from an affected venue arrangement.

const event = {
  id: 'req-1',
  name: 'Careers Fair',
  status: 'approved',
  start_at: '2030-01-01T01:00:00Z',
  end_at: '2030-01-01T07:00:00Z',
} as unknown as EventRequest

const closure = {
  kind: 'unavailability',
  id: 'closure-1',
  start_at: '2030-01-01T01:00:00Z',
  end_at: '2030-01-01T03:00:00Z',
  effective_start_at: '2030-01-01T01:00:00Z',
  effective_end_at: '2030-01-01T03:00:00Z',
  message: 'venue is unavailable',
}

const affected = {
  id: 'booking-1',
  venue_id: 'venue-1',
  session_label: 'Keynote',
  start_at: '2030-01-01T01:00:00Z',
  end_at: '2030-01-01T03:00:00Z',
  status: 'confirmed',
  conflict: closure,
  replaces_booking_id: null,
}

const suitability = {
  mismatch_codes: [],
  expected_attendance: 50,
  venue_capacity: 100,
  unavailable_facilities: [],
  accessibility_need: null,
  venue_accessibility: [],
  layout_need: null,
  venue_layouts: [],
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

function renderList(bookings: unknown[]) {
  let listed = bookings
  const posted: Record<string, unknown>[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)) as Record<string, unknown>
      posted.push(body)
      const created = { ...affected, ...body, id: 'booking-2', status: 'pending', conflict: null }
      listed = [...listed, created]
      return json({ ...created, suitability }, 201)
    }
    if (url.endsWith('/venue-bookings')) return json(listed)
    if (url.includes('/suitability')) return json(suitability)
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
  return posted
}

describe('SCRUM-116 linked replacement', () => {
  test('AC1, AC2: a replacement keeps the session and period and links to the original', async () => {
    const posted = renderList([affected])

    fireEvent.click(await screen.findByRole('button', { name: 'Find a replacement for Keynote' }))

    expect(screen.getByRole('note')).toHaveTextContent('Requesting a replacement for Keynote')
    expect(screen.getByLabelText('Session label')).toBeDisabled()
    expect(screen.getByLabelText('Session label')).toHaveValue('Keynote')
    expect(screen.getByLabelText('Session start')).toBeDisabled()
    fireEvent.change(await screen.findByLabelText('Active venue'), {
      target: { value: 'venue-2' },
    })
    const send = screen.getByRole('button', { name: 'Submit booking request' })
    await waitFor(() => expect(send).toBeEnabled())
    fireEvent.click(send)

    expect(await screen.findByText(/Replacement for Keynote at Hall A/)).toBeInTheDocument()
    expect(posted).toEqual([
      {
        venue_id: 'venue-2',
        session_label: 'Keynote',
        start_at: '2030-01-01T01:00:00.000Z',
        end_at: '2030-01-01T03:00:00.000Z',
        replaces_booking_id: 'booking-1',
      },
    ])
    // AC3: the original stays, shows its replacement, and offers no second one.
    const items = screen.getAllByRole('listitem')
    expect(within(items[0]).getByText(/Replacement requested at Hall B \(pending\)/)).toBeVisible()
    expect(screen.queryByRole('button', { name: /Find a replacement/ })).not.toBeInTheDocument()
  })

  test('AC6: after a rejected replacement another one can be requested', async () => {
    renderList([
      affected,
      {
        ...affected,
        id: 'booking-2',
        venue_id: 'venue-2',
        status: 'rejected',
        conflict: null,
        replaces_booking_id: 'booking-1',
      },
    ])

    expect(
      await screen.findByRole('button', { name: 'Find a replacement for Keynote' }),
    ).toBeInTheDocument()
  })

  test('an arrangement that needs nothing offers no replacement', async () => {
    renderList([{ ...affected, conflict: null }])

    expect(await screen.findByText('Keynote')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Find a replacement/ })).not.toBeInTheDocument()
  })
})
