import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import type { EventRequest } from '../api/eventRequests'
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
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <EventRequestForm />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function fillValidForm() {
  const values: Record<string, string> = {
    Name: 'Orientation Day',
    Purpose: 'Welcome new students',
    Description: 'Campus orientation activities',
    'Start date and time': '2099-12-01T09:00',
    'End date and time': '2099-12-01T13:00',
    'Expected attendance': '200',
    'Venue requirement': 'Auditorium-type venue',
    'Accessibility requirement': 'Step-free access',
    'Equipment requirement': 'Projector-type requirement',
    'Layout requirement': 'Theatre style',
    'Registration requirement': 'Open registration',
  }
  for (const [label, value] of Object.entries(values)) {
    fireEvent.change(screen.getByLabelText(`${label} *`), { target: { value } })
  }
}

test('saves an incomplete request without start or end dates as a draft', async () => {
  const saved = eventRequest({ id: 'request-1', name: 'Hackathon' })
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    expect(String(input)).toBe('/api/event-requests/drafts')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toMatchObject({
      name: 'Hackathon',
      purpose: null,
      start_at: null,
      end_at: null,
    })
    return json(saved, 201)
  })
  renderForm()

  fireEvent.change(screen.getByLabelText('Name *'), { target: { value: 'Hackathon' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))

  expect(await screen.findByRole('status')).toHaveTextContent('was saved as a draft')
  expect(fetchMock).toHaveBeenCalledOnce()
  expect(screen.queryByText('This field is required.')).not.toBeInTheDocument()
  expect(screen.getByLabelText('Name *')).toHaveValue('Hackathon')
})

test('refuses to submit the same incomplete request with clear date errors', () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch')
  renderForm()

  fireEvent.change(screen.getByLabelText('Name *'), { target: { value: 'Hackathon' } })
  fireEvent.click(screen.getByRole('button', { name: 'Submit for review' }))

  expect(screen.getByLabelText('Start date and time *').parentElement).toHaveTextContent(
    'This field is required.',
  )
  expect(screen.getByLabelText('End date and time *').parentElement).toHaveTextContent(
    'This field is required.',
  )
  expect(fetchMock).not.toHaveBeenCalled()
})

test('submits a complete request and resets the form to a new editable request', async () => {
  const draft = eventRequest({
    id: 'request-1',
    name: 'Orientation Day',
    start_at: '2099-12-01T09:00:00Z',
    end_at: '2099-12-01T13:00:00Z',
  })
  const submitted = eventRequest({
    ...draft,
    status: 'submitted',
    status_permits: [],
    submitted_at: '2099-01-01T00:00:00Z',
  })
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(json(draft, 201))
    .mockResolvedValueOnce(json(submitted))
  renderForm()
  fillValidForm()

  fireEvent.click(screen.getByRole('button', { name: 'Submit for review' }))

  expect(await screen.findByRole('status')).toHaveTextContent(
    'has been submitted for review and is now read-only',
  )
  expect(fetchMock).toHaveBeenNthCalledWith(
    1,
    '/api/event-requests/drafts',
    expect.objectContaining({ method: 'POST' }),
  )
  expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    '/api/event-requests/request-1/submit',
    expect.objectContaining({ method: 'POST' }),
  )
  expect(screen.getByLabelText('Name *')).toHaveValue('')
})

test('allows a complete valid request to be saved without submitting it', async () => {
  const saved = eventRequest({
    id: 'request-1',
    name: 'Orientation Day',
    start_at: '2099-12-01T09:00:00Z',
    end_at: '2099-12-01T13:00:00Z',
  })
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(saved, 201))
  renderForm()
  fillValidForm()

  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))

  expect(await screen.findByRole('status')).toHaveTextContent('was saved as a draft')
  expect(fetchMock).toHaveBeenCalledOnce()
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/event-requests/drafts',
    expect.objectContaining({ method: 'POST' }),
  )
})

test('keeps a saved draft open and updates that draft on the next save', async () => {
  const first = eventRequest({ id: 'request-1', name: 'Hackathon' })
  const updated = eventRequest({
    ...first,
    description: 'Updated while the saved draft stayed open',
  })
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(json(first, 201))
    .mockResolvedValueOnce(json(updated))
  renderForm()
  fireEvent.change(screen.getByLabelText('Name *'), { target: { value: 'Hackathon' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))
  await screen.findByText(/saved draft remains open/i)

  fireEvent.change(screen.getByLabelText('Description *'), {
    target: { value: 'Updated while the saved draft stayed open' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    '/api/event-requests/request-1',
    expect.objectContaining({ method: 'PATCH' }),
  )
  expect(screen.getByLabelText('Description *')).toHaveValue(
    'Updated while the saved draft stayed open',
  )
})

test('identifies an invalid date range and non-whole attendance before submission', () => {
  renderForm()
  fillValidForm()
  fireEvent.change(screen.getByLabelText('End date and time *'), {
    target: { value: '2099-12-01T08:00' },
  })
  fireEvent.change(screen.getByLabelText('Expected attendance *'), { target: { value: '1.5' } })
  fireEvent.click(screen.getByRole('button', { name: 'Submit for review' }))

  expect(
    screen.getByText('End date and time must be after the start date and time.'),
  ).toBeInTheDocument()
  expect(screen.getByText('Enter a positive whole number.')).toBeInTheDocument()
})

test('rejects equal start and end times before submission', () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch')
  renderForm()
  fillValidForm()
  fireEvent.change(screen.getByLabelText('End date and time *'), {
    target: { value: '2099-12-01T09:00' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Submit for review' }))

  expect(
    screen.getByText('End date and time must be after the start date and time.'),
  ).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
})

test('rejects a start date in the past before submission', () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch')
  renderForm()
  fillValidForm()
  fireEvent.change(screen.getByLabelText('Start date and time *'), {
    target: { value: '2020-12-01T09:00' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Submit for review' }))

  expect(screen.getByText('Start date and time must be in the future.')).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
})

test('uses catalogue selects for venue and equipment in the unified form', () => {
  renderForm()

  expect(screen.getByLabelText('Venue requirement *').tagName).toBe('SELECT')
  expect(screen.getByLabelText('Venue requirement *')).toHaveTextContent('Auditorium-type venue')
  expect(screen.getByLabelText('Equipment requirement *').tagName).toBe('SELECT')
  expect(screen.getByLabelText('Equipment requirement *')).toHaveTextContent(
    'Projector-type requirement',
  )
})

test('shows a draft server validation problem beside its field', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    json({ detail: [{ field: 'expected_attendance', reason: 'must be a whole number' }] }, 422),
  )
  renderForm()
  fireEvent.change(screen.getByLabelText('Expected attendance *'), {
    target: { value: '1.5' },
  })

  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('validation errors')
  expect(screen.getByLabelText('Expected attendance *').parentElement).toHaveTextContent(
    'must be a whole number',
  )
})

function eventRequest(overrides: Partial<EventRequest>): EventRequest {
  return {
    id: 'request',
    status: 'draft',
    coordinator_id: null,
    name: null,
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
    created_at: '2026-10-11T00:00:00Z',
    updated_at: '2026-10-11T00:00:00Z',
    submitted_at: null,
    decided_by_id: null,
    decided_at: null,
    rejection_reason: null,
    status_permits: ['edit', 'submit'],
    ...overrides,
  }
}
