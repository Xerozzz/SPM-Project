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
    session_start_at: null,
    session_end_at: null,
    related_booking_id: null,
    affected_booking_ids: [],
    changes: [],
    equipment_type: null,
    quantity: null,
    actor_recorded: true,
    replan_cause: null,
    related_entry_ids: [],
    period_start_at: null,
    period_end_at: null,
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

// SCRUM-119: venue change entries. The API decides which fields each carries (ADR-0064);
// the component shows the period, the replacement link, the affected arrangements and
// each before-and-after value under the label the API sends.
describe('SCRUM-119 venue change entries (frontend unit)', () => {
  const START = '2026-12-01T02:00:00Z'
  const END = '2026-12-01T04:00:00Z'
  const venue = {
    source_type: 'venue_booking' as const,
    venue_name: 'Hall A',
    session_label: 'Main session',
    session_start_at: START,
    session_end_at: END,
  }

  test('venue entries show the session label and period in Singapore time', async () => {
    renderWith(
      ok([entry({ ...venue, id: 'venue_requested:bk-1', action: 'venue_requested' })]),
      history,
    )
    const [row] = await screen.findAllByRole('listitem')

    expect(row).toHaveTextContent(
      `Hall A, Main session, ${formatSingaporeTime(START)} to ${formatSingaporeTime(END)}`,
    )
  })

  test('a cancellation shows the Coordinator and reason; adoption links both ways', async () => {
    renderWith(
      ok([
        entry({
          ...venue,
          id: 'replacement_adopted:bk-2',
          action: 'replacement_adopted',
          source_id: 'bk-2',
          actor_id: 'u-coord',
          actor_email: 'coordinator@example.com',
          related_booking_id: 'bk-1',
        }),
        entry({
          ...venue,
          id: 'arrangement_cancelled:bk-1',
          action: 'arrangement_cancelled',
          source_id: 'bk-1',
          actor_id: 'u-coord',
          actor_email: 'coordinator@example.com',
          reason: 'Replaced by an adopted replacement venue request',
          related_booking_id: 'bk-2',
        }),
      ]),
      history,
    )
    const [adopted, cancelled] = await screen.findAllByRole('listitem')

    expect(adopted).toHaveTextContent('Replacement adopted by coordinator@example.com')
    expect(adopted).toHaveTextContent('Replaces arrangement bk-1')
    expect(cancelled).toHaveTextContent('Venue arrangement cancelled by coordinator@example.com')
    expect(cancelled).toHaveTextContent('Reason: Replaced by an adopted replacement venue request')
    expect(cancelled).toHaveTextContent('Replaced by arrangement bk-2')
  })

  test('a buffer change shows each labelled value, old and new, and the affected booking', async () => {
    renderWith(
      ok([
        entry({
          id: 'buffer_changed:bc-1',
          action: 'buffer_changed',
          source_type: 'venue_buffer_change',
          source_id: 'bc-1',
          actor_id: 'u-staff',
          actor_email: 'staff@example.com',
          venue_name: 'Hall A',
          affected_booking_ids: ['bk-1'],
          changes: [
            {
              field: 'setup_minutes',
              label: 'Setup time (minutes)',
              old: '0',
              new: '45',
              kind: 'text',
            },
            {
              field: 'turnaround_minutes',
              label: 'Turnaround time (minutes)',
              kind: 'text',
              old: null,
              new: '30',
            },
          ],
        }),
      ]),
      history,
    )
    const [row] = await screen.findAllByRole('listitem')

    expect(row).toHaveTextContent('Venue buffers changed by staff@example.com')
    expect(row.textContent).toContain('Hall A')
    expect(row).not.toHaveTextContent('null')
    expect(row).toHaveTextContent('Setup time (minutes): 0 → 45')
    expect(row).toHaveTextContent('Turnaround time (minutes): — → 30')
    expect(row).toHaveTextContent('Affected arrangements: bk-1')
    expect(row).toHaveTextContent('Record: venue buffer change bc-1')
    // Labels come from the API; the column names never reach the screen.
    expect(row).not.toHaveTextContent('setup_minutes')
  })
})

