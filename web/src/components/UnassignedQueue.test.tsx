import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import ActiveAssignments from './ActiveAssignments'
import UnassignedQueue from './UnassignedQueue'

// TC-101-07: the Lead queue renders loading, empty, populated and failed states with
// every required field (event ID, name, organiser, start/end, attendance, submitted).
// TC-98-09 (frontend part): the Lead picks an eligible coordinator, assigns, and the
// request leaves the queue; a failed assignment keeps the row visible with an error.

const row = {
  id: 'req-1',
  name: 'Orientation Day',
  organiser_email: 'organiser@example.com',
  start_at: '2026-12-01T01:00:00Z',
  end_at: '2026-12-01T05:00:00Z',
  expected_attendance: 200,
  submitted_at: '2026-04-01T09:00:00Z',
}

const coordinators = [
  { id: 'coord-1', email: 'coordinator@example.com' },
  { id: 'coord-2', email: 'coordinator2@example.com' },
]

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

function signInAsLead() {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'lead-1', roles: ['coordinator_lead'] }),
  )
}

// Both components mount together (as on the Home page), so every fetch mock must
// also answer the overview endpoint — otherwise the overview errors and its text
// collides with the queue assertions.
function withOverview(
  fetchImpl: (input: string | URL | Request, init?: RequestInit) => Promise<Response>,
) {
  return async (input: string | URL | Request, init?: RequestInit) => {
    if (String(input) === '/api/event-requests/active-assignments') return json([])
    return fetchImpl(input, init)
  }
}

function renderQueue(
  fetchImpl: (
    input: string | URL | Request,
    init?: RequestInit,
  ) => Promise<Response>,
) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    fetchImpl as typeof globalThis.fetch,
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <UnassignedQueue />
        <ActiveAssignments />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return client
}

test('shows a loading state while the queue loads', () => {
  signInAsLead()
  renderQueue(() => new Promise<Response>(() => {}))
  expect(screen.getByText('Loading unassigned requests…')).toBeDefined()
})

test('shows an empty state when the queue has no rows', async () => {
  signInAsLead()
  renderQueue(withOverview(async () => json([])))
  await waitFor(() =>
    expect(screen.getByText('No unassigned requests.')).toBeDefined(),
  )
})

test('shows every required field for a queued request', async () => {
  signInAsLead()
  renderQueue(
    withOverview(async (input) => {
      if (String(input) === '/api/event-requests/unassigned') return json([row])
      if (String(input) === '/api/event-requests/assignable-coordinators')
        return json(coordinators)
      throw new Error(`unexpected fetch ${String(input)}`)
    }),
  )
  await waitFor(() => expect(screen.getByText('Orientation Day')).toBeDefined())
  for (const value of [
    'req-1',
    'organiser@example.com',
    '2026-12-01T01:00:00Z',
    '2026-12-01T05:00:00Z',
    '200',
    '2026-04-01T09:00:00Z',
  ]) {
    expect(screen.getByText(value)).toBeDefined()
  }
  expect(screen.getByLabelText('Unassigned requests')).toBeDefined()
  // The picker lists the eligible coordinators for this row.
  await waitFor(() =>
    expect(
      screen.getByLabelText('Coordinator for Orientation Day'),
    ).toBeDefined(),
  )
  expect(screen.getByText('coordinator@example.com')).toBeDefined()
  expect(screen.getByText('coordinator2@example.com')).toBeDefined()
})

test('shows a failure state when the queue cannot load', async () => {
  signInAsLead()
  renderQueue(withOverview(async () => json({ detail: 'boom' }, 500)))
  await waitFor(() =>
    expect(screen.getByRole('alert').textContent).toMatch(
      'Could not load unassigned requests',
    ),
  )
})

