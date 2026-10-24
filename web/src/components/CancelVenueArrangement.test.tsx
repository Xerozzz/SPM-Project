import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { EventRequest, VenueBooking } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import VenueBookingRequest from './VenueBookingRequest'

// SCRUM-109: the assigned Coordinator cancels one venue arrangement from the event page.

const EVENT = {
  id: 'event-1',
  status: 'approved',
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
  status: 'pending',
  conflict: null,
}
const AFTERNOON: VenueBooking = {
  ...MORNING,
  id: 'booking-2',
  session_label: 'Afternoon talk',
  start_at: '2030-01-10T04:00:00Z',
  end_at: '2030-01-10T06:00:00Z',
}
const CANCEL_URL = `/api/event-requests/event-1/venue-bookings/booking-1/cancel`

const sgt = (value: string) =>
  new Date(value).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })

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

/** The bookings list, plus a cancel route that answers `onCancel`. */
function renderPage(
  bookings: VenueBooking[],
  onCancel: (body: { reason: string }) => Response | Promise<Response> = () => json({}),
  event: EventRequest = EVENT,
) {
  let rows = bookings
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url === CANCEL_URL) {
      const body = JSON.parse(String(init?.body)) as { reason: string }
      const response = await onCancel(body)
      if (response.ok) {
        rows = rows.map((row) =>
          row.id === 'booking-1'
            ? {
                ...row,
                status: 'cancelled',
                cancelled_by_id: 'coordinator-1',
                cancelled_at: '2030-01-05T01:00:00Z',
                cancellation_reason: body.reason,
              }
            : row,
        )
      }
      return response
    }
    if (url === '/api/event-requests/event-1/venue-bookings') return json(rows)
    if (url === '/api/venues') return json([{ id: 'venue-1', name: 'Hall A', is_active: true }])
    throw new Error(`unexpected request ${url}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <VenueBookingRequest event={event} />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return spy
}

const cancelButton = (session: string) =>
  screen.findByRole('button', { name: `Cancel arrangement for ${session}` })

function bookingsFetched(spy: ReturnType<typeof renderPage>) {
  return spy.mock.calls.filter(
    ([input, init]) =>
      String(input) === '/api/event-requests/event-1/venue-bookings' && !init?.method,
  ).length
}

/** The dialog has closed and the refreshed row carries the reason. */
async function shownAsCancelled(reason: string) {
  await waitFor(() =>
    expect(screen.getByText('Reason:').parentElement).toHaveTextContent(`Reason: ${reason}`),
  )
  expect(screen.queryByRole('dialog')).toBeNull()
}

async function openDialog(session = 'Morning workshop') {
  fireEvent.click(await cancelButton(session))
  return screen.findByRole('dialog')
}

test('SCRUM-109: each live arrangement offers cancel, and no other does', async () => {
  renderPage([
    MORNING,
    { ...AFTERNOON, status: 'confirmed' },
    {
      ...MORNING,
      id: 'b3',
      session_label: 'Held',
      status: 'tentative',
      expires_at: '2099-01-01T00:00:00Z',
    },
    {
      ...MORNING,
      id: 'b4',
      session_label: 'Lapsed',
      status: 'tentative',
      expires_at: '2020-01-01T00:00:00Z',
    },
    { ...MORNING, id: 'b5', session_label: 'Rejected', status: 'rejected' },
    { ...MORNING, id: 'b6', session_label: 'Expired', status: 'expired' },
  ])

  for (const session of ['Morning workshop', 'Afternoon talk', 'Held']) {
    expect(await cancelButton(session)).toBeInTheDocument()
  }
  for (const session of ['Lapsed', 'Rejected', 'Expired']) {
    expect(screen.queryByRole('button', { name: `Cancel arrangement for ${session}` })).toBeNull()
  }
})

test('SCRUM-109: a Coordinator who is not assigned is not offered cancel', async () => {
  renderPage([MORNING], undefined, { ...EVENT, coordinator_id: 'coordinator-2' })

  expect(await screen.findByText('Morning workshop')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Cancel arrangement/ })).toBeNull()
})

test('SCRUM-109: the dialog names the venue and time and focuses the reason', async () => {
  renderPage([MORNING])
  const dialog = await openDialog()

  expect(within(dialog).getByText('Cancel Morning workshop at Hall A?')).toBeInTheDocument()
  expect(
    within(dialog).getByText(new RegExp(`${sgt(MORNING.start_at)} to ${sgt(MORNING.end_at)}`)),
  ).toBeInTheDocument()
  await waitFor(() => expect(within(dialog).getByLabelText('Reason for cancelling')).toHaveFocus())
})

test('SCRUM-109: Escape and "Keep arrangement" close the dialog without cancelling', async () => {
  const spy = renderPage([MORNING])

  fireEvent.keyDown(await openDialog(), { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  fireEvent.click(within(await openDialog()).getByRole('button', { name: 'Keep arrangement' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(spy.mock.calls.some(([input]) => String(input) === CANCEL_URL)).toBe(false)
})

test('SCRUM-109: a blank reason cannot be sent', async () => {
  renderPage([MORNING])
  const dialog = await openDialog()
  const confirm = within(dialog).getByRole('button', { name: 'Confirm cancellation' })

  expect(confirm).toBeDisabled()
  fireEvent.change(within(dialog).getByLabelText('Reason for cancelling'), {
    target: { value: '   ' },
  })
  expect(confirm).toBeDisabled()
})

test('SCRUM-109: the API refusing the reason is still shown', async () => {
  renderPage([MORNING], () =>
    json({ detail: [{ field: 'reason', reason: 'Give a reason for cancelling' }] }, 422),
  )
  const dialog = await openDialog()
  fireEvent.change(within(dialog).getByLabelText('Reason for cancelling'), {
    target: { value: 'x' },
  })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm cancellation' }))

  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Give a reason for cancelling')
})

test('SCRUM-109: confirming refreshes the bookings and shows who, when and why', async () => {
  const reasons: string[] = []
  const spy = renderPage([MORNING, AFTERNOON], (body) => {
    reasons.push(body.reason)
    return json({})
  })
  const dialog = await openDialog()
  fireEvent.change(within(dialog).getByLabelText('Reason for cancelling'), {
    target: { value: 'Moved online' },
  })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm cancellation' }))

  await shownAsCancelled('Moved online')
  expect(screen.getByText('cancelled')).toBeInTheDocument()
  expect(screen.getByText('Cancelled by you:')).toBeInTheDocument()
  expect(screen.getByText(sgt('2030-01-05T01:00:00Z'))).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(reasons).toEqual(['Moved online'])
  expect(bookingsFetched(spy)).toBe(2)
  expect(
    screen.queryByRole('button', { name: 'Cancel arrangement for Morning workshop' }),
  ).toBeNull()
})

test('SCRUM-109: the buttons are disabled while the cancellation is sent', async () => {
  let answer: (response: Response) => void = () => {}
  renderPage([MORNING], () => new Promise<Response>((resolve) => (answer = resolve)))
  const dialog = await openDialog()
  fireEvent.change(within(dialog).getByLabelText('Reason for cancelling'), {
    target: { value: 'Moved online' },
  })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm cancellation' }))

  expect(await within(dialog).findByRole('button', { name: 'Cancelling…' })).toBeDisabled()
  expect(within(dialog).getByRole('button', { name: 'Keep arrangement' })).toBeDisabled()
  answer(json({}))
  await shownAsCancelled('Moved online')
})

test('SCRUM-109: the other arrangement is unchanged and can still be cancelled', async () => {
  renderPage([MORNING, AFTERNOON])
  const dialog = await openDialog()
  fireEvent.change(within(dialog).getByLabelText('Reason for cancelling'), {
    target: { value: 'Moved online' },
  })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm cancellation' }))
  await shownAsCancelled('Moved online')

  const afternoon = screen.getByText('Afternoon talk').closest('li')
  expect(afternoon).not.toBeNull()
  expect(within(afternoon!).getByText('pending')).toBeInTheDocument()
  expect(within(afternoon!).queryByText(/Cancelled by/)).toBeNull()
  expect(await cancelButton('Afternoon talk')).toBeInTheDocument()
})

test.each([
  [409, 'This hold has expired and cannot be cancelled'],
  [403, 'Forbidden'],
  [404, 'Venue booking not found'],
])('SCRUM-109: a %s shows the API message and changes nothing', async (status, detail) => {
  const spy = renderPage([MORNING], () => json({ detail }, status))
  const dialog = await openDialog()
  fireEvent.change(within(dialog).getByLabelText('Reason for cancelling'), {
    target: { value: 'Moved online' },
  })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm cancellation' }))

  expect(await within(dialog).findByRole('alert')).toHaveTextContent(detail)
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.getByText('pending')).toBeInTheDocument()
  expect(bookingsFetched(spy)).toBe(1)
})
