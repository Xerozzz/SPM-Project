import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import VenueSearch from './VenueSearch'

// SCRUM-55: the coordinator's venue search form. These are the tests the component never
// had, which is why the default-period bug below reached main.

afterEach(() => {
  vi.useRealTimers()
  localStorage.clear()
  vi.restoreAllMocks()
})

beforeEach(() => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'user-1', roles: ['coordinator'] }),
  )
})

function json(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
}

function renderSearch(fetcher?: typeof fetch) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetcher ?? (async () => json([])))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <VenueSearch />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

function defaults() {
  return {
    startDate: (screen.getByLabelText(/^Start date/) as HTMLInputElement).value,
    startTime: (screen.getByLabelText(/^Start time/) as HTMLInputElement).value,
    endDate: (screen.getByLabelText(/^End date/) as HTMLInputElement).value,
    endTime: (screen.getByLabelText(/^End time/) as HTMLInputElement).value,
  }
}

// Every seeded venue opens by 09:00 and closes by 18:00 at the earliest, so a default
// period outside that window can never match anything.
const EARLIEST_OPEN = '09:00'
const EARLIEST_CLOSE = '18:00'

test.each([
  ['02:30', 'the small hours'],
  ['08:10', 'before opening'],
  ['10:05', 'mid-morning'],
  ['16:40', 'late afternoon'],
  ['21:05', 'evening'],
  ['23:50', 'just before midnight'],
])('the form opens on a period inside venue hours at %s (%s)', (clock) => {
  // Regression: the default used to be simply "one hour from now", so from late evening
  // until morning the form opened on a period every venue is closed for. The first search
  // then returned nothing and the empty-state copy blamed the filters.
  vi.useFakeTimers()
  vi.setSystemTime(new Date(`2026-09-28T${clock}:00`))
  renderSearch()

  const { startTime, endTime } = defaults()
  expect(startTime >= EARLIEST_OPEN).toBe(true)
  expect(endTime <= EARLIEST_CLOSE).toBe(true)
  expect(startTime < endTime).toBe(true)
})

test('the default period is never in the past', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-09-28T21:05:00'))
  renderSearch()

  const { startDate, startTime } = defaults()
  expect(new Date(`${startDate}T${startTime}`).getTime()).toBeGreaterThan(Date.now())
})

test('searching sends the period as UTC instants and lists what comes back', async () => {
  let requested = ''
  renderSearch(async (input) => {
    requested = String(input)
    return json([
      {
        id: 'venue-1',
        name: 'Hall A',
        location: 'Level 2, School of Computing',
        maximum_capacity: 200,
        facilities: ['Projector'],
        supported_layouts: ['theatre'],
        accessibility_features: ['Step-free access'],
        opens_at: '08:00:00',
        closes_at: '22:00:00',
        is_active: true,
      },
    ])
  })

  fireEvent.change(screen.getByLabelText(/^Start date/), { target: { value: '2026-12-01' } })
  fireEvent.change(screen.getByLabelText(/^Start time/), { target: { value: '10:00' } })
  fireEvent.change(screen.getByLabelText(/^End date/), { target: { value: '2026-12-01' } })
  fireEvent.change(screen.getByLabelText(/^End time/), { target: { value: '12:00' } })
  fireEvent.click(screen.getByRole('button', { name: /search/i }))

  await waitFor(() => expect(requested).toContain('/api/venues/search'))
  const query = new URL(requested, 'http://example.test').searchParams
  // The form's times are Singapore wall-clock whatever the browser's zone is, so these
  // are fixed instants: 10:00 and 12:00 SGT are 02:00 and 04:00 UTC.
  expect(query.get('start_at')).toBe('2026-12-01T02:00:00.000Z')
  expect(query.get('end_at')).toBe('2026-12-01T04:00:00.000Z')
  expect(await screen.findByText(/Hall A/)).toHaveTextContent('seats 200')
})

test('a failed search says so rather than looking like no matches', async () => {
  renderSearch(async () => new Response('nope', { status: 500 }))

  fireEvent.click(screen.getByRole('button', { name: /search/i }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not/i)
})
