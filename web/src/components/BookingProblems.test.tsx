import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { VenueProblems } from '../api/venues'
import { AuthProvider } from '../auth/context'
import BookingProblems from './BookingProblems'
import VenueCatalogue from './VenueCatalogue'

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
      event_request_id: 'event-1',
      event_name: 'Orientation Day',
      start_at: '2030-03-04T02:00:00Z',
      end_at: '2030-03-04T04:00:00Z',
      status: 'confirmed',
      conflict: {
        kind: 'booking',
        id: 'booking-2',
        start_at: '2030-03-04T04:00:00Z',
        end_at: '2030-03-04T05:00:00Z',
        // Held wider than the event: 30 minutes of setup is what makes these clash.
        effective_start_at: '2030-03-04T03:30:00Z',
        effective_end_at: '2030-03-04T05:00:00Z',
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
  // Named by the period the venue is held for, not the event period. The two bookings
  // here are back to back; it is the 30 minutes of setup that makes them clash, and a
  // message quoting only 12:00-13:00 would look like no clash at all.
  expect(
    within(card).getByText(/Clashes with a confirmed booking holding the venue/),
  ).toBeInTheDocument()
  expect(within(card).getByText(/11:30:00 am/)).toBeInTheDocument()
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


test('SCRUM-89 AC4: a problem names the event, so staff know whose it is', async () => {
  // The panel tells Venue Staff the Coordinator decides what moves. Without the event it
  // names nobody, and a Venue Staff member has a time range and no way to act on it.
  renderPanel(async () => json([PROBLEM]))

  const card = await screen.findByRole('article')
  expect(within(card).getByText(/Orientation Day/)).toBeInTheDocument()
})

test('SCRUM-89 AC6: saving a venue refreshes this panel instead of leaving it stale', async () => {
  // Found by review: the catalogue and this panel sit on the same Venue Staff page, and
  // the catalogue only invalidated its own query. Venue Staff saw "Nothing needs
  // attention" directly under a save that had just caused some.
  let saved = false
  const calls: string[] = []
  const fetcher = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    calls.push(key)
    if (init?.method === 'PATCH') {
      saved = true
      return json({ id: 'venue-1', name: 'Hall A', buffer_change: { changed: true, problems: [] } })
    }
    if (String(input).endsWith('/booking-problems')) return json(saved ? [PROBLEM] : [])
    if (String(input) === '/api/venues') {
      return json([
        {
          id: 'venue-1',
          name: 'Hall A',
          location: 'Level 2',
          maximum_capacity: 10,
          facilities: [],
          supported_layouts: ['theatre'],
          accessibility_features: [],
          opens_at: '08:00:00',
          closes_at: '22:00:00',
          setup_minutes: 0,
          turnaround_minutes: 0,
          is_active: true,
        },
      ])
    }
    return json([])
  }) as typeof fetch

  vi.spyOn(globalThis, 'fetch').mockImplementation(fetcher)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <VenueCatalogue />
        <BookingProblems />
      </AuthProvider>
    </QueryClientProvider>,
  )

  await screen.findByText(/Nothing needs attention/)
  fireEvent.click(await screen.findByRole('button', { name: 'Edit Hall A' }))
  fireEvent.change(screen.getByLabelText(/^Turnaround time/), { target: { value: '45' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

  // The panel reloads and the stale reassurance goes away.
  await waitFor(() => {
    expect(screen.queryByText(/Nothing needs attention/)).toBeNull()
  })
  expect(calls.filter((c) => c.endsWith('/booking-problems')).length).toBeGreaterThan(1)
})

test('SCRUM-89 AC6: the save says what it did to existing bookings', async () => {
  // The API has always answered this; nothing read it. A Venue Staff member changing a
  // buffer was told the venue was updated and nothing about what that cost.
  vi.spyOn(globalThis, 'fetch').mockImplementation((async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ) => {
    if (init?.method === 'PATCH') {
      return json({
        id: 'venue-1',
        name: 'Hall A',
        buffer_change: { changed: true, problems: [PROBLEM.problems[0]] },
      })
    }
    if (String(input) === '/api/venues') {
      return json([
        {
          id: 'venue-1',
          name: 'Hall A',
          location: 'Level 2',
          maximum_capacity: 10,
          facilities: [],
          supported_layouts: ['theatre'],
          accessibility_features: [],
          opens_at: '08:00:00',
          closes_at: '22:00:00',
          setup_minutes: 0,
          turnaround_minutes: 0,
          is_active: true,
        },
      ])
    }
    return json([])
  }) as typeof fetch)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <VenueCatalogue />
      </AuthProvider>
    </QueryClientProvider>,
  )

  fireEvent.click(await screen.findByRole('button', { name: 'Edit Hall A' }))
  fireEvent.change(screen.getByLabelText(/^Turnaround time/), { target: { value: '45' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

  expect(await screen.findByRole('status')).toHaveTextContent(
    '1 existing booking can no longer fit',
  )
})

test('SCRUM-89: a tentative hold needing attention is labelled as one', async () => {
  // Holds are reviewed alongside confirmed bookings now. The two need different answers
  // from the Coordinator - a hold can be left to expire, a confirmed booking cannot - so
  // a panel that showed them identically would be asking for the wrong decision.
  renderPanel(async () =>
    json([
      {
        ...PROBLEM,
        problems: [{ ...PROBLEM.problems[0], booking_id: 'hold-1', status: 'tentative' }],
      },
    ]),
  )

  expect(await screen.findByText('Tentative hold')).toBeInTheDocument()
})

test('SCRUM-89: a confirmed booking is not labelled as a hold', async () => {
  renderPanel(async () => json([PROBLEM]))

  await screen.findByText('Orientation Day')
  expect(screen.queryByText('Tentative hold')).toBeNull()
})
