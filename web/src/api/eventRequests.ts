/**
 * Event request API calls for organisers (SCRUM-46). Mirrors api/schemas/event_requests.py.
 */

export type EventStatus = 'draft' | 'submitted'

export type EventAction = 'edit' | 'submit'

export interface EventRequest {
  id: string
  status: EventStatus
  name: string | null
  purpose: string | null
  description: string | null
  start_at: string | null
  end_at: string | null
  expected_attendance: number | null
  venue_requirement: string | null
  accessibility_requirement: string | null
  equipment_requirement: string | null
  layout_requirement: string | null
  registration_requirement: string | null
  created_at: string
  updated_at: string
  submitted_at: string | null
  allowed_actions: EventAction[]
}

/** One field the organiser has to fix before submission is accepted (AC2). */
export interface FieldProblem {
  field: string
  reason: string
}

/** Thrown when the API answers 422: the request is not complete enough to submit. */
export class SubmissionRejectedError extends Error {
  readonly problems: FieldProblem[]

  constructor(problems: FieldProblem[]) {
    super('The request is not complete')
    this.name = 'SubmissionRejectedError'
    this.problems = problems
  }
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

export async function listMyEventRequests(token: string): Promise<EventRequest[]> {
  const response = await fetch('/api/event-requests', { headers: authHeaders(token) })
  if (!response.ok) {
    throw new Error(`/api/event-requests responded ${response.status}`)
  }
  return (await response.json()) as EventRequest[]
}

export async function submitEventRequest(token: string, id: string): Promise<EventRequest> {
  const response = await fetch(`/api/event-requests/${id}/submit`, {
    method: 'POST',
    headers: authHeaders(token),
  })
  if (response.status === 422) {
    const body = (await response.json()) as { detail: FieldProblem[] }
    throw new SubmissionRejectedError(body.detail)
  }
  if (!response.ok) {
    throw new Error(`Submission failed (${response.status})`)
  }
  return (await response.json()) as EventRequest
}

/** Human-readable field names, in the order the ticket lists them. */
export const FIELD_LABELS: Record<string, string> = {
  name: 'Name',
  purpose: 'Purpose',
  description: 'Description',
  start_at: 'Start date and time',
  end_at: 'End date and time',
  expected_attendance: 'Expected attendance',
  venue_requirement: 'Venue requirement',
  accessibility_requirement: 'Accessibility requirement',
  equipment_requirement: 'Equipment requirement',
  layout_requirement: 'Layout requirement',
  registration_requirement: 'Registration requirement',
}
