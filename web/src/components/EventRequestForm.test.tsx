import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import EventRequestForm from './EventRequestForm'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

function renderForm() {
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
    return new Response(JSON.stringify({ id: 'request-1', name: 'Orientation Day', status: 'draft' }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <EventRequestForm />
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
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
})

test('creates a complete event request without submitting it', async () => {
  renderForm()
  await fillValidForm()
  const fetchMock = vi.mocked(globalThis.fetch)
  fetchMock.mockClear()
  fireEvent.click(screen.getByRole('button', { name: 'Create event request' }))

  await waitFor(() => {
    expect(screen.getByRole('status')).toHaveTextContent('has been created')
  })
  expect(fetchMock).toHaveBeenNthCalledWith(
    1,
    '/api/event-requests',
    expect.objectContaining({ method: 'POST' }),
  )
  expect(fetchMock).toHaveBeenCalledTimes(1)
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
