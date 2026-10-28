import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { EventRequest, VenueBooking } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import VenueArrangements from './VenueArrangements'

// SCRUM-118: cancelling an arrangement of a Confirmed event is a venue change.

const EVENT = {
  id: 'event-1',
  status: 'confirmed',
  name: 'Orientation Day',
  start_at: '2030-01-10T02:00:00Z',
  end_at: '2030-01-10T06:00:00Z',
  status_permits: [],
  coordinator_id: 'coordinator-1',
} as unknown as EventRequest

const MORNING: VenueBooking = {
  id: 'booking-1',
  venue_id: 'venue-1',
  session_label: 'Morning workshop',
  start_at: '2030-01-10T02:00:00Z',
  end_at: '2030-01-10T04:00:00Z',
  status: 'confirmed',
  conflict: null,
}
const AFTERNOON: VenueBooking = {
  ...MORNING,
  id: 'booking-2',
  session_label: 'Afternoon talk',
  start_at: '2030-01-10T04:00:00Z',
  end_at: '2030-01-10T06:00:00Z',
}
const CHANGE_URL = '/api/event-requests/event-1/venue-bookings/booking-1/venue-change'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'coordinator-1', roles: ['coordinator'] }),
  )
})

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

/** The arrangements list, plus a venue-change route that answers `onChange`. */
function renderSection(
  event: EventRequest = EVENT,
  onChange: () => Response = () =>
    json({ booking: { ...MORNING, status: 'cancelled' }, event_status: 'approved' }),
) {
  const onVenueChanged = vi.fn()
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url === CHANGE_URL) return onChange()
    if (url === '/api/event-requests/event-1/venue-arrangements') {
      return json([MORNING, AFTERNOON])
    }
    if (url === '/api/venues') return json([{ id: 'venue-1', name: 'Hall A', is_active: true }])
    throw new Error(`unexpected request ${url}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <VenueArrangements event={event} onVenueChanged={onVenueChanged} />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return { spy, onVenueChanged }
}

async function openDialog() {
  fireEvent.click(
    await screen.findByRole('button', { name: 'Cancel arrangement for Morning workshop' }),
  )
  return screen.getByRole('dialog')
}

test('SCRUM-118: the assigned Coordinator is offered Cancel arrangement on a Confirmed event', async () => {
  renderSection()

  expect(
    await screen.findByRole('button', { name: 'Cancel arrangement for Morning workshop' }),
  ).toBeInTheDocument()
  expect(
    screen.getByRole('button', { name: 'Cancel arrangement for Afternoon talk' }),
  ).toBeInTheDocument()
})

test.each([
  ['another Coordinator', { ...EVENT, coordinator_id: 'coordinator-2' }],
  ['an event still in planning', { ...EVENT, status: 'approved' }],
] as const)('SCRUM-118: nothing is offered for %s', async (_case, event) => {
  renderSection(event as EventRequest)

  expect(await screen.findByText(/Morning workshop/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Cancel arrangement/ })).toBeNull()
})

test('SCRUM-118: the dialog warns what a venue change does', async () => {
  renderSection()
  const dialog = await openDialog()

  expect(within(dialog).getByRole('note')).toHaveTextContent(
    'The event returns to planning, its safety approval stops counting, and new registrations are suspended. Existing registrations are kept.',
  )
})

test('SCRUM-118: Start venue change needs both a reason and the tick', async () => {
  renderSection()
  const dialog = await openDialog()
  const start = within(dialog).getByRole('button', { name: 'Start venue change' })
  const tick = within(dialog).getByRole('checkbox', {
    name: 'I understand this returns the event to planning',
  })

  expect(start).toBeDisabled()
  fireEvent.change(within(dialog).getByLabelText('Reason for cancelling'), {
    target: { value: 'Hall flooded' },
  })
  expect(start).toBeDisabled()
  fireEvent.click(tick)
  expect(start).toBeEnabled()
  fireEvent.change(within(dialog).getByLabelText('Reason for cancelling'), {
    target: { value: '   ' },
  })
  expect(start).toBeDisabled()
})

test('SCRUM-118: starting sends the reason and confirm_venue_change, then reports back', async () => {
  const { spy, onVenueChanged } = renderSection()
  const dialog = await openDialog()
  fireEvent.change(within(dialog).getByLabelText('Reason for cancelling'), {
    target: { value: 'Hall flooded' },
  })
  fireEvent.click(within(dialog).getByRole('checkbox'))
  fireEvent.click(within(dialog).getByRole('button', { name: 'Start venue change' }))

  await waitFor(() =>
    expect(onVenueChanged).toHaveBeenCalledWith(
      '“Orientation Day” is back in planning. Morning workshop at Hall A is cancelled.',
    ),
  )
  const [, init] = spy.mock.calls.find(([input]) => String(input) === CHANGE_URL) ?? []
  expect(init?.method).toBe('POST')
  expect(JSON.parse(String(init?.body))).toEqual({
    reason: 'Hall flooded',
    confirm_venue_change: true,
  })
})

test('SCRUM-118: a refusal is shown in the dialog and nothing changes', async () => {
  const { onVenueChanged } = renderSection(EVENT, () =>
    json({ detail: 'This arrangement has already been cancelled' }, 409),
  )
  const dialog = await openDialog()
  fireEvent.change(within(dialog).getByLabelText('Reason for cancelling'), {
    target: { value: 'Hall flooded' },
  })
  fireEvent.click(within(dialog).getByRole('checkbox'))
  fireEvent.click(within(dialog).getByRole('button', { name: 'Start venue change' }))

  expect(await within(dialog).findByRole('alert')).toHaveTextContent(
    'This arrangement has already been cancelled',
  )
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(onVenueChanged).not.toHaveBeenCalled()
})
