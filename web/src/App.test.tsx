import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import App from './App'

// Smoke test for the scaffold: the page renders and reports what /health said.
// Component tests for real pages arrive with their stories.

afterEach(() => {
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

test('shows the API health status once it loads', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )

  renderApp()

  expect(await screen.findByText(/API and database are ok/)).toBeInTheDocument()
})
