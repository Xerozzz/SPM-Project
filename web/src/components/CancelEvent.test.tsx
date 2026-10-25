import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import type { Cancellation, CancellationRequest } from '../api/eventCancellation'
import type { EventRequest } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import CancelEvent from './CancelEvent'
import CancellationRecord from './CancellationRecord'
import RequestCancellation from './RequestCancellation'

// SCRUM-115: cancel a whole event, and the Organiser's requests to do so.

const event = {
  id: 'event-1',
  name: 'Careers Fair',
  status: 'confirmed',
  status_permits: ['cancel', 'complete', 'replan'],
} as EventRequest

const waiting: CancellationRequest = {
  id: 'request-1',
  status: 'pending',
  reason: 'Speaker is ill',
  requested_by_id: 'org-1',
  requested_at: '2030-03-01T02:00:00Z',
  decided_by_id: null,
  decided_at: null,
  decision_note: null,
}

function record(requests: CancellationRequest[], cancelled = false): Cancellation {
  return {
    event_request_id: 'event-1',
    status: cancelled ? 'cancelled' : 'confirmed',
    cancelled_by_id: cancelled ? 'coord-1' : null,
    cancelled_at: cancelled ? '2030-03-02T02:00:00Z' : null,
    cancellation_reason: cancelled ? 'Storm warning' : null,
    requests,
  }
}

beforeEach(() => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'coord-1', roles: ['coordinator'] }),
  )
})

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

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>{node}</AuthProvider>
    </QueryClientProvider>,
  )
}

/** Answers each call by its method and path, and remembers what was sent. */
function api(routes: Record<string, () => Response>) {
  const sent: { route: string; body: unknown }[] = []
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const method = init?.method ?? 'GET'
    const path = String(input).replace('/api/event-requests/event-1', '')
    const route = `${method} ${path}`
    sent.push({ route, body: init?.body ? JSON.parse(String(init.body)) : null })
    const answer = routes[route]
    if (!answer) throw new Error(`unexpected ${route}`)
    return answer()
  })
  return { sent, spy }
}

describe('SCRUM-115 Coordinator cancels an event', () => {
  test('nothing is fetched until the panel is opened', () => {
    const { spy } = api({})
    wrap(<CancelEvent event={event} onCancelled={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Cancel this event…' })).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })

  test('AC3: cancelling sends the reason and tells the parent', async () => {
    const { sent } = api({
      'GET /cancellation': () => json(record([])),
      'POST /cancel': () => json(record([], true)),
    })
    const onCancelled = vi.fn()
    wrap(<CancelEvent event={event} onCancelled={onCancelled} />)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel this event…' }))
    fireEvent.change(await screen.findByLabelText('Reason for cancelling'), {
      target: { value: 'Storm warning' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel event' }))

    await vi.waitFor(() => expect(onCancelled).toHaveBeenCalled())
    expect(onCancelled.mock.calls[0][0]).toContain('is cancelled')
    expect(sent.at(-1)).toEqual({
      route: 'POST /cancel',
      body: { reason: 'Storm warning', request_id: null },
    })
  })

  test('AC1: the Organiser’s request is shown and can be applied as asked', async () => {
    const { sent } = api({
      'GET /cancellation': () => json(record([waiting])),
      'POST /cancel': () => json(record([{ ...waiting, status: 'applied' }], true)),
    })
    const onCancelled = vi.fn()
    wrap(<CancelEvent event={event} onCancelled={onCancelled} />)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel this event…' }))
    expect(await screen.findByText('Speaker is ill')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel the event as asked' }))

    await vi.waitFor(() => expect(onCancelled).toHaveBeenCalled())
    expect(sent.at(-1)).toEqual({
      route: 'POST /cancel',
      body: { reason: null, request_id: 'request-1' },
    })
  })

  test('AC1: declining sends the note and the request is no longer waiting', async () => {
    let answered = false
    const { sent } = api({
      'GET /cancellation': () =>
        json(
          record([
            answered
              ? { ...waiting, status: 'declined', decision_note: 'Numbers are fine' }
              : waiting,
          ]),
        ),
      'POST /cancellation-requests/request-1/decline': () => {
        answered = true
        return json({ ...waiting, status: 'declined', decision_note: 'Numbers are fine' })
      },
    })
    wrap(<CancelEvent event={event} onCancelled={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel this event…' }))
    fireEvent.change(await screen.findByLabelText('Why you are declining'), {
      target: { value: 'Numbers are fine' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Decline request' }))

    await vi.waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Decline request' })).not.toBeInTheDocument(),
    )
    expect(sent).toContainEqual({
      route: 'POST /cancellation-requests/request-1/decline',
      body: { note: 'Numbers are fine' },
    })
  })

  test('AC2: a refusal is shown as the API says it', async () => {
    api({
      'GET /cancellation': () => json(record([])),
      'POST /cancel': () => json({ detail: 'This event is already cancelled' }, 409),
    })
    const onCancelled = vi.fn()
    wrap(<CancelEvent event={event} onCancelled={onCancelled} />)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel this event…' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel event' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('This event is already cancelled')
    expect(onCancelled).not.toHaveBeenCalled()
  })

  test('AC3: a missing reason is shown by field', async () => {
    api({
      'GET /cancellation': () => json(record([])),
      'POST /cancel': () => json({ detail: [{ field: 'reason', reason: 'is required' }] }, 422),
    })
    wrap(<CancelEvent event={event} onCancelled={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Cancel this event…' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel event' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('reason is required')
  })
})

describe('SCRUM-115 Organiser asks to cancel', () => {
  test('AC1: the request is sent and then shown as waiting', async () => {
    let asked = false
    const { sent } = api({
      'GET /cancellation': () => json(record(asked ? [waiting] : [])),
      'POST /cancellation-requests': () => {
        asked = true
        return json(waiting, 201)
      },
    })
    wrap(<RequestCancellation event={event} />)

    fireEvent.click(screen.getByRole('button', { name: 'Ask to cancel' }))
    fireEvent.change(await screen.findByLabelText('Why should it be cancelled?'), {
      target: { value: 'Speaker is ill' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send request' }))

    expect(await screen.findByText('Your Coordinator has not answered yet.')).toBeInTheDocument()
    expect(sent).toContainEqual({
      route: 'POST /cancellation-requests',
      body: { reason: 'Speaker is ill' },
    })
  })

  test('AC1: a declined request shows the Coordinator’s note and a new one can be sent', async () => {
    api({
      'GET /cancellation': () =>
        json(record([{ ...waiting, status: 'declined', decision_note: 'Numbers are fine' }])),
    })
    wrap(<RequestCancellation event={event} />)

    fireEvent.click(screen.getByRole('button', { name: 'Ask to cancel' }))

    expect(await screen.findByText('Declined.')).toBeInTheDocument()
    expect(screen.getByText(/Numbers are fine/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send request' })).toBeInTheDocument()
  })

  test('AC3: a cancelled event shows when and why', async () => {
    api({ 'GET /cancellation': () => json(record([], true)) })
    wrap(<CancellationRecord eventId="event-1" />)

    expect(await screen.findByText(/Reason: Storm warning/)).toBeInTheDocument()
  })
})
