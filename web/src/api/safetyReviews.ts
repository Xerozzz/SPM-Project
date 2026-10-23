/**
 * SCRUM-79: the Safety Officer's review of an event's plan.
 *
 * Mirrors `/safety-reviews`. No rules live here. Whether a plan may be reviewed, what
 * blocks it and whether a decision is still about the plan in front of the Officer are
 * all the API's answers; this module carries them, and turns the two refusals the screen
 * has to explain into errors a person can read.
 */

import type { RequirementReview, ReservationState } from './equipmentRequirements'
import type { BookingStatus } from './venueBookingDecisions'

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

/** AC4: what an Officer may record. Both of the last two send the plan back (AC5). */
export const SAFETY_DECISIONS = ['approve', 'request_changes', 'reject'] as const

export type SafetyDecision = (typeof SAFETY_DECISIONS)[number]

export const DECISION_LABELS: Record<SafetyDecision, string> = {
  approve: 'Approve',
  request_changes: 'Request changes',
  reject: 'Reject',
}

/** AC3: one venue arrangement, as the Officer sees it. */
export interface PlannedVenue {
  booking_id: string
  venue_id: string
  session_label: string
  start_at: string
  end_at: string
  status: BookingStatus
  /** ADR-0030 expires a hold on a sweep, so a tentative hold can still have run out. */
  hold_expired: boolean
}

/** AC3: one equipment requirement, as the Officer sees it. */
export interface PlannedEquipment {
  requirement_id: string
  equipment_type: string
  quantity: number
  review_status: RequirementReview
  reservation_state: ReservationState
  has_flagged_reservation: boolean
}

/** AC9: one decision, as it was taken. */
export interface SafetyReview {
  id: string
  event_request_id: string
  decision: SafetyDecision
  comment: string
  plan_fingerprint: string
  decided_by_id: string
  decided_at: string
  /** AC5: the API's answer, not ours. Comparing against 'approve' here would put the
   *  rule in a second place, and a fourth outcome would read as an approval. */
  returns_to_coordinator: boolean
  /** SCRUM-130: set when the event went back to planning after this approval. */
  invalidated_at?: string | null
  invalidation_cause?: string | null
}

/** AC1, AC2 and AC3: one event's plan, whether it may be judged, and the last word. */
export interface EventPlan {
  event_request_id: string
  event_name: string | null
  event_start_at: string | null
  event_end_at: string | null
  expected_attendance: number | null
  accessibility_requirement: string | null
  layout_requirement: string | null
  venues: PlannedVenue[]
  equipment: PlannedEquipment[]
  /** AC7: sent back with a decision, so one taken against a moved plan is refused. */
  plan_fingerprint: string
  may_review: boolean
  blockers: string[]
  /** AC5: the decision the Coordinator still has to act on, or null. */
  latest_decision: SafetyReview | null
}

/**
 * AC2's reasons, said as what a Coordinator still has to do.
 *
 * The API's vocabulary names the state; the Officer needs to know who owes what, because
 * they cannot clear any of these themselves.
 */
const BLOCKER_REASONS: Record<string, string> = {
  // Also what the Officer sees when every arrangement was refused or ran out: the API
  // leaves those out of the plan, so "none standing" and "none ever asked for" arrive
  // the same way and the wording has to be true of both.
  no_venue_arrangement: 'No venue is currently held for this event.',
  venue_not_held: 'A venue request is still waiting on Venue Staff.',
  hold_expired: 'A venue hold has run out and has to be renewed.',
  equipment_unreviewed: 'Technical Support have not assessed every equipment requirement.',
  equipment_not_fulfilled: 'Equipment that was assessed has not been fully reserved.',
  reservation_needs_reconsidering:
    'A requirement changed after equipment was reserved against it (SCRUM-43 AC6).',
}

export function describeBlocker(blocker: string): string {
  return BLOCKER_REASONS[blocker] ?? blocker
}

/** AC2: the plan is not arranged enough to judge, with every reason at once. */
export class PlanNotReviewableError extends Error {
  readonly blockers: string[]

  constructor(blockers: string[]) {
    super('This plan cannot be reviewed yet.')
    this.name = 'PlanNotReviewableError'
    this.blockers = blockers
  }
}

/** AC7: the plan moved between the Officer reading it and deciding on it. */
export class PlanChangedError extends Error {
  constructor() {
    super('The plan changed while you were reviewing it. Read it again before deciding.')
    this.name = 'PlanChangedError'
  }
}

/** A 409 carries a reason object; anything else is reported as it arrived. */
async function failureOf(response: Response, fallback: string): Promise<Error> {
  const detail = await response
    .clone()
    .json()
    .then((body: { detail?: unknown }) => body.detail)
    .catch(() => null)
  if (detail !== null && typeof detail === 'object') {
    const reason = detail as { reason?: unknown; blockers?: unknown }
    if (reason.reason === 'plan_not_reviewable') {
      return new PlanNotReviewableError(
        Array.isArray(reason.blockers) ? (reason.blockers as string[]) : [],
      )
    }
    if (reason.reason === 'plan_changed') return new PlanChangedError()
  }
  if (typeof detail === 'string') return new Error(detail)
  return new Error(`${fallback} (${response.status})`)
}

/** AC1: every event in planning, ready to review or not, with the reasons either way. */
export async function listPlansToReview(token: string): Promise<EventPlan[]> {
  const response = await fetch('/api/safety-reviews', { headers: authHeaders(token) })
  if (!response.ok) {
    throw new Error(`Could not load the safety review worklist (${response.status})`)
  }
  return (await response.json()) as EventPlan[]
}

/** AC9: every decision taken on this event, oldest first. */
export async function listDecisions(token: string, eventId: string): Promise<SafetyReview[]> {
  const response = await fetch(`/api/safety-reviews/${eventId}/history`, {
    headers: authHeaders(token),
  })
  if (!response.ok) {
    throw new Error(`Could not load the review history (${response.status})`)
  }
  return (await response.json()) as SafetyReview[]
}

/**
 * AC4: record a decision against the plan the Officer was actually looking at.
 *
 * `planFingerprint` comes from the plan on screen, never recomputed here: the point of
 * sending it is that the API can tell the two apart.
 */
export async function recordDecision(
  token: string,
  eventId: string,
  decision: SafetyDecision,
  comment: string,
  planFingerprint: string,
): Promise<SafetyReview> {
  const response = await fetch(`/api/safety-reviews/${eventId}`, {
    method: 'POST',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, comment, plan_fingerprint: planFingerprint }),
  })
  if (!response.ok) throw await failureOf(response, 'The decision could not be recorded')
  return (await response.json()) as SafetyReview
}