test('assigning a coordinator confirms and removes the request from the queue', async () => {
  signInAsLead()
  let queueCalls = 0
  renderQueue(
    withOverview(async (input, init) => {
      if (String(input) === '/api/event-requests/assignable-coordinators')
        return json(coordinators)
      if (String(input) === '/api/event-requests/unassigned') {
        queueCalls += 1
        return json(queueCalls === 1 ? [row] : [])
      }
      if (String(input) === '/api/event-requests/req-1/assign' && init?.method === 'POST')
        return json({ ...row, coordinator_id: 'coord-1' })
      throw new Error(`unexpected fetch ${String(input)}`)
    }),
  )
  await waitFor(() => expect(screen.getByText('Orientation Day')).toBeDefined())
  expect(screen.getByText('organiser@example.com')).toBeDefined()
  fireEvent.change(screen.getByLabelText('Coordinator for Orientation Day'), {
    target: { value: 'coord-1' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Assign' }))
  await waitFor(() =>
    expect(screen.getByRole('status').textContent).toMatch(
      '“Orientation Day” has been assigned.',
    ),
  )
  await waitFor(() =>
    expect(screen.getByText('No unassigned requests.')).toBeDefined(),
  )
})

test('a failed assignment keeps the request visible with an error', async () => {
  signInAsLead()
  renderQueue(
    withOverview(async (input, init) => {
      if (String(input) === '/api/event-requests/assignable-coordinators')
        return json(coordinators)
      if (String(input) === '/api/event-requests/unassigned') return json([row])
      if (String(input) === '/api/event-requests/req-1/assign' && init?.method === 'POST')
        return json({ detail: 'This request already has an owner' }, 409)
      throw new Error(`unexpected fetch ${String(input)}`)
    }),
  )
  await waitFor(() => expect(screen.getByText('Orientation Day')).toBeDefined())
  fireEvent.change(screen.getByLabelText('Coordinator for Orientation Day'), {
    target: { value: 'coord-1' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Assign' }))
  await waitFor(() =>
    expect(screen.getByRole('alert').textContent).toMatch(
      'The assignment could not be recorded',
    ),
  )
  // The row stays: the Lead can pick someone else or retry.
  expect(screen.getByText('Orientation Day')).toBeDefined()
})

test('assigning refetches the active-assignment overview with the new owner', async () => {
  // Regression test for the stale-overview bug: assigning moved the row to the
  // overview, but the overview kept its cached `coordinator_id: null` snapshot
  // ("Unassigned") until a manual refresh. Both components share one QueryClient
  // here, exactly as on the Home page.
  signInAsLead()
  let queueCalls = 0
  let overviewCalls = 0
  renderQueue(async (input, init) => {
    if (String(input) === '/api/event-requests/assignable-coordinators')
      return json(coordinators)
    if (String(input) === '/api/event-requests/unassigned') {
      queueCalls += 1
      return json(queueCalls === 1 ? [row] : [])
    }
    if (String(input) === '/api/event-requests/active-assignments') {
      overviewCalls += 1
      // First load: row not yet assigned. After the assign mutation, the
      // invalidated overview refetches and sees the new owner.
      return json(
        overviewCalls === 1
          ? []
          : [
              {
                ...row,
                status: 'submitted',
                coordinator_email: 'coordinator@example.com',
              },
            ],
      )
    }
    if (String(input) === '/api/event-requests/req-1/assign' && init?.method === 'POST')
      return json({ ...row, coordinator_id: 'coord-1' })
    throw new Error(`unexpected fetch ${String(input)}`)
  })
  await waitFor(() => expect(screen.getByText('Orientation Day')).toBeDefined())
  expect(overviewCalls).toBe(1)
  fireEvent.change(screen.getByLabelText('Coordinator for Orientation Day'), {
    target: { value: 'coord-1' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Assign' }))
  await waitFor(() =>
    expect(screen.getByText('No unassigned requests.')).toBeDefined(),
  )
  // The overview refetched after the assignment and now shows the owner.
  await waitFor(() => expect(overviewCalls).toBeGreaterThan(1))
  await waitFor(() => expect(screen.getByText('coordinator@example.com')).toBeDefined())
})
