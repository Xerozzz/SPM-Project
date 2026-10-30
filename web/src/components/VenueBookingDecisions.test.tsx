import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { describeConflict, type VenueBookingDecision } from '../api/venueBookingDecisions'
import { AuthProvider } from '../auth/context'
import VenueBookingDecisions from './VenueBookingDecisions'

// SCRUM-40: the Venue Staff panel for reviewing and rejecting booking requests.
// SCRUM-75: the same panel shows clashes and approves.
// SCRUM-110: approval creates a time-limited tentative hold, so it needs an expiry.

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
  start_at: '2030-01-01T02:00:00Z',
  end_at: '2030-01-01T06:00:00Z',
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
  effective_start_at: '2030-01-01T02:00:00Z',
  effective_end_at: '2030-01-01T06:00:00Z',
  setup_minutes: 0,
  turnaround_minutes: 0,
  conflict: null,
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

// SCRUM-110: approval needs a hold expiry, so every test that clicks Approve enters one first.
async function enterExpiry(scope: Pick<typeof screen, 'findByLabelText'>) {
  fireEvent.change(await scope.findByLabelText('Hold until (Singapore time)'), {
    target: { value: '2029-12-31T10:00' },
  })
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

test('a refused decision shows its message on the request it belongs to', async () => {
  const other = { ...PENDING, id: 'booking-2', event_name: 'Careers Fair' }
  renderPanel(async (input, init) =>
    init?.method === 'POST' && String(input).includes('booking-2')
      ? json({ detail: 'This booking request is already rejected' }, 409)
      : json([PENDING, other]),
  )

  const cards = await screen.findAllByRole('article')
  fireEvent.click(within(cards[1]).getByRole('button', { name: 'Reject' }))

  expect(await within(cards[1]).findByRole('alert')).toHaveTextContent('already rejected')
  expect(within(cards[0]).queryByRole('alert')).toBeNull()
})

test('shows each decided request by its own status', async () => {
  renderPanel(async () =>
    json([
      { ...PENDING, id: 'b-2', venue_name: 'Hall B', status: 'confirmed' },
      { ...PENDING, id: 'b-3', venue_name: 'Hall C', status: 'cancelled' },
    ]),
  )

  expect((await screen.findAllByText('Confirmed')).length).toBeGreaterThan(0)
  expect(screen.getAllByText('Cancelled').length).toBeGreaterThan(0)
  expect(screen.getAllByText('When')).toHaveLength(2)
  expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull()

  fireEvent.click(screen.getAllByRole('button', { name: /View details/ })[0])

  expect(screen.queryByRole('tablist')).toBeNull()
  expect(screen.getByRole('button', { name: /Back to booking requests/ })).toBeInTheDocument()
})

test('SCRUM-75 AC1: a clash is shown and Approve is disabled', async () => {
  renderPanel(async () =>
    json([
      {
        ...PENDING,
        conflict: {
          kind: 'unavailability',
          id: 'closure-1',
          start_at: '2030-01-01T00:00:00Z',
          end_at: '2030-01-01T08:00:00Z',
          // A closure is never widened (SCRUM-82 AC5), so these match its own times.
          effective_start_at: '2030-01-01T00:00:00Z',
          effective_end_at: '2030-01-01T08:00:00Z',
          message: 'venue is unavailable for period closure-1',
        },
      },
    ]),
  )

  // The clash period must be in Singapore time whatever zone the browser is in.
  const sgt = (value: string) =>
    new Date(value).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })
  expect(
    await screen.findByText(
      `The venue is closed from ${sgt('2030-01-01T00:00:00Z')} to ${sgt('2030-01-01T08:00:00Z')}. It cannot be approved.`,
    ),
  ).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Reject' })).toBeEnabled()
})

test('SCRUM-110: Approve stays disabled until a hold expiry is entered', async () => {
  renderPanel(async () => json([PENDING]))

  const approve = await screen.findByRole('button', { name: 'Approve' })
  expect(approve).toBeDisabled()

  fireEvent.change(screen.getByLabelText('Hold until (Singapore time)'), {
    target: { value: '2029-12-31T10:00' },
  })
  expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled()
})