// SCRUM-119 AC6: equipment entries. Quantities and who did it, "System" for a flag, and
// requirement changes through the same labelled before-and-after renderer.
describe('SCRUM-119 equipment entries (frontend unit)', () => {
  const reservation = {
    source_type: 'equipment_reservation' as const,
    source_id: 'rs-1',
    equipment_type: 'Projector',
    quantity: 2,
  }

  test('a reservation, its flag and its release show the quantity and who', async () => {
    renderWith(
      ok([
        entry({
          ...reservation,
          id: 'equipment_reserved:rs-1',
          action: 'equipment_reserved',
          actor_id: 'u-tech',
          actor_email: 'tech@example.com',
        }),
        entry({
          ...reservation,
          id: 'reservation_flagged:rs-1',
          action: 'reservation_flagged',
          actor_id: null,
          actor_email: null,
        }),
        entry({
          ...reservation,
          id: 'reservation_released:rs-1',
          action: 'reservation_released',
          actor_id: 'u-coord',
          actor_email: 'coordinator@example.com',
        }),
      ]),
      history,
    )
    const [reserved, flagged, released] = await screen.findAllByRole('listitem')

    expect(reserved).toHaveTextContent('Equipment reserved by tech@example.com')
    expect(reserved).toHaveTextContent('Projector × 2')
    expect(flagged).toHaveTextContent('Reservation flagged for reconsideration by System')
    expect(flagged).toHaveTextContent('Projector × 2')
    expect(released).toHaveTextContent('Reservation released by coordinator@example.com')
    expect(released).toHaveTextContent('Record: equipment reservation rs-1')
  })

  test('a requirement change shows its type and each labelled value, old and new', async () => {
    renderWith(
      ok([
        entry({
          id: 'requirement_updated:rc-1',
          action: 'requirement_updated',
          source_type: 'equipment_requirement_change',
          source_id: 'rc-1',
          actor_id: 'u-coord',
          actor_email: 'coordinator@example.com',
          equipment_type: 'Projector',
          changes: [
            { field: 'quantity', label: 'Quantity', old: '2', new: '3', kind: 'text' },
            {
              field: 'technical_requirements',
              label: 'Technical requirements',
              old: null,
              new: 'HDMI',
              kind: 'text',
            },
          ],
        }),
      ]),
      history,
    )
    const [row] = await screen.findAllByRole('listitem')

    expect(row).toHaveTextContent('Equipment requirement changed by coordinator@example.com')
    expect(row).toHaveTextContent('Projector')
    expect(row).not.toHaveTextContent('×')
    expect(row).toHaveTextContent('Quantity: 2 → 3')
    expect(row).toHaveTextContent('Technical requirements: — → HDMI')
    expect(row).not.toHaveTextContent('technical_requirements')
  })
})

describe('SCRUM-120 lifecycle entries (frontend unit)', () => {
  const coordinator = { actor_id: 'u-coord', actor_email: 'coordinator@example.com' }
  const arrangement = entry({
    ...coordinator,
    id: 'arrangement_cancelled:bk-1',
    action: 'arrangement_cancelled',
    source_type: 'venue_booking',
    source_id: 'bk-1',
    venue_name: 'Hall A',
    session_label: 'Morning',
    reason: 'Funding withdrawn',
  })
  const released = entry({
    ...coordinator,
    id: 'reservation_released:rs-1',
    action: 'reservation_released',
    source_type: 'equipment_reservation',
    source_id: 'rs-1',
    equipment_type: 'Projector',
    quantity: 2,
  })

  test('a confirmation names the Coordinator', async () => {
    renderWith(
      ok([entry({ ...coordinator, id: 'event_confirmed:ev-1', action: 'event_confirmed' })]),
      history,
    )

    expect(await screen.findByRole('listitem')).toHaveTextContent(
      'Event confirmed by coordinator@example.com',
    )
  })

  test('a return to planning shows its cause and links what caused it', async () => {
    renderWith(
      ok([
        arrangement,
        entry({
          ...coordinator,
          id: 'returned_to_planning:sr-1',
          action: 'returned_to_planning',
          source_type: 'safety_review',
          source_id: 'sr-1',
          replan_cause: 'venue_cancellation',
          related_entry_ids: [arrangement.id],
        }),
      ]),
      history,
    )
    const rows = await screen.findAllByRole('listitem')
    const back = rows.find((row) => row.textContent?.startsWith('Returned to planning'))

    expect(back).toHaveTextContent('Returned to planning by coordinator@example.com')
    expect(back).toHaveTextContent('Cause: a venue change')
    expect(back).toHaveTextContent('Caused by:Venue arrangement cancelled: Hall A, Morning')
    expect(back).toHaveTextContent('Record: safety approval sr-1')
  })

  test('a return with no recorded actor says so, never "System"', async () => {
    renderWith(
      ok([
        entry({
          id: 'returned_to_planning:sr-1',
          action: 'returned_to_planning',
          source_type: 'safety_review',
          source_id: 'sr-1',
          actor_id: null,
          actor_email: null,
          actor_recorded: false,
          replan_cause: 'change_request',
        }),
      ]),
      history,
    )
    const row = await screen.findByRole('listitem')

    expect(row).toHaveTextContent('(actor not recorded)')
    expect(row).not.toHaveTextContent('System')
    expect(row).toHaveTextContent('Cause: a change request was approved')
  })

  test('a cancellation shows its reason once and names what it released', async () => {
    renderWith(
      ok([
        arrangement,
        released,
        entry({
          ...coordinator,
          id: 'event_cancelled:ev-1',
          action: 'event_cancelled',
          reason: 'Funding withdrawn',
          related_entry_ids: [arrangement.id, released.id],
        }),
      ]),
      history,
    )
    const rows = await screen.findAllByRole('listitem')
    const cancelled = rows.find((row) => row.textContent?.startsWith('Event cancelled'))

    expect(cancelled).toHaveTextContent('Event cancelled by coordinator@example.com')
    expect(cancelled).toHaveTextContent('Reason: Funding withdrawn')
    expect(cancelled).toHaveTextContent(
      'Released:Venue arrangement cancelled: Hall A, MorningReservation released: Projector × 2',
    )
    // The released entries are still their own rows, each shown once.
    expect(
      rows.filter((row) => row.textContent?.startsWith('Venue arrangement cancelled by')),
    ).toHaveLength(1)
  })
})

