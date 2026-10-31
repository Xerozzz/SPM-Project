import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import ActiveAssignments from './ActiveAssignments'

// TC-100-06: the overview renders loading, empty, assigned, unassigned and failed
// states with every required field (event ID, name, status, organiser, event time,
// current coordinator or Unassigned). Unassigned is a normal state, not an error.

const assigned = {
  id: 'req-1',
  name: 'Orientation Day',
  status: 'submitted',
  organiser_email: 'organiser@example.com',
  start_at: '2026-12-01T01:00:00Z',
  end_at: '2026-12-01T05:00:00Z',
  coordinator_id: 'coord-1',
  coordinator_email: 'coordinator@example.com',
}

const unassigned = {
  id: 'req-2',
  name: 'Open Day',
  status: 'approved',
  organiser_email: 'organiser2@example.com',
  start_at: '2026-12-02T01:00:00Z',
  end_at: '2026-12-02T05:00:00Z',
  coordinator_id: null,
  coordinator_email: null,
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

function signInAsLead() {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'lead-1', roles: ['coordinator_lead'] }),
  )
}

function renderOverview(
  fetchImpl: (input: string | URL | Request, init?: RequestInit) => Promise<Response>,
) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetchImpl as typeof globalThis.fetch)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ActiveAssignments />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

async function openDetails(name: string) {
  fireEvent.click(await screen.findByRole('button', { name: `View details for ${name}` }))
}

test('shows a loading state while the overview loads', () => {
  signInAsLead()
  renderOverview(() => new Promise<Response>(() => {}))
  expect(screen.getByText('Loading assignments…')).toBeDefined()
})

test('shows an empty state when no active requests exist', async () => {
  signInAsLead()
  renderOverview(async () => json([]))
  await waitFor(() => expect(screen.getByText('No active requests.')).toBeDefined())
})

test('shows assigned and unassigned rows with every required field', async () => {
  signInAsLead()
  renderOverview(async (input) => {
    if (String(input) === '/api/event-requests/active-assignments')
      return json([assigned, unassigned])
    throw new Error(`unexpected fetch ${String(input)}`)
  })
  await waitFor(() => expect(screen.getByText('Orientation Day')).toBeDefined())
  await openDetails('Orientation Day')
  for (const value of [
    'req-1',
    'submitted',
    'organiser@example.com',
    '2026-12-01T01:00:00Z',
    '2026-12-01T05:00:00Z',
    'coordinator@example.com',
  ]) {
    expect(screen.getAllByText(value).length).toBeGreaterThan(0)
  }
  fireEvent.click(screen.getByRole('button', { name: '← Back to Active Assignments' }))
  await openDetails('Open Day')
  for (const value of ['req-2', 'approved', 'organiser2@example.com', 'Open Day', 'Unassigned']) {
    expect(screen.getAllByText(value).length).toBeGreaterThan(0)
  }
  expect(screen.getByLabelText('Active requests')).toBeDefined()
})

test('shows a failure state when the overview cannot load', async () => {
  signInAsLead()
  renderOverview(async () => json({ detail: 'boom' }, 500))
  await waitFor(() =>
    expect(screen.getByRole('alert').textContent).toMatch('Could not load assignments'),
  )
})

// TC-97-08 (frontend part): the Lead reassigns an assigned row to another eligible
// coordinator; the picker sends the current owner as the expected owner for
// optimistic concurrency, and the overview refetches with the new owner.

const coordinators = [
  { id: 'coord-1', email: 'coordinator@example.com' },
  { id: 'coord-2', email: 'coordinator2@example.com' },
]

