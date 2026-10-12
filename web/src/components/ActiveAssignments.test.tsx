import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
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
  coordinator_email: 'coordinator@example.com',
}

const unassigned = {
  id: 'req-2',
  name: 'Open Day',
  status: 'approved',
  organiser_email: 'organiser2@example.com',
  start_at: '2026-12-02T01:00:00Z',
  end_at: '2026-12-02T05:00:00Z',
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

function renderOverview(fetchImpl: (input: string | URL | Request) => Promise<Response>) {
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
  for (const value of [
    'req-1',
    'submitted',
    'organiser@example.com',
    '2026-12-01T01:00:00Z',
    '2026-12-01T05:00:00Z',
    'coordinator@example.com',
    'req-2',
    'approved',
    'organiser2@example.com',
    'Open Day',
    'Unassigned',
  ]) {
    expect(screen.getByText(value)).toBeDefined()
  }
  expect(screen.getByLabelText('Active assignments')).toBeDefined()
})

test('shows a failure state when the overview cannot load', async () => {
  signInAsLead()
  renderOverview(async () => json({ detail: 'boom' }, 500))
  await waitFor(() =>
    expect(screen.getByRole('alert').textContent).toMatch('Could not load assignments'),
  )
})
