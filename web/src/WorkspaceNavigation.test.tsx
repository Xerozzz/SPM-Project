import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import App from './App'
import type { EventRequest } from './api/eventRequests'

// SCRUM-99 / SCRUM-29: notification navigation is reloadable, role-limited and guarded.
const event: EventRequest = {
  id: 'req-1',
  name: 'Welcome Fair',
  status: 'draft',
  status_permits: ['edit', 'submit'],
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
  coordinator_id: null,
  created_at: '2026-04-01T10:00:00Z',
  updated_at: '2026-04-01T10:00:00Z',
  submitted_at: null,
  decided_at: null,
  decided_by_id: null,
  rejection_reason: null,
}
const notification = {
  id: 'n-1',
  event_request_id: event.id,
  event_name: event.name,
  type: 'request_approved',
  source_type: 'event_decision',
  source_id: 'decision-1',
  occurred_at: '2026-04-01T10:00:00Z',
  created_at: '2026-04-01T10:00:00Z',
  viewed_at: null,
  is_unread: true,
}
function json(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200 })
}
function renderWorkspace(role = 'organiser') {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'u-1', roles: [role] }),
  )
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url === '/api/notifications') return json([notification])
    if (url === '/api/event-requests') return json([event])
    if (url === '/api/event-requests/req-1') return json(event)
    return json([])
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rendered = render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
  return { ...rendered, fetch }
}
beforeEach(() => {
  window.history.replaceState(null, '', '/')
})
afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
  window.history.replaceState(null, '', '/')
})

test('readable notifications open the related event and support browser Back', async () => {
  window.history.replaceState(null, '', '/?view=notifications')
  renderWorkspace()
  expect(await screen.findByRole('heading', { name: 'Event request approved' })).toBeVisible()
  expect(screen.getByLabelText('1 unread notifications')).toBeVisible()
  fireEvent.click(screen.getByRole('link', { name: 'View event' }))
  expect(await screen.findByRole('heading', { name: 'Welcome Fair', level: 2 })).toBeVisible()
  expect(window.location.search).toBe('?view=my-events&event=req-1')
  window.history.back()
  await waitFor(() =>
    expect(screen.getByRole('heading', { name: 'Notifications', level: 1 })).toBeVisible(),
  )
})
test('a direct event URL restores the selected event on reload', async () => {
  window.history.replaceState(null, '', '/?view=my-events&event=req-1')
  renderWorkspace()
  expect(await screen.findByRole('heading', { name: 'Welcome Fair', level: 2 })).toBeVisible()
})
test('an unavailable role screen falls back without reading organiser events', async () => {
  window.history.replaceState(null, '', '/?view=my-events&event=req-1')
  const { fetch } = renderWorkspace('attendee')
  expect(
    await screen.findByRole('heading', { name: 'Event Registrations', level: 1 }),
  ).toBeVisible()
  expect(fetch.mock.calls.map(([url]) => String(url))).not.toContain('/api/event-requests')
})
test('unsaved event details survive cancelled navigation and warn on reload', async () => {
  renderWorkspace()
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  fireEvent.click(await screen.findByRole('button', { name: /Create event/ }))
  fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: 'Unfinished event' } })
  const unload = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(unload)
  expect(unload.defaultPrevented).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: /Notifications/ }))
  expect(confirm).toHaveBeenCalledWith('Discard your unsaved changes?')
  expect(screen.getByLabelText(/^Name/)).toHaveValue('Unfinished event')
  confirm.mockReturnValue(true)
  fireEvent.click(screen.getByRole('button', { name: /Notifications/ }))
  expect(await screen.findByRole('heading', { name: 'Notifications', level: 1 })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'My Events' }))
  fireEvent.click(screen.getByRole('button', { name: /Create event/ }))
  expect(screen.getByLabelText(/^Name/)).toHaveValue('')
})
