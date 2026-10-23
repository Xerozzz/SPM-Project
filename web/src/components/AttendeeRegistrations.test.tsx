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
          intake_open: true,
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

  fireEvent.change(await screen.findByLabelText('Full name'), { target: { value: 'Ada Lovelace' } })
  fireEvent.change(screen.getByLabelText('Age'), { target: { value: '24' } })
  fireEvent.change(screen.getByLabelText('Phone number'), { target: { value: '+65 8123 4567' } })
  fireEvent.click(await screen.findByRole('button', { name: 'Register' }))

  expect(await screen.findByRole('status')).toHaveTextContent('Registration status: Pending')
})

test('SCRUM-42: invalid fields are named and entered values stay in the form', async () => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'attendee-1', roles: ['attendee'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input) === '/api/attendee/events') {
      return json([
        {
          id: 'event-1',
          name: 'Open Day',
          description: null,
          start_at: null,
          end_at: null,
          intake_open: true,
        },
      ])
    }
    if (String(input) === '/api/attendee/events/event-1/registration') {
      return json({ detail: 'Registration not found' }, 404)
    }
    throw new Error(`unexpected request ${String(input)}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <AttendeeRegistrations />
      </AuthProvider>
    </QueryClientProvider>,
  )

  fireEvent.change(await screen.findByLabelText('Full name'), { target: { value: 'Ada Lovelace' } })
  fireEvent.click(screen.getByRole('button', { name: 'Register' }))

  expect(screen.getByText('Age must be a whole number.')).toBeInTheDocument()
  expect(screen.getByText('Phone number is required.')).toBeInTheDocument()
  expect(screen.getByLabelText('Full name')).toHaveValue('Ada Lovelace')
})

test('SCRUM-128: an attendee withdraws and sees the withdrawn status', async () => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'attendee-1', roles: ['attendee'] }),
  )
  let withdrawn = false
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const request = `${init?.method ?? 'GET'} ${String(input)}`
    if (request === 'GET /api/attendee/events') {
      return json([
        {
          id: 'event-1',
          name: 'Open Day',
          description: null,
          start_at: null,
          end_at: null,
          intake_open: true,
        },
      ])
    }
    if (request === 'GET /api/attendee/events/event-1/registration') {
      return json({ ...registration(), status: withdrawn ? 'withdrawn' : 'pending' })
    }
    if (request === 'POST /api/attendee/events/event-1/registration/withdraw') {
      withdrawn = true
      return json({ ...registration(), status: 'withdrawn', already_withdrawn: false })
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

  expect(await screen.findByRole('status')).toHaveTextContent('Registration status: Pending')
  fireEvent.click(screen.getByRole('button', { name: 'Withdraw registration' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Registration status: Withdrawn')
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
