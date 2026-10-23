import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import AttendeeRegistrations from './AttendeeRegistrations'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

test('SCRUM-42: an attendee registers and sees the pending status', async () => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'attendee-1', roles: ['attendee'] }),
  )
  let registered = false
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const request = `${init?.method ?? 'GET'} ${String(input)}`
    if (request === 'GET /api/attendee/events') {
      return json([
        {
          id: 'event-1',
          name: 'Open Day',
          description: 'Campus tours',
          start_at: '2030-03-04T10:00:00Z',
          end_at: '2030-03-04T12:00:00Z',
        },
      ])
    }
    if (request === 'GET /api/attendee/events/event-1/registration') {
      return registered ? json(registration()) : json({ detail: 'Registration not found' }, 404)
    }
    if (request === 'POST /api/attendee/events/event-1/registrations') {
      registered = true
      return json(registration(), 201)
    }
    throw new Error(`unexpected request ${request}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <AttendeeRegistrations />
      </AuthProvider>
    </QueryClientProvider>,
  )

  fireEvent.click(await screen.findByRole('button', { name: 'Register' }))

  expect(await screen.findByRole('status')).toHaveTextContent('Registration status: Pending')
})

function registration() {
  return {
    id: 'registration-1',
    event_request_id: 'event-1',
    status: 'pending',
    submitted_at: '2030-01-01T00:00:00Z',
    submission_order: 1,
  }
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
