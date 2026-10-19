import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import EventRequestReview from './EventRequestReview'

// SCRUM-38: coordinators discover their approved events, assess venue suitability, and
// submit pending booking requests without treating suitability warnings as blockers.

const submitted = {
  id: 'req-1',
  status: 'submitted',
  name: 'Orientation Day',
  purpose: 'Welcome students',
  description: 'Talks and tours',
  start_at: '2026-12-01T01:00:00Z',
  end_at: '2026-12-01T05:00:00Z',
  expected_attendance: 200,
  venue_requirement: 'Auditorium',
  accessibility_requirement: 'Step-free access',
  equipment_requirement: 'Projector',
  layout_requirement: 'Theatre',
  registration_requirement: 'Open registration',
  status_permits: ['approve', 'reject'],
  coordinator_id: 'user-1',
}

const approved = { ...submitted, status: 'approved', status_permits: [] }

const suitability = {
  mismatch_codes: ['CAPACITY_EXCEEDED'],
  expected_attendance: 200,
  venue_capacity: 100,
  unavailable_facilities: ['Projector'],
  accessibility_need: 'Step-free access',
  venue_accessibility: ['Lift access'],
  layout_need: 'Theatre',
  venue_layouts: ['classroom'],
}

const pendingBooking = {
  id: 'booking-1',
  venue_id: 'venue-1',
  start_at: approved.start_at,
  end_at: approved.end_at,
  status: 'pending',
}

const rejectedBooking = {
  id: 'booking-2',
  venue_id: 'venue-2',
  start_at: approved.start_at,
  end_at: approved.end_at,
  status: 'rejected',
}

function bookingPeriod(booking: { start_at: string; end_at: string }) {
  // Singapore time, because that is what the screen shows. Using the machine's own
  // locale passed here and would have failed on CI, which runs in UTC.
  const sgt = (value: string) =>
    new Date(value).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })
  return `${sgt(booking.start_at)} to ${sgt(booking.end_at)}`
}

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

function signInAsCoordinator() {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'user-1', roles: ['coordinator'] }),
  )
}

