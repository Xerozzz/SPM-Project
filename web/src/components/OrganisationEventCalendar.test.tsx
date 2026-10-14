import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import type { EventCalendarEntry, EventRequest } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import OrganisationEventCalendar from './OrganisationEventCalendar'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const shared: EventCalendarEntry = {
  id: 'colleague-event',
  name: 'Shared workshop',
  status: 'draft',
  start_at: '2026-11-01T09:00:00Z',
  end_at: '2026-11-01T11:00:00Z',
}

const sharedDetail = eventRequest({
  id: shared.id,
  name: shared.name,
  purpose: 'Organisation planning',
  description: 'A colleague-owned draft',
  start_at: shared.start_at,
  end_at: shared.end_at,
  venue_requirement: 'Auditorium-type venue',
})

function renderCalendar({
  entries = [],
  detail = sharedDetail,
  status = 200,
  pending = false,
}: {
  entries?: EventCalendarEntry[]
  detail?: EventRequest
  status?: number
  pending?: boolean
} = {}) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'organiser', roles: ['organiser'] }),
  )
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    expect(init?.headers).toEqual({ Authorization: 'Bearer token' })
    const url = String(input)
    if (url === '/api/event-requests/organisation-calendar') {
      if (pending) return new Promise<Response>(() => {})
      return new Response(JSON.stringify(entries), { status })
    }
    if (url === `/api/event-requests/${detail.id}`) {
      return new Response(JSON.stringify(detail), { status: 200 })
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
}

describe('SCRUM-87 organisation calendar (frontend unit)', () => {
  test('renders event name, formatted start/end and current status', async () => {
    renderCalendar({ entries: [shared] })
    expect(await screen.findByText(shared.name!)).toBeInTheDocument()
    expect(screen.getByText(new Date(shared.start_at).toLocaleString())).toBeInTheDocument()
    expect(screen.getByText(new Date(shared.end_at).toLocaleString())).toBeInTheDocument()
    expect(screen.getByText('draft')).toBeInTheDocument()
  })

  test('renders multiple organisation events as separate entries', async () => {
    renderCalendar({
      entries: [shared, { ...shared, id: 'own-event', name: 'Own event', status: 'submitted' }],
    })
    const entries = await screen.findAllByRole('listitem')
    expect(entries).toHaveLength(2)
    expect(within(entries[0]).getByText('Shared workshop')).toBeInTheDocument()
    expect(within(entries[1]).getByText('Own event')).toBeInTheDocument()
    expect(within(entries[1]).getByText('submitted')).toBeInTheDocument()
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

  test('opens a colleague event in a read-only detail view', async () => {
    renderCalendar({ entries: [shared] })
    fireEvent.click(await screen.findByRole('button', { name: 'View Shared workshop details' }))

    const details = await screen.findByRole('article', { name: 'Event request details' })
    expect(within(details).getByText('Organisation planning')).toBeInTheDocument()
    expect(within(details).getByText('A colleague-owned draft')).toBeInTheDocument()
    expect(within(details).getByText('Auditorium-type venue')).toBeInTheDocument()
    expect(within(details).getByText('Read-only organisation view')).toBeInTheDocument()
    expect(
      within(details).queryByRole('button', { name: /edit|save|submit/i }),
    ).not.toBeInTheDocument()
    expect(within(details).queryByRole('textbox')).not.toBeInTheDocument()
  })

  test('unnamed dated drafts remain identifiable and openable', async () => {
    const untitled = { ...shared, name: null }
    renderCalendar({ entries: [untitled], detail: eventRequest({ ...sharedDetail, name: null }) })
    fireEvent.click(await screen.findByRole('button', { name: 'View Untitled event details' }))
    const details = await screen.findByRole('article', { name: 'Event request details' })
    expect(within(details).getByText('Untitled event')).toBeInTheDocument()
  })
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
