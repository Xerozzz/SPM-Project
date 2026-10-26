import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import type { EventHistoryEntry } from '../api/eventHistory'
import { formatSingaporeTime } from '../api/venueCalendar'
import { AuthProvider } from '../auth/context'
import CompletedEvents from './CompletedEvents'
import EventHistory, { EventHistoryToggle } from './EventHistory'

// SCRUM-88: the event history display. The API decides who may read it, which notes they
// get and the order (ADR-0062); these tests prove the component shows exactly that.

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const URL = '/api/event-requests/ev-1/history'

function entry(overrides: Partial<EventHistoryEntry>): EventHistoryEntry {
  return {
    id: 'draft_created:ev-1',
    action: 'draft_created',
    occurred_at: '2026-10-01T01:00:00Z',
    actor_id: 'u-owner',
    actor_email: 'owner@example.com',
    source_type: 'event_request',
    source_id: 'ev-1',
    outcome: null,
    reason: null,
    previous_coordinator_email: null,
    new_coordinator_email: null,
    venue_name: null,
    session_label: null,
    hold_expires_at: null,
    note: null,
    ...overrides,
  }
}

const created = entry({})
const rejected = entry({
  id: 'review_decided:ev-1',
  action: 'review_decided',
  occurred_at: '2026-10-02T03:00:00Z',
  actor_id: 'u-coord',
  actor_email: 'coordinator@example.com',
  outcome: 'rejected',
  reason: 'Expected attendance exceeds the venue',
})
const assigned = entry({
  id: 'coordinator_reassigned:as-1',
  action: 'coordinator_reassigned',
  occurred_at: '2026-10-02T02:00:00Z',
  actor_id: 'u-lead',
  actor_email: 'lead@example.com',
  source_type: 'coordinator_assignment',
  source_id: 'as-1',
  previous_coordinator_email: 'alice@example.com',
  new_coordinator_email: 'bob@example.com',
})
const venueRejected = entry({
  id: 'venue_decided:bk-1',
  action: 'venue_decided',
  occurred_at: '2026-10-03T04:00:00Z',
  actor_id: 'u-staff',
  actor_email: 'staff@example.com',
  source_type: 'venue_booking',
  source_id: 'bk-1',
  outcome: 'rejected',
  reason: 'Closed for maintenance',
  venue_name: 'Hall A',
  session_label: 'Main session',
})
const held = entry({
  id: 'hold_created:bk-2',
  action: 'hold_created',
  occurred_at: '2026-10-03T05:00:00Z',
  actor_id: 'u-staff',
  actor_email: 'staff@example.com',
  source_type: 'venue_booking',
  source_id: 'bk-2',
  venue_name: 'Hall B',
  session_label: 'Workshop',
  hold_expires_at: '2026-10-10T09:00:00Z',
})
const expired = entry({
  id: 'hold_expired:bk-2',
  action: 'hold_expired',
  occurred_at: '2026-10-10T09:00:00Z',
  actor_id: null,
  actor_email: null,
  source_type: 'venue_booking',
  source_id: 'bk-2',
  venue_name: 'Hall B',
  session_label: 'Workshop',
})
const note = entry({
  id: 'clarification_requested:cl-1',
  action: 'clarification_requested',
  occurred_at: '2026-10-02T02:30:00Z',
  actor_id: 'u-coord',
  actor_email: 'coordinator@example.com',
  source_type: 'clarification',
  source_id: 'cl-1',
  note: 'Budget looks unrealistic',
})

