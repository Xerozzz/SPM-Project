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

test('shows an error state when the inbox fails to load', async () => {
  signIn()
  renderInbox(async () => {
    throw new Error('boom')
  })
  await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
})
