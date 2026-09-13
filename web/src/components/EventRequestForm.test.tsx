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
    JSON.stringify({ token: 'token', roles: ['organiser'] }),
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

function fillValidForm() {
  const values: Record<string, string> = {
    Name: 'Orientation Day',
    Purpose: 'Welcome new students',
    Description: 'Campus orientation activities',
    'Start date and time': '2026-12-01T09:00',
    'End date and time': '2026-12-01T13:00',
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

test('shows every required field error and keeps entered details for correction', () => {
  renderForm()
  fireEvent.change(screen.getByLabelText('Name *'), { target: { value: 'Orientation Day' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))

  expect(screen.getAllByText('This field is required.')).toHaveLength(10)
  expect(screen.getByLabelText('Name *')).toHaveValue('Orientation Day')
})

test('identifies an end time before the start and a non-whole attendance value', () => {
  renderForm()
  fillValidForm()
  fireEvent.change(screen.getByLabelText('End date and time *'), {
    target: { value: '2026-12-01T08:00' },
  })
  fireEvent.change(screen.getByLabelText('Expected attendance *'), { target: { value: '1.5' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))

  expect(
    screen.getByText('End date and time must be after the start date and time.'),
  ).toBeInTheDocument()
  expect(screen.getByText('Enter a positive whole number.')).toBeInTheDocument()
  expect(screen.getByLabelText('End date and time *').parentElement).toHaveTextContent(
    'End date and time must be after the start date and time.',
  )
})

test('identifies an end time equal to the start time', () => {
  renderForm()
  fillValidForm()
  fireEvent.change(screen.getByLabelText('End date and time *'), {
    target: { value: '2026-12-01T09:00' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))

  expect(
    screen.getByText('End date and time must be after the start date and time.'),
  ).toBeInTheDocument()
})

test('rejects zero attendance and accepts the minimum value of one', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ id: 'request-1', name: 'Orientation Day', status: 'draft' }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  renderForm()
  fillValidForm()
  const attendance = screen.getByLabelText('Expected attendance *')
  fireEvent.change(attendance, { target: { value: '0' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))
  expect(screen.getByText('Enter a positive whole number.')).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()

  fireEvent.change(attendance, { target: { value: '1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
})

test('creates a draft without submitting it or selecting resources', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ id: 'request-1', name: 'Orientation Day', status: 'draft' }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  renderForm()
  fillValidForm()
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }))

  await waitFor(() => {
    expect(screen.getByRole('status')).toHaveTextContent('was saved as a Draft')
  })
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/event-requests',
    expect.objectContaining({ method: 'POST' }),
  )
  expect(String(fetchMock.mock.calls[0]?.[0])).not.toContain('submit')
})

test('offers catalogue requirement choices without offering a specific resource', () => {
  renderForm()

  expect(screen.getByLabelText('Venue requirement *')).toHaveTextContent('Auditorium-type venue')
  expect(screen.getByLabelText('Equipment requirement *')).toHaveTextContent(
    'Projector-type requirement',
  )
  expect(screen.getAllByText(/does not reserve a specific resource/i)).toHaveLength(2)
})
