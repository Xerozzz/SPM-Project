import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
  localStorage.setItem('connectsphere.token', JSON.stringify({ token: 'token', userId: 'user-1', roles: [role] }))
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
  expect(screen.queryByRole('button', { name: /^Deactivate/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /^Edit/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Add venue' })).not.toBeInTheDocument()
  expect(requested).toBe('/api/venues')
})

test('venue staff see the maintenance controls', async () => {
  let requested = ''
  renderCatalogue('venue_staff', async (input) => {
    requested = String(input)
    return json([venue()])
  })

  expect(await within(await screen.findByRole('list')).findByText('Hall A')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Deactivate Hall A' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Edit Hall A' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Add venue' })).toBeInTheDocument()
  expect(requested).toBe('/api/venues')
})

test('venue staff can record unavailability for a selected venue', async () => {
  let posted: Record<string, unknown> = {}
  renderCatalogue('venue_staff', async (input, init) => {
    const url = String(input)
    if (url === '/api/venues') return json([venue()])
    if ((init?.method ?? 'GET') === 'GET') return json([])
    posted = JSON.parse(String(init?.body)) as Record<string, unknown>
    return json({ id: 'closure-1', venue_id: 'venue-1', ...posted }, 201)
  })

  fireEvent.change(await screen.findByLabelText(/^Venue$/), { target: { value: 'venue-1' } })
  fireEvent.change(screen.getByLabelText(/^Start date and time/), {
    target: { value: '2026-10-01T09:00' },
  })
  fireEvent.change(screen.getByLabelText(/^End date and time/), {
    target: { value: '2026-10-01T11:00' },
  })
  fireEvent.change(screen.getByLabelText(/^Reason/), {
    target: { value: 'Air-conditioning maintenance' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Record unavailability' }))

  await waitFor(() => expect(posted.reason).toBe('Air-conditioning maintenance'))
  expect(posted.starts_at).toBe(new Date(2026, 9, 1, 9, 0).toISOString())
  expect(posted.ends_at).toBe(new Date(2026, 9, 1, 11, 0).toISOString())
  await waitFor(() => {
    expect(screen.getByLabelText(/^Start date and time/)).toHaveValue('')
  })
  expect(screen.getByLabelText(/^End date and time/)).toHaveValue('')
  expect(screen.getByLabelText(/^Reason/)).toHaveValue('')
})

test('unavailability validation names the date and reason fields to correct', async () => {
  renderCatalogue('venue_staff', async (input, init) => {
    if (String(input) === '/api/venues') return json([venue()])
    if ((init?.method ?? 'GET') === 'GET') return json([])
    return json(
      {
        detail: [
          { field: 'ends_at', reason: 'must be after the start time' },
          { field: 'reason', reason: 'is required' },
        ],
      },
      422,
    )
  })

  fireEvent.change(await screen.findByLabelText(/^Venue$/), { target: { value: 'venue-1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Record unavailability' }))

  expect(
    await screen.findByText('End date and time must be after the start time'),
  ).toBeInTheDocument()
  expect(screen.getByText('Reason is required')).toBeInTheDocument()
})

test('venue staff see the recorded unavailability periods for the selected venue', async () => {
  renderCatalogue('venue_staff', async (input) => {
    if (String(input) === '/api/venues') return json([venue()])
    return json([
      {
        id: 'closure-1',
        venue_id: 'venue-1',
        starts_at: '2026-09-24T03:10:00Z',
        ends_at: '2026-09-25T03:10:00Z',
        reason: 'Maintenance',
      },
    ])
  })

  fireEvent.change(await screen.findByLabelText(/^Venue$/), { target: { value: 'venue-1' } })

  expect(await screen.findByText('Recorded unavailability periods')).toBeInTheDocument()
  expect(await screen.findByText('Maintenance')).toBeInTheDocument()
})

test('editing a closure prefills it and saves with PUT', async () => {
  let method = ''
  let url = ''
  let body: Record<string, unknown> = {}
  const record = {
    id: 'closure-1',
    venue_id: 'venue-1',
    starts_at: new Date(2026, 9, 1, 9, 0).toISOString(),
    ends_at: new Date(2026, 9, 1, 11, 0).toISOString(),
    reason: 'Maintenance',
  }
  renderCatalogue('venue_staff', async (input, init) => {
    if (String(input) === '/api/venues') return json([venue()])
    if ((init?.method ?? 'GET') === 'GET') return json([record])
    method = String(init?.method)
    url = String(input)
    body = JSON.parse(String(init?.body)) as Record<string, unknown>
    return json(record)
  })

  fireEvent.change(await screen.findByLabelText(/^Venue$/), { target: { value: 'venue-1' } })
  fireEvent.click(await screen.findByRole('button', { name: /^Edit closure:/ }))

  // UTC returned by the API is prefilled as the same local wall-clock time.
  expect(screen.getByLabelText(/^Start date and time/)).toHaveValue('2026-10-01T09:00')
  fireEvent.click(screen.getByRole('button', { name: 'Save closure' }))

  await waitFor(() => expect(method).toBe('PUT'))
  expect(url).toBe('/api/venues/venue-1/unavailabilities/closure-1')
  expect(body.starts_at).toBe(new Date(2026, 9, 1, 9, 0).toISOString())
})

test('deleting a closure calls its DELETE endpoint', async () => {
  let method = ''
  let url = ''
  const record = {
    id: 'closure-1',
    venue_id: 'venue-1',
    starts_at: new Date(2026, 9, 1, 9, 0).toISOString(),
    ends_at: new Date(2026, 9, 1, 11, 0).toISOString(),
    reason: 'Maintenance',
  }
  renderCatalogue('venue_staff', async (input, init) => {
    if (String(input) === '/api/venues') return json([venue()])
    if ((init?.method ?? 'GET') === 'GET') return json([record])
    method = String(init?.method)
    url = String(input)
    return new Response(null, { status: 204 })
  })

  fireEvent.change(await screen.findByLabelText(/^Venue$/), { target: { value: 'venue-1' } })
  fireEvent.click(await screen.findByRole('button', { name: /^Delete closure:/ }))

  await waitFor(() => expect(method).toBe('DELETE'))
  expect(url).toBe('/api/venues/venue-1/unavailabilities/closure-1')
})

test('deactivating a venue calls the deactivate endpoint and confirms', async () => {
  let posted = ''
  renderCatalogue('venue_staff', async (input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json([venue()])
    posted = String(input)
    return json(venue({ is_active: false }))
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Deactivate Hall A' }))

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
  fireEvent.change(screen.getByLabelText(/^Facilities/), {
    target: { value: 'Projector, Hearing loop' },
  })
  fireEvent.change(screen.getByLabelText(/^Accessibility features/), {
    target: { value: 'Step-free access' },
  })
  fireEvent.change(screen.getByLabelText(/^Opens at/), { target: { value: '09:00' } })
  fireEvent.change(screen.getByLabelText(/^Closes at/), { target: { value: '17:00' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add venue' }))

  await waitFor(() => {
    expect(body.name).toBe('Hall B')
  })
  expect(body.maximum_capacity).toBe(80)
  expect(body.supported_layouts).toEqual(['theatre'])
  // AC1 lists facilities and accessibility features among a venue's attributes, so the
  // form has to be able to set them. Typed as one line, sent as an array.
  expect(body.facilities).toEqual(['Projector', 'Hearing loop'])
  expect(body.accessibility_features).toEqual(['Step-free access'])
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

test('editing a venue loads its values and saves them with PATCH', async () => {
  // AC1's update half: the form is prefilled from the venue, and Save changes sends a PATCH.
  let method = ''
  let url = ''
  let body: Record<string, unknown> = {}
  renderCatalogue('venue_staff', async (input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json([venue()])
    method = String(init?.method)
    url = String(input)
    body = JSON.parse(String(init?.body)) as Record<string, unknown>
    return json(venue({ maximum_capacity: 250 }))
  })

  fireEvent.click(await screen.findByRole('button', { name: 'Edit Hall A' }))

  // Prefilled from the venue, with the API's "HH:MM:SS" shown as "HH:MM".
  expect(screen.getByLabelText(/^Name/)).toHaveValue('Hall A')
  expect(screen.getByLabelText(/^Opens at/)).toHaveValue('08:00')
  expect(screen.getByLabelText('theatre')).toBeChecked()
  // The form holds these as one line, so the array has to come back joined. Prefilling
  // them as an array would send them back as [] and quietly wipe them on save.
  expect(screen.getByLabelText(/^Facilities/)).toHaveValue('Projector')
  expect(screen.getByLabelText(/^Accessibility features/)).toHaveValue('Step-free access')

  fireEvent.change(screen.getByLabelText(/^Maximum capacity/), { target: { value: '250' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

  await waitFor(() => {
    expect(method).toBe('PATCH')
  })
  expect(url).toBe('/api/venues/venue-1')
  expect(body.maximum_capacity).toBe(250)
  expect(body.facilities).toEqual(['Projector'])
  expect(body.accessibility_features).toEqual(['Step-free access'])
  expect(body.opens_at).toBe('08:00:00')
  expect(await screen.findByRole('status')).toHaveTextContent('“Hall A” has been updated.')
})

test('cancelling an edit returns the form to adding a venue', async () => {
  renderCatalogue('venue_staff', async () => json([venue()]))

  fireEvent.click(await screen.findByRole('button', { name: 'Edit Hall A' }))
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

  expect(screen.getByRole('button', { name: 'Add venue' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
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

test('an empty or untidy list of facilities is sent as a clean array', async () => {
  // A venue with no projector and no step-free access is still a valid venue, so an empty
  // box means an empty list rather than [''], and stray commas do not become blank entries.
  let body: Record<string, unknown> = {}
  renderCatalogue('venue_staff', async (_input, init) => {
    if ((init?.method ?? 'GET') === 'GET') return json([])
    body = JSON.parse(String(init?.body)) as Record<string, unknown>
    return json(venue(), 201)
  })

  fireEvent.change(await screen.findByLabelText(/^Facilities/), {
    target: { value: ' Projector , , Hearing loop , ' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Add venue' }))

  await waitFor(() => {
    expect(body).toHaveProperty('facilities')
  })
  expect(body.facilities).toEqual(['Projector', 'Hearing loop'])
  expect(body.accessibility_features).toEqual([])
})
