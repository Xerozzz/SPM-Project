import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import VenueCatalogue from './VenueCatalogue'

// SCRUM-59: the catalogue is read-only here. The API decides who may change it; these
// tests cover what the component shows and which endpoint it asks for.

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

function venue(overrides: Record<string, unknown> = {}) {
  return {
    id: 'venue-1',
    name: 'Hall A',
    location: 'Level 2, SCIS',
    maximum_capacity: 200,
    facilities: ['Projector'],
    supported_layouts: ['theatre', 'classroom'],
    accessibility_features: ['Step-free access'],
    opens_at: '08:00:00',
    closes_at: '22:00:00',
    is_active: true,
    ...overrides,
  }
}

function renderCatalogue(role: 'venue_staff' | 'coordinator', fetcher: typeof fetch) {
  localStorage.setItem('connectsphere.token', JSON.stringify({ token: 'token', roles: [role] }))
  vi.spyOn(globalThis, 'fetch').mockImplementation(fetcher)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <VenueCatalogue />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

test('a coordinator sees every attribute of a venue', async () => {
  let requested = ''
  renderCatalogue('coordinator', async (input) => {
    requested = String(input)
    return json([venue()])
  })

  expect(await screen.findByText('Hall A')).toBeInTheDocument()
  expect(screen.getByText(/Level 2, SCIS/)).toHaveTextContent('up to 200 people')
  // "HH:MM:SS" from the API reads better as "HH:MM" in a list.
  expect(screen.getByText(/Level 2, SCIS/)).toHaveTextContent('08:00 to 22:00')
  expect(screen.getByText(/Layouts:/)).toHaveTextContent('theatre, classroom')
  expect(screen.getByText(/Facilities:/)).toHaveTextContent('Projector')
  expect(screen.getByText(/Accessibility:/)).toHaveTextContent('Step-free access')
  expect(requested).toBe('/api/venues')
})

test('the catalogue offers no controls that would change it', async () => {
  // AC2: a coordinator views but cannot create, edit or deactivate.
  renderCatalogue('coordinator', async () => json([venue()]))

  expect(await screen.findByText('Hall A')).toBeInTheDocument()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})

test('an empty catalogue says so', async () => {
  renderCatalogue('coordinator', async () => json([]))

  expect(await screen.findByText('No venues in the catalogue yet.')).toBeInTheDocument()
})

test('shows an error when the catalogue cannot be loaded', async () => {
  renderCatalogue('coordinator', async () => json({ detail: 'boom' }, 500))

  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the venue catalogue')
})