function renderWith(response: Response | (() => Response), ui: ReactElement) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'organiser', roles: ['organiser'] }),
  )
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input) === URL) return typeof response === 'function' ? response() : response
    throw new Error(`unexpected request ${String(input)}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>{ui}</AuthProvider>
    </QueryClientProvider>,
  )
  return fetchSpy
}

function ok(entries: EventHistoryEntry[]) {
  return new Response(JSON.stringify(entries), { status: 200 })
}

const history = <EventHistory eventId="ev-1" eventName="Open Day" />

describe('SCRUM-88 event history display (frontend unit)', () => {
  test('rows keep the API order, even where the times are not ascending', async () => {
    // Deliberately out of time order: the API owns ordering, so the UI must not re-sort.
    renderWith(ok([created, rejected, assigned]), history)
    const [first, second, third, ...rest] = await screen.findAllByRole('listitem')

    expect(first).toHaveTextContent(/^Draft created/)
    expect(second).toHaveTextContent(/^Coordinator review: rejected/)
    expect(third).toHaveTextContent(/^Coordinator reassigned/)
    expect(rest).toHaveLength(0)
  })

  test('each row shows action, actor, Singapore time, record and every detail it has', async () => {
    renderWith(ok([rejected, assigned, venueRejected, held, note]), history)
    const [decision, reassignment, venue, hold, internal] = await screen.findAllByRole('listitem')

    expect(decision).toHaveTextContent('Coordinator review: rejected by coordinator@example.com')
    expect(decision).toHaveTextContent('Reason: Expected attendance exceeds the venue')
    expect(decision).toHaveTextContent('Record: event request ev-1')
    const time = decision.querySelector('time')
    expect(time).toHaveAttribute('dateTime', rejected.occurred_at)
    expect(time).toHaveTextContent(formatSingaporeTime(rejected.occurred_at))
    expect(decision).not.toHaveTextContent(rejected.occurred_at)

    expect(reassignment).toHaveTextContent('by lead@example.com')
    expect(reassignment).toHaveTextContent('alice@example.com → bob@example.com')
    expect(reassignment).toHaveTextContent('Record: assignment as-1')

    expect(venue).toHaveTextContent('Venue Staff decision: rejected by staff@example.com')
    expect(venue).toHaveTextContent('Hall A, Main session')
    expect(venue).toHaveTextContent('Reason: Closed for maintenance')
    expect(venue).toHaveTextContent('Record: venue booking bk-1')

    expect(hold).toHaveTextContent('Tentative hold placed by staff@example.com')
    expect(hold).toHaveTextContent(`Held until ${formatSingaporeTime('2026-10-10T09:00:00Z')}`)

    expect(internal).toHaveTextContent('Internal note by coordinator@example.com')
    expect(internal).toHaveTextContent('Note: Budget looks unrealistic')
    expect(internal).toHaveTextContent('Record: internal note cl-1')
  })

  test('an entry with no actor is the system; an actor without an email is unknown', async () => {
    renderWith(ok([expired, { ...created, actor_email: null }]), history)
    const [expiry, missing] = await screen.findAllByRole('listitem')

    expect(expiry).toHaveTextContent('Hold expired by System')
    expect(missing).toHaveTextContent('Draft created by Unknown user')
  })

  test('shows no note entries when the API sends none: the UI never invents them', async () => {
    renderWith(ok([created, rejected]), history)
    await screen.findAllByRole('listitem')

    expect(screen.queryByText(/Internal note/)).toBeNull()
    expect(screen.queryByText(/^Note:/)).toBeNull()
  })

  test('an empty history has a clear empty state', async () => {
    renderWith(ok([]), history)

    expect(await screen.findByText('No history you can see for Open Day yet.')).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).toBeNull()
  })

  test('a 403 shows that the history is not available, and no entries', async () => {
    renderWith(new Response(JSON.stringify({ detail: 'Forbidden' }), { status: 403 }), history)

    expect(
      await screen.findByText('This event’s history is not available to you.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  test('any other failure is reported as an error', async () => {
    renderWith(new Response('', { status: 500 }), history)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load history: Could not load event history (500)',
    )
  })

  test('the toggle fetches nothing until opened, and offers no other control', async () => {
    const fetchSpy = renderWith(
      () => ok([created]),
      <EventHistoryToggle eventId="ev-1" eventName="Open Day" />,
    )
    const toggle = screen.getByRole('button', { name: 'View event history' })

    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(fetchSpy).not.toHaveBeenCalled()

    fireEvent.click(toggle)
    expect(await screen.findByText('Draft created')).toBeInTheDocument()
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Hide event history' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(screen.getAllByRole('button')).toHaveLength(1)
  })
})

// SCRUM-88: CompletedEvents has no test file of its own; its list holds only completed
// events assigned to the viewer, so each one offers the history.
describe('SCRUM-88 completed events offer the event history (frontend unit)', () => {
  test('a completed event offers the toggle', async () => {
    localStorage.setItem(
      'connectsphere.token',
      JSON.stringify({ token: 'token', userId: 'coord', roles: ['coordinator'] }),
    )
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url === '/api/event-requests/assigned-completed')
        return new Response(JSON.stringify([{ id: 'ev-1', name: 'Open Day' }]), { status: 200 })
      if (url === '/api/event-requests/ev-1/closure') return new Response('', { status: 404 })
      if (url === URL) return ok([created])
      throw new Error(`unexpected request ${url}`)
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <CompletedEvents />
        </AuthProvider>
      </QueryClientProvider>,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'View event history' }))
    expect(await screen.findByText('Draft created')).toBeInTheDocument()
  })
})