describe('SCRUM-120 change request and completion entries (frontend unit)', () => {
  const start = { old: '2030-01-10T02:00:00+00:00', new: '2030-01-11T02:00:00+00:00' }

  test('a change request shows its reason, and dates in Singapore time', async () => {
    renderWith(
      ok([
        entry({
          id: 'change_requested:cr-1',
          action: 'change_requested',
          source_type: 'event_change_request',
          source_id: 'cr-1',
          reason: 'Speaker moved',
          changes: [
            { field: 'event.start_at', label: 'Start date and time', ...start, kind: 'datetime' },
            {
              field: 'event.expected_attendance',
              label: 'Expected attendance',
              old: '80',
              new: '120',
              kind: 'text',
            },
          ],
        }),
      ]),
      history,
    )
    const row = await screen.findByRole('listitem')

    expect(row).toHaveTextContent('Change requested by owner@example.com')
    expect(row).toHaveTextContent('Reason: Speaker moved')
    expect(row).toHaveTextContent(
      `Start date and time: ${formatSingaporeTime(start.old)} → ${formatSingaporeTime(start.new)}`,
    )
    expect(row).not.toHaveTextContent(start.old)
    expect(row).toHaveTextContent('Expected attendance: 80 → 120')
    expect(row).toHaveTextContent('Record: change request cr-1')
  })

  test('two sessions changing the same field are both shown', async () => {
    renderWith(
      ok([
        entry({
          id: 'change_requested:cr-1',
          action: 'change_requested',
          changes: [
            { field: 'session.start_at', label: 'Session “AM”: start', ...start, kind: 'datetime' },
            { field: 'session.start_at', label: 'Session “PM”: start', ...start, kind: 'datetime' },
          ],
        }),
      ]),
      history,
    )
    const row = await screen.findByRole('listitem')

    expect(row).toHaveTextContent('Session “AM”: start')
    expect(row).toHaveTextContent('Session “PM”: start')
  })

  test('a decision names its outcome and note', async () => {
    renderWith(
      ok([
        entry({
          id: 'change_decided:cr-1',
          action: 'change_decided',
          source_type: 'event_change_request',
          source_id: 'cr-1',
          actor_id: 'u-coord',
          actor_email: 'coordinator@example.com',
          outcome: 'rejected',
          reason: 'Programme is printed',
        }),
      ]),
      history,
    )

    expect(await screen.findByRole('listitem')).toHaveTextContent(
      'Change request decision: rejected by coordinator@example.com',
    )
  })

  test('completion and a correction show the closure values, old and new', async () => {
    renderWith(
      ok([
        entry({
          id: 'event_completed:ev-1',
          action: 'event_completed',
          changes: [
            {
              field: 'actual_attendance',
              label: 'Actual attendance',
              old: null,
              new: '40',
              kind: 'text',
            },
          ],
        }),
        entry({
          id: 'closure_corrected:cn-2',
          action: 'closure_corrected',
          source_type: 'event_closure_note',
          source_id: 'cn-2',
          changes: [
            {
              field: 'actual_attendance',
              label: 'Actual attendance',
              old: '40',
              new: '42',
              kind: 'text',
            },
          ],
        }),
      ]),
      history,
    )
    const [done, corrected] = await screen.findAllByRole('listitem')

    expect(done).toHaveTextContent('Event completed by owner@example.com')
    expect(done).toHaveTextContent('Actual attendance: — → 40')
    expect(corrected).toHaveTextContent('Closure record corrected')
    expect(corrected).toHaveTextContent('Actual attendance: 40 → 42')
    expect(corrected).toHaveTextContent('Record: closure record cn-2')
  })
})

