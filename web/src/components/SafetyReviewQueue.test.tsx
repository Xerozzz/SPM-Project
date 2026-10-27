import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { AuthProvider } from '../auth/context'
import SafetyReviewQueue from './SafetyReviewQueue'

// SCRUM-79: the Safety Officer reviews the plan an event is being run to.
//
// The rules stay on the API: what blocks a review (AC2) and whether the plan has moved
// since it was read (AC7) are its answers. These tests check that the plan reaches the
// Officer in full (AC1, AC3), that a decision carries the fingerprint it was taken
// against, and that both refusals say something the Officer can act on.

beforeEach(() => {
  localStorage.setItem(
    'connectsphere.token',
    JSON.stringify({ token: 'token', userId: 'officer-1', roles: ['safety_officer'] }),
  )
})

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

const READY = {
  event_request_id: 'event-1',
  event_name: 'Orientation Day',
  event_start_at: '2030-01-01T02:00:00Z',
  event_end_at: '2030-01-01T06:00:00Z',
  expected_attendance: 200,
  accessibility_requirement: 'Step-free access',
  layout_requirement: 'Theatre',
  venues: [
    {
      booking_id: 'booking-1',
      venue_id: 'venue-1',
      session_label: 'Main session',
      start_at: '2030-01-01T02:00:00Z',
      end_at: '2030-01-01T06:00:00Z',
      status: 'tentative',
      hold_expired: false,
    },
  ],
  equipment: [
    {
      requirement_id: 'req-1',
      equipment_type: 'Projector',
      quantity: 4,
      review_status: 'available',
      reservation_state: 'reserved',
      has_flagged_reservation: false,
    },
  ],
  plan_fingerprint: 'fingerprint-abc',
  may_review: true,
  blockers: [],
  latest_decision: null,
}