function renderReview(reviewable: unknown[], bookable: unknown[] = []) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    if (key === 'GET /api/event-requests/reviewable') return json(reviewable)
    if (key === 'GET /api/event-requests/bookable') return json(bookable)
    if (key.startsWith('GET ') && key.endsWith('/venue-bookings')) return json([])
    if (key === 'GET /api/venues') return json([])
    if (key.endsWith('/clarifications')) return json([])
    // SCRUM-43 put an equipment editor on this card; empty is enough for these tests.
    if (key.endsWith('/equipment-requirements')) return json([])
    if (key.endsWith('/catalogue-types')) return json([])
    if (key === 'POST /api/event-requests/req-1/approve') {
      return json({ ...submitted, status: 'approved' })
    }
    throw new Error(`unexpected request ${key}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <EventRequestReview />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

function renderBookingReview(submission: unknown, status = 200, existingBookings: unknown[] = []) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    if (key === 'GET /api/event-requests/reviewable') return json([])
    if (key === 'GET /api/event-requests/bookable') return json([approved])
    if (key.startsWith('GET ') && key.endsWith('/venue-bookings')) return json(existingBookings)
    if (key === 'GET /api/venues') {
      return json([{ id: 'venue-1', name: 'Small Hall', is_active: true }])
    }
    if (key.endsWith('/clarifications')) return json([])
    // SCRUM-43 put an equipment editor on this card; empty is enough for these tests.
    if (key.endsWith('/equipment-requirements')) return json([])
    if (key.endsWith('/catalogue-types')) return json([])
    if (key.includes('/venue-bookings/suitability?venue_id=venue-1')) return json(suitability)
    if (key === 'POST /api/event-requests/req-1/venue-bookings') {
      return submission instanceof Response ? submission : json(submission, status)
    }
    throw new Error(`unexpected request ${key}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <EventRequestReview />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

function renderExistingBookingReview(existingBookings: unknown[]) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    if (key === 'GET /api/event-requests/reviewable') return json([])
    if (key === 'GET /api/event-requests/bookable') return json([approved])
    if (key.startsWith('GET ') && key.endsWith('/venue-bookings')) return json(existingBookings)
    if (key === 'GET /api/venues') {
      return json([{ id: 'venue-1', name: 'Small Hall', is_active: true }])
    }
    if (key.endsWith('/clarifications')) return json([])
    // SCRUM-43 put an equipment editor on this card; empty is enough for these tests.
    if (key.endsWith('/equipment-requirements')) return json([])
    if (key.endsWith('/catalogue-types')) return json([])
    throw new Error(`unexpected request ${key}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <EventRequestReview />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

test('coordinator reviews a request assigned to them and approves it', async () => {
  signInAsCoordinator()
  renderReview([submitted])

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.getByText('Auditorium')).toBeInTheDocument()
  expect(screen.getByLabelText('Internal note')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
  expect(await screen.findByRole('status')).toHaveTextContent(
    '“Orientation Day” has been approved.',
  )
})

test('SCRUM-104: the coordinator list holds only assigned events, so each card is actionable', async () => {
  // The API scopes /reviewable to the signed-in coordinator and refuses other events
  // with 403, so someone else's event never reaches this list — there is no read-only
  // card state to assert on. Every rendered card offers the status-permitted decision.
  signInAsCoordinator()
  renderReview([submitted])

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
  expect(screen.queryByText(/Assigned to another coordinator/)).not.toBeInTheDocument()
  expect(screen.queryByText(/Not assigned to a coordinator yet/)).not.toBeInTheDocument()
})

test('coordinator events include submitted and approved bookable requests', async () => {
  signInAsCoordinator()
  const awardsNight = {
    ...submitted,
    id: 'req-2',
    name: 'Awards Night',
    status: 'approved',
    status_permits: [],
  }
  renderReview([submitted], [awardsNight])

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.getByText('Awards Night')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: 'Venue booking request' })).toBeInTheDocument()
})

// SCRUM-71: coordinators see retained venue booking requests, while submission
// behaviour stays owned by SCRUM-38, extended by SCRUM-78 for additional venues.

test('SCRUM-78: pending venue booking history keeps the submission form available', async () => {
  signInAsCoordinator()
  renderExistingBookingReview([pendingBooking])

  expect(
    await screen.findByRole('heading', { name: 'Existing venue booking requests' }),
  ).toBeInTheDocument()
  expect(screen.getByText('pending')).toBeInTheDocument()
  const bookingRecord = screen.getByRole('listitem')
  expect(await within(bookingRecord).findByText('Small Hall')).toBeInTheDocument()
  expect(within(bookingRecord).getByText(bookingPeriod(pendingBooking))).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Venue booking request' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Submit booking request' })).toBeInTheDocument()
})

test('multiple venue bookings are displayed as independent records', async () => {
  signInAsCoordinator()
  renderExistingBookingReview([pendingBooking, rejectedBooking])

  expect(
    await screen.findByRole('heading', { name: 'Existing venue booking requests' }),
  ).toBeInTheDocument()
  expect(screen.getByText('pending')).toBeInTheDocument()
  const bookingRecords = screen.getAllByRole('listitem')
  expect(await within(bookingRecords[0]).findByText('Small Hall')).toBeInTheDocument()
  expect(within(bookingRecords[0]).getByText(bookingPeriod(pendingBooking))).toBeInTheDocument()
  expect(screen.getByText('rejected')).toBeInTheDocument()
  expect(screen.getByText('venue-2')).toBeInTheDocument()
  expect(within(bookingRecords[1]).getByText(bookingPeriod(rejectedBooking))).toBeInTheDocument()
  expect(bookingRecords).toHaveLength(2)
  // SCRUM-78: independent history does not prevent another submission.
  expect(screen.getByRole('button', { name: 'Submit booking request' })).toBeInTheDocument()
})

test('no existing venue booking keeps the normal submission form available', async () => {
  signInAsCoordinator()
  renderBookingReview({
    id: 'booking-1',
    venue_id: 'venue-1',
    start_at: approved.start_at,
    end_at: approved.end_at,
    status: 'pending',
    suitability,
  })

  expect(await screen.findByRole('heading', { name: 'Venue booking request' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Submit booking request' })).toBeInTheDocument()
})

test('rejected-only venue booking history keeps the normal submission form available', async () => {
  signInAsCoordinator()
  renderBookingReview(
    {
      id: 'booking-2',
      venue_id: 'venue-1',
      start_at: approved.start_at,
      end_at: approved.end_at,
      status: 'pending',
      suitability,
    },
    200,
    [rejectedBooking],
  )

  expect(
    await screen.findByRole('heading', { name: 'Existing venue booking requests' }),
  ).toBeInTheDocument()
  expect(screen.getByText('rejected')).toBeInTheDocument()
  expect(screen.getByText(bookingPeriod(rejectedBooking))).toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: 'Venue booking request' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Submit booking request' })).toBeInTheDocument()
})

test('SCRUM-78: adds another venue, retains both records on reload and accepts a third', async () => {
  signInAsCoordinator()
  const retainedBookings = [pendingBooking]
  const suitable = {
    ...suitability,
    mismatch_codes: [],
    venue_capacity: 300,
    unavailable_facilities: [],
  }
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    if (key === 'GET /api/event-requests/reviewable') return json([])
    if (key === 'GET /api/event-requests/bookable') return json([approved])
    if (key.startsWith('GET ') && key.endsWith('/venue-bookings')) return json(retainedBookings)
    if (key === 'GET /api/venues') {
      return json([
        { id: 'venue-1', name: 'Small Hall', is_active: true },
        { id: 'venue-2', name: 'Large Hall', is_active: true },
        { id: 'venue-3', name: 'Studio', is_active: true },
      ])
    }
    if (key.endsWith('/clarifications')) return json([])
    // SCRUM-43 put an equipment editor on this card; empty is enough for these tests.
    if (key.endsWith('/equipment-requirements')) return json([])
    if (key.endsWith('/catalogue-types')) return json([])
    if (key.includes('/venue-bookings/suitability?venue_id=')) {
      return json(key.endsWith('venue-2') ? suitable : suitability)
    }
    if (key === 'POST /api/event-requests/req-1/venue-bookings') {
      const { venue_id } = JSON.parse(String(init?.body)) as { venue_id: string }
      const booking = { ...pendingBooking, id: `booking-${retainedBookings.length + 1}`, venue_id }
      retainedBookings.push(booking)
      return json({ ...booking, suitability: venue_id === 'venue-2' ? suitable : suitability }, 201)
    }
    throw new Error(`unexpected request ${key}`)
  })
  const mount = () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <EventRequestReview />
        </AuthProvider>
      </QueryClientProvider>,
    )
  }
  const view = mount()

  expect(
    await screen.findByRole('heading', { name: 'Existing venue booking requests' }),
  ).toBeInTheDocument()
  await screen.findByRole('option', { name: 'Large Hall' })
  fireEvent.change(screen.getByLabelText('Active venue'), { target: { value: 'venue-2' } })
  expect(await screen.findByText('Capacity and facilities are suitable.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Submit booking request' }))
  await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(2))
  const records = screen.getAllByRole('listitem')
  expect(within(records[0]).getByText('Small Hall')).toBeInTheDocument()
  expect(within(records[1]).getByText('Large Hall')).toBeInTheDocument()
  for (const record of records) {
    expect(within(record).getByText('pending')).toBeInTheDocument()
    expect(within(record).getByText(bookingPeriod(pendingBooking))).toBeInTheDocument()
  }
  expect(screen.getByRole('button', { name: 'Submit booking request' })).toBeDisabled()
  // Changing the venue resets the successful mutation and evaluates the newly selected venue.
  fireEvent.change(screen.getByLabelText('Active venue'), { target: { value: 'venue-3' } })
  expect(await screen.findByText(/Capacity mismatch/)).toBeInTheDocument()
  expect(screen.queryByText('Capacity and facilities are suitable.')).not.toBeInTheDocument()
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Submit booking request' })).toBeEnabled(),
  )
  view.unmount()
  mount()

  expect(
    await screen.findByRole('heading', { name: 'Existing venue booking requests' }),
  ).toBeInTheDocument()
  expect(screen.getAllByRole('listitem')).toHaveLength(2)
  await screen.findByRole('option', { name: 'Studio' })
  fireEvent.change(screen.getByLabelText('Active venue'), { target: { value: 'venue-3' } })
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Submit booking request' })).toBeEnabled(),
  )
  fireEvent.click(screen.getByRole('button', { name: 'Submit booking request' }))
  await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(3))
  expect(within(screen.getAllByRole('listitem')[2]).getByText('Studio')).toBeInTheDocument()
  const posts = fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')
  expect(posts.map(([, init]) => JSON.parse(String(init?.body)))).toEqual([
    { venue_id: 'venue-2' },
    { venue_id: 'venue-3' },
  ])
})

test('SCRUM-104: another coordinator\u2019s approved event never reaches the booking list', async () => {
  // /bookable is already scoped to the signed-in coordinator
  // (list_bookable_for_coordinator), so someone else's approved event is refused
  // before it renders — no booking form and no clarification box appear for it.
  signInAsCoordinator()
  renderReview([], [])

  expect(await screen.findByText('No coordinator events are available.')).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Venue booking request' })).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Internal note')).not.toBeInTheDocument()
})

test('approved event previews advisory warnings and submits a pending booking request', async () => {
  signInAsCoordinator()
  renderBookingReview({
    id: 'booking-1',
    venue_id: 'venue-1',
    start_at: approved.start_at,
    end_at: approved.end_at,
    status: 'pending',
    suitability,
  })

  await screen.findByRole('option', { name: 'Small Hall' })
  fireEvent.change(screen.getByLabelText('Active venue'), {
    target: { value: 'venue-1' },
  })
  expect(await screen.findByText(/Capacity mismatch/)).toBeInTheDocument()
  expect(screen.getByText('Missing facilities: Projector')).toBeInTheDocument()
  expect(screen.getByText('Venue accessibility: Lift access')).toBeInTheDocument()
  expect(screen.getByText('Supported layouts: classroom')).toBeInTheDocument()
  const submit = screen.getByRole('button', { name: 'Submit booking request' })
  expect(submit).toBeEnabled()
  fireEvent.click(submit)
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Booking request submitted. Status: pending.',
  )
  expect(screen.getByRole('heading', { name: 'Venue booking request' })).toBeInTheDocument()
})

test('booking authorization failure shows the backend detail', async () => {
  signInAsCoordinator()
  renderBookingReview({ detail: 'Forbidden' }, 403)

  await screen.findByRole('option', { name: 'Small Hall' })
  fireEvent.change(screen.getByLabelText('Active venue'), {
    target: { value: 'venue-1' },
  })
  await screen.findByText(/Capacity mismatch/)
  fireEvent.click(screen.getByRole('button', { name: 'Submit booking request' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Forbidden')
})

test('booking failure with a non-JSON body shows the generic status error', async () => {
  signInAsCoordinator()
  renderBookingReview(new Response(null, { status: 500 }))

  await screen.findByRole('option', { name: 'Small Hall' })
  fireEvent.change(screen.getByLabelText('Active venue'), {
    target: { value: 'venue-1' },
  })
  await screen.findByText(/Capacity mismatch/)
  fireEvent.click(screen.getByRole('button', { name: 'Submit booking request' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Booking request failed (500)')
})

// --------------------------------------------------------- SCRUM-89 AC4

const CLASH = {
  kind: 'booking' as const,
  id: 'booking-9',
  start_at: '2030-03-04T04:00:00Z',
  end_at: '2030-03-04T05:00:00Z',
  // No buffers on this venue, so the held period is the event period (SCRUM-82 AC7).
  effective_start_at: '2030-03-04T04:00:00Z',
  effective_end_at: '2030-03-04T05:00:00Z',
  message: 'conflicts with confirmed booking booking-9',
}

test('SCRUM-89 AC4: a booking needing attention says so on the coordinator own event', async () => {
  // The Coordinator who has to act finds out on the event they own, rather than being
  // sent to a Venue Staff screen they cannot open.
  signInAsCoordinator()
  renderExistingBookingReview([{ ...rejectedBooking, status: 'confirmed', conflict: CLASH }])

  expect(await screen.findByText(/Needs attention/)).toBeInTheDocument()
  // The same wording the Venue Staff panel uses, not a second vocabulary.
  expect(screen.getByText(/Clashes with a confirmed booking from/)).toBeInTheDocument()
  // Nothing has been cancelled, and the screen has to say whose decision it is.
  expect(screen.getByText(/contact them to agree what moves/)).toBeInTheDocument()
})

test('SCRUM-89 AC4: a booking with nothing wrong says nothing', async () => {
  // AC7 from the reader's side: no marker to dismiss, so none is shown.
  signInAsCoordinator()
  renderExistingBookingReview([{ ...rejectedBooking, conflict: null }])

  expect(
    await screen.findByRole('heading', { name: 'Existing venue booking requests' }),
  ).toBeInTheDocument()
  expect(screen.queryByText(/Needs attention/)).toBeNull()
})

// ------------------------------------------ SCRUM-82: the Coordinator's side of a clash
//
// Reported from testing: a clash named a period that did not overlap the booking it was
// refusing. Venue Staff see it on their queue and the Coordinator sees it here, so both
// screens need the period the venue is actually held for, not just the event period.

test('SCRUM-82 AC3: a booking says how long the venue is held when buffers widen it', async () => {
  const sgt = (value: string) =>
    new Date(value).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })
  const held = {
    ...pendingBooking,
    effective_start_at: '2030-05-01T01:30:00Z',
    effective_end_at: '2030-05-01T06:45:00Z',
  }
  signInAsCoordinator()
  renderExistingBookingReview([held])

  expect(await screen.findByText('Venue held:')).toBeInTheDocument()
  expect(
    screen.getByText(`${sgt('2030-05-01T01:30:00Z')} to ${sgt('2030-05-01T06:45:00Z')}`),
  ).toBeInTheDocument()
})

test('SCRUM-82 AC7: a booking at a venue with no buffers says nothing extra', async () => {
  // The held period equals the event period, so repeating it would be noise.
  const held = {
    ...pendingBooking,
    effective_start_at: pendingBooking.start_at,
    effective_end_at: pendingBooking.end_at,
  }
  signInAsCoordinator()
  renderExistingBookingReview([held])

  await screen.findByText(bookingPeriod(pendingBooking))
  expect(screen.queryByText('Venue held:')).toBeNull()
})
