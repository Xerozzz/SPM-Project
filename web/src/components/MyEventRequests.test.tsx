import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import type { EventRequest } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import MyEventRequests from './MyEventRequests'

// SCRUM-46: the organiser's list, and what they see after submitting — confirmation for a
// complete draft (AC1), the fields to fix for an incomplete one (AC2), and a lock once
// submitted (AC3). The API is mocked; the rules live there, not here.
//
// SCRUM-35: the API also says what each status permits, and the component offers only
// those. These fixtures carry the same `status_permits` the real API returns.
// SCRUM-46 keeps submit behaviour visible. SCRUM-29 adds the draft save/reopen path:
// incomplete drafts can be saved, reopened with persisted values, edited, and submitted with
// API validation feedback. SCRUM-112 removes the organisation drafts list: drafts are no
// longer shared, so only the organiser's own requests are shown.

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const draft = eventRequest({
  id: 'req-1',
  status: 'draft',
  name: 'Orientation Day',
  description: 'Campus welcome',
  submitted_at: null,
  status_permits: ['edit', 'submit'],
})

const submitted = eventRequest({
  id: 'req-2',
  status: 'submitted',
  name: 'Open Day',
  submitted_at: '2026-09-12T09:00:00Z',
  status_permits: [],
})

const rejected = eventRequest({
  id: 'req-3',
  status: 'rejected',
  name: 'Rejected Open Day',
  status_permits: ['edit', 'submit'],
  rejection_reason: 'Please provide a more accessible venue.',
})