test('SCRUM-110: approving posts the expiry to the approve route and shows the hold', async () => {
  let approved = false
  const spy = renderPanel(async (_input, init) => {
    if (init?.method === 'POST') {
      approved = true
      expect(init.body).toBe(JSON.stringify({ expires_at: '2029-12-31T02:00:00.000Z' }))
      return json({ id: 'booking-1', status: 'tentative' })
    }
    return json([approved ? { ...PENDING, status: 'tentative' } : PENDING])
  })

  fireEvent.change(await screen.findByLabelText('Hold until (Singapore time)'), {
    target: { value: '2029-12-31T10:00' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

  expect(await screen.findByRole('status')).toHaveTextContent(
    'The request for Hall A is on a tentative hold.',
  )
  expect(await screen.findByText('Tentative hold')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
  const post = spy.mock.calls.find(([, init]) => init?.method === 'POST')
  expect(post?.[0]).toBe('/api/venue-bookings/booking-1/approve')
})

test('SCRUM-110: an invalid expiry shows the reason', async () => {
  renderPanel(async (_input, init) =>
    init?.method === 'POST'
      ? json({ detail: [{ loc: ['body', 'expires_at'], reason: 'must be in the future' }] }, 422)
      : json([PENDING]),
  )

  fireEvent.change(await screen.findByLabelText('Hold until (Singapore time)'), {
    target: { value: '2029-12-31T10:00' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Could not approve: Expiry must be in the future',
  )
})

test('SCRUM-75 AC3: a refused approval shows why', async () => {
  renderPanel(async (_input, init) =>
    init?.method === 'POST'
      ? json({ detail: 'conflicts with confirmed booking b-9' }, 409)
      : json([PENDING]),
  )

  await enterExpiry(screen)
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Could not approve: conflicts with confirmed booking b-9',
  )
})

test('SCRUM-75: a refusal from a stale list reloads it and shows the named clash', async () => {
  // The list loaded before a closure was recorded, so the card had no clash yet.
  let refused = false
  renderPanel(async (_input, init) => {
    if (init?.method === 'POST') {
      refused = true
      return json({ detail: 'venue is unavailable for period closure-1' }, 409)
    }
    return json([
      refused
        ? {
            ...PENDING,
            conflict: {
              kind: 'unavailability',
              id: 'closure-1',
              start_at: '2030-01-01T00:00:00Z',
              end_at: '2030-01-01T08:00:00Z',
              effective_start_at: '2030-01-01T00:00:00Z',
              effective_end_at: '2030-01-01T08:00:00Z',
              message: 'venue is unavailable for period closure-1',
            },
          }
        : PENDING,
    ])
  })

  await enterExpiry(screen)
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

  expect(
    await screen.findByText(/The venue is closed from .* It cannot be approved\./),
  ).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
  expect(screen.queryByText(/closure-1/)).toBeNull()
})

test('SCRUM-75: an old refusal goes away when the next decision is tried', async () => {
  let attempts = 0
  renderPanel(async (_input, init) => {
    if (init?.method === 'POST') {
      attempts += 1
      return attempts === 1
        ? json({ detail: 'conflicts with confirmed booking b-9' }, 409)
        : json({ ...PENDING, status: 'rejected' })
    }
    return json([PENDING])
  })

  await enterExpiry(screen)
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not approve')
  fireEvent.click(screen.getByRole('button', { name: 'Reject' }))

  await waitFor(() => expect(screen.queryByText(/Could not approve/)).toBeNull())
})

test('SCRUM-75: a refused approval shows its message on the request it belongs to', async () => {
  const other = { ...PENDING, id: 'booking-2', event_name: 'Careers Fair' }
  renderPanel(async (input, init) =>
    init?.method === 'POST' && String(input).includes('booking-2')
      ? json({ detail: 'conflicts with confirmed booking b-9' }, 409)
      : json([PENDING, other]),
  )

  const cards = await screen.findAllByRole('article')
  await enterExpiry(within(cards[1]))
  fireEvent.click(within(cards[1]).getByRole('button', { name: 'Approve' }))

  expect(await within(cards[1]).findByRole('alert')).toHaveTextContent('Could not approve')
  expect(within(cards[0]).queryByRole('alert')).toBeNull()
})

test('SCRUM-75: an old rejection error goes away when Approve is tried', async () => {
  renderPanel(async (input, init) => {
    if (init?.method === 'POST' && String(input).endsWith('/reject')) {
      return json({ detail: 'This booking request is already rejected' }, 409)
    }
    if (init?.method === 'POST') return json({ ...PENDING, status: 'tentative' })
    return json([PENDING])
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Reject' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('already rejected')
  await enterExpiry(screen)
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

  await waitFor(() => expect(screen.queryByText(/already rejected/)).toBeNull())
})

// ------------------------------------------------- SCRUM-82: buffers on screen
//
// Reported from testing: a request at 9:14 pm was refused for clashing with a booking
// "from 6:00 pm to 8:00 pm". On its face that is not a clash at all. What makes it one
// is the venue's 45 minutes of turnaround, and nothing on the screen said so.

const sgtOf = (value: string) =>
  new Date(value).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })

test('SCRUM-82: a refusal names the period the venue is held, not just the event', () => {
  const text = describeConflict({
    kind: 'booking',
    id: 'other-1',
    start_at: '2030-01-01T10:00:00Z',
    end_at: '2030-01-01T12:00:00Z',
    effective_start_at: '2030-01-01T09:30:00Z',
    effective_end_at: '2030-01-01T12:45:00Z',
    message: 'conflicts with confirmed booking other-1',
  })

  expect(text).toContain(sgtOf('2030-01-01T12:45:00Z'))
  expect(text).toContain('holding the venue')
  // The event period is still there, so the reader can tell the two apart.
  expect(text).toContain(sgtOf('2030-01-01T12:00:00Z'))
})

test('SCRUM-82 AC7: with no buffers the refusal keeps its plain wording', () => {
  const text = describeConflict({
    kind: 'booking',
    id: 'other-1',
    start_at: '2030-01-01T10:00:00Z',
    end_at: '2030-01-01T12:00:00Z',
    effective_start_at: '2030-01-01T10:00:00Z',
    effective_end_at: '2030-01-01T12:00:00Z',
    message: 'conflicts with confirmed booking other-1',
  })

  expect(text).toBe(
    `Clashes with a confirmed booking from ${sgtOf('2030-01-01T10:00:00Z')} to ${sgtOf(
      '2030-01-01T12:00:00Z',
    )}.`,
  )
})

test('SCRUM-82 AC3: the request card says how long the venue is held for', async () => {
  const buffered: VenueBookingDecision = {
    ...PENDING,
    effective_start_at: '2030-01-01T01:30:00Z',
    effective_end_at: '2030-01-01T06:45:00Z',
    setup_minutes: 30,
    turnaround_minutes: 45,
  }
  renderPanel(async () => json([buffered]))

  await screen.findByText('Orientation Day')
  expect(screen.getByText('Venue held:')).toBeInTheDocument()
  expect(
    screen.getByText(
      `${sgtOf('2030-01-01T01:30:00Z')} to ${sgtOf(
        '2030-01-01T06:45:00Z',
      )} (30 min setup, 45 min turnaround)`,
    ),
  ).toBeInTheDocument()
})

test('SCRUM-82 AC7: a venue with no buffers has no held line to show', async () => {
  renderPanel(async () => json([PENDING]))

  await screen.findByText('Orientation Day')
  // Absent, not shown empty: the row renders "Not given" for a null value.
  expect(screen.queryByText('Venue held:')).toBeNull()
})

// ------------------------------------- SCRUM-43: what the event needs now, not then
//
// Venue Staff decide whether their venue suits an event. They were shown
// `equipment_requirement`, the single string the organiser submitted, which nothing
// writes back to (ADR-0033). The moment a Coordinator changed anything, the queue was
// asking for a decision on a stale answer.

test('SCRUM-43: the queue lists every requirement the event currently has', async () => {
  renderPanel(async () =>
    json([{ ...PENDING, equipment_requirements: ['Projector x2', 'Microphone x3'] }]),
  )

  await screen.findByText('Orientation Day')
  expect(screen.getByText('Projector x2, Microphone x3')).toBeInTheDocument()
})

test('SCRUM-43: an event needing nothing says so rather than looking unanswered', async () => {
  // The row renders "Not given" for a null, which reads as missing information. The
  // Coordinator recording nothing is an answer, not a gap.
  renderPanel(async () => json([{ ...PENDING, equipment_requirements: [] }]))

  await screen.findByText('Orientation Day')
  expect(screen.getByText('None recorded')).toBeInTheDocument()
  expect(screen.queryByText('Not given')).toBeNull()
})
