import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
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
    if (key === 'GET /api/venues') return json([])
    if (key.endsWith('/clarifications')) return json([])
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

function renderBookingReview(submission: unknown, status = 200) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    if (key === 'GET /api/event-requests/reviewable') return json([])
    if (key === 'GET /api/event-requests/bookable') return json([approved])
    if (key === 'GET /api/venues') {
      return json([{ id: 'venue-1', name: 'Small Hall', is_active: true }])
    }
    if (key.endsWith('/clarifications')) return json([])
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

test('coordinator reviews a request assigned to them and approves it', async () => {
  signInAsCoordinator()
  renderReview([submitted])

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.getByText('Auditorium')).toBeInTheDocument()
  expect(screen.getByLabelText('Clarification request')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
  expect(await screen.findByRole('status')).toHaveTextContent(
    '“Orientation Day” has been approved.',
  )
})

test('a request assigned to another coordinator offers no decision buttons', async () => {
  // The API refuses these with 403 (require_event_access(DECIDE) wants the assigned
  // coordinator), but the UI used to show Approve and Reject on every submitted request,
  // because status_permits describes the status and not the viewer. Four of seven buttons
  // on a seeded database did nothing but raise a 403.
  signInAsCoordinator()
  renderReview([{ ...submitted, coordinator_id: 'someone-else' }])

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument()
  expect(screen.getByText(/Assigned to another coordinator/)).toBeInTheDocument()
})

test('an unassigned request offers no decision buttons either', async () => {
  signInAsCoordinator()
  renderReview([{ ...submitted, coordinator_id: null }])

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
  // Not the same sentence as "assigned to another coordinator": nobody is assigned here.
  expect(screen.getByText(/Not assigned to a coordinator yet/)).toBeInTheDocument()
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
  expect(screen.getByRole('heading', { name: 'Venue booking request' })).toBeInTheDocument()
})

test('approved event assigned to another coordinator hides the booking UI', async () => {
  signInAsCoordinator()
  renderReview([], [{ ...approved, coordinator_id: 'someone-else' }])

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Venue booking request' })).not.toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'Clarification history' })).toBeInTheDocument()
  expect(await screen.findByText('No clarification messages yet.')).toBeInTheDocument()
  expect(screen.queryByLabelText('Clarification request')).not.toBeInTheDocument()
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
  expect(screen.getByText(/Capacity mismatch/)).toBeInTheDocument()
})

test('booking conflict shows the backend detail', async () => {
  signInAsCoordinator()
  renderBookingReview({ detail: 'A pending booking request already exists.' }, 409)

  await screen.findByRole('option', { name: 'Small Hall' })
  fireEvent.change(screen.getByLabelText('Active venue'), {
    target: { value: 'venue-1' },
  })
  await screen.findByText(/Capacity mismatch/)
  fireEvent.click(screen.getByRole('button', { name: 'Submit booking request' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'A pending booking request already exists.',
  )
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
