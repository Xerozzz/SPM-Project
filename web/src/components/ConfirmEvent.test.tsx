import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { EventRequest } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import ConfirmEvent from './ConfirmEvent'

// SCRUM-80: the assigned Coordinator commits a planned event.
//
// The rules stay on the API: what is missing, and whether the Safety Officer's approval
// still applies to the plan as it stands (AC7), are its answers. These tests check that
// the reasons reach the person who has to chase them, that the button cannot be pressed
// when it would be refused, and that a refusal arriving anyway is explained.

beforeEach(() => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'coord-1', roles: ['coordinator'] }),
  )
})

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const EVENT = { id: 'event-1', name: 'Orientation Day' } as EventRequest

const READY = {
  event_request_id: 'event-1',
  may_confirm: true,
  arrangement_blockers: [],
  safety_blockers: [],
}

const CONFIRMED = {
  event_request_id: 'event-1',
  status: 'confirmed',
  confirmed_by_id: 'coord-1',
  confirmed_at: '2030-01-01T02:00:00Z',
  confirmed_bookings: [
    {
      booking_id: 'booking-1',
      venue_id: 'venue-1',
      session_label: 'Main session',
      start_at: '2030-02-01T02:00:00Z',
      end_at: '2030-02-01T06:00:00Z',
    },
  ],
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderCard(
  readiness: unknown = READY,
  handler?: (key: string, init?: RequestInit) => Response | undefined,
  onConfirmed: (message: string) => void = () => {},
) {
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    const answer = handler?.(key, init)
    if (answer) return answer
    if (key === 'GET /api/event-requests/event-1/confirmation') return json(readiness)
    throw new Error(`unexpected request ${key}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ConfirmEvent event={EVENT} onConfirmed={onConfirmed} />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return spy
}

test('a ready event offers confirmation', async () => {
  renderCard()

  const button = await screen.findByLabelText('Confirm Orientation Day')
  await waitFor(() => expect(button).toBeEnabled())
  expect(screen.queryByText('Not ready to confirm.')).not.toBeInTheDocument()
})

test('what is still missing is shown, in the words of whoever owes it', async () => {
  renderCard({
    ...READY,
    may_confirm: false,
    arrangement_blockers: ['hold_expired', 'equipment_unreviewed'],
    safety_blockers: ['safety_not_reviewed'],
  })

  expect(await screen.findByText('Not ready to confirm.')).toBeInTheDocument()
  expect(screen.getByText(/A venue hold has run out/)).toBeInTheDocument()
  expect(screen.getByText(/Technical Support have not assessed/)).toBeInTheDocument()
  expect(screen.getByText(/Safety Officer has not reviewed/)).toBeInTheDocument()
  expect(screen.getByLabelText('Confirm Orientation Day')).toBeDisabled()
})

test('an approval that no longer matches the plan is explained as needing review again', async () => {
  // AC7: the reason this is its own message rather than "not approved" is that the
  // Coordinator's next step differs — the plan moved, so the Officer has to look again.
  renderCard({
    ...READY,
    may_confirm: false,
    arrangement_blockers: [],
    safety_blockers: ['safety_approval_stale'],
  })

  expect(
    await screen.findByText(/plan changed after the Safety Officer approved it/),
  ).toBeInTheDocument()
})

test('confirming commits the event and hands the outcome to the parent', async () => {
  // Reported upward rather than shown here: a confirmed event leaves the Coordinator's
  // list, so this card unmounts on success and anything it rendered would vanish with
  // it. Pressing the button looked like it had done nothing at all.
  const told: string[] = []
  const spy = renderCard(
    READY,
    (key) => (key === 'POST /api/event-requests/event-1/confirm' ? json(CONFIRMED) : undefined),
    (message) => told.push(message),
  )

  const button = await screen.findByLabelText('Confirm Orientation Day')
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)

  await waitFor(() => {
    expect(told).toEqual(['“Orientation Day” is confirmed. Its venue booking is now committed.'])
  })
  expect(spy.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true)
})

test('several committed bookings are counted rather than described as one', async () => {
  const told: string[] = []
  renderCard(
    READY,
    (key) =>
      key === 'POST /api/event-requests/event-1/confirm'
        ? json({
            ...CONFIRMED,
            confirmed_bookings: [
              ...CONFIRMED.confirmed_bookings,
              { ...CONFIRMED.confirmed_bookings[0], booking_id: 'booking-2' },
            ],
          })
        : undefined,
    (message) => told.push(message),
  )

  const button = await screen.findByLabelText('Confirm Orientation Day')
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)

  await waitFor(() => {
    expect(told[0]).toContain('2 venue bookings are now committed.')
  })
})

test('a refusal that arrives anyway is explained with its reasons', async () => {
  // The readiness answer is a moment old: a hold can run out between the card loading
  // and the button being pressed, and the API refuses rather than confirming.
  renderCard(READY, (key) =>
    key === 'POST /api/event-requests/event-1/confirm'
      ? json(
          {
            detail: {
              reason: 'not_confirmable',
              arrangement_blockers: ['hold_expired'],
              safety_blockers: [],
            },
          },
          409,
        )
      : undefined,
  )

  const button = await screen.findByLabelText('Confirm Orientation Day')
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)

  await waitFor(() => {
    expect(screen.getByRole('alert')).toHaveTextContent('This event cannot be confirmed yet.')
  })
  expect(screen.getByRole('alert')).toHaveTextContent('A venue hold has run out')
})

test('a readiness check that cannot be loaded is reported', async () => {
  renderCard(READY, (key) =>
    key === 'GET /api/event-requests/event-1/confirmation' ? json({ detail: 'nope' }, 500) : undefined,
  )

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Could not check whether this event can be confirmed (500)',
  )
})
