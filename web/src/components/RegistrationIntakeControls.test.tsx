import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import type { EventRequest } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import RegistrationIntakeControls from './RegistrationIntakeControls'

const event: EventRequest = {
  id: 'event-1',
  status: 'confirmed',
  name: 'Open Day',
  purpose: 'Welcome visitors',
  description: 'Campus tours',
  start_at: '2030-03-04T10:00:00Z',
  end_at: '2030-03-04T12:00:00Z',
  expected_attendance: 150,
  venue_requirement: 'Hall A',
  accessibility_requirement: 'Step-free access',
  equipment_requirement: 'Projector',
  layout_requirement: 'Theatre',
  registration_requirement: 'Open registration',
  created_at: '2030-01-01T00:00:00Z',
  updated_at: '2030-01-01T00:00:00Z',
  submitted_at: '2030-01-01T00:00:00Z',
  status_permits: [],
  coordinator_id: null,
  decided_by_id: null,
  decided_at: null,
  rejection_reason: null,
}

const openSettings = {
  event_request_id: event.id,
  registration_enabled: true,
  opened_at: '2030-01-01T00:00:00Z',
  closes_at: null,
  suspended_at: null,
  closed_at: null,
  intake_open: true,
}

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

test('SCRUM-113: owner can close registration and sees its closed state', async () => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'owner', roles: ['organiser'] }),
  )
  let closed = false
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const request = `${init?.method ?? 'GET'} ${String(input)}`
    if (request === 'GET /api/event-requests/event-1/registration') {
      return json(
        closed
          ? { ...openSettings, intake_open: false, closed_at: '2030-01-02T00:00:00Z' }
          : openSettings,
      )
    }
    if (request === 'POST /api/event-requests/event-1/registration/close') {
      closed = true
      return json({ ...openSettings, intake_open: false, closed_at: '2030-01-02T00:00:00Z' })
    }
    throw new Error(`unexpected request ${request}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <RegistrationIntakeControls event={event} />
      </AuthProvider>
    </QueryClientProvider>,
  )

  await screen.findByRole('button', { name: 'Close registration' })
  fireEvent.click(screen.getByRole('button', { name: 'Close registration' }))

  await waitFor(() => expect(screen.getByText(/Closed at/)).toBeInTheDocument())
  expect(screen.queryByRole('button', { name: 'Close registration' })).not.toBeInTheDocument()
})

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
  })
}
