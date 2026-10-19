import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { CalendarEntry, CalendarEntryDetails } from '../api/venueCalendar'
import {
  describeConflict,
  singaporeLocalToUtc,
  type VenueBookingDecision,
} from '../api/venueBookingDecisions'
import { AuthProvider } from '../auth/context'
import EventRequestReview from './EventRequestReview'
import VenueBookingDecisions from './VenueBookingDecisions'
import VenueCalendar from './VenueCalendar'

// SCRUM-83: Venue Staff place tentative holds, and holds are shown as Tentative.
// SCRUM-110: approval creates the hold, so the pending card approves with an expiry.

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
  session_label: 'Morning workshop',
  start_at: '2030-01-10T02:00:00Z',
  end_at: '2030-01-10T06:00:00Z',
  expected_attendance: 150,
  venue_requirement: 'Hall A',
  accessibility_requirement: 'Step-free access',
  equipment_requirements: ['Projector x1'],
  layout_requirement: 'Theatre style',
  requested_by_id: 'coordinator-1',
  decided_by_id: null,
  decided_at: null,
  decision_reason: null,
  // No buffers on this venue, so the held period is the event period (AC7).
  effective_start_at: '2030-01-10T02:00:00Z',
  effective_end_at: '2030-01-10T06:00:00Z',
  setup_minutes: 0,
  turnaround_minutes: 0,
  expires_at: null,
  held_by_id: null,
  held_at: null,
  coordinator_id: 'coordinator-1',
  conflict: null,
}

const HELD: VenueBookingDecision = {
  ...PENDING,
  status: 'tentative',
  expires_at: '2030-01-05T09:00:00Z',
  held_by_id: 'staff-1',
  held_at: '2030-01-01T01:00:00Z',
}

const sgt = (value: string) =>
  new Date(value).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderWith(ui: ReactNode, fetcher: typeof fetch) {
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(fetcher)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>{ui}</AuthProvider>
    </QueryClientProvider>,
  )
  return spy
}

// ------------------------------------------------------------------ AC1: placing a hold

test('SCRUM-83: a Singapore wall-clock expiry is sent as the same instant in UTC', () => {
  expect(singaporeLocalToUtc('2030-01-05T17:00')).toBe('2030-01-05T09:00:00.000Z')
})

test('SCRUM-110: Venue Staff approve with an expiry and it moves to Tentative holds', async () => {
  let rows: VenueBookingDecision[] = [PENDING]
  const spy = renderWith(<VenueBookingDecisions />, async (_input, init) => {
    if (init?.method === 'POST') {
      rows = [HELD]
      return json(HELD)
    }
    return json(rows)
  })

  const card = (await screen.findByText('Orientation Day')).closest('article') as HTMLElement
  fireEvent.change(within(card).getByLabelText('Hold until (Singapore time)'), {
    target: { value: '2030-01-05T17:00' },
  })
  fireEvent.click(within(card).getByRole('button', { name: 'Approve' }))

  expect(
    await screen.findByText('The request for Hall A is on a tentative hold.'),
  ).toBeInTheDocument()
  const post = spy.mock.calls.find(([, init]) => init?.method === 'POST')
  expect(String(post?.[0])).toBe('/api/venue-bookings/booking-1/approve')
  expect(JSON.parse(String(post?.[1]?.body))).toEqual({ expires_at: '2030-01-05T09:00:00.000Z' })
  expect(await screen.findByRole('heading', { name: 'Tentative holds' })).toBeInTheDocument()
  expect(screen.getByText(`Tentative hold until ${sgt(HELD.expires_at ?? '')}`)).toBeInTheDocument()
})

test('SCRUM-110: Approve waits for an expiry and is off when there is a clash', async () => {
  renderWith(<VenueBookingDecisions />, async () =>
    json([
      PENDING,
      {
        ...PENDING,
        id: 'booking-2',
        event_name: 'Careers Fair',
        conflict: {
          kind: 'booking',
          id: 'b-9',
          start_at: PENDING.start_at,
          end_at: PENDING.end_at,
          message: 'conflicts with confirmed booking b-9',
        },
      },
    ]),
  )

  const free = (await screen.findByText('Orientation Day')).closest('article') as HTMLElement
  const clashing = screen.getByText('Careers Fair').closest('article') as HTMLElement
  expect(within(free).getByRole('button', { name: 'Approve' })).toBeDisabled()

  fireEvent.change(within(free).getByLabelText('Hold until (Singapore time)'), {
    target: { value: '2030-01-05T17:00' },
  })
  fireEvent.change(within(clashing).getByLabelText('Hold until (Singapore time)'), {
    target: { value: '2030-01-05T17:00' },
  })

  expect(within(free).getByRole('button', { name: 'Approve' })).toBeEnabled()
  expect(within(clashing).getByRole('button', { name: 'Approve' })).toBeDisabled()
})