type Handler = (init?: RequestInit) => Response

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderSignedIn(
  handlers: Record<string, Handler>,
  onEditDraft: (request: EventRequest) => void = () => {},
) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'user-1', roles: ['organiser'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    const handler = handlers[key] ?? defaultHandler(key)
    if (!handler) throw new Error(`unexpected request ${key}`)
    return handler(init)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <MyEventRequests onEditDraft={onEditDraft} />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

function defaultHandler(key: string): Handler | null {
  if (key === 'GET /api/event-requests/equipment-types') return () => json(['Projector'])
  if (key === 'GET /api/event-requests/venue-names') return () => json(['Hall A'])
  // SCRUM-37: a submitted request lists its change requests.
  if (key.startsWith('GET /api/event-requests/') && key.endsWith('/change-requests'))
    return () => json([])
  // SCRUM-106: the organiser view renders no clarification surface at all — the
  // thread lives only on the coordinator review card — so no clarification fetch
  // is expected here. If one fires, the mock throws and the test fails loudly.
  return null
}

test('lists drafts with a submit button and submitted requests as proposals only', async () => {
  renderSignedIn({ 'GET /api/event-requests': () => json([draft, submitted]) })

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Submit for review' })).toBeInTheDocument()
  expect(screen.getByText('Open Day')).toBeInTheDocument()
  // SCRUM-37: a submitted request is no longer edited directly, only changed by proposal.
  expect(screen.getAllByRole('button', { name: /Propose a change/ })).toHaveLength(1)
  expect(screen.getAllByRole('button', { name: /Edit draft/ })).toHaveLength(1)
})

test('shows a rejection reason to the organiser', async () => {
  renderSignedIn({ 'GET /api/event-requests': () => json([rejected]) })

  expect(await screen.findByText('Rejected Open Day')).toBeInTheDocument()
  expect(
    screen.getByText('Rejection reason: Please provide a more accessible venue.'),
  ).toBeInTheDocument()
})

test('submitting an incomplete draft names the fields to correct', async () => {
  renderSignedIn({
    'GET /api/event-requests': () => json([draft]),
    'GET /api/event-requests/req-1': () => json(draft),
    'POST /api/event-requests/req-1/submit': () =>
      json(
        {
          detail: [
            { field: 'description', reason: 'is required' },
            { field: 'end_at', reason: 'must be after the start' },
          ],
        },
        422,
      ),
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Submit for review' }))

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('“Orientation Day” cannot be submitted yet')
  expect(alert).toHaveTextContent('Description is required')
  expect(alert).toHaveTextContent('End date and time must be after the start')
  // Still offered, so the organiser can fix the draft and try again.
  expect(screen.getByRole('button', { name: 'Submit for review' })).toBeInTheDocument()
})

test('submitting a complete draft shows confirmation and the new status', async () => {
  let listed = [draft]
  renderSignedIn({
    'GET /api/event-requests': () => json(listed),
    'POST /api/event-requests/req-1/submit': () => {
      listed = [
        { ...draft, status: 'submitted', submitted_at: '2026-09-12T09:00:00Z', status_permits: [] },
      ]
      return json(listed[0])
    },
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Submit for review' }))

  expect(await screen.findByRole('status')).toHaveTextContent(
    '“Orientation Day” has been submitted for review. Its status is now Submitted.',
  )
  expect(
    await screen.findByRole('button', { name: 'Propose a change to Orientation Day' }),
  ).toBeInTheDocument()
})

describe('SCRUM-112 own drafts only (frontend unit)', () => {
  test('shows no organisation drafts section and never requests the drafts list', async () => {
    renderSignedIn({ 'GET /api/event-requests': () => json([draft]) })

    expect(await screen.findByLabelText('Edit draft Orientation Day')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Organisation drafts' })).toBeNull()
    expect(screen.queryByText(/Shared draft|Read-only/)).toBeNull()
    const urls = vi.mocked(globalThis.fetch).mock.calls.map(([input]) => String(input))
    expect(urls).not.toContain('/api/event-requests/drafts')
  })
})

test('shows an error when the list cannot be loaded', async () => {
  renderSignedIn({ 'GET /api/event-requests': () => json({ detail: 'boom' }, 500) })

  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load your requests')
})

test('offers only what the API permits, not what the status implies', async () => {
  // A draft the server permits editing but not submitting. Status alone would offer
  // Submit; status_permits does not, and the component must follow the server. Editing is
  // still allowed, so it is not "Locked" either.
  const notSubmittable = { ...draft, status_permits: ['edit'] }
  renderSignedIn({ 'GET /api/event-requests': () => json([notSubmittable]) })

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Submit for review' })).not.toBeInTheDocument()
  expect(screen.queryByText(/Locked/)).not.toBeInTheDocument()
})
function eventRequest(overrides: Partial<EventRequest>): EventRequest {
  return {
    id: 'req',
    status: 'draft',
    coordinator_id: null,
    name: null,
    purpose: null,
    description: null,
    start_at: null,
    end_at: null,
    expected_attendance: null,
    venue_requirement: null,
    accessibility_requirement: null,
    equipment_requirement: null,
    layout_requirement: null,
    registration_requirement: null,
    created_at: '2026-09-12T08:00:00Z',
    updated_at: '2026-09-12T08:00:00Z',
    submitted_at: null,
    decided_by_id: null,
    decided_at: null,
    rejection_reason: null,
    ...overrides,
    status_permits: overrides.status_permits ?? ['edit', 'submit'],
  }
}

test('choosing a draft hands the full request to the form above', async () => {
  // The list carries a summary, so it fetches the whole request before handing it over.
  // Editing happens in the one form on the page; this component no longer owns one.
  const chosen: EventRequest[] = []
  renderSignedIn(
    {
      'GET /api/event-requests': () => json([draft]),
      'GET /api/event-requests/req-1': () => json(draft),
    },
    (request) => chosen.push(request),
  )

  fireEvent.click(await screen.findByLabelText('Edit draft Orientation Day'))

  await waitFor(() => expect(chosen).toHaveLength(1))
  expect(chosen[0].id).toBe('req-1')
  expect(chosen[0].description).toBe('Campus welcome')
  // No second form appears here.
  expect(screen.queryByRole('form', { name: 'Event request draft form' })).toBeNull()
})

test('there is no New draft button, because the form above is always there', async () => {
  renderSignedIn({
    'GET /api/event-requests': () => json([draft]),
  })

  await screen.findByLabelText('Edit draft Orientation Day')
  expect(screen.queryByRole('button', { name: 'New draft' })).toBeNull()
})

describe('SCRUM-105 owner views assignment history (frontend unit)', () => {
  const historyUrl = '/api/event-requests/req-2/assignment-history'
  const entry = {
    id: 'h-1',
    previous_coordinator_id: null,
    previous_coordinator_email: null,
    new_coordinator_id: 'c-1',
    new_coordinator_email: 'coordinator@example.com',
    acted_by_id: 'l-1',
    acted_by_email: 'lead@example.com',
    assigned_at: '2026-09-13T02:00:00Z',
  }

  function requestedUrls() {
    return vi.mocked(globalThis.fetch).mock.calls.map(([input]) => String(input))
  }

  test('a submitted row offers the toggle, a draft row does not, and nothing loads until opened', async () => {
    renderSignedIn({
      'GET /api/event-requests': () => json([draft, submitted]),
      [`GET ${historyUrl}`]: () => json([entry]),
    })
    const rows = await screen.findAllByRole('listitem')
    const draftRow = rows.find((row) => row.textContent?.includes('Orientation Day'))!
    const submittedRow = rows.find((row) => row.textContent?.includes('Open Day'))!

    expect(within(draftRow).queryByRole('button', { name: 'View assignment history' })).toBeNull()
    expect(requestedUrls()).not.toContain(historyUrl)

    fireEvent.click(within(submittedRow).getByRole('button', { name: 'View assignment history' }))

    expect(
      await within(submittedRow).findByText(/First assignment → coordinator@example.com/),
    ).toHaveTextContent('by lead@example.com')
    expect(requestedUrls().filter((url) => url === historyUrl)).toHaveLength(1)
    expect(within(submittedRow).queryByRole('button', { name: /^(re)?assign$/i })).toBeNull()
    expect(within(submittedRow).queryByRole('combobox')).toBeNull()
  })

  test('a submitted event that was never assigned shows the existing empty state', async () => {
    renderSignedIn({
      'GET /api/event-requests': () => json([submitted]),
      [`GET ${historyUrl}`]: () => json([]),
    })

    fireEvent.click(await screen.findByRole('button', { name: 'View assignment history' }))

    expect(await screen.findByText('No assignment history for Open Day yet.')).toBeInTheDocument()
  })
})
