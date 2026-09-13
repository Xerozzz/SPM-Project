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
}

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

function json(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
}

test('coordinator sees review details and must enter a note before requesting clarification', async () => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', roles: ['coordinator'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    if (key === 'GET /api/event-requests/review') return json([submitted])
    if (key === 'POST /api/event-requests/req-1/request-clarification') {
      return json({ ...submitted, status: 'clarification_requested' })
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

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.getByText('Auditorium')).toBeInTheDocument()
  const clarification = screen.getByRole('button', { name: 'Request clarification' })
  expect(clarification).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Coordinator note'), {
    target: { value: 'Needs a safer venue' },
  })
  expect(clarification).toBeEnabled()
  fireEvent.click(clarification)
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Clarification was requested for “Orientation Day”.',
  )
})
