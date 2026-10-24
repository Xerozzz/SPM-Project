import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import RegistrationReviewList from './RegistrationReviewList'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

function renderList(response: unknown, canDecide = false) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'owner', roles: ['organiser'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(response), { headers: { 'Content-Type': 'application/json' } }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <RegistrationReviewList eventId="event-1" canDecide={canDecide} />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

test('SCRUM-114: shows the server-provided submission order without decision controls', async () => {
  renderList([
    {
      id: 'registration-1',
      event_request_id: 'event-1',
      full_name: 'Ada Lovelace',
      age: 24,
      phone_number: '+65 8123 4567',
      dietary_accessibility_notes: 'Step-free access',
      status: 'pending',
      submitted_at: '2030-01-01T00:00:00Z',
      submission_order: 1,
    },
  ])

  expect(await screen.findByText('Ada Lovelace')).toBeInTheDocument()
  expect(screen.getByText(/Status: pending/)).toBeInTheDocument()
  expect(screen.getByText(/Notes: Step-free access/)).toBeInTheDocument()
  expect(screen.queryByRole('button')).toBeNull()
})

test('SCRUM-134: owner sees decision controls on the existing list', async () => {
  renderList([
    {
      id: 'registration-1', event_request_id: 'event-1', full_name: 'Ada Lovelace', age: 24,
      phone_number: '+65 8123 4567', dietary_accessibility_notes: null, status: 'pending',
      submitted_at: '2030-01-01T00:00:00Z', submission_order: 1,
    },
  ], true)

  expect(await screen.findByText('Ada Lovelace')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Accept' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Waitlist' })).toBeInTheDocument()
})

test('SCRUM-114: explains an empty registration list', async () => {
  renderList([])

  expect(await screen.findByText('No registrations yet.')).toBeInTheDocument()
})
