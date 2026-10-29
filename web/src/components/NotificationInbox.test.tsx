import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import NotificationInbox from './NotificationInbox'

// TC-99-08: the inbox renders loading, empty, populated (event/action/time, newest
// first, unread distinguishable) and failed states; marking viewed keeps the row
// visible with its viewed time.

const newer = {
  id: 'notif-newer',
  event_request_id: 'req-1',
  type: 'general',
  source_type: 'general',
  source_id: 'newer',
  occurred_at: '2026-04-01T10:00:00Z',
  created_at: '2026-04-01T10:00:00Z',
  viewed_at: null,
  is_unread: true,
}

const older = {
  id: 'notif-older',
  event_request_id: 'req-1',
  type: 'general',
  source_type: 'general',
  source_id: 'older',
  occurred_at: '2026-04-01T09:00:00Z',
  created_at: '2026-04-01T09:00:00Z',
  viewed_at: null,
  is_unread: true,
}

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function signIn() {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'user-1', roles: ['organiser'] }),
  )
}

function renderInbox(
  fetchImpl: (input: string | URL | Request, init?: RequestInit) => Promise<Response>,
) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetchImpl as typeof globalThis.fetch)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <NotificationInbox />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return client
}

test('shows a loading state while the inbox loads', () => {
  signIn()
  renderInbox(() => new Promise<Response>(() => {}))
  expect(screen.getByText('Loading notifications…')).toBeDefined()
})

test('shows an empty state when the inbox has no rows', async () => {
  signIn()
  renderInbox(async () => json([]))
  await waitFor(() =>
    expect(
      screen.getByText('You have no notifications. New activity on your events will appear here.'),
    ).toBeDefined(),
  )
})

test('shows event, action and time newest first with unread distinguishable', async () => {
  signIn()
  renderInbox(async () => json([newer, older]))
  await waitFor(() => expect(screen.getAllByText('Unread')).toHaveLength(2))
  const items = screen.getAllByRole('listitem')
  expect(items[0].textContent).toContain('req-1')
  expect(items[0].textContent).toContain('newer')
  expect(items[0].textContent).toContain('2026-04-01T10:00:00Z')
  expect(items[1].textContent).toContain('older')
})

test('marking viewed keeps the row visible with its viewed time', async () => {
  signIn()
  const viewed = { ...newer, viewed_at: '2026-04-01T11:00:00Z', is_unread: false }
  let calls = 0
  renderInbox(async (input, init) => {
    calls += 1
    if (String(input).endsWith('/viewed') && init?.method === 'POST') return json(viewed)
    if (calls === 1) return json([newer])
    return json([viewed])
  })
  await waitFor(() => expect(screen.getByText('Mark viewed')).toBeDefined())
  fireEvent.click(screen.getByText('Mark viewed'))
  await waitFor(() => expect(screen.getByText('2026-04-01T11:00:00Z')).toBeDefined())
  expect(screen.queryByText('Mark viewed')).toBeNull()
})

test('links registration-status notifications to the attendee registration view', async () => {
  signIn()
  renderInbox(async () =>
    json([{ ...newer, type: 'registration_accepted', source_type: 'registration_status' }]),
  )
  const link = await screen.findByRole('link', { name: 'View my registration status' })
  expect(link.getAttribute('href')).toBe('#event-registration-req-1')
})

// TC-124-04: an equipment-review item identifies the requirement (source id),
// the review action (type) and the change time, and opens the authorised review
// view — the Technical Support-only queue, whose route requires that role.
test('links equipment-review notifications to the authorised review queue', async () => {
  signIn()
  renderInbox(async () =>
    json([
      {
        ...newer,
        type: 'equipment_review_needed',
        source_type: 'equipment_requirement_change',
        source_id: 'change-1',
      },
    ]),
  )
  const item = await screen.findByRole('listitem')
  expect(item.textContent).toContain('equipment_review_needed')
  expect(item.textContent).toContain('change-1')
  expect(item.textContent).toContain('2026-04-01T10:00:00Z')
  const link = screen.getByRole('link', { name: 'Review equipment requirements' })
  expect(link.getAttribute('href')).toBe('#equipment-review-queue')
})

