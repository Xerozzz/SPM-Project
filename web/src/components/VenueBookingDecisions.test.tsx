import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { VenueBookingDecision } from '../api/venueBookingDecisions'
import { AuthProvider } from '../auth/context'
import VenueBookingDecisions from './VenueBookingDecisions'

// SCRUM-40: the Venue Staff panel for reviewing and rejecting booking requests.

beforeEach(() => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'staff-1', roles: ['venue_staff'] }),
  )
})

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const PENDING: VenueBookingDecision = {
  id: 'booking-1',
  status: 'pending',
  venue_id: 'venue-1',
  venue_name: 'Hall A',
  venue_location: 'Level 2',
  event_request_id: 'event-1',
  event_name: 'Orientation Day',
  start_at: '2030-01-01T02:00:00Z',
  end_at: '2030-01-01T06:00:00Z',
  expected_attendance: 150,
  venue_requirement: 'Auditorium-type venue',
  accessibility_requirement: 'Step-free access',
  equipment_requirement: 'Projector-type requirement',
  layout_requirement: 'Theatre style',
  requested_by_id: 'coordinator-1',
  decided_by_id: null,
  decided_at: null,
  decision_reason: null,
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderPanel(fetcher: typeof fetch) {
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(fetcher)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <VenueBookingDecisions />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return spy
}

test('shows a pending request with its venue, event and requirements', async () => {
  renderPanel(async () => json([PENDING]))

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.getByText('Hall A, Level 2')).toBeInTheDocument()
  expect(screen.getByText('150')).toBeInTheDocument()
  expect(screen.getByText('Theatre style')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
})

test('shows an empty state when nothing is waiting', async () => {
  renderPanel(async () => json([]))

  expect(await screen.findByText('No booking requests are waiting.')).toBeInTheDocument()
})

test('rejecting sends the reason and shows the decision without a reload', async () => {
  const rejected = {
    ...PENDING,
    status: 'rejected',
    decided_by_id: 'staff-1',
    decided_at: '2029-12-01T01:00:00Z',
    decision_reason: 'Hall closed for works',
  }
  let decided = false
  const spy = renderPanel(async (_input, init) => {
    if (init?.method === 'POST') {
      decided = true
      return json(rejected)
    }
    return json([decided ? rejected : PENDING])
  })

  fireEvent.change(await screen.findByLabelText(/Reason for the Coordinator/), {
    target: { value: 'Hall closed for works' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Reject' }))

  expect(await screen.findByRole('status')).toHaveTextContent('Hall A has been rejected')
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull())
  expect(screen.getByText(/Hall closed for works/)).toBeInTheDocument()
  const post = spy.mock.calls.find(([, init]) => init?.method === 'POST')
  expect(post?.[0]).toBe('/api/venue-bookings/booking-1/reject')
  expect(JSON.parse(String(post?.[1]?.body))).toEqual({ reason: 'Hall closed for works' })
})

test('a refused decision shows the API message', async () => {
  renderPanel(async (_input, init) =>
    init?.method === 'POST'
      ? json({ detail: 'This booking request is already rejected' }, 409)
      : json([PENDING]),
  )

  fireEvent.click(await screen.findByRole('button', { name: 'Reject' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('already rejected')
})

test('shows each decided request by its own status', async () => {
  renderPanel(async () =>
    json([
      { ...PENDING, id: 'b-2', venue_name: 'Hall B', status: 'confirmed' },
      { ...PENDING, id: 'b-3', venue_name: 'Hall C', status: 'cancelled' },
    ]),
  )

  expect(await screen.findByText('Confirmed')).toBeInTheDocument()
  expect(screen.getByText('Cancelled')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull()
})
