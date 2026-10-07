import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { CalendarEntry } from '../api/venueCalendar'
import { singaporeDayEnd, singaporeDayStart } from '../api/venueCalendar'
import { AuthProvider } from '../auth/context'
import VenueCalendar from './VenueCalendar'

// SCRUM-54: the venue availability calendar. SCRUM-76: the free or not free verdict.
// SCRUM-77: opening an entry.

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
  // SCRUM-82: a venue with no buffers, so the venue is held for exactly the event period.
  effective_start_at: '2030-03-04T01:00:00Z',
  effective_end_at: '2030-03-04T03:00:00Z',
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
  // The whole sentence, so the opening hours disclaimer cannot be trimmed away unnoticed.
  [
    true,
    'No confirmed booking or closure in this range. Pending requests do not block it. Opening hours are not considered.',
  ],
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

const DETAILS = {
  kind: 'booking',
  id: 'b-1',
  venue_id: 'v-1',
  venue_name: 'Hall A',
  venue_location: 'Level 2',
  start_at: '2030-03-04T01:00:00Z',
  end_at: '2030-03-04T03:00:00Z',
  status: 'confirmed',
  reason: null,
  event_request_id: 'e-1',
}

test('SCRUM-77 AC1 and AC2: a booking shows its details and the event', async () => {
  renderCalendar((url) => {
    if (url.startsWith('/api/venue-calendar/bookings/')) return json(DETAILS)
    if (url.startsWith('/api/event-requests/'))
      return json({ id: 'e-1', name: 'Orientation Day', expected_attendance: 150 })
    return json([ENTRY])
  })

  fireEvent.click(await screen.findByRole('button', { name: /Confirmed booking/ }))

  const panel = await screen.findByRole('article', { name: 'Entry details' })
  expect(await within(panel).findByText('Hall A, Level 2')).toBeInTheDocument()
  expect(within(panel).getByText('Confirmed booking')).toBeInTheDocument()
  expect(await within(panel).findByText('Orientation Day')).toBeInTheDocument()
})

test('SCRUM-77 AC3: without access to the event, the entry still shows', async () => {
  renderCalendar((url) => {
    if (url.startsWith('/api/venue-calendar/bookings/')) return json(DETAILS)
    if (url.startsWith('/api/event-requests/')) return json({ detail: 'Forbidden' }, 403)
    return json([ENTRY])
  })

  fireEvent.click(await screen.findByRole('button', { name: /Confirmed booking/ }))

  const panel = await screen.findByRole('article', { name: 'Entry details' })
  expect(await within(panel).findByText(/do not have access/)).toBeInTheDocument()
  expect(within(panel).getByText('Hall A, Level 2')).toBeInTheDocument()
  expect(within(panel).queryByText('Orientation Day')).toBeNull()
})

test('SCRUM-77 AC1: a closure shows its reason', async () => {
  renderCalendar((url) => {
    if (url.startsWith('/api/venue-calendar/unavailabilities/'))
      return json({
        ...DETAILS,
        kind: 'unavailability',
        id: 'u-1',
        status: 'unavailable',
        reason: 'Repairs',
        event_request_id: null,
      })
    return json([{ ...ENTRY, id: 'u-1', kind: 'unavailability', status: 'unavailable' }])
  })

  fireEvent.click(await screen.findByRole('button', { name: /Unavailable/ }))

  expect(await screen.findByText('Repairs')).toBeInTheDocument()
})

test.each([
  ['To', '2030-12-31'],
  ['From', '2030-01-01'],
])('SCRUM-77: changing %s closes the open entry', async (label, value) => {
  renderCalendar((url) =>
    url.startsWith('/api/venue-calendar/bookings/') ? json(DETAILS) : json([ENTRY]),
  )

  fireEvent.click(await screen.findByRole('button', { name: /Confirmed booking/ }))
  await screen.findByRole('article', { name: 'Entry details' })
  fireEvent.change(screen.getByLabelText(label), { target: { value } })

  expect(screen.queryByRole('article', { name: 'Entry details' })).toBeNull()
})

test('SCRUM-77: choosing another venue closes the open entry', async () => {
  renderCalendar((url) =>
    url.startsWith('/api/venue-calendar/bookings/') ? json(DETAILS) : json([ENTRY]),
  )

  fireEvent.click(await screen.findByRole('button', { name: /Confirmed booking/ }))
  await screen.findByRole('article', { name: 'Entry details' })
  fireEvent.change(screen.getByLabelText('Venue'), { target: { value: 'v-1' } })

  expect(screen.queryByRole('article', { name: 'Entry details' })).toBeNull()
})

test.each([
  ['rejected', 'Rejected request'],
  ['cancelled', 'Cancelled request'],
])('SCRUM-77: a %s booking opened in full shows its label', async (status, label) => {
  renderCalendar((url) => {
    if (url.startsWith('/api/venue-calendar/bookings/')) return json({ ...DETAILS, status })
    if (url.startsWith('/api/event-requests/')) return json({ detail: 'Forbidden' }, 403)
    return json([ENTRY])
  })

  fireEvent.click(await screen.findByRole('button', { name: /Confirmed booking/ }))

  const panel = await screen.findByRole('article', { name: 'Entry details' })
  expect(await within(panel).findByText(label)).toBeInTheDocument()
})

test.each([
  [500, 'Could not load the event (status 500).'],
  [404, 'The event for this booking no longer exists.'],
])(
  'SCRUM-77: an event lookup that fails with %s is an error, not no access',
  async (code, message) => {
    renderCalendar((url) => {
      if (url.startsWith('/api/venue-calendar/bookings/')) return json(DETAILS)
      if (url.startsWith('/api/event-requests/')) return json({ detail: 'Boom' }, code)
      return json([ENTRY])
    })

    fireEvent.click(await screen.findByRole('button', { name: /Confirmed booking/ }))

    const panel = await screen.findByRole('article', { name: 'Entry details' })
    expect(await within(panel).findByRole('alert')).toHaveTextContent(message)
    expect(within(panel).queryByText(/do not have access/)).toBeNull()
  },
)


// --------------------------------------------------------------- SCRUM-82 buffers

test('SCRUM-82: an entry held longer than its event says so', async () => {
  // A 09:00-11:00 SGT event at a venue with 30 minutes setup and 45 turnaround holds the
  // venue 08:30-11:45. Without this line the entry would appear outside the window the
  // Coordinator asked for with nothing to explain why.
  renderCalendar(() =>
    json([
      {
        ...ENTRY,
        effective_start_at: '2030-03-04T00:30:00Z',
        effective_end_at: '2030-03-04T03:45:00Z',
      },
    ]),
  )

  expect(
    await screen.findByText(/Venue held .* to .* for setup and turnaround/),
  ).toBeInTheDocument()
})

test('SCRUM-82: an entry with no buffers says nothing extra', async () => {
  // AC7: the common case stays as uncluttered as it was before this story.
  renderCalendar(() => json([ENTRY]))

  await screen.findByRole('button', { name: /Confirmed booking/ })
  expect(screen.queryByText(/Venue held/)).toBeNull()
})
