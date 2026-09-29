import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

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

/**
 * The instant the API client will actually send for a form value. The form's fields are
 * Singapore wall clock whatever the browser's zone is (singaporeWallClockToUtc in
 * api/venues.ts), so asserting against browser-local time proves nothing: that was exactly
 * the hole that let the timezone bug through the first time.
 */
function instantSent(date: string, time: string): Date {
  return new Date(`${date}T${time}:00+08:00`)
}

// Sampled across the clock and across the offsets a coordinator might actually sit at. The
// second axis is the one that matters: the default used to be derived from the browser's
// clock while being read back as Singapore time, so for a browser west of SGT it produced a
// period that had already ended and the search answered 422 rather than returning nothing.
const TIMES = ['00:30', '02:30', '06:10', '08:10', '10:05', '13:20', '16:40', '21:05', '23:50']
const OFFSETS = ['+08:00', '+00:00', '-04:00', '-11:00', '+13:00']

describe.each(OFFSETS)('with the browser at UTC%s', (offset) => {
  test.each(TIMES)('the default period is still in the future at %s', (clock) => {
    vi.useFakeTimers()
    const now = new Date(`2026-09-28T${clock}:00${offset}`)
    vi.setSystemTime(now)
    renderSearch()

    const { endDate, endTime } = defaults()
    expect(instantSent(endDate, endTime).getTime()).toBeGreaterThan(now.getTime())
  })

  test.each(TIMES)('the default period is inside venue hours at %s', (clock) => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(`2026-09-28T${clock}:00${offset}`))
    renderSearch()

    const { startDate, startTime, endDate, endTime } = defaults()
    expect(startTime >= EARLIEST_OPEN).toBe(true)
    expect(endTime <= EARLIEST_CLOSE).toBe(true)
    expect(instantSent(startDate, startTime).getTime()).toBeLessThan(
      instantSent(endDate, endTime).getTime(),
    )
  })
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
