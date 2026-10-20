/** SCRUM-37: an Organiser's significant-change requests. The API checks every value. */

export interface PlannedSession {
  id: string
  session_label: string
  start_at: string
  end_at: string
}

export interface PlannedRequirement {
  id: string
  equipment_type: string
  quantity: number
  technical_requirements: string | null
}

/** What the change form starts from, and the catalogue choices it may use. */
export interface ChangePlan {
  event: Record<string, string | number | null>
  sessions: PlannedSession[]
  equipment: PlannedRequirement[]
  venue_options: string[]
  equipment_types: string[]
}

export interface SessionChange {
  booking_id: string
  session_label?: string
  start_at?: string
  end_at?: string
}

export interface EquipmentChange {
  requirement_id?: string
  equipment_type?: string
  quantity?: number
  technical_requirements?: string | null
  remove?: boolean
}

export interface ChangeRequestInput {
  /** New per submit action and reused on a retry, so a retry never makes a second request. */
  submission_key: string
  reason: string
  event: Record<string, string | number | null>
  sessions: SessionChange[]
  equipment: EquipmentChange[]
}

export interface ChangeItem {
  target: 'event' | 'session' | 'equipment'
  target_id: string | null
  field: string
  current_value: unknown
  proposed_value: unknown
  /** SCRUM-47: applied or needs_replanning once approved, null before. */
  outcome: string | null
}

export interface ChangeRequest {
  id: string
  event_request_id: string
  requested_by_id: string
  reason: string
  status: string
  event_updated_at: string
  created_at: string
  decided_by_id: string | null
  decided_at: string | null
  decision_note: string | null
  items: ChangeItem[]
}

export type Decision = 'approve' | 'reject'

export interface ChangeProblem {
  field: string
  reason: string
}

/** Thrown when the API refuses a proposal and names what to correct (AC4). */
export class ChangeRejectedError extends Error {
  readonly problems: ChangeProblem[]

  constructor(problems: ChangeProblem[], message = 'The change request has validation errors') {
    super(message)
    this.name = 'ChangeRejectedError'
    this.problems = problems
  }
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

function base(eventId: string): string {
  return `/api/event-requests/${eventId}/change-requests`
}

/** A 422 from the rules is a list of problems. One from the schema is FastAPI's shape. */
function problemsFrom(detail: unknown): ChangeProblem[] {
  if (!Array.isArray(detail)) return []
  return detail.map(
    (item: { field?: unknown; reason?: unknown; loc?: unknown; msg?: unknown }) => ({
      field:
        typeof item.field === 'string'
          ? item.field
          : Array.isArray(item.loc)
            ? item.loc.slice(1).join('.')
            : 'request',
      reason:
        typeof item.reason === 'string'
          ? item.reason
          : typeof item.msg === 'string'
            ? item.msg
            : 'is not valid',
    }),
  )
}

export async function getChangePlan(token: string, eventId: string): Promise<ChangePlan> {
  const response = await fetch(`${base(eventId)}/plan`, { headers: authHeaders(token) })
  if (!response.ok) throw new Error(`Could not load the current plan (${response.status})`)
  return (await response.json()) as ChangePlan
}

export async function listChangeRequests(token: string, eventId: string): Promise<ChangeRequest[]> {
  const response = await fetch(base(eventId), { headers: authHeaders(token) })
  if (!response.ok) throw new Error(`Could not load change requests (${response.status})`)
  return (await response.json()) as ChangeRequest[]
}

export async function proposeChange(
  token: string,
  eventId: string,
  input: ChangeRequestInput,
): Promise<ChangeRequest> {
  const response = await fetch(base(eventId), {
    method: 'POST',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (response.status === 422) {
    const body = (await response.json()) as { detail?: unknown }
    throw new ChangeRejectedError(problemsFrom(body.detail))
  }
  if (!response.ok) throw new Error(`The change request could not be sent (${response.status})`)
  return (await response.json()) as ChangeRequest
}

/** SCRUM-47: the assigned Coordinator approves or rejects a pending request. */
export async function decideChangeRequest(
  token: string,
  eventId: string,
  changeId: string,
  decision: Decision,
  note: string,
): Promise<ChangeRequest> {
  const response = await fetch(`${base(eventId)}/${changeId}/decision`, {
    method: 'POST',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, note }),
  })
  if (response.status === 422) {
    const body = (await response.json()) as { detail?: unknown }
    throw new ChangeRejectedError(problemsFrom(body.detail))
  }
  if (response.status === 409) {
    const body = (await response.json()) as { detail?: unknown }
    // AC2: a list names what changed since the request was made. AC9: text says it was
    // already decided.
    if (Array.isArray(body.detail)) {
      throw new ChangeRejectedError(
        problemsFrom(body.detail),
        'The event has changed since this request was made. Ask for a new request against the current values.',
      )
    }
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Already decided')
  }
  if (!response.ok) throw new Error(`The decision could not be recorded (${response.status})`)
  return (await response.json()) as ChangeRequest
}
