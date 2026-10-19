/**
 * SCRUM-44 and SCRUM-53: the Technical Support side of an event's equipment.
 *
 * Mirrors the `/equipment-requirements` review routes and the reserve route. No rules
 * live here: what may be reviewed, how much may be reserved and what a refusal means are
 * the API's decisions, and this module only carries the answers.
 */

import type { RequirementReview, ReservationState } from './equipmentRequirements'

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

function jsonHeaders(token: string): HeadersInit {
  return { ...authHeaders(token), 'Content-Type': 'application/json' }
}

/** SCRUM-44 AC1: one requirement to assess, with the timing needed to assess it. */
export interface RequirementForReview {
  id: string
  event_request_id: string
  event_name: string | null
  event_start_at: string | null
  event_end_at: string | null
  equipment_type: string
  quantity: number
  technical_requirements: string | null
  review_status: RequirementReview
  reserved_quantity: number
  reservation_state: ReservationState
  /** SCRUM-43 AC6: changed or removed after something was reserved against it. */
  has_flagged_reservation: boolean
}

/** SCRUM-53 AC7: what one reserve action did, and where the requirement now stands. */
export interface ReservationOutcome {
  requirement_id: string
  event_request_id: string
  equipment_type: string
  reserved_now: number
  total_reserved: number
  outstanding: number
  state: ReservationState
}

/** The three outcomes SCRUM-44 records. `pending_review` is where a line starts, not a verdict. */
export const REVIEW_OUTCOMES = ['available', 'partially_available', 'unavailable'] as const

export type ReviewOutcome = (typeof REVIEW_OUTCOMES)[number]

/**
 * Why nothing was reserved, in the words the API uses.
 *
 * The refusal reaches us as the message of a plain error, so these are mapped to
 * something a person can act on rather than shown raw.
 */
const REFUSAL_REASONS: Record<string, string> = {
  above_outstanding: 'That is more than this requirement still needs.',
  above_free: 'That is more than is free for the event period.',
  nothing_outstanding: 'Everything this requirement needs is already reserved.',
  nothing_free: 'None of this type is free for the event period.',
}

export class ReservationRefusedError extends Error {
  constructor(refusal: string) {
    super(REFUSAL_REASONS[refusal] ?? refusal)
    this.name = 'ReservationRefusedError'
  }
}

async function failureOf(response: Response, fallback: string): Promise<Error> {
  const detail = await response
    .clone()
    .json()
    .then((body: { detail?: unknown }) => (typeof body.detail === 'string' ? body.detail : null))
    .catch(() => null)
  if (detail && detail in REFUSAL_REASONS) return new ReservationRefusedError(detail)
  return new Error(detail ?? `${fallback} (${response.status})`)
}

export async function listRequirementsForReview(
  token: string,
): Promise<RequirementForReview[]> {
  const response = await fetch('/api/equipment-requirements/review', {
    headers: authHeaders(token),
  })
  if (!response.ok) {
    throw new Error(`Could not load the equipment review queue (${response.status})`)
  }
  return (await response.json()) as RequirementForReview[]
}

/** SCRUM-44 AC2: record whether this requirement can be fulfilled. */
export async function reviewRequirement(
  token: string,
  requirementId: string,
  reviewStatus: ReviewOutcome,
): Promise<void> {
  const response = await fetch(`/api/equipment-requirements/${requirementId}/review`, {
    method: 'PATCH',
    headers: jsonHeaders(token),
    body: JSON.stringify({ review_status: reviewStatus }),
  })
  if (!response.ok) throw await failureOf(response, 'The review could not be recorded')
}

/**
 * SCRUM-53: reserve equipment for a requirement.
 *
 * `quantity` left out means as much as is needed and free, which is what the API does
 * with an absent body and the common case for Technical Support.
 */
export async function reserveEquipment(
  token: string,
  eventRequestId: string,
  requirementId: string,
  quantity?: number,
): Promise<ReservationOutcome> {
  const response = await fetch(
    `/api/event-requests/${eventRequestId}/equipment-requirements/${requirementId}/reserve`,
    {
      method: 'POST',
      headers: jsonHeaders(token),
      body: JSON.stringify(quantity === undefined ? {} : { quantity }),
    },
  )
  if (!response.ok) throw await failureOf(response, 'The reservation could not be made')
  return (await response.json()) as ReservationOutcome
}
