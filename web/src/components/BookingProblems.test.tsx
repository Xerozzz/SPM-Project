import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { VenueProblems } from '../api/venues'
import { AuthProvider } from '../auth/context'
import BookingProblems from './BookingProblems'

// SCRUM-89 AC4: the Venue Staff view of confirmed bookings that no longer fit their venue.

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

const PROBLEM: VenueProblems = {
  venue_id: 'venue-1',
  venue_name: 'Hall A',
  venue_location: 'Level 2',
  setup_minutes: 30,
  turnaround_minutes: 45,
  is_active: true,
  problems: [
    {
      booking_id: 'booking-1',
      start_at: '2030-03-04T02:00:00Z',
      end_at: '2030-03-04T04:00:00Z',
      conflict: {
        kind: 'booking',
        id: 'booking-2',
        start_at: '2030-03-04T04:00:00Z',
        end_at: '2030-03-04T05:00:00Z',
        message: 'conflicts with confirmed booking booking-2',
      },
    },
  ],
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderPanel(fetcher: typeof fetch) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetcher)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <BookingProblems />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

test('SCRUM-89 AC4: each venue lists the bookings needing attention and why', async () => {
  renderPanel(async () => json([PROBLEM]))

  const card = await screen.findByRole('article')
  expect(within(card).getByText(/Hall A, Level 2/)).toBeInTheDocument()
  expect(within(card).getByText(/30 min setup, 45 min turnaround/)).toBeInTheDocument()
  // The clash itself, in the same words the decisions panel uses, so Venue Staff do not
  // have to learn two vocabularies for the same thing.
  expect(within(card).getByText(/Clashes with a confirmed booking from/)).toBeInTheDocument()
  // The raw id is what the API's message carries; the screen must not repeat it.
  expect(within(card).queryByText(/booking-2/)).toBeNull()
  // And the reassuring message must not sit above a list of problems. Found by mutation:
  // without this, rendering the empty state unconditionally went unnoticed.
  expect(screen.queryByText(/Nothing needs attention/)).toBeNull()
})

test('SCRUM-89 AC4: the times are shown in Singapore time', async () => {
  renderPanel(async () => json([PROBLEM]))

  const card = await screen.findByRole('article')
  const sgt = (value: string) =>
    new Date(value).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })
  expect(card).toHaveTextContent(sgt(PROBLEM.problems[0].start_at))
  expect(card).toHaveTextContent(sgt(PROBLEM.problems[0].end_at))
})

test('SCRUM-89 AC6: an empty list says nothing needs attention', async () => {
  // Not "no venues": the API leaves out every venue with nothing wrong, so an empty
  // response means the opposite of empty.
  renderPanel(async () => json([]))

  expect(await screen.findByText(/Nothing needs attention/)).toBeInTheDocument()
  expect(screen.queryByRole('article')).toBeNull()
})

test('SCRUM-89: a deactivated venue is still listed, and says so', async () => {
  // Its bookings are the ones nobody is watching, so hiding them would be the worst case.
  renderPanel(async () => json([{ ...PROBLEM, is_active: false }]))

  const card = await screen.findByRole('article')
  expect(within(card).getByText(/deactivated/)).toBeInTheDocument()
})

test('SCRUM-89: a failed load is reported rather than shown as nothing wrong', async () => {
  // The dangerous failure for this screen: silently looking like all is well.
  renderPanel(async () => json({ detail: 'nope' }, 500))

  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load booking problems')
  expect(screen.queryByText(/Nothing needs attention/)).toBeNull()
})