test('SCRUM-110: a refused approval shows why, on the card it belongs to', async () => {
  renderWith(<VenueBookingDecisions />, async (_input, init) =>
    init?.method === 'POST'
      ? json({ detail: [{ field: 'expires_at', reason: 'must be in the future' }] }, 422)
      : json([PENDING, { ...PENDING, id: 'booking-2', event_name: 'Careers Fair' }]),
  )

  const card = (await screen.findByText('Orientation Day')).closest('article') as HTMLElement
  const other = screen.getByText('Careers Fair').closest('article') as HTMLElement
  fireEvent.change(within(card).getByLabelText('Hold until (Singapore time)'), {
    target: { value: '2020-01-05T17:00' },
  })
  fireEvent.click(within(card).getByRole('button', { name: 'Approve' }))

  expect(await within(card).findByRole('alert')).toHaveTextContent(
    'Could not approve: Expiry must be in the future',
  )
  expect(within(other).queryByRole('alert')).toBeNull()
})

test('SCRUM-110: a clash with another request shows the API message', async () => {
  renderWith(<VenueBookingDecisions />, async (_input, init) =>
    init?.method === 'POST'
      ? json({ detail: 'conflicts with tentative hold b-7' }, 409)
      : json([PENDING]),
  )

  const card = (await screen.findByText('Orientation Day')).closest('article') as HTMLElement
  fireEvent.change(within(card).getByLabelText('Hold until (Singapore time)'), {
    target: { value: '2030-01-05T17:00' },
  })
  fireEvent.click(within(card).getByRole('button', { name: 'Approve' }))

  expect(await within(card).findByRole('alert')).toHaveTextContent(
    'Could not approve: conflicts with tentative hold b-7',
  )
})

// ------------------------------------------------------------------ AC2: shown as Tentative

test('SCRUM-83 AC2: a held request is shown apart, without rejection or approval', async () => {
  renderWith(<VenueBookingDecisions />, async () => json([HELD]))

  const section = await screen.findByRole('heading', { name: 'Tentative holds' })
  expect(section).toBeInTheDocument()
  // SCRUM-110: a hold is terminal until it expires, so neither Reject nor Approve is offered.
  expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
  expect(screen.queryByRole('heading', { name: 'Decided' })).toBeNull()
})

test('SCRUM-83 AC2: the calendar labels a hold Tentative and says until when', async () => {
  const hold: CalendarEntry = {
    kind: 'booking',
    id: 'b-1',
    venue_id: 'v-1',
    venue_name: 'Hall A',
    start_at: '2030-03-04T01:00:00Z',
    end_at: '2030-03-04T03:00:00Z',
    effective_start_at: '2030-03-04T01:00:00Z',
    effective_end_at: '2030-03-04T03:00:00Z',
    status: 'tentative',
    expires_at: '2030-03-01T09:00:00Z',
  }
  const details: CalendarEntryDetails = {
    kind: 'booking',
    id: 'b-1',
    venue_id: 'v-1',
    venue_name: 'Hall A',
    venue_location: 'Level 2',
    start_at: hold.start_at,
    end_at: hold.end_at,
    status: 'tentative',
    reason: null,
    event_request_id: null,
    expires_at: hold.expires_at,
  }
  renderWith(<VenueCalendar />, async (input) => {
    const url = String(input)
    if (url.startsWith('/api/venues')) return json([{ id: 'v-1', name: 'Hall A' }])
    if (url.startsWith('/api/venue-calendar/bookings/')) return json(details)
    return json([hold, { ...hold, id: 'b-2', status: 'confirmed', expires_at: null }])
  })

  const entry = await screen.findByRole('button', { name: /Tentative hold/ })
  expect(entry).toHaveTextContent(`Held until ${sgt('2030-03-01T09:00:00Z')}`)
  expect(screen.getByRole('button', { name: /Confirmed booking/ })).not.toHaveTextContent(
    'Held until',
  )

  fireEvent.click(entry)
  const panel = await screen.findByRole('article', { name: 'Entry details' })
  await waitFor(() => expect(panel).toHaveTextContent('Tentative hold'))
  expect(panel).toHaveTextContent(`Held until: ${sgt('2030-03-01T09:00:00Z')}`)
})

// ------------------------------------------------------------------ AC3: clashes named

test('SCRUM-83 AC3: a clash with a hold is described as a tentative hold', () => {
  expect(
    describeConflict({
      kind: 'hold',
      id: 'b-7',
      start_at: '2030-01-10T02:00:00Z',
      end_at: '2030-01-10T06:00:00Z',
      effective_start_at: '2030-01-10T02:00:00Z',
      effective_end_at: '2030-01-10T06:00:00Z',
      message: 'conflicts with tentative hold b-7',
    }),
  ).toBe(
    `Clashes with a tentative hold from ${sgt('2030-01-10T02:00:00Z')} to ${sgt('2030-01-10T06:00:00Z')}.`,
  )
})

