import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import type { EventRequest } from '../api/eventRequests'
import EventRequestForm from './EventRequestForm'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

function renderForm(props: { editing?: EventRequest | null } = {}) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'user-1', roles: ['organiser'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input) === '/api/event-requests/equipment-types') {
      return new Response(JSON.stringify(['Projector']), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    if (String(input) === '/api/event-requests/venue-names') {
      return new Response(JSON.stringify(['Hall A']), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    // Creating now submits, so the stub answers both calls. The submit response carries
    // the status the organiser is told about.
    const submitted = String(input).endsWith('/submit')
    return new Response(
      JSON.stringify({
        id: 'request-1',
        name: 'Orientation Day',
        status: submitted ? 'submitted' : 'draft',
      }),
      { status: submitted ? 200 : 201, headers: { 'Content-Type': 'application/json' } },
    )
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <EventRequestForm editing={props.editing ?? null} />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

async function fillValidForm() {
  await screen.findByRole('option', { name: 'Projector' })
  const values: Record<string, string> = {
    Name: 'Orientation Day',
    Purpose: 'Welcome new students',
    Description: 'Campus orientation activities',
    'Start date and time': '2026-12-01T09:00',
    'End date and time': '2026-12-01T13:00',
    'Expected attendance': '200',
    'Venue requirement': 'Hall A',
    'Accessibility requirement': 'Step-free access',
    'Equipment requirement': 'Projector',
    'Layout requirement': 'Theatre style',
    'Registration requirement': 'Open registration',
  }
  for (const [label, value] of Object.entries(values)) {
    fireEvent.change(screen.getByLabelText(`${label} *`), { target: { value } })
  }
}

test('shows every required field error and keeps entered details for correction', async () => {
  renderForm()
  await screen.findByRole('option', { name: 'Projector' })
  fireEvent.change(screen.getByLabelText('Name *'), { target: { value: 'Orientation Day' } })
  fireEvent.click(screen.getByRole('button', { name: 'Create event request' }))

  expect(screen.getAllByText('This field is required.')).toHaveLength(10)
  expect(screen.getByLabelText('Name *')).toHaveValue('Orientation Day')
})

test('identifies an end time before the start and a non-whole attendance value', async () => {
  renderForm()
  await fillValidForm()
  fireEvent.change(screen.getByLabelText('End date and time *'), {
    target: { value: '2026-12-01T08:00' },
  })
  fireEvent.change(screen.getByLabelText('Expected attendance *'), { target: { value: '1.5' } })
  fireEvent.click(screen.getByRole('button', { name: 'Create event request' }))

  expect(
    screen.getByText('End date and time must be after the start date and time.'),
  ).toBeInTheDocument()
  expect(screen.getByText('Enter a positive whole number.')).toBeInTheDocument()
  expect(screen.getByLabelText('End date and time *').parentElement).toHaveTextContent(
    'End date and time must be after the start date and time.',
  )
})

test('identifies an end time equal to the start time', async () => {
  renderForm()
  await fillValidForm()
  fireEvent.change(screen.getByLabelText('End date and time *'), {
    target: { value: '2026-12-01T09:00' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Create event request' }))

  expect(
    screen.getByText('End date and time must be after the start date and time.'),
  ).toBeInTheDocument()
})

test('rejects zero attendance and accepts the minimum value of one', async () => {
  renderForm()
  await fillValidForm()
  const fetchMock = vi.mocked(globalThis.fetch)
  fetchMock.mockClear()
  const attendance = screen.getByLabelText('Expected attendance *')
  fireEvent.change(attendance, { target: { value: '0' } })
  fireEvent.click(screen.getByRole('button', { name: 'Create event request' }))
  expect(screen.getByText('Enter a positive whole number.')).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()

  fireEvent.change(attendance, { target: { value: '1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Create event request' }))
  await waitFor(() => expect(fetchMock).toHaveBeenCalled())
})

test('creating a complete event request sends it for review', async () => {
  // The organiser presses one button and the request is with a coordinator. Creating and
  // submitting are two API calls because the API keeps them apart, but there is no state
  // in between that anyone sees. Saving without review is the other button.
  renderForm()
  await fillValidForm()
  const fetchMock = vi.mocked(globalThis.fetch)
  fetchMock.mockClear()
  fireEvent.click(screen.getByRole('button', { name: 'Create event request' }))

  await waitFor(() => {
    expect(screen.getByRole('status')).toHaveTextContent('has been submitted for review')
  })
  expect(fetchMock).toHaveBeenNthCalledWith(
    1,
    '/api/event-requests',
    expect.objectContaining({ method: 'POST' }),
  )
  expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    '/api/event-requests/request-1/submit',
    expect.objectContaining({ method: 'POST' }),
  )
})

test('an incomplete form can still be saved as a draft', async () => {
  // A draft is allowed to be unfinished: the completeness check belongs to submission,
  // which is why Save draft does not run it.
  renderForm()
  const fetchMock = vi.mocked(globalThis.fetch)
  await waitFor(() => expect(screen.getByLabelText('Name *')).toBeInTheDocument())
  fireEvent.change(screen.getByLabelText('Name *'), { target: { value: 'Half an idea' } })
  fetchMock.mockClear()
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))

  await waitFor(() => {
    expect(screen.getByRole('status')).toHaveTextContent('saved as a draft')
  })
  expect(fetchMock).toHaveBeenNthCalledWith(
    1,
    '/api/event-requests/drafts',
    expect.objectContaining({ method: 'POST' }),
  )
})

test('an empty field is saved as absent, not as an empty string', async () => {
  // The API stores absence. Sending "" would make a blank purpose look like an answer.
  renderForm()
  const fetchMock = vi.mocked(globalThis.fetch)
  await waitFor(() => expect(screen.getByLabelText('Name *')).toBeInTheDocument())
  fireEvent.change(screen.getByLabelText('Name *'), { target: { value: 'Half an idea' } })
  fetchMock.mockClear()
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalled())
  const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body)) as Record<string, unknown>
  expect(body.name).toBe('Half an idea')
  expect(body.purpose).toBeNull()
  expect(body.start_at).toBeNull()
  expect(body.expected_attendance).toBeNull()
})

test('shows server validation errors beside the relevant fields', async () => {
  renderForm()
  await fillValidForm()
  const fetchMock = vi.mocked(globalThis.fetch)
  fetchMock.mockClear()
  fetchMock.mockResolvedValueOnce(
    new Response(
      JSON.stringify({ detail: [{ field: 'name', reason: 'must be unique' }] }),
      { status: 422, headers: { 'Content-Type': 'application/json' } },
    ),
  )
  fireEvent.click(screen.getByRole('button', { name: 'Create event request' }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  expect(screen.getByLabelText('Name *').parentElement).toHaveTextContent('must be unique')
})

test('maps missing-field server errors beside the relevant fields', async () => {
  renderForm()
  await fillValidForm()
  const fetchMock = vi.mocked(globalThis.fetch)
  fetchMock.mockClear()
  fetchMock.mockResolvedValueOnce(
    new Response(
      JSON.stringify({ detail: [{ loc: ['body', 'name'], msg: 'Field required' }] }),
      { status: 422, headers: { 'Content-Type': 'application/json' } },
    ),
  )
  fireEvent.click(screen.getByRole('button', { name: 'Create event request' }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  expect(screen.getByLabelText('Name *').parentElement).toHaveTextContent('Field required')
})

test('does not create an incomplete form', async () => {
  renderForm()
  await screen.findByRole('option', { name: 'Projector' })
  const fetchMock = vi.mocked(globalThis.fetch)
  fetchMock.mockClear()
  fireEvent.click(screen.getByRole('button', { name: 'Create event request' }))

  expect(screen.getAllByText('This field is required.')).toHaveLength(11)
  expect(fetchMock).not.toHaveBeenCalled()
})

test('rejects a start date in the past before creating a request', async () => {
  renderForm()
  await fillValidForm()
  const fetchMock = vi.mocked(globalThis.fetch)
  fetchMock.mockClear()
  fireEvent.change(screen.getByLabelText('Start date and time *'), {
    target: { value: '2020-12-01T09:00' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Create event request' }))

  expect(screen.getByText('Start date and time must be in the future.')).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
})

test('shows venue names and equipment types loaded from the catalogues', async () => {
  renderForm()

  expect(await screen.findByRole('option', { name: 'Hall A' })).toBeInTheDocument()
  expect(await screen.findByRole('option', { name: 'Projector' })).toBeInTheDocument()
  expect(screen.getAllByText(/does not reserve a specific resource/i)).toHaveLength(2)
})


const existingDraft = {
  id: 'req-7',
  name: 'Orientation Day',
  purpose: 'Campus welcome',
  description: 'A long description',
  start_at: '2030-03-04T02:00:00Z',
  end_at: '2030-03-04T04:00:00Z',
  expected_attendance: 120,
  venue_requirement: 'Hall A',
  accessibility_requirement: 'Step-free access',
  equipment_requirement: 'Projector',
  layout_requirement: 'Theatre',
  registration_requirement: 'None',
  status: 'draft',
  status_permits: ['edit', 'submit'],
} as unknown as EventRequest

test('a draft chosen in the list fills in this form rather than a second one', async () => {
  // The whole point of the change: one form on the page. Editing arrives as a prop.
  renderForm({ editing: existingDraft })

  await waitFor(() => {
    expect(screen.getByLabelText('Name *')).toHaveValue('Orientation Day')
  })
  expect(screen.getByLabelText('Purpose *')).toHaveValue('Campus welcome')
  expect(screen.getByLabelText('Expected attendance *')).toHaveValue(120)
  // Editing offers review rather than creation, because the request already exists.
  expect(screen.getByRole('button', { name: 'Submit for review' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Create event request' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
})

test('editing a draft patches it rather than creating another', async () => {
  renderForm({ editing: existingDraft })
  const fetchMock = vi.mocked(globalThis.fetch)
  await waitFor(() => expect(screen.getByLabelText('Name *')).toHaveValue('Orientation Day'))
  fetchMock.mockClear()
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalled())
  expect(fetchMock).toHaveBeenNthCalledWith(
    1,
    '/api/event-requests/req-7',
    expect.objectContaining({ method: 'PATCH' }),
  )
})
