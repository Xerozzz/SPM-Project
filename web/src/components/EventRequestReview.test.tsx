import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import EventRequestReview from './EventRequestReview'

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

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

function json(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
}

function signInAsCoordinator() {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'user-1', roles: ['coordinator'] }),
  )
}

function renderReview(requests: unknown[]) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    if (key === 'GET /api/event-requests/reviewable') return json(requests)
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

test('coordinator reviews a request assigned to them and approves it', async () => {
  signInAsCoordinator()
  renderReview([submitted])

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.getByText('Auditorium')).toBeInTheDocument()
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