test('SCRUM-83 AC2: the Coordinator sees their request is on a tentative hold', async () => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'coordinator-1', roles: ['coordinator'] }),
  )
  const approved = {
    id: 'event-1',
    status: 'approved',
    name: 'Orientation Day',
    purpose: 'Welcome students',
    description: 'Talks',
    start_at: PENDING.start_at,
    end_at: PENDING.end_at,
    expected_attendance: 150,
    venue_requirement: 'Hall A',
    accessibility_requirement: 'Step-free access',
    equipment_requirements: ['Projector x1'],
    layout_requirement: 'Theatre style',
    registration_requirement: 'Open',
    status_permits: [],
    coordinator_id: 'coordinator-1',
  }
  renderWith(<EventRequestReview />, async (input) => {
    const url = String(input)
    if (url === '/api/event-requests/reviewable') return json([])
    if (url === '/api/event-requests/bookable') return json([approved])
    if (url === '/api/venues') return json([{ id: 'venue-1', name: 'Hall A', is_active: true }])
    if (url.endsWith('/clarifications')) return json([])
    if (url.endsWith('/venue-bookings')) {
      return json([
        {
          id: 'booking-1',
          venue_id: 'venue-1',
          start_at: PENDING.start_at,
          end_at: PENDING.end_at,
          status: 'tentative',
          expires_at: HELD.expires_at,
          conflict: null,
        },
      ])
    }
    throw new Error(`unexpected request ${url}`)
  })

  expect(
    await screen.findByText(
      `tentative hold until ${sgt(HELD.expires_at ?? '')}`,
    ),
  ).toBeInTheDocument()
})

// ------------------------------------------------------------------ SCRUM-110
//
// Approval creates the hold, so a hold is never offered for approval: it is terminal
// until it expires (SCRUM-108) or is confirmed by the SCRUM-80 flow.

test('SCRUM-110: an active hold is shown with its expiry and no approval control', async () => {
  renderWith(<VenueBookingDecisions />, async () =>
    json([{ ...HELD, expires_at: '2099-01-01T00:00:00Z' }]),
  )

  expect(await screen.findByRole('heading', { name: 'Tentative holds' })).toBeInTheDocument()
  expect(
    screen.getByText(`Tentative hold until ${sgt('2099-01-01T00:00:00Z')}`),
  ).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
  expect(screen.queryByRole('heading', { name: 'Decided' })).toBeNull()
})

test('SCRUM-110: an expired hold says so and offers no approval', async () => {
  renderWith(<VenueBookingDecisions />, async () =>
    json([{ ...HELD, expires_at: '2020-01-01T00:00:00Z' }]),
  )

  expect(await screen.findByText('This hold has expired.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
})

test('SCRUM-110: a hold with a clash names it and offers no approval', async () => {
  renderWith(<VenueBookingDecisions />, async () =>
    json([
      {
        ...HELD,
        expires_at: '2099-01-01T00:00:00Z',
        conflict: {
          kind: 'unavailability',
          id: 'closure-1',
          start_at: HELD.start_at,
          end_at: HELD.end_at,
          message: 'venue is unavailable for period closure-1',
        },
      },
    ]),
  )

  expect(await screen.findByText(/The venue is closed from/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
})

// ------------------------------------------------------------------ SCRUM-108

const EXPIRED: VenueBookingDecision = {
  ...HELD,
  status: 'expired',
  expires_at: '2030-01-05T09:00:00Z',
}

test('SCRUM-108 AC2: an expired hold is kept and shown as Expired with its expiry', async () => {
  renderWith(<VenueBookingDecisions />, async () => json([EXPIRED]))

  expect(await screen.findByRole('heading', { name: 'Decided' })).toBeInTheDocument()
  expect(screen.getByText(`Expired hold at ${sgt('2030-01-05T09:00:00Z')}`)).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Tentative holds' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
})

test('SCRUM-108: the Coordinator sees that their hold expired', async () => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'coordinator-1', roles: ['coordinator'] }),
  )
  renderWith(<EventRequestReview />, async (input) => {
    const url = String(input)
    if (url === '/api/event-requests/reviewable') return json([])
    if (url === '/api/event-requests/bookable') {
      return json([
        {
          id: 'event-1',
          status: 'approved',
          name: 'Orientation Day',
          purpose: 'Welcome',
          description: 'Talks',
          start_at: PENDING.start_at,
          end_at: PENDING.end_at,
          expected_attendance: 150,
          venue_requirement: 'Hall A',
          accessibility_requirement: 'Step-free access',
          equipment_requirements: ['Projector x1'],
          layout_requirement: 'Theatre style',
          registration_requirement: 'Open',
          status_permits: [],
          coordinator_id: 'coordinator-1',
        },
      ])
    }
    if (url === '/api/venues') return json([{ id: 'venue-1', name: 'Hall A', is_active: true }])
    if (url.endsWith('/clarifications')) return json([])
    if (url.endsWith('/venue-bookings')) {
      return json([
        {
          id: 'booking-1',
          venue_id: 'venue-1',
          start_at: PENDING.start_at,
          end_at: PENDING.end_at,
          status: 'expired',
          expires_at: EXPIRED.expires_at,
          conflict: null,
        },
      ])
    }
    throw new Error(`unexpected request ${url}`)
  })

  expect(
    await screen.findByText(
      `tentative hold expired at ${sgt(EXPIRED.expires_at ?? '')}`,
    ),
  ).toBeInTheDocument()
})
