import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import type { EventCalendarEntry } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import OrganisationEventCalendar from './OrganisationEventCalendar'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const calendarDate = new Date()
const eventStart = new Date(calendarDate.getFullYear(), calendarDate.getMonth(), 15, 9, 0, 0)
const eventEnd = new Date(eventStart.getTime() + 2 * 60 * 60 * 1000)

const shared: EventCalendarEntry = {
  id: 'colleague-event',
  name: 'Shared workshop',
  status: 'draft',
  start_at: eventStart.toISOString(),
  end_at: eventEnd.toISOString(),
}

function renderCalendar({
  entries = [],
  status = 200,
  pending = false,
}: {
  entries?: EventCalendarEntry[]
  status?: number
  pending?: boolean
} = {}) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'organiser', roles: ['organiser'] }),
  )
  // SCRUM-112: the calendar endpoint is the only one this component may call; any other
  // request, including the full event request, fails the test.
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    expect(init?.headers).toEqual({ Authorization: 'Bearer token' })
    const url = String(input)
    if (url === '/api/event-requests/organisation-calendar') {
      if (pending) return new Promise<Response>(() => {})
      return new Response(JSON.stringify(entries), { status })
    }
    throw new Error(`unexpected request ${url}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <OrganisationEventCalendar />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return fetchSpy
}

describe('SCRUM-87 organisation calendar (frontend unit)', () => {
  test('renders event name, formatted start/end and current status', async () => {
    renderCalendar({ entries: [shared] })
    const event = await screen.findByRole('button', { name: 'View Shared workshop details' })
    expect(event).toHaveTextContent('Shared workshop')
    expect(event).toHaveTextContent('draft')

    fireEvent.click(event)
    const details = screen.getByRole('article', { name: 'Event calendar details' })
    expect(
      within(details).getByText(new Date(shared.start_at).toLocaleString()),
    ).toBeInTheDocument()
    expect(within(details).getByText(new Date(shared.end_at).toLocaleString())).toBeInTheDocument()
  })

  test('renders multiple organisation events as separate entries', async () => {
    renderCalendar({
      entries: [shared, { ...shared, id: 'own-event', name: 'Own event', status: 'submitted' }],
    })
    expect(
      await screen.findByRole('button', { name: 'View Shared workshop details' }),
    ).toBeInTheDocument()
    const ownEvent = screen.getByRole('button', { name: 'View Own event details' })
    expect(ownEvent).toHaveTextContent('submitted')
  })

  test('shows the no-event state', async () => {
    renderCalendar()
    expect(await screen.findByText('No dated events.')).toBeInTheDocument()
  })

  test('shows loading state', () => {
    renderCalendar({ pending: true })
    expect(screen.getByRole('status')).toHaveTextContent('Loading organisation calendar...')
  })

  test('shows an error when the calendar cannot load', async () => {
    renderCalendar({ status: 500 })
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load organisation calendar (500)',
    )
  })
})

describe('SCRUM-112 peer calendar entries show calendar fields only (frontend unit)', () => {
  test('selecting an entry shows name, start, end and status without fetching the request', async () => {
    const fetchSpy = renderCalendar({ entries: [shared] })
    fireEvent.click(await screen.findByRole('button', { name: 'View Shared workshop details' }))

    const details = screen.getByRole('article', { name: 'Event calendar details' })
    expect(within(details).getByRole('heading', { name: 'Shared workshop' })).toBeInTheDocument()
    expect(within(details).getByText('draft')).toBeInTheDocument()
    expect(
      within(details).getByText(new Date(shared.start_at).toLocaleString()),
    ).toBeInTheDocument()
    expect(within(details).getByText(new Date(shared.end_at).toLocaleString())).toBeInTheDocument()
    expect(within(details).getByText('Calendar details only')).toBeInTheDocument()
    expect(within(details).queryByText(/purpose|description|venue|attendance/i)).toBeNull()
    expect(within(details).queryByRole('button')).not.toBeInTheDocument()
    expect(within(details).queryByRole('textbox')).not.toBeInTheDocument()
    expect(fetchSpy.mock.calls.map(([input]) => String(input))).toEqual([
      '/api/event-requests/organisation-calendar',
    ])
  })

  // SCRUM-88: a peer may not read the history (ADR-0039), so the calendar never offers it.
  test('the calendar offers no event history', async () => {
    renderCalendar({ entries: [shared] })
    fireEvent.click(await screen.findByRole('button', { name: 'View Shared workshop details' }))

    expect(screen.queryByRole('button', { name: /event history/i })).toBeNull()
  })

  test('unnamed dated drafts remain identifiable and openable', async () => {
    const fetchSpy = renderCalendar({ entries: [{ ...shared, name: null }] })
    fireEvent.click(await screen.findByRole('button', { name: 'View Untitled event details' }))
    const details = screen.getByRole('article', { name: 'Event calendar details' })
    expect(within(details).getByText('Untitled event')).toBeInTheDocument()
    expect(fetchSpy).toHaveBeenCalledTimes(1)
  })
})
