import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

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
// incomplete drafts can be saved, reopened with persisted values, edited, submitted with
// API validation feedback, and organisation-visible non-owned drafts stay read-only.

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

function renderSignedIn(handlers: Record<string, Handler>) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', roles: ['organiser'] }),
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
        <MyEventRequests />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

function defaultHandler(key: string): Handler | null {
  if (key === 'GET /api/event-requests/drafts') return () => json([])
  // Submitted requests render their clarification thread, which loads on mount.
  if (/^GET \/api\/event-requests\/[^/]+\/clarifications$/.test(key)) return () => json([])
  return null
}

test('lists drafts with a submit button and submitted requests as locked', async () => {
  renderSignedIn({ 'GET /api/event-requests': () => json([draft, submitted]) })

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Submit for review' })).toBeInTheDocument()
  expect(screen.getByText('Open Day')).toBeInTheDocument()
  expect(screen.getAllByText(/Locked/)).toHaveLength(1)
})

test('shows a rejection reason to the organiser', async () => {
  renderSignedIn({ 'GET /api/event-requests': () => json([rejected]) })

  expect(await screen.findByText('Rejected Open Day')).toBeInTheDocument()
  expect(
    screen.getByText('Rejection reason: Please provide a more accessible venue.'),
  ).toBeInTheDocument()
})

test('incomplete form can be saved as a draft with confirmation and status', async () => {
  let listed: EventRequest[] = []
  const saved = eventRequest({ id: 'req-3', name: 'Hackathon', status: 'draft' })
  const create = vi.fn((init?: RequestInit) => {
    expect(JSON.parse(String(init?.body))).toMatchObject({
      name: 'Hackathon',
      purpose: null,
      start_at: null,
      expected_attendance: null,
    })
    listed = [saved]
    return json(saved, 201)
  })

  renderSignedIn({
    'GET /api/event-requests': () => json(listed),
    'GET /api/event-requests/drafts': () => json(listed),
    'POST /api/event-requests/drafts': create,
  })

  fireEvent.click(await screen.findByRole('button', { name: 'New draft' }))
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Hackathon' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save Draft' }))

  expect(await screen.findByRole('status')).toHaveTextContent('“Hackathon” was saved as a Draft.')
  expect(create).toHaveBeenCalledOnce()
  expect(await screen.findAllByText('Draft')).not.toHaveLength(0)
})

test('reopened draft shows persisted values and can be edited', async () => {
  let listed = [draft]
  const update = vi.fn((init?: RequestInit) => {
    expect(JSON.parse(String(init?.body))).toMatchObject({
      description: 'Updated campus welcome',
    })
    listed = [eventRequest({ ...draft, description: 'Updated campus welcome' })]
    return json(listed[0])
  })

  renderSignedIn({
    'GET /api/event-requests': () => json(listed),
    'GET /api/event-requests/drafts': () => json(listed),
    'GET /api/event-requests/req-1': () => json(draft),
    'PATCH /api/event-requests/req-1': update,
  })

  fireEvent.click(await screen.findByLabelText('Edit draft Orientation Day'))

  const form = await screen.findByRole('form', { name: 'Event request draft form' })
  expect(within(form).getByDisplayValue('Orientation Day')).toBeInTheDocument()
  expect(within(form).getByDisplayValue('Campus welcome')).toBeInTheDocument()

  fireEvent.change(within(form).getByLabelText('Description'), {
    target: { value: 'Updated campus welcome' },
  })
  fireEvent.click(within(form).getByRole('button', { name: 'Save Draft' }))

  expect(await screen.findByRole('status')).toHaveTextContent(
    '“Orientation Day” was saved as a Draft.',
  )
  expect(update).toHaveBeenCalledOnce()
})

test('submitting an incomplete draft names the fields to correct', async () => {
  renderSignedIn({
    'GET /api/event-requests': () => json([draft]),
    'GET /api/event-requests/drafts': () => json([draft]),
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

  fireEvent.click(await screen.findByLabelText('Edit draft Orientation Day'))
  const form = await screen.findByRole('form', { name: 'Event request draft form' })
  fireEvent.click(within(form).getByRole('button', { name: 'Submit for review' }))

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('“Orientation Day” cannot be submitted yet')
  expect(alert).toHaveTextContent('Description is required')
  expect(alert).toHaveTextContent('End date and time must be after the start')
  expect(within(form).getByRole('button', { name: 'Submit for review' })).toBeInTheDocument()
})

test('submitting a complete draft shows confirmation and the new status', async () => {
  let listed = [draft]
  renderSignedIn({
    'GET /api/event-requests': () => json(listed),
    'GET /api/event-requests/drafts': () => json(listed),
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
  expect(await screen.findByText(/Locked/)).toBeInTheDocument()
})

test('same-organisation non-owner draft is visible without edit controls', async () => {
  const shared = eventRequest({ id: 'req-shared', name: 'Shared Planning', status: 'draft' })
  renderSignedIn({
    'GET /api/event-requests': () => json([]),
    'GET /api/event-requests/drafts': () => json([shared]),
  })

  expect(await screen.findByText('Shared Planning')).toBeInTheDocument()
  expect(screen.getByText('Read-only')).toBeInTheDocument()
  expect(screen.queryByLabelText('Edit draft Shared Planning')).not.toBeInTheDocument()
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
    ...overrides,
    status_permits: overrides.status_permits ?? ['edit', 'submit'],
  }
}
