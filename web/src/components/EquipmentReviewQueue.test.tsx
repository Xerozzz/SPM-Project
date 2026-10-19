import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import EquipmentReviewQueue from './EquipmentReviewQueue'

// SCRUM-44 and SCRUM-53: Technical Support assess what events need, and reserve it.
//
// The routes behind this merged with SCRUM-44 and nothing ever reached them, so neither
// story could be shown through the UI. The rules stay on the API: these tests check that
// each action is sent correctly and that the answer, refusals included, reaches the
// person who has to act on it.

beforeEach(() => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'tech-1', roles: ['tech_support'] }),
  )
})

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const PROJECTOR = {
  id: 'req-1',
  event_request_id: 'event-1',
  event_name: 'Orientation Day',
  event_start_at: '2030-01-01T02:00:00Z',
  event_end_at: '2030-01-01T06:00:00Z',
  equipment_type: 'Projector',
  quantity: 4,
  technical_requirements: 'Needs an HDMI cable',
  review_status: 'pending_review',
  reserved_quantity: 0,
  reservation_state: 'not_reserved',
  has_flagged_reservation: false,
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderQueue(handler?: (key: string, init?: RequestInit) => Response | undefined) {
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    const answer = handler?.(key, init)
    if (answer) return answer
    if (key === 'GET /api/equipment-requirements/review') return json([PROJECTOR])
    throw new Error(`unexpected request ${key}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <EquipmentReviewQueue />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return spy
}

const outcomeLabel = 'Outcome for Projector on Orientation Day'
const reserveLabel = 'Reserve equipment for Projector on Orientation Day'

test('SCRUM-44 AC1: what needs assessing, with the timing needed to assess it', async () => {
  const sgt = (value: string) =>
    new Date(value).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })
  renderQueue()

  // "Projector" is also in the two action labels, so match the row's own line.
  expect(await screen.findByText(/Projector .4/)).toBeInTheDocument()
  expect(screen.getByText(/for Orientation Day/)).toBeInTheDocument()
  expect(
    screen.getByText(`${sgt('2030-01-01T02:00:00Z')} to ${sgt('2030-01-01T06:00:00Z')}`),
  ).toBeInTheDocument()
  expect(screen.getByText('Needs an HDMI cable')).toBeInTheDocument()
  expect(screen.getByText('Pending review')).toBeInTheDocument()
})

test('SCRUM-44 AC2: recording an outcome sends it and says so', async () => {
  const spy = renderQueue((key) =>
    key === 'PATCH /api/equipment-requirements/req-1/review' ? json({}) : undefined,
  )
  await screen.findByLabelText(outcomeLabel)
  fireEvent.change(screen.getByLabelText(outcomeLabel), {
    target: { value: 'partially_available' },
  })

  await waitFor(() => {
    const patch = spy.mock.calls.find((call) => call[1]?.method === 'PATCH')
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      review_status: 'partially_available',
    })
  })
  expect(await screen.findByRole('status')).toHaveTextContent('partially available')
})

test('SCRUM-44 AC2: choosing the placeholder sends nothing', async () => {
  // The select opens on "Record an outcome". Without the guard, clearing it back would
  // send an empty verdict the API has to refuse.
  const spy = renderQueue()
  await screen.findByLabelText(outcomeLabel)
  fireEvent.change(screen.getByLabelText(outcomeLabel), { target: { value: '' } })

  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(spy.mock.calls.filter((call) => call[1]?.method === 'PATCH')).toHaveLength(0)
})

test('SCRUM-53: reserving says how much was taken and what is left', async () => {
  renderQueue((key) =>
    key.startsWith('POST /api/event-requests/event-1/equipment-requirements/req-1/reserve')
      ? json(
          {
            requirement_id: 'req-1',
            event_request_id: 'event-1',
            equipment_type: 'Projector',
            reserved_now: 3,
            total_reserved: 3,
            outstanding: 1,
            state: 'partially_reserved',
          },
          201,
        )
      : undefined,
  )
  await screen.findByLabelText(reserveLabel)
  fireEvent.click(screen.getByLabelText(reserveLabel))

  // Partial is allowed, so "reserved" on its own would overstate it.
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Reserved 3 Projector. 1 still outstanding.',
  )
})

test('SCRUM-53: a refusal is explained, not shown as a status code', async () => {
  renderQueue((key) =>
    key.startsWith('POST /api/event-requests/event-1/equipment-requirements/req-1/reserve')
      ? json({ detail: 'nothing_free' }, 409)
      : undefined,
  )
  await screen.findByLabelText(reserveLabel)
  fireEvent.click(screen.getByLabelText(reserveLabel))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'None of this type is free for the event period.',
  )
})

test('SCRUM-43 AC6: a flagged reservation is shown to Technical Support', async () => {
  // The other half of AC6. The Coordinator sees the flag on their event; this is the
  // surface where Technical Support decide what happens to the reservation.
  renderQueue((key) =>
    key === 'GET /api/equipment-requirements/review'
      ? json([{ ...PROJECTOR, reserved_quantity: 2, has_flagged_reservation: true }])
      : undefined,
  )

  expect(await screen.findByText('Reservation to reconsider')).toBeInTheDocument()
  expect(screen.getByText('2 of 4 reserved')).toBeInTheDocument()
})

test('an empty queue says so rather than showing nothing', async () => {
  renderQueue((key) => (key === 'GET /api/equipment-requirements/review' ? json([]) : undefined))

  expect(await screen.findByText('Nothing is waiting to be assessed.')).toBeInTheDocument()
})
