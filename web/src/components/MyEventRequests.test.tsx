import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import MyEventRequests from './MyEventRequests'

// SCRUM-46: the organiser's list, and what they see after submitting — confirmation for a
// complete draft (AC1), the fields to fix for an incomplete one (AC2), and a lock once
// submitted (AC3). The API is mocked; the rules live there, not here.
//
// SCRUM-35: the API also says what each status permits, and the component offers only
// those. These fixtures carry the same `status_permits` the real API returns.

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const draft = {
  id: 'req-1',
  status: 'draft',
  name: 'Orientation Day',
  submitted_at: null,
  status_permits: ['edit', 'submit'],
}
const submitted = {
  ...draft,
  id: 'req-2',
  name: 'Open Day',
  status: 'submitted',
  status_permits: [],
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderSignedIn(handlers: Record<string, () => Response>) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', roles: ['organiser'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    const handler = handlers[key]
    if (!handler) throw new Error(`unexpected request ${key}`)
    return handler()
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

test('lists drafts with a submit button and submitted requests as locked', async () => {
  renderSignedIn({ 'GET /api/event-requests': () => json([draft, submitted]) })

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Submit for review' })).toBeInTheDocument()
  expect(screen.getByText('Open Day')).toBeInTheDocument()
  expect(screen.getByText(/Locked/)).toBeInTheDocument()
})

test('submitting a complete draft shows confirmation and the new status', async () => {
  let listed = [draft]
  renderSignedIn({
    'GET /api/event-requests': () => json(listed),
    'POST /api/event-requests/req-1/submit': () => {
      listed = [{ ...draft, status: 'submitted', status_permits: [] }]
      return json({
        ...draft,
        status: 'submitted',
        status_permits: [],
        submitted_at: '2026-09-12T09:00:00Z',
      })
    },
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Submit for review' }))

  expect(await screen.findByRole('status')).toHaveTextContent(
    '“Orientation Day” has been submitted for review. Its status is now Submitted.',
  )
  expect(await screen.findByText(/Locked/)).toBeInTheDocument()
})

test('submitting an incomplete draft names the fields to correct', async () => {
  renderSignedIn({
    'GET /api/event-requests': () => json([draft]),
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
  // Still a draft: the button is still there.
  expect(screen.getByRole('button', { name: 'Submit for review' })).toBeInTheDocument()
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