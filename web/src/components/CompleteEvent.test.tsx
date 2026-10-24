import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import type { EventRequest } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import ClosureRecord from './ClosureRecord'
import CompleteEvent from './CompleteEvent'

// SCRUM-86: the Coordinator completes an event and keeps its closure record.

const event = { id: 'event-1', name: 'Careers Fair', status: 'confirmed' } as EventRequest

const closure = {
  event_request_id: 'event-1',
  status: 'completed',
  completed_by_id: 'coord-1',
  completed_at: '2030-03-04T12:00:00Z',
  current: {
    version: 2,
    actual_attendance: 125,
    notes: 'Recounted',
    recorded_by_id: 'coord-1',
    recorded_at: '2030-03-05T02:00:00Z',
  },
  history: [
    {
      version: 1,
      actual_attendance: null,
      notes: null,
      recorded_by_id: 'coord-1',
      recorded_at: '2030-03-04T12:00:00Z',
    },
    {
      version: 2,
      actual_attendance: 125,
      notes: 'Recounted',
      recorded_by_id: 'coord-1',
      recorded_at: '2030-03-05T02:00:00Z',
    },
  ],
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

describe('SCRUM-86 complete an event', () => {
  test('AC1, AC3: completing sends the attendance and notes and tells the parent', async () => {
    const sent: unknown[] = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      sent.push(JSON.parse(String(init?.body)))
      return json(closure)
    })
    const onCompleted = vi.fn()
    wrap(<CompleteEvent event={event} onCompleted={onCompleted} />)

    fireEvent.change(screen.getByLabelText('Actual attendance (optional)'), {
      target: { value: '172' },
    })
    fireEvent.change(screen.getByLabelText('Operational notes and issues (optional)'), {
      target: { value: 'Ran late' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Complete Careers Fair' }))

    await vi.waitFor(() => expect(onCompleted).toHaveBeenCalled())
    expect(sent).toEqual([{ actual_attendance: 172, notes: 'Ran late' }])
  })

  test('AC3: an empty attendance is sent as no count, not zero', async () => {
    const sent: unknown[] = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      sent.push(JSON.parse(String(init?.body)))
      return json(closure)
    })
    wrap(<CompleteEvent event={event} onCompleted={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Complete Careers Fair' }))

    await vi.waitFor(() => expect(sent).toEqual([{ actual_attendance: null, notes: null }]))
  })

  test('AC1: a refusal is shown as the API says it', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json({ detail: 'This event has not ended yet' }, 409),
    )
    wrap(<CompleteEvent event={event} onCompleted={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Complete Careers Fair' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('This event has not ended yet')
  })
})

describe('SCRUM-86 closure record', () => {
  test('AC4, AC5: the current version and earlier ones are shown, no count is not zero', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(closure))
    wrap(<ClosureRecord eventId="event-1" />)

    expect(await screen.findByText('Actual attendance: 125')).toBeInTheDocument()
    expect(screen.getByText('Earlier versions (1)')).toBeInTheDocument()
    expect(screen.getByText('Actual attendance: not recorded')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save correction' })).not.toBeInTheDocument()
  })

  test('AC5: the Coordinator saves a correction as a new version', async () => {
    const posted: unknown[] = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      if (init?.method === 'POST') {
        posted.push(JSON.parse(String(init.body)))
        return json(closure.current, 201)
      }
      return json(closure)
    })
    wrap(<ClosureRecord eventId="event-1" canCorrect />)

    fireEvent.change(await screen.findByLabelText('Actual attendance'), {
      target: { value: '0' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save correction' }))

    await vi.waitFor(() => expect(posted).toEqual([{ actual_attendance: 0, notes: null }]))
  })

  test('AC4: a reader who is refused sees why', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: 'Forbidden' }, 403))
    wrap(<ClosureRecord eventId="event-1" />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Forbidden')
  })
})
