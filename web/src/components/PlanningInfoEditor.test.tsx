import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import EventRequestReview from './EventRequestReview'

// SCRUM-36: the assigned coordinator views and updates ordinary planning information
// from the coordinator events panel.

const submitted = {
  id: 'req-1',
  status: 'submitted',
  name: 'Orientation Day',
  purpose: 'Welcome students',
  description: 'Talks and tours',
  start_at: '2026-12-01T01:00:00Z',
  end_at: '2026-12-01T05:00:00Z',
  expected_attendance: 200,
  venue_requirement: 'Auditorium',
  accessibility_requirement: 'Step-free access',
  equipment_requirement: 'Projector',
  layout_requirement: 'Theatre',
  registration_requirement: 'Open registration',
  status_permits: ['approve', 'reject'],
  coordinator_id: 'user-1',
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

/** Renders the panel with one request. `update` answers the planning-info PATCH. */
function renderPanel(request: unknown, update: () => Response = () => json(request)) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'user-1', roles: ['coordinator'] }),
  )
  let current = request
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    if (key === 'GET /api/event-requests/reviewable') return json([current])
    if (key === 'GET /api/event-requests/bookable') return json([])
    if (key === 'GET /api/event-requests/assigned-confirmed') return json([])
    if (key.endsWith('/clarifications')) return json([])
    if (key === 'PATCH /api/event-requests/req-1/planning-info') {
      const response = update()
      if (response.ok) current = await response.clone().json()
      return response
    }
    throw new Error(`unexpected request ${key}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <EventRequestReview />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return fetchMock
}

async function openEditor() {
  fireEvent.click(await screen.findByRole('button', { name: 'Edit planning information' }))
  return screen.getByRole('form', { name: 'Edit planning information' })
}

test('SCRUM-36 AC2: the assigned coordinator saves an ordinary change and sees it', async () => {
  const fetchMock = renderPanel(submitted, () => json({ ...submitted, name: 'Orientation Night' }))

  const form = await openEditor()
  fireEvent.change(within(form).getByLabelText('Name'), {
    target: { value: 'Orientation Night' },
  })
  fireEvent.click(within(form).getByRole('button', { name: 'Save' }))

  expect(await screen.findByText('Planning information saved.')).toBeInTheDocument()
  // Only the changed field is sent.
  const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
  expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ name: 'Orientation Night' })
  // The list is reloaded, so the card shows the saved value.
  expect(await screen.findByRole('heading', { name: 'Orientation Night' })).toBeInTheDocument()
})

test('SCRUM-36 AC3: only ordinary fields are offered', async () => {
  renderPanel(submitted)

  const form = await openEditor()

  for (const label of ['Name', 'Purpose', 'Description', 'Registration']) {
    expect(within(form).getByLabelText(label)).toBeInTheDocument()
  }
  // AC4 (ADR-0046): layout and accessibility go through change control now.
  expect(within(form).queryByLabelText('Layout')).not.toBeInTheDocument()
  expect(within(form).queryByLabelText('Accessibility')).not.toBeInTheDocument()
  expect(within(form).getAllByRole('textbox')).toHaveLength(4)
  expect(
    within(form).getByText(
      'Date, time, attendance, venue, equipment, layout and accessibility cannot be changed here. The Organiser proposes those as a change request.',
    ),
  ).toBeInTheDocument()
})

test('SCRUM-36: a blank field or no change keeps Save disabled', async () => {
  renderPanel(submitted)

  const form = await openEditor()
  const save = within(form).getByRole('button', { name: 'Save' })
  expect(save).toBeDisabled()

  fireEvent.change(within(form).getByLabelText('Purpose'), { target: { value: '  ' } })

  expect(within(form).getByText('Purpose is required.')).toBeInTheDocument()
  expect(save).toBeDisabled()
})

test('SCRUM-36: a refused field shows the problem the API names', async () => {
  renderPanel(submitted, () => json({ detail: [{ field: 'name', reason: 'is required' }] }, 422))

  const form = await openEditor()
  fireEvent.change(within(form).getByLabelText('Name'), { target: { value: 'New name' } })
  fireEvent.click(within(form).getByRole('button', { name: 'Save' }))

  expect(await within(form).findByRole('alert')).toHaveTextContent('name is required')
})

test('SCRUM-36 AC4: a refused update shows the API message and saves nothing', async () => {
  renderPanel(submitted, () => json({ detail: 'Forbidden' }, 403))

  const form = await openEditor()
  fireEvent.change(within(form).getByLabelText('Name'), { target: { value: 'New name' } })
  fireEvent.click(within(form).getByRole('button', { name: 'Save' }))

  expect(await within(form).findByRole('alert')).toHaveTextContent('Could not save: Forbidden')
  expect(screen.queryByText('Planning information saved.')).toBeNull()
  expect(screen.getByRole('heading', { name: 'Orientation Day' })).toBeInTheDocument()
})

test('SCRUM-36: cancelling discards the edits', async () => {
  renderPanel(submitted)

  const form = await openEditor()
  fireEvent.change(within(form).getByLabelText('Name'), { target: { value: 'Discarded' } })
  fireEvent.click(within(form).getByRole('button', { name: 'Cancel' }))
  const reopened = await openEditor()

  expect(within(reopened).getByLabelText('Name')).toHaveValue('Orientation Day')
})

test('SCRUM-104: someone else\u2019s event never reaches the coordinator list', async () => {
  // SCRUM-104 scopes /reviewable to the signed-in coordinator, so an event assigned
  // to another coordinator (or to nobody yet) is refused before it renders — there is
  // no card, and therefore no edit control, to assert on.
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'user-1', roles: ['coordinator'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    if (key === 'GET /api/event-requests/reviewable') return json([])
    if (key === 'GET /api/event-requests/bookable') return json([])
    if (key === 'GET /api/event-requests/assigned-confirmed') return json([])
    throw new Error(`unexpected request ${key}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <EventRequestReview />
      </AuthProvider>
    </QueryClientProvider>,
  )

  expect(await screen.findByText('No coordinator events are available.')).toBeInTheDocument()
  expect(
    screen.queryByRole('button', { name: 'Edit planning information' }),
  ).not.toBeInTheDocument()
})

test('SCRUM-36 AC5: a Confirmed event does not offer ordinary edits', async () => {
  renderPanel({ ...submitted, status: 'confirmed', status_permits: [] })

  await screen.findByRole('heading', { name: 'Orientation Day' })

  await waitFor(() =>
    expect(screen.queryByRole('button', { name: 'Edit planning information' })).toBeNull(),
  )
})

test('SCRUM-36 AC1: an Approved event still offers ordinary edits', async () => {
  renderPanel({ ...submitted, status: 'approved', status_permits: [] })

  expect(
    await screen.findByRole('button', { name: 'Edit planning information' }),
  ).toBeInTheDocument()
})