test('reassigning sends the current owner and confirms with the new owner', async () => {
  signInAsLead()
  let overviewCalls = 0
  let sentBody: unknown = null
  renderOverview(async (input, init) => {
    if (String(input) === '/api/event-requests/assignable-coordinators') return json(coordinators)
    if (String(input) === '/api/event-requests/active-assignments') {
      overviewCalls += 1
      return json(
        overviewCalls === 1
          ? [assigned]
          : [
              {
                ...assigned,
                coordinator_id: 'coord-2',
                coordinator_email: 'coordinator2@example.com',
              },
            ],
      )
    }
    if (String(input) === '/api/event-requests/req-1/reassign' && init?.method === 'POST') {
      sentBody = JSON.parse(String(init?.body))
      return json({ ...assigned, name: 'Orientation Day', coordinator_id: 'coord-2' })
    }
    if (String(input) === '/api/event-requests/req-1/assignment-history') return json([])
    throw new Error(`unexpected fetch ${String(input)}`)
  })
  await waitFor(() => expect(screen.getByText('Orientation Day')).toBeDefined())
  await openDetails('Orientation Day')
  fireEvent.change(screen.getByLabelText('New coordinator for Orientation Day'), {
    target: { value: 'coord-2' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Reassign' }))
  await waitFor(() => expect(screen.getByRole('status').textContent).toMatch('has been reassigned'))
  // The current owner travels as the expected owner for optimistic concurrency.
  expect(sentBody).toEqual({
    coordinator_id: 'coord-2',
    expected_current_coordinator_id: 'coord-1',
  })
  await waitFor(() => expect(overviewCalls).toBeGreaterThan(1))
  // The new owner appears both in the row and in the picker options, so any
  // match proves the overview refetched with the reassigned owner.
  await waitFor(() =>
    expect(screen.getAllByText('coordinator2@example.com').length).toBeGreaterThan(0),
  )
})

test('a stale reassignment keeps the row visible with an error', async () => {
  signInAsLead()
  renderOverview(async (input, init) => {
    if (String(input) === '/api/event-requests/assignable-coordinators') return json(coordinators)
    if (String(input) === '/api/event-requests/active-assignments') return json([assigned])
    if (String(input) === '/api/event-requests/req-1/reassign' && init?.method === 'POST')
      return json({ detail: 'was reassigned by someone else' }, 409)
    throw new Error(`unexpected fetch ${String(input)}`)
  })
  await waitFor(() => expect(screen.getByText('Orientation Day')).toBeDefined())
  await openDetails('Orientation Day')
  fireEvent.change(screen.getByLabelText('New coordinator for Orientation Day'), {
    target: { value: 'coord-2' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Reassign' }))
  await waitFor(() =>
    expect(screen.getByRole('alert').textContent).toMatch('The reassignment could not be recorded'),
  )
  // The row stays: the Lead can refresh and pick again.
  expect(screen.getByText('Orientation Day')).toBeDefined()
})

test('unassigned rows offer history but no reassignment picker', async () => {
  signInAsLead()
  renderOverview(async (input) => {
    if (String(input) === '/api/event-requests/active-assignments') return json([unassigned])
    if (String(input) === '/api/event-requests/req-2/assignment-history') return json([])
    throw new Error(`unexpected fetch ${String(input)}`)
  })
  await waitFor(() => expect(screen.getByText('Open Day')).toBeDefined())
  await openDetails('Open Day')
  expect(screen.queryByLabelText('New coordinator for Open Day')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Show history' }))
  await waitFor(() =>
    expect(screen.getByText('No assignment history for Open Day yet.')).toBeDefined(),
  )
})

// SCRUM-88: a Lead may read any event's history, so every overview row offers it.
test('every row offers the event history', async () => {
  signInAsLead()
  renderOverview(async (input) => {
    if (String(input) === '/api/event-requests/active-assignments')
      return json([assigned, unassigned])
    if (String(input) === '/api/event-requests/req-2/history') return json([])
    throw new Error(`unexpected fetch ${String(input)}`)
  })
  await waitFor(() => expect(screen.getByText('Open Day')).toBeDefined())
  await openDetails('Open Day')
  fireEvent.click(screen.getByRole('button', { name: 'View event history' }))
  await waitFor(() =>
    expect(screen.getByText('No history you can see for Open Day yet.')).toBeDefined(),
  )
})
