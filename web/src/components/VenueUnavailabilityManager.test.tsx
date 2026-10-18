import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { Venue } from '../api/venues'
import { AuthProvider } from '../auth/context'
import VenueUnavailabilityManager from './VenueUnavailabilityManager'

// SCRUM-62: Venue Staff record when a venue is closed.
//
// SCRUM-82 is why the times matter here. This list sits directly above the booking
// clashes on the same page, and a clash is judged against a closure's period. Rendering
// the closure in the reader's own timezone while the clash beside it is in Singapore
// time is how you misread whether the two overlap.

beforeEach(() => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'staff-1', roles: ['venue_staff'] }),
  )
})

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const venue = {
  id: 'venue-1',
  name: 'Hall A',
  location: 'Level 2',
  is_active: true,
} as unknown as Venue

const closure = {
  id: 'closure-1',
  venue_id: 'venue-1',
  starts_at: '2030-01-01T02:00:00Z',
  ends_at: '2030-01-01T06:00:00Z',
  reason: 'Air-conditioning maintenance',
}

function renderManager() {
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () =>
      new Response(JSON.stringify([closure]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <VenueUnavailabilityManager venues={[venue]} />
      </AuthProvider>
    </QueryClientProvider>,
  )
  fireEvent.change(screen.getByLabelText('Venue'), { target: { value: venue.id } })
}

test('SCRUM-82: a recorded closure is shown in Singapore time, like the clashes beside it', async () => {
  const sgt = (value: string) =>
    new Date(value).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })
  renderManager()

  expect(
    await screen.findByText(`${sgt(closure.starts_at)} to ${sgt(closure.ends_at)}`),
  ).toBeInTheDocument()
})
