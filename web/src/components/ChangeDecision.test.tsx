import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import ChangeRequestList from './ChangeRequestList'

// SCRUM-47: the assigned Coordinator approves or rejects a pending change request.

const pending = {
  id: 'cr-1',
  event_request_id: 'req-1',
  requested_by_id: 'org-1',
  reason: 'More people signed up',
  status: 'pending',
  event_updated_at: '2026-10-01T00:00:00Z',
  created_at: '2026-10-20T01:00:00Z',
  decided_by_id: null,
  decided_at: null,
  decision_note: null,
  items: [
    {
      target: 'event',
      target_id: null,
      field: 'expected_attendance',
      current_value: 100,
      proposed_value: 150,
      outcome: null,
    },
    {
      target: 'equipment',
      target_id: 'e-1',
      field: 'quantity',
      current_value: 2,
      proposed_value: 3,
      outcome: null,
    },
  ],
}

const approved = {
  ...pending,
  status: 'approved',
  decided_by_id: 'coord-1',
  decided_at: '2026-10-20T02:00:00Z',
  decision_note: 'Hall fits',
  items: [
    { ...pending.items[0], outcome: 'applied' },
    { ...pending.items[1], outcome: 'needs_replanning' },
  ],
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

function renderList(decide: () => Response, canDecide = true) {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'coord-1', roles: ['coordinator'] }),
  )
  let listed: unknown = pending
  const sent: unknown[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    if (key === 'GET /api/event-requests/req-1/change-requests') return json([listed])
    if (key === 'POST /api/event-requests/req-1/change-requests/cr-1/decision') {
      sent.push(JSON.parse(String(init?.body)))
      const response = decide()
      if (response.ok) listed = await response.clone().json()
      return response
    }
    throw new Error(`unexpected request ${key}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ChangeRequestList eventId="req-1" canDecide={canDecide} />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return sent
}

describe('SCRUM-47 decide a change request', () => {
  test('AC1, AC3: approving with a note shows what was applied and what needs replanning', async () => {
    const sent = renderList(() => json(approved))

    const approve = await screen.findByRole('button', { name: 'Approve change' })
    expect(approve).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Decision note'), { target: { value: 'Hall fits' } })
    fireEvent.click(approve)

    expect(await screen.findByText('Approved')).toBeInTheDocument()
    expect(sent).toEqual([{ decision: 'approve', note: 'Hall fits' }])
    expect(screen.getByText('Hall fits')).toBeInTheDocument()
    const rows = screen.getAllByRole('row')
    expect(within(rows[1]).getByText('Applied')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Needs replanning')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve change' })).not.toBeInTheDocument()
  })

  test('AC6: rejecting sends the reason', async () => {
    const sent = renderList(() =>
      json({ ...pending, status: 'rejected', decision_note: 'Too big' }),
    )

    fireEvent.change(await screen.findByLabelText('Decision note'), {
      target: { value: 'Too big' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Reject change' }))

    expect(await screen.findByText('Rejected')).toBeInTheDocument()
    expect(sent).toEqual([{ decision: 'reject', note: 'Too big' }])
  })

  test('AC2: a stale request explains why and stays pending', async () => {
    renderList(() =>
      json(
        { detail: [{ field: 'items[0]', reason: 'has changed since the request was made' }] },
        409,
      ),
    )

    fireEvent.change(await screen.findByLabelText('Decision note'), { target: { value: 'ok' } })
    fireEvent.click(screen.getByRole('button', { name: 'Approve change' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The event has changed since this request was made',
    )
    expect(screen.getByText('Pending review')).toBeInTheDocument()
  })

  test('AC9: an already decided request shows the API message', async () => {
    renderList(() => json({ detail: 'this change request is already approved' }, 409))

    fireEvent.change(await screen.findByLabelText('Decision note'), { target: { value: 'ok' } })
    fireEvent.click(screen.getByRole('button', { name: 'Reject change' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'this change request is already approved',
    )
  })

  test('the Organiser sees the requests but no decision buttons', async () => {
    renderList(() => json(approved), false)

    expect(await screen.findByText('Pending review')).toBeInTheDocument()
    expect(screen.queryByLabelText('Decision note')).not.toBeInTheDocument()
  })
})