const RECORDED = {
  id: 'review-1',
  event_request_id: 'event-1',
  decision: 'approve',
  comment: 'Egress is clear.',
  plan_fingerprint: 'fingerprint-abc',
  decided_by_id: 'officer-1',
  decided_at: '2029-12-01T02:00:00Z',
  returns_to_coordinator: false,
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderQueue(
  worklist: unknown[] = [READY],
  handler?: (key: string, init?: RequestInit) => Response | undefined,
) {
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    const answer = handler?.(key, init)
    if (answer) return answer
    if (key === 'GET /api/safety-reviews') return json(worklist)
    throw new Error(`unexpected request ${key}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <SafetyReviewQueue />
      </AuthProvider>
    </QueryClientProvider>,
  )
  return spy
}

async function typeReason(text: string) {
  const reason = await screen.findByLabelText('Reason for this decision')
  fireEvent.change(reason, { target: { value: text } })
}

test('the plan a decision is about is shown in full', async () => {
  renderQueue()

  expect(await screen.findByText('Orientation Day')).toBeInTheDocument()
  expect(screen.getByText('200 expected')).toBeInTheDocument()
  expect(screen.getByText(/Step-free access/)).toBeInTheDocument()
  expect(screen.getByText(/Theatre/)).toBeInTheDocument()
  expect(screen.getByText('Main session')).toBeInTheDocument()
  expect(screen.getByText('Tentative hold')).toBeInTheDocument()
  expect(screen.getByText(/Projector/)).toBeInTheDocument()
  expect(screen.getByText('Available')).toBeInTheDocument()
  expect(screen.getByText('reserved')).toBeInTheDocument()
})

test('a hold that has run out is called out on the venue it belongs to', async () => {
  renderQueue([{ ...READY, venues: [{ ...READY.venues[0], hold_expired: true }] }])

  expect(await screen.findByText('Hold has run out')).toBeInTheDocument()
})

test('a plan that cannot be reviewed yet says why, and offers no decision', async () => {
  renderQueue([
    {
      ...READY,
      may_review: false,
      blockers: ['hold_expired', 'equipment_unreviewed'],
    },
  ])

  expect(await screen.findByText('This plan cannot be reviewed yet.')).toBeInTheDocument()
  expect(screen.getByText(/A venue hold has run out/)).toBeInTheDocument()
  expect(screen.getByText(/Technical Support have not assessed/)).toBeInTheDocument()
  expect(screen.queryByLabelText('Reason for this decision')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Approve the plan for Orientation Day')).not.toBeInTheDocument()
})

test('a decision needs a reason before it can be recorded', async () => {
  renderQueue()

  const approve = await screen.findByLabelText('Approve the plan for Orientation Day')
  expect(approve).toBeDisabled()
  expect(screen.getByText('A reason is needed to record a decision.')).toBeInTheDocument()

  // Whitespace is not a reason: the API strips it, so the screen must agree.
  await typeReason('   ')
  expect(approve).toBeDisabled()

  await typeReason('Egress is clear.')
  expect(approve).toBeEnabled()
})

test('approving sends the fingerprint of the plan that was read, and says it confirms nothing', async () => {
  const spy = renderQueue([READY], (key) =>
    key === 'POST /api/safety-reviews/event-1' ? json(RECORDED, 201) : undefined,
  )

  await typeReason('Egress is clear.')
  fireEvent.click(screen.getByLabelText('Approve the plan for Orientation Day'))

  await waitFor(() => {
    expect(screen.getByRole('status')).toHaveTextContent(
      'Safety approved for Orientation Day. This does not confirm the event.',
    )
  })
  const posted = spy.mock.calls.find(([, init]) => init?.method === 'POST')
  expect(JSON.parse(String(posted?.[1]?.body))).toEqual({
    decision: 'approve',
    comment: 'Egress is clear.',
    plan_fingerprint: 'fingerprint-abc',
  })
})

test('rejecting says the plan goes back to the Coordinator', async () => {
  renderQueue([READY], (key) =>
    key === 'POST /api/safety-reviews/event-1'
      ? json(
          {
            ...RECORDED,
            decision: 'reject',
            comment: 'Exit route is blocked.',
            returns_to_coordinator: true,
          },
          201,
        )
      : undefined,
  )

  await typeReason('Exit route is blocked.')
  fireEvent.click(screen.getByLabelText('Reject the plan for Orientation Day'))

  await waitFor(() => {
    expect(screen.getByRole('status')).toHaveTextContent(
      'Reject recorded for Orientation Day. The Coordinator has been notified.',
    )
  })
})

test('requesting changes is offered as its own decision', async () => {
  renderQueue([READY], (key) =>
    key === 'POST /api/safety-reviews/event-1'
      ? json(
          {
            ...RECORDED,
            decision: 'request_changes',
            comment: 'Add a second exit.',
            returns_to_coordinator: true,
          },
          201,
        )
      : undefined,
  )

  await typeReason('Add a second exit.')
  fireEvent.click(screen.getByLabelText('Request changes the plan for Orientation Day'))

  await waitFor(() => {
    expect(screen.getByRole('status')).toHaveTextContent(
      'Request changes recorded for Orientation Day. The Coordinator has been notified.',
    )
  })
})

test('a decision against a plan that has moved is refused and the list is reloaded', async () => {
  let loads = 0
  const spy = renderQueue([READY], (key) => {
    if (key === 'GET /api/safety-reviews') {
      loads += 1
      return json([READY])
    }
    if (key === 'POST /api/safety-reviews/event-1') {
      return json({ detail: { reason: 'plan_changed', plan_fingerprint: 'fingerprint-xyz' } }, 409)
    }
    return undefined
  })

  await typeReason('Egress is clear.')
  const before = loads
  fireEvent.click(screen.getByLabelText('Approve the plan for Orientation Day'))

  await waitFor(() => {
    expect(screen.getByRole('alert')).toHaveTextContent(
      'The plan changed while you were reviewing it. Read it again before deciding.',
    )
  })
  await waitFor(() => expect(loads).toBeGreaterThan(before))
  expect(spy).toHaveBeenCalled()
})

test('a prerequisite that broke after the plan was read is reported with its reasons', async () => {
  renderQueue([READY], (key) =>
    key === 'POST /api/safety-reviews/event-1'
      ? json({ detail: { reason: 'plan_not_reviewable', blockers: ['hold_expired'] } }, 409)
      : undefined,
  )

  await typeReason('Egress is clear.')
  fireEvent.click(screen.getByLabelText('Approve the plan for Orientation Day'))

  await waitFor(() => {
    expect(screen.getByRole('alert')).toHaveTextContent('This plan cannot be reviewed yet.')
  })
  expect(screen.getByRole('alert')).toHaveTextContent('A venue hold has run out')
})

test('the decision the Coordinator still has to act on stays on the card', async () => {
  renderQueue([
    {
      ...READY,
      latest_decision: {
        ...RECORDED,
        decision: 'request_changes',
        comment: 'Add a second exit.',
        returns_to_coordinator: true,
      },
    },
  ])

  // Scoped to the card's own paragraph: "Request changes" is also a button label, and
  // the point of this test is that the outstanding decision is readable, not that the
  // words appear somewhere.
  const outstanding = await screen.findByText(/Add a second exit\./)
  expect(outstanding).toHaveTextContent('Request changes')
})

test('past decisions are loaded only when they are asked for', async () => {
  const spy = renderQueue([READY], (key) =>
    key === 'GET /api/safety-reviews/event-1/history'
      ? json([{ ...RECORDED, comment: 'Egress is clear.' }])
      : undefined,
  )

  await screen.findByText('Orientation Day')
  const asked = (url: string) => spy.mock.calls.some(([input]) => String(input) === url)
  expect(asked('/api/safety-reviews/event-1/history')).toBe(false)

  fireEvent.click(screen.getByRole('button', { name: 'Past decisions' }))

  expect(await screen.findByText(/Egress is clear\./)).toBeInTheDocument()
  expect(asked('/api/safety-reviews/event-1/history')).toBe(true)
})

test('an empty worklist says so rather than looking broken', async () => {
  renderQueue([])

  expect(await screen.findByText('No events are being planned.')).toBeInTheDocument()
})

test('a worklist that cannot be loaded is reported', async () => {
  renderQueue([], (key) =>
    key === 'GET /api/safety-reviews' ? json({ detail: 'nope' }, 500) : undefined,
  )

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Could not load the safety review worklist (500)',
  )
})

test('the worklist separates what can be reviewed from what is waiting on a Coordinator', async () => {
  renderQueue([
    READY,
    {
      ...READY,
      event_request_id: 'event-2',
      event_name: 'Hackathon',
      may_review: false,
      blockers: ['no_venue_arrangement'],
    },
  ])

  expect(await screen.findByText('Ready to review (1)')).toBeInTheDocument()
  expect(screen.getByText('Waiting on arrangements (1)')).toBeInTheDocument()
})

test('the answer appears on the card that was acted on, not at the foot of the list', async () => {
  // The whole point: on a real board most events are waiting, so a message at the end of
  // the section is thousands of pixels below the button that produced it.
  renderQueue([READY, { ...READY, event_request_id: 'event-2', event_name: 'Hackathon' }], (key) =>
    key === 'POST /api/safety-reviews/event-2' ? json(RECORDED, 201) : undefined,
  )

  const hackathon = (await screen.findByText('Hackathon')).closest('article')
  const orientation = screen.getByText('Orientation Day').closest('article')
  expect(hackathon).not.toBeNull()

  const reason = screen.getByLabelText('Reason for this decision', {
    selector: `#safety-comment-event-2`,
  })
  fireEvent.change(reason, { target: { value: 'Egress is clear.' } })
  fireEvent.click(screen.getByLabelText('Approve the plan for Hackathon'))

  await waitFor(() => {
    expect(hackathon?.querySelector('[role="status"]')).not.toBeNull()
  })
  expect(orientation?.querySelector('[role="status"]')).toBeNull()
})