describe('SCRUM-120 safety decision and venue closure entries (frontend unit)', () => {
  test('a safety decision names the Officer, a readable outcome and the comment', async () => {
    renderWith(
      ok([
        entry({
          id: 'safety_decided:sr-1',
          action: 'safety_decided',
          source_type: 'safety_review',
          source_id: 'sr-1',
          actor_id: 'u-officer',
          actor_email: 'officer@example.com',
          outcome: 'changes_requested',
          reason: 'Add a second exit sign',
        }),
      ]),
      history,
    )
    const row = await screen.findByRole('listitem')

    expect(row).toHaveTextContent('Safety decision: changes requested by officer@example.com')
    expect(row).toHaveTextContent('Reason: Add a second exit sign')
    expect(row).not.toHaveTextContent('changes_requested')
  })

  test('a closure shows its venue, period in Singapore time, reason and arrangements', async () => {
    const period = { start: '2030-01-10T02:00:00Z', end: '2030-01-10T06:00:00Z' }
    renderWith(
      ok([
        entry({
          id: 'venue_closed:ci-1',
          action: 'venue_closed',
          source_type: 'venue_closure_impact',
          source_id: 'ci-1',
          actor_id: 'u-staff',
          actor_email: 'staff@example.com',
          venue_name: 'Hall A',
          reason: 'Burst pipe',
          affected_booking_ids: ['bk-1'],
          period_start_at: period.start,
          period_end_at: period.end,
        }),
      ]),
      history,
    )
    const row = await screen.findByRole('listitem')

    expect(row).toHaveTextContent('Venue closure by staff@example.com')
    expect(row).toHaveTextContent('Hall A')
    expect(row).toHaveTextContent(
      `Closed ${formatSingaporeTime(period.start)} to ${formatSingaporeTime(period.end)}`,
    )
    expect(row).toHaveTextContent('Reason: Burst pipe')
    expect(row).toHaveTextContent('Affected arrangements: bk-1')
    expect(row).toHaveTextContent('Record: venue closure ci-1')
  })
})

describe('SCRUM-136 hold expiry change entries (frontend unit)', () => {
  test('an expiry change shows the hold and its old and new expiry in Singapore time', async () => {
    const expiry = { old: '2030-01-08T02:00:00+00:00', new: '2030-01-09T02:00:00+00:00' }
    renderWith(
      ok([
        entry({
          id: 'hold_expiry_changed:hx-1',
          action: 'hold_expiry_changed',
          source_type: 'venue_hold_expiry_change',
          source_id: 'hx-1',
          actor_id: 'u-staff',
          actor_email: 'staff@example.com',
          venue_name: 'Hall A',
          session_label: 'Morning',
          changes: [{ field: 'expires_at', label: 'Held until', ...expiry, kind: 'datetime' }],
        }),
      ]),
      history,
    )
    const row = await screen.findByRole('listitem')

    expect(row).toHaveTextContent('Hold expiry changed by staff@example.com')
    expect(row).toHaveTextContent('Hall A, Morning')
    expect(row).toHaveTextContent(
      `Held until: ${formatSingaporeTime(expiry.old)} → ${formatSingaporeTime(expiry.new)}`,
    )
    expect(row).toHaveTextContent('Record: hold expiry change hx-1')
  })
})
