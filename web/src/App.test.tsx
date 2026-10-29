import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import App from './App'

// SCRUM-27 (F1): unauthenticated users see sign-in; valid sign-in enters the app;
// invalid credentials show a generic error; sign-out returns to sign-in.

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

test('unauthenticated user is shown the sign-in page', () => {
  renderApp()
  expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
})

test('valid sign-in enters the app and shows roles', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/api/auth/login')) {
      return new Response(
        JSON.stringify({ access_token: 'token', token_type: 'bearer', roles: ['organiser'] }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      )
    }
    if (
      url.endsWith('/equipment-types') ||
      url.endsWith('/venue-names') ||
      url.endsWith('/organisation-calendar')
    ) {
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    if (url.endsWith('/api/event-requests')) {
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    if (url.endsWith('/api/venues') || url.endsWith('/api/equipment')) {
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    return new Response(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  renderApp()

  fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'organiser@example.com' } })
  fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'password123' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

  await waitFor(() => {
    expect(screen.getByText(/you are logged in as: organiser/i)).toBeInTheDocument()
  })
})

test('invalid credentials show a generic error', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ detail: 'Invalid email or password' }), { status: 401 }),
  )
  renderApp()

  fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'nobody@example.com' } })
  fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'wrong' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

  await waitFor(() => {
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid email or password')
  })
})

test('sign-out returns to the sign-in page', async () => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'user-1', roles: ['attendee'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  renderApp()

  fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }))

  await waitFor(() => {
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
  expect(localStorage.getItem('connectsphere.token')).toBeNull()
})

test('a session stored before user ids existed is treated as signed out', async () => {
  // Without the userId guard in readStored, such a session survives with userId undefined.
  // Nothing then equals request.coordinator_id, so every Approve and Reject button vanishes
  // permanently and silently. Signing the user out once is the recoverable failure.
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', roles: ['coordinator'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  renderApp()

  expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
})

test('a stored session carrying a user id is kept', async () => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'user-1', roles: ['attendee'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  renderApp()

  expect(await screen.findByRole('button', { name: 'Sign out' })).toBeInTheDocument()
})

// SCRUM-46 / SCRUM-29: create, save, reopen and return through My Events.
test('My Events opens creation separately and returns to the saved draft with feedback', async () => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({
      token: 'token',
      userId: 'user-1',
      roles: ['organiser'],
    }),
  )
  const draft = {
    id: 'draft-1',
    name: 'Welcome Fair',
    description: null,
    status: 'draft',
    status_permits: ['edit', 'submit'],
    start_at: null,
    end_at: null,
    expected_attendance: null,
    venue_requirement: null,
  }
  let saved = false
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    let body: unknown = []
    if (url === '/api/event-requests') body = saved ? [draft] : []
    if (url === '/api/event-requests/draft-1') body = draft
    if (url === '/api/event-requests/drafts' && init?.method === 'POST') {
      saved = true
      body = draft
    }
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  renderApp()

  expect(await screen.findByText(/No events yet/)).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'New event request' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: /Create event/ }))
  expect(screen.getByRole('heading', { name: 'New event request' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /Back to My Events/ }))
  expect(screen.queryByRole('heading', { name: 'New event request' })).toBeNull()

  fireEvent.click(screen.getByRole('button', { name: /Create event/ }))
  fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: 'Welcome Fair' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))
  expect(await screen.findByRole('status')).toHaveTextContent(
    '“Welcome Fair” has been saved as a draft.',
  )
  expect(screen.queryByRole('heading', { name: 'New event request' })).toBeNull()
  fireEvent.click(await screen.findByRole('button', { name: 'View details for Welcome Fair' }))
  fireEvent.click(screen.getByRole('button', { name: 'Edit draft Welcome Fair' }))
  expect(await screen.findByRole('heading', { name: 'Edit draft' })).toBeInTheDocument()
  expect(screen.getByLabelText(/^Name/)).toHaveValue('Welcome Fair')
})

// SCRUM-46: only the organiser workspace exposes event creation.
test('an attendee has no My Events creation action', async () => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({
      token: 'token',
      userId: 'user-1',
      roles: ['attendee'],
    }),
  )
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }))
  renderApp()

  expect(await screen.findByRole('heading', { name: 'Event Registrations' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Create event/ })).toBeNull()
})
