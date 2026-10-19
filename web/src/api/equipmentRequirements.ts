/**
 * SCRUM-43: the equipment an event needs, as the assigned Coordinator maintains it.
 *
 * Mirrors schemas/equipment_requirements.py. No rules live here: what counts as a valid
 * quantity, which types are allowed and when a requirement goes back for review are the
 * API's decisions, and this module only carries the answers.
 */

// Defined here rather than shared, the way every other api module in this folder does
// it. Pulling them into one place is a tidy-up for its own change, not this one.
function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

function jsonHeaders(token: string): HeadersInit {
  return { ...authHeaders(token), 'Content-Type': 'application/json' }
}

/** SCRUM-44's closed vocabulary. SCRUM-43 only ever produces `pending_review`. */
export type RequirementReview =
  | 'pending_review'
  | 'available'
  | 'partially_available'
  | 'unavailable'

export const REVIEW_LABELS: Record<RequirementReview, string> = {
  pending_review: 'Pending review',
  available: 'Available',
  partially_available: 'Partially available',
  unavailable: 'Unavailable',
}

/** SCRUM-53: how much of a requirement's quantity is reserved. Derived, never stored. */
export type ReservationState = 'not_reserved' | 'partially_reserved' | 'reserved'

export interface EquipmentRequirement {
  id: string
  event_request_id: string
  equipment_type: string
  quantity: number
  technical_requirements: string | null
  review_status: RequirementReview
  removed_at: string | null
  created_at: string
  updated_at: string
  /** SCRUM-53: how many of this type Technical Support have committed. */
  reserved_quantity: number
  reservation_state: ReservationState
  /**
   * SCRUM-43 AC6: this requirement changed or was removed after something was reserved
   * against it. The reservation is not released; Technical Support reconsider it, and
   * the AC says the Coordinator can see the flag, which is what this is for.
   */
  has_flagged_reservation: boolean
}

export interface RequirementInput {
  equipment_type: string | null
  quantity: number | null
  technical_requirements: string | null
}

/** What the API changes: never the type, because AC4 makes one type one line. */
export interface RequirementChange {
  quantity?: number | null
  technical_requirements?: string | null
}

export interface RequirementProblem {
  field: string
  reason: string
}

/** The fields a 422 can name, in the words the form uses for them. */
export const REQUIREMENT_FIELD_LABELS: Record<string, string> = {
  equipment_type: 'Equipment type',
  quantity: 'Quantity',
  technical_requirements: 'Technical requirements',
}

/** Thrown when the API refuses a save and names the fields to correct (AC3, AC4). */
export class RequirementRejectedError extends Error {
  readonly problems: RequirementProblem[]

  constructor(problems: RequirementProblem[]) {
    super('The equipment requirement has validation errors')
    this.name = 'RequirementRejectedError'
    this.problems = problems
  }
}

function problemsFrom(detail: unknown): RequirementProblem[] | null {
  if (!Array.isArray(detail)) return null
  const problems = detail.filter(
    (item): item is RequirementProblem =>
      !!item &&
      typeof item === 'object' &&
      typeof (item as RequirementProblem).field === 'string' &&
      typeof (item as RequirementProblem).reason === 'string',
  )
  return problems.length > 0 ? problems : null
}

async function read(response: Response): Promise<EquipmentRequirement> {
  if (response.status === 422) {
    const body = (await response.json()) as { detail?: unknown }
    const problems = problemsFrom(body.detail)
    if (problems) throw new RequirementRejectedError(problems)
  }
  if (!response.ok) {
    throw new Error(`The equipment requirement could not be saved (${response.status})`)
  }
  return (await response.json()) as EquipmentRequirement
}

function base(eventId: string): string {
  return `/api/event-requests/${eventId}/equipment-requirements`
}

/** AC1: the live requirements for this event. Removed ones are not returned. */
export async function listEquipmentRequirements(
  token: string,
  eventId: string,
): Promise<EquipmentRequirement[]> {
  const response = await fetch(base(eventId), { headers: authHeaders(token) })
  if (!response.ok) {
    throw new Error(`Could not load equipment requirements (${response.status})`)
  }
  return (await response.json()) as EquipmentRequirement[]
}

/** AC2 and AC3. */
export async function addEquipmentRequirement(
  token: string,
  eventId: string,
  input: RequirementInput,
): Promise<EquipmentRequirement> {
  return read(
    await fetch(base(eventId), {
      method: 'POST',
      headers: jsonHeaders(token),
      body: JSON.stringify(input),
    }),
  )
}

/** AC2 and AC5: changing a line sends it back for review. */
export async function updateEquipmentRequirement(
  token: string,
  eventId: string,
  requirementId: string,
  change: RequirementChange,
): Promise<EquipmentRequirement> {
  return read(
    await fetch(`${base(eventId)}/${requirementId}`, {
      method: 'PATCH',
      headers: jsonHeaders(token),
      body: JSON.stringify(change),
    }),
  )
}

/** AC7: out of the live set, but the row and its history stay. */
export async function removeEquipmentRequirement(
  token: string,
  eventId: string,
  requirementId: string,
): Promise<EquipmentRequirement> {
  return read(
    await fetch(`${base(eventId)}/${requirementId}`, {
      method: 'DELETE',
      headers: authHeaders(token),
    }),
  )
}

/**
 * AC3: the active catalogue types this event's Coordinator may choose from.
 *
 * Not `/event-requests/equipment-types`, which is the organiser's route and refuses a
 * Coordinator. This one is guarded by the same access as maintaining a requirement, so
 * the list is readable exactly when choosing from it is allowed.
 */
export async function listCatalogueTypes(token: string, eventId: string): Promise<string[]> {
  const response = await fetch(`${base(eventId)}/catalogue-types`, {
    headers: authHeaders(token),
  })
  if (!response.ok) {
    throw new Error(`Could not load the equipment catalogue (${response.status})`)
  }
  return (await response.json()) as string[]
}
