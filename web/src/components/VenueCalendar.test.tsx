import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { CalendarEntry } from '../api/venueCalendar'
import { singaporeDayEnd, singaporeDayStart } from '../api/venueCalendar'
import { AuthProvider } from '../auth/context'
import VenueCalendar from './VenueCalendar'

// SCRUM-54: the venue availability calendar. SCRUM-76: the free or not free verdict.

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

const ENTRY: CalendarEntry = {
  kind: 'booking',
  id: 'b-1',
  venue_id: 'v-1',
  venue_name: 'Hall A',
  start_at: '2030-03-04T01:00:00Z',
  end_at: '2030-03-04T03:00:00Z',
  status: 'confirmed',
}

const VENUES = [{ id: 'v-1', name: 'Hall A' }]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderCalendar(entries: (url: string) => Response) {
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    return url.startsWith('/api/venues') ? json(VENUES) : entries(url)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <VenueCalendar />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return spy
}

test('AC1: each kind of entry is shown with its own label', async () => {
  renderCalendar(() =>
    json([
      ENTRY,
      { ...ENTRY, id: 'b-2', status: 'pending' },
      { ...ENTRY, id: 'u-1', kind: 'unavailability', status: 'unavailable' },
    ]),
  )

  expect(await screen.findByText('Confirmed booking')).toBeInTheDocument()
  expect(screen.getByText('Pending request')).toBeInTheDocument()
  expect(screen.getByText('Unavailable')).toBeInTheDocument()
})

test('AC1: choosing a venue asks for that venue only', async () => {
  const spy = renderCalendar(() => json([]))

  await screen.findByRole('option', { name: 'Hall A' })
  fireEvent.change(screen.getByLabelText('Venue'), { target: { value: 'v-1' } })

  await waitFor(() =>
    expect(spy.mock.calls.some(([input]) => String(input).includes('venue_id=v-1'))).toBe(true),
  )
})

test('AC2: an empty range says nothing is booked', async () => {
  renderCalendar(() => json([]))

  expect(await screen.findByText('Nothing is booked or blocked in this range.')).toBeInTheDocument()
})

test('a refused range shows the reason', async () => {
  renderCalendar(() =>
    json({ detail: [{ field: 'end_at', reason: 'must be after the start' }] }, 422),
  )

  expect(await screen.findByRole('alert')).toHaveTextContent('end_at must be after the start')
})

test('a day range covers whole Singapore days', () => {
  expect(singaporeDayStart('2030-03-04')).toBe('2030-03-03T16:00:00.000Z')
  expect(singaporeDayEnd('2030-03-04')).toBe('2030-03-04T16:00:00.000Z')
})

test('SCRUM-76: no verdict until one venue is chosen', async () => {
  const spy = renderCalendar(() => json([]))

  await screen.findByText('Nothing is booked or blocked in this range.')

  expect(screen.queryByRole('status')).toBeNull()
  expect(spy.mock.calls.some(([input]) => String(input).includes('availability'))).toBe(false)
})

test.each([
  [true, 'This venue is free for the whole range'],
  [false, 'This venue is not available for all of this range'],
])('SCRUM-76: the verdict for a chosen venue (available: %s)', async (available, message) => {
  renderCalendar((url) =>
    url.includes('availability')
      ? json({ venue_id: 'v-1', start_at: '', end_at: '', available, entries: [] })
      : json([]),
  )

  await screen.findByRole('option', { name: 'Hall A' })
  fireEvent.change(screen.getByLabelText('Venue'), { target: { value: 'v-1' } })

  expect(await screen.findByRole('status')).toHaveTextContent(message)
})
