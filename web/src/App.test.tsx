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
    if (url.endsWith('/api/event-requests')) {
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
    expect(screen.getByText(/signed in as: organiser/i)).toBeInTheDocument()
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
    JSON.stringify({ token: 'token', roles: ['attendee'] }),
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