// TC-125-05: a review-outcome and a reservation item each identify the requirement
// (source id), the outcome (type) and the action time, and open the authorised
// record view — the Coordinator's own assigned-events section, which the API scopes
// by Coordinator ID so nobody else's event is reachable.
test.each([
  ['equipment_review_available', 'equipment_review'],
  ['equipment_review_partially_available', 'equipment_review'],
  ['equipment_review_unavailable', 'equipment_review'],
  ['equipment_reserved_full', 'equipment_reservation'],
  ['equipment_reserved_partial', 'equipment_reservation'],
])('links %s notifications to the authorised coordinator view', async (type, source) => {
  signIn()
  renderInbox(async () =>
    json([{ ...newer, type, source_type: source, source_id: 'outcome-1' }]),
  )
  const item = await screen.findByRole('listitem')
  expect(item.textContent).toContain(type)
  expect(item.textContent).toContain('outcome-1')
  expect(item.textContent).toContain('2026-04-01T10:00:00Z')
  const link = screen.getByRole('link', { name: 'View equipment outcome' })
  expect(link.getAttribute('href')).toBe('#coordinator-events')
})

// TC-122-05: a venue decision and a hold-expiry edit each identify the arrangement
// (source id), the outcome (type) and the action time, and open the authorised
// record view — the Coordinator's own assigned-events section, which the API scopes
// by Coordinator ID so nobody else's event is reachable.
test.each([
  ['venue_booking_approved', 'venue_decision'],
  ['venue_booking_rejected', 'venue_decision'],
  ['venue_hold_expiry_updated', 'venue_decision'],
])('links %s notifications to the authorised coordinator view', async (type, source) => {
  signIn()
  renderInbox(async () =>
    json([{ ...newer, type, source_type: source, source_id: 'decision-1' }]),
  )
  const item = await screen.findByRole('listitem')
  expect(item.textContent).toContain(type)
  expect(item.textContent).toContain('decision-1')
  expect(item.textContent).toContain('2026-04-01T10:00:00Z')
  const link = screen.getByRole('link', { name: 'View venue decision' })
  expect(link.getAttribute('href')).toBe('#coordinator-events')
})

// TC-123-05 (frontend part): a cancelled arrangement identifies the booking
// (source id), the cancellation action (type) and the cancellation time, and
// opens the authorised record view — the Venue Staff-only decisions section.
test('links venue-cancellation notifications to the authorised staff view', async () => {
  signIn()
  renderInbox(async () =>
    json([
      {
        ...newer,
        type: 'venue_arrangement_cancelled',
        source_type: 'venue_cancellation',
        source_id: 'booking-1',
      },
    ]),
  )
  const item = await screen.findByRole('listitem')
  expect(item.textContent).toContain('venue_arrangement_cancelled')
  expect(item.textContent).toContain('booking-1')
  expect(item.textContent).toContain('2026-04-01T10:00:00Z')
  const link = screen.getByRole('link', { name: 'View venue booking decisions' })
  expect(link.getAttribute('href')).toBe('#venue-booking-decisions')
})

// TC-127-04 (frontend part): a revised request identifies the replacement booking
// (source id), the revision action (type) and the submission time, and opens the
// authorised review view — the Venue Staff-only decisions section.
test('links venue-revision notifications to the authorised staff view', async () => {
  signIn()
  renderInbox(async () =>
    json([
      {
        ...newer,
        type: 'venue_revision_submitted',
        source_type: 'venue_revision',
        source_id: 'revision-1',
      },
    ]),
  )
  const item = await screen.findByRole('listitem')
  expect(item.textContent).toContain('venue_revision_submitted')
  expect(item.textContent).toContain('revision-1')
  expect(item.textContent).toContain('2026-04-01T10:00:00Z')
  const link = screen.getByRole('link', { name: 'Review revised venue request' })
  expect(link.getAttribute('href')).toBe('#venue-booking-decisions')
})

test('shows an error state when the inbox fails to load', async () => {
  signIn()
  renderInbox(async () => {
    throw new Error('boom')
  })
  await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
})
