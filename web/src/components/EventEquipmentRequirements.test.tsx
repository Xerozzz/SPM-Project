import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { EventRequest } from '../api/eventRequests'
import { AuthProvider } from '../auth/context'
import EventEquipmentRequirements from './EventEquipmentRequirements'

// SCRUM-43: the assigned Coordinator maintains an event's equipment.
//
// The backend for this landed in Sprint 3 and the screen did not, so a Coordinator had
// no way to do any of it. The rules stay on the API: these tests check that each action
// is sent correctly and that the answer, including a refusal, reaches the Coordinator.

beforeEach(() => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'coordinator-1', roles: ['coordinator'] }),
  )
})

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const EVENT = { id: 'event-1', name: 'Orientation Day' } as unknown as EventRequest

const PROJECTOR = {
  id: 'req-1',
  event_request_id: 'event-1',
  equipment_type: 'Projector',
  quantity: 2,
  technical_requirements: 'Needs an HDMI cable',
  review_status: 'pending_review',
  reserved_quantity: 0,
  reservation_state: 'not_reserved',
  has_flagged_reservation: false,
  removed_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderEditor(handler?: (key: string, init?: RequestInit) => Response | undefined) {
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    const answer = handler?.(key, init)
    if (answer) return answer
    if (key === 'GET /api/event-requests/event-1/equipment-requirements/catalogue-types')
      return json(['Projector', 'Microphone'])
    if (key === 'GET /api/event-requests/event-1/equipment-requirements') return json([PROJECTOR])
    throw new Error(`unexpected request ${key}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <EventEquipmentRequirements event={EVENT} />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return spy
}

test('AC1: the requirements already on the event are listed with their review status', async () => {
  renderEditor()

  expect(await screen.findByLabelText('Quantity for Projector')).toBeInTheDocument()
  expect(screen.getByLabelText('Quantity for Projector')).toHaveValue(2)
  expect(screen.getByText('Pending review')).toBeInTheDocument()
  expect(screen.getByText('Needs an HDMI cable')).toBeInTheDocument()
})

test('AC3: a requirement is added from the catalogue, not typed free hand', async () => {
  const spy = renderEditor((key) =>
    key === 'POST /api/event-requests/event-1/equipment-requirements'
      ? json({ ...PROJECTOR, id: 'req-2', equipment_type: 'Microphone' }, 201)
      : undefined,
  )
  await screen.findByLabelText('Quantity for Projector')
  // The only types offered are the active catalogue ones the API returned.
  expect(await screen.findByRole('option', { name: 'Microphone' })).toBeInTheDocument()

  fireEvent.change(screen.getByLabelText('Equipment type'), { target: { value: 'Microphone' } })
  fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '3' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add requirement' }))

  await waitFor(() => {
    const post = spy.mock.calls.find((call) => call[1]?.method === 'POST')
    expect(post).toBeDefined()
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      equipment_type: 'Microphone',
      quantity: 3,
      technical_requirements: null,
    })
  })
})

test('AC3: a blank quantity is sent as absent, not as zero', async () => {
  // The API reports a missing quantity differently from an invalid one, and the
  // Coordinator should get the message that matches what they actually did.
  const spy = renderEditor((key) =>
    key === 'POST /api/event-requests/event-1/equipment-requirements'
      ? json(PROJECTOR, 201)
      : undefined,
  )
  await screen.findByLabelText('Quantity for Projector')
  fireEvent.change(screen.getByLabelText('Equipment type'), { target: { value: 'Microphone' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add requirement' }))

  await waitFor(() => {
    const post = spy.mock.calls.find((call) => call[1]?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body)).quantity).toBeNull()
  })
})

test('AC3 and AC4: a refusal names the field to correct', async () => {
  renderEditor((key) =>
    key === 'POST /api/event-requests/event-1/equipment-requirements'
      ? json(
          { detail: [{ field: 'equipment_type', reason: 'is already required for this event' }] },
          422,
        )
      : undefined,
  )
  await screen.findByLabelText('Quantity for Projector')
  fireEvent.change(screen.getByLabelText('Equipment type'), { target: { value: 'Projector' } })
  fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add requirement' }))

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Equipment type is already required for this event',
  )
})

test('AC5: changing a quantity sends a patch and says it is back for review', async () => {
  const spy = renderEditor((key) =>
    key === 'PATCH /api/event-requests/event-1/equipment-requirements/req-1'
      ? json({ ...PROJECTOR, quantity: 5, review_status: 'pending_review' })
      : undefined,
  )
  await screen.findByLabelText('Quantity for Projector')
  const quantity = screen.getByLabelText('Quantity for Projector')
  fireEvent.change(quantity, { target: { value: '5' } })
  fireEvent.blur(quantity)

  await waitFor(() => {
    const patch = spy.mock.calls.find((call) => call[1]?.method === 'PATCH')
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ quantity: 5 })
  })
  expect(await screen.findByRole('status')).toHaveTextContent('back to pending review')
})

test('AC5: a quantity left untouched sends nothing', async () => {
  // Blur fires whenever focus leaves the field, so without this the Coordinator would
  // send a pointless change - and send the line back for review - just by tabbing past.
  const spy = renderEditor()
  await screen.findByLabelText('Quantity for Projector')
  fireEvent.blur(screen.getByLabelText('Quantity for Projector'))

  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(spy.mock.calls.filter((call) => call[1]?.method === 'PATCH')).toHaveLength(0)
})

test('AC7: removing a requirement says the history is kept', async () => {
  const spy = renderEditor((key) =>
    key === 'DELETE /api/event-requests/event-1/equipment-requirements/req-1'
      ? json({ ...PROJECTOR, removed_at: '2026-02-01T00:00:00Z' })
      : undefined,
  )
  await screen.findByLabelText('Quantity for Projector')
  fireEvent.click(screen.getByRole('button', { name: 'Remove Projector' }))

  await waitFor(() => {
    expect(spy.mock.calls.some((call) => call[1]?.method === 'DELETE')).toBe(true)
  })
  expect(await screen.findByRole('status')).toHaveTextContent("stays in the event's history")
})

test('a failure that names no field still reaches the Coordinator', async () => {
  renderEditor((key) =>
    key === 'DELETE /api/event-requests/event-1/equipment-requirements/req-1'
      ? new Response('boom', { status: 500 })
      : undefined,
  )
  await screen.findByLabelText('Quantity for Projector')
  fireEvent.click(screen.getByRole('button', { name: 'Remove Projector' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('could not be saved (500)')
})

test('an event with nothing required says so rather than showing an empty list', async () => {
  renderEditor((key) =>
    key === 'GET /api/event-requests/event-1/equipment-requirements' ? json([]) : undefined,
  )

  expect(await screen.findByText('Nothing is required for this event yet.')).toBeInTheDocument()
})

test('AC3: the catalogue comes from the route the Coordinator is allowed to read', async () => {
  // Not the organiser's `/event-requests/equipment-types`, which refuses a Coordinator
  // outright. That left the dropdown empty and the whole screen unusable, which no
  // mocked test would have shown.
  const spy = renderEditor()
  await screen.findByLabelText('Quantity for Projector')

  const asked = spy.mock.calls.map((call) => String(call[0]))
  expect(asked).toContain('/api/event-requests/event-1/equipment-requirements/catalogue-types')
  expect(asked).not.toContain('/api/event-requests/equipment-types')
})

// ------------------------------------------------- AC6: what a change did to a booking
//
// SCRUM-53 reserves equipment against a requirement. Changing or removing that
// requirement does not release the reservation; Technical Support reconsider it. AC6
// says the Coordinator can see the flag, and this is the screen where they would.

test('AC6: a requirement with equipment reserved against it says how much', async () => {
  renderEditor((key) =>
    key === 'GET /api/event-requests/event-1/equipment-requirements'
      ? json([
          {
            ...PROJECTOR,
            quantity: 9,
            reserved_quantity: 2,
            reservation_state: 'partially_reserved',
          },
        ])
      : undefined,
  )

  expect(await screen.findByText('2 of 9 reserved')).toBeInTheDocument()
})

test('AC6: a flagged reservation is shown to the Coordinator', async () => {
  renderEditor((key) =>
    key === 'GET /api/event-requests/event-1/equipment-requirements'
      ? json([{ ...PROJECTOR, reserved_quantity: 1, has_flagged_reservation: true }])
      : undefined,
  )

  expect(await screen.findByText('Reservation to reconsider')).toBeInTheDocument()
})

test('AC6: nothing reserved means no flag and no count', async () => {
  renderEditor()

  await screen.findByLabelText('Quantity for Projector')
  expect(screen.queryByText('Reservation to reconsider')).toBeNull()
  expect(screen.queryByText(/reserved/)).toBeNull()
})

test('AC6: removing a requirement says the reservation is not simply gone', async () => {
  // "Removed. It stays in the event's history." on its own lets a Coordinator believe
  // the matter is closed while Technical Support still hold equipment for it.
  renderEditor((key) =>
    key === 'DELETE /api/event-requests/event-1/equipment-requirements/req-1'
      ? json({ ...PROJECTOR, removed_at: '2026-02-01T00:00:00Z', has_flagged_reservation: true })
      : undefined,
  )
  await screen.findByLabelText('Quantity for Projector')
  fireEvent.click(screen.getByRole('button', { name: 'Remove Projector' }))

  expect(await screen.findByRole('status')).toHaveTextContent(
    'Technical Support have equipment reserved for it and will reconsider',
  )
})
