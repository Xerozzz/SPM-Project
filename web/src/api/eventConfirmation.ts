/**
 * SCRUM-80: the assigned Coordinator confirms an event.
 *
 * Mirrors `/event-requests/{id}/confirmation` and `/confirm`. No rules live here. What
 * is still missing, and whether the safety approval still applies to the plan, are the
 * API's answers; this module carries them and says them in words the Coordinator can act
 * on, because the whole point of the two lists is knowing whose job each reason is.
 */

import { describeBlocker } from './safetyReviews'

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

/** AC2, AC3 and AC10: whether this event may be confirmed, and what is missing. */
export interface ConfirmationReadiness {
  event_request_id: string
  may_confirm: boolean
  /** SCRUM-79's vocabulary: work for Venue Staff, Technical Support or the Coordinator. */
  arrangement_blockers: string[]
  /** SCRUM-80's own: the Safety Officer's to clear. */
  safety_blockers: string[]
}

/** AC4: one hold that is now a real booking. */
export interface ConfirmedBooking {
  booking_id: string
  venue_id: string
  session_label: string
  start_at: string
  end_at: string
}

/** AC4 and AC6: what confirmation did. */
export interface Confirmation {
  event_request_id: string
  status: string
  confirmed_by_id: string | null
  confirmed_at: string | null
  confirmed_bookings: ConfirmedBooking[]
}

/**
 * The safety reasons, said as what has to happen next.
 *
 * The API names the state; the Coordinator needs to know who to go to, because none of
 * these are theirs to clear by pressing anything on this screen.
 */
const SAFETY_REASONS: Record<string, string> = {
  not_in_planning: 'This event is not in planning, so there is nothing to confirm.',
  safety_not_reviewed: 'The Safety Officer has not reviewed this event yet.',
  safety_not_approved: 'The Safety Officer sent the plan back rather than approving it.',
  safety_approval_stale:
    'The plan changed after the Safety Officer approved it, so it needs reviewing again.',
}

export function describeSafetyBlocker(blocker: string): string {
  return SAFETY_REASONS[blocker] ?? blocker
}

/** AC2, AC3, AC7 and AC10: the refusal, with every reason, in its two halves. */
export class NotConfirmableError extends Error {
  readonly arrangementBlockers: string[]
  readonly safetyBlockers: string[]

  constructor(arrangement: string[], safety: string[]) {
    super('This event cannot be confirmed yet.')
    this.name = 'NotConfirmableError'
    this.arrangementBlockers = arrangement
    this.safetyBlockers = safety
  }
}

function listOf(value: unknown): string[] {
  return Array.isArray(value) ? (value as string[]) : []
}

async function failureOf(response: Response, fallback: string): Promise<Error> {
  const detail = await response
    .clone()
    .json()
    .then((body: { detail?: unknown }) => body.detail)
    .catch(() => null)
  if (detail !== null && typeof detail === 'object') {
    const reason = detail as {
      reason?: unknown
      arrangement_blockers?: unknown
      safety_blockers?: unknown
    }
    if (reason.reason === 'not_confirmable') {
      return new NotConfirmableError(
        listOf(reason.arrangement_blockers),
        listOf(reason.safety_blockers),
      )
    }
  }
  if (typeof detail === 'string') return new Error(detail)
  return new Error(`${fallback} (${response.status})`)
}

/** Everything standing between this event and confirmation, as words. */
export function describeBlockers(readiness: ConfirmationReadiness): string[] {
  return [
    ...readiness.arrangement_blockers.map(describeBlocker),
    ...readiness.safety_blockers.map(describeSafetyBlocker),
  ]
}

export async function readConfirmationReadiness(
  token: string,
  eventId: string,
): Promise<ConfirmationReadiness> {
  const response = await fetch(`/api/event-requests/${eventId}/confirmation`, {
    headers: authHeaders(token),
  })
  if (!response.ok) {
    throw new Error(`Could not check whether this event can be confirmed (${response.status})`)
  }
  return (await response.json()) as ConfirmationReadiness
}

/** AC4: commit the event and its holds. */
export async function confirmEvent(token: string, eventId: string): Promise<Confirmation> {
  const response = await fetch(`/api/event-requests/${eventId}/confirm`, {
    method: 'POST',
    headers: authHeaders(token),
  })
  if (!response.ok) throw await failureOf(response, 'The event could not be confirmed')
  return (await response.json()) as Confirmation
}
