import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import VenueCatalogue from './VenueCatalogue'

// SCRUM-59: Venue Staff maintain the catalogue and everyone else reads it. The API decides
// who may do what; these tests cover what the component shows and which endpoint it calls.

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

test('a coordinator sees the catalogue read-only', async () => {
  let requested = ''
  renderCatalogue('coordinator', async (input) => {
    requested = String(input)
    return json([venue()])
  })

  expect(await screen.findByText('Hall A')).toBeInTheDocument()
  expect(screen.getByText(/Level 2, SCIS/)).toHaveTextContent('up to 200 people')
  expect(screen.getByText(/Level 2, SCIS/)).toHaveTextContent('08:00 to 22:00')
  expect(screen.getByText(/Layouts:/)).toHaveTextContent('theatre, classroom')
  // AC2: no controls that would create, edit or deactivate a venue.
  expect(screen.queryByRole('button', { name: 'Deactivate' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Add venue' })).not.toBeInTheDocument()
  expect(requested).toBe('/api/venues')
})

test('venue staff see the maintenance controls', async () => {
  let requested = ''
  renderCatalogue('venue_staff', async (input) => {
    requested = String(input)
    return json([venue()])
  })

  expect(await screen.findByText('Hall A')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Deactivate' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Add venue' })).toBeInTheDocument()
  expect(requested).toBe('/api/venues')
})

test('deactivating a venue calls the deactivate endpoint and confirms', async () => {
  let posted = ''
  renderCatalogue('venue_staff', async (input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json([venue()])
    posted = String(input)
    return json(venue({ is_active: false }))
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Deactivate' }))

  await waitFor(() => {
    expect(posted).toBe('/api/venues/venue-1/deactivate')
  })
  expect(await screen.findByRole('status')).toHaveTextContent(
    '“Hall A” has been deactivated and can no longer be selected.',
  )
})

test('adding a venue posts the form and confirms', async () => {
  let body: Record<string, unknown> = {}
  renderCatalogue('venue_staff', async (_input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json([])
    body = JSON.parse(String(init?.body)) as Record<string, unknown>
    return json(venue({ name: 'Hall B' }), 201)
  })

  expect(await screen.findByText('No venues in the catalogue yet.')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: 'Hall B' } })
  fireEvent.change(screen.getByLabelText(/^Location/), { target: { value: 'Level 3' } })
  fireEvent.change(screen.getByLabelText(/^Maximum capacity/), { target: { value: '80' } })
  fireEvent.click(screen.getByLabelText('theatre'))
  fireEvent.change(screen.getByLabelText(/^Opens at/), { target: { value: '09:00' } })
  fireEvent.change(screen.getByLabelText(/^Closes at/), { target: { value: '17:00' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add venue' }))

  await waitFor(() => {
    expect(body.name).toBe('Hall B')
  })
  expect(body.maximum_capacity).toBe(80)
  expect(body.supported_layouts).toEqual(['theatre'])
  // The time inputs give "HH:MM"; the API is sent seconds too.
  expect(body.opens_at).toBe('09:00:00')
  expect(body.closes_at).toBe('17:00:00')
  expect(await screen.findByRole('status')).toHaveTextContent(
    '“Hall B” has been added to the catalogue.',
  )
})

test('an untouched time field is sent as null, not an empty string', async () => {
  // Regression: "" is not a time, so the API rejected it with a parser error in its own
  // shape and the form showed nothing at all. An empty input means "not supplied", so it
  // has to go as null for AC5 to name the field. Caught by the e2e test, locked in here.
  let body: Record<string, unknown> = {}
  renderCatalogue('venue_staff', async (_input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json([])
    body = JSON.parse(String(init?.body)) as Record<string, unknown>
    return json({ detail: [{ field: 'opens_at', reason: 'is required' }] }, 422)
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Add venue' }))

  await waitFor(() => {
    expect(body).toHaveProperty('opens_at')
  })
  expect(body.opens_at).toBeNull()
  expect(body.closes_at).toBeNull()
  expect(await screen.findByText('Opens at is required')).toBeInTheDocument()
})

test('a 422 that is not in the field-problem shape still reports something', async () => {
  // FastAPI's own validation errors look nothing like ours; showing no message at all
  // leaves the user staring at a form that silently did nothing.
  renderCatalogue('venue_staff', async (_input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json([])
    return json({ detail: [{ type: 'time_parsing', loc: ['body', 'opens_at'] }] }, 422)
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Add venue' }))

  expect(await screen.findByRole('status')).toHaveTextContent('The venue could not be saved (422)')
})

test('a refused save names the fields to correct', async () => {
  renderCatalogue('venue_staff', async (_input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json([])
    return json(
      {
        detail: [
          { field: 'name', reason: 'is required' },
          { field: 'maximum_capacity', reason: 'must be at least 1' },
        ],
      },
      422,
    )
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Add venue' }))

  // AC5: the affected field is identified, next to the input it belongs to.
  expect(await screen.findByText('Name is required')).toBeInTheDocument()
  expect(screen.getByText('Maximum capacity must be at least 1')).toBeInTheDocument()
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

test('a duplicate name is reported on the name field', async () => {
  renderCatalogue('venue_staff', async (_input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json([])
    return json({ detail: 'A venue with that name already exists' }, 409)
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Add venue' }))

  expect(await screen.findByText('Name is already used by another venue')).toBeInTheDocument()
})

test('shows an error when the catalogue cannot be loaded', async () => {
  renderCatalogue('coordinator', async () => json({ detail: 'boom' }, 500))

  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the venue catalogue')
})
