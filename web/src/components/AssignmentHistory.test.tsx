import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import type { AssignmentHistoryEntry } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import AssignmentHistory, { AssignmentHistoryToggle } from './AssignmentHistory'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const URL = '/api/event-requests/req-1/assignment-history'
const ASSIGNED_AT = '2026-10-20T01:30:00Z'

const first: AssignmentHistoryEntry = {
  id: 'h-1',
  previous_coordinator_id: null,
  previous_coordinator_email: null,
  new_coordinator_id: 'c-1',
  new_coordinator_email: 'alice@example.com',
  acted_by_id: 'l-1',
  acted_by_email: 'lead@example.com',
  assigned_at: ASSIGNED_AT,
}

const second: AssignmentHistoryEntry = {
  ...first,
  id: 'h-2',
  previous_coordinator_id: 'c-1',
  previous_coordinator_email: 'alice@example.com',
  new_coordinator_id: 'c-2',
  new_coordinator_email: 'bob@example.com',
  assigned_at: '2026-10-21T08:00:00Z',
}

function renderWith(entries: AssignmentHistoryEntry[], ui: ReactElement) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'organiser', roles: ['organiser'] }),
  )
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input) === URL) return new Response(JSON.stringify(entries), { status: 200 })
    throw new Error(`unexpected request ${String(input)}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>{ui}</AuthProvider>
    </QueryClientProvider>,
  )
  return fetchSpy
}

const history = <AssignmentHistory requestId="req-1" requestName="Open Day" />

describe('SCRUM-105 assignment history display (frontend unit)', () => {
  test('names people by email, oldest first, with "First assignment" for the first', async () => {
    renderWith([first, second], history)
    const entries = await screen.findAllByRole('listitem')

    expect(entries).toHaveLength(2)
    expect(entries[0]).toHaveTextContent('First assignment → alice@example.com by lead@example.com')
    expect(entries[1]).toHaveTextContent('alice@example.com → bob@example.com by lead@example.com')
    expect(screen.queryByText(/Unknown user/)).toBeNull()
  })

  test('shows "Unknown user" for each person the API has no email for', async () => {
    renderWith(
      [
        {
          ...second,
          previous_coordinator_email: null,
          new_coordinator_email: null,
          acted_by_email: null,
        },
      ],
      history,
    )
    const [entry] = await screen.findAllByRole('listitem')

    expect(entry).toHaveTextContent('Unknown user → Unknown user by Unknown user')
    expect(entry).not.toHaveTextContent('First assignment')
  })

  test("shows assigned_at in the viewer's local time, not the raw UTC string", async () => {
    renderWith([first], history)
    const [entry] = await screen.findAllByRole('listitem')
    const time = entry.querySelector('time')

    expect(time).not.toBeNull()
    expect(time).toHaveAttribute('dateTime', ASSIGNED_AT)
    expect(time).toHaveTextContent(new Date(ASSIGNED_AT).toLocaleString())
    expect(entry).not.toHaveTextContent(ASSIGNED_AT)
  })

  test('keeps the existing empty state for an event that was never assigned', async () => {
    renderWith([], history)
    expect(await screen.findByText('No assignment history for Open Day yet.')).toBeInTheDocument()
  })

  test('the toggle fetches nothing until opened, and offers no assign or reassign', async () => {
    const fetchSpy = renderWith(
      [first],
      <AssignmentHistoryToggle requestId="req-1" requestName="Open Day" />,
    )
    const toggle = screen.getByRole('button', { name: 'View assignment history' })

    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(fetchSpy).not.toHaveBeenCalled()

    fireEvent.click(toggle)
    const [entry] = await screen.findAllByRole('listitem')
    expect(within(entry).getByText(/alice@example.com/)).toBeInTheDocument()
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Hide assignment history' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    // The toggle is the only control: no assign or reassign action comes with the view.
    expect(screen.getAllByRole('button')).toHaveLength(1)
  })
})
