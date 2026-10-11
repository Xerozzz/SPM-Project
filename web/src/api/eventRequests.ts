/**
 * Event request API calls for organisers. Mirrors api/schemas/event_requests.py.
 */

export type EventStatus = 'draft' | 'submitted' | 'approved' | 'rejected' | 'confirmed'

export type EventAction = 'edit' | 'submit' | 'approve' | 'reject'

export const VENUE_REQUIREMENTS = [
  'Auditorium-type venue',
  'Lecture theatre-type venue',
  'Seminar room-type venue',
  'Outdoor event space',
] as const

export const EQUIPMENT_REQUIREMENTS = [
  'Projector-type requirement',
  'Microphone-type requirement',
  'PA system-type requirement',
  'Display screen-type requirement',
] as const

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
  /** What the status allows, regardless of who is asking (SCRUM-35). Not an authorisation. */
  status_permits: EventAction[]
  /** The assigned coordinator (SCRUM-34). Compare with the viewer's id for "may I decide?". */
  coordinator_id: string | null
  decided_by_id: string | null
  decided_at: string | null
  rejection_reason: string | null
}

/** The fields required to create an event request (SCRUM-28). */
export interface EventRequestCreate {
  name: string
  purpose: string
  description: string
  start_at: string
  end_at: string
  expected_attendance: number
  venue_requirement: string
  accessibility_requirement: string
  equipment_requirement: string
  layout_requirement: string
  registration_requirement: string
}
export type EventRequestDraftInput = Partial<
  Pick<
    EventRequest,
    | 'name'
    | 'purpose'
    | 'description'
    | 'start_at'
    | 'end_at'
    | 'expected_attendance'
    | 'venue_requirement'
    | 'accessibility_requirement'
    | 'equipment_requirement'
    | 'layout_requirement'
    | 'registration_requirement'
  >
>

/** One field the organiser has to fix before submission is accepted (AC2). */
export interface FieldProblem {
  field: string
  reason: string
}

export interface VenueSuitability {
  mismatch_codes: string[]
  expected_attendance: number
  venue_capacity: number
  unavailable_facilities: string[]
  accessibility_need: string | null
  venue_accessibility: string[]
  layout_need: string | null
  venue_layouts: string[]
}

export type BookingStatus = 'pending' | 'confirmed' | 'rejected' | 'cancelled'

export interface VenueBookingSubmission {
  id: string
  venue_id: string
  start_at: string
  end_at: string
  status: BookingStatus
  suitability: VenueSuitability
}

export interface VenueBooking {
  id: string
  venue_id: string
  start_at: string
  end_at: string
  status: BookingStatus
}

/** Thrown when the API answers 422 with field-level validation problems. */
export class EventRequestValidationError extends Error {
  readonly problems: FieldProblem[]

  constructor(problems: FieldProblem[]) {
    super('The request has validation errors')
    this.name = 'EventRequestValidationError'
    this.problems = problems
  }
}

/** Kept distinct for the submit UI, which gives incomplete drafts a specific message. */
export class SubmissionRejectedError extends EventRequestValidationError {
  constructor(problems: FieldProblem[]) {
    super(problems)
    this.name = 'SubmissionRejectedError'
  }
}

function parseValidationProblems(body: unknown): FieldProblem[] | null {
  if (!body || typeof body !== 'object' || !('detail' in body) || !Array.isArray(body.detail)) {
    return null
  }

  const problems = body.detail.flatMap((problem: unknown): FieldProblem[] => {
    if (
      problem &&
      typeof problem === 'object' &&
      'field' in problem &&
      'reason' in problem &&
      typeof problem.field === 'string' &&
      typeof problem.reason === 'string'
    ) {
      return [{ field: problem.field, reason: problem.reason }]
    }
    if (
      problem &&
      typeof problem === 'object' &&
      'loc' in problem &&
      Array.isArray(problem.loc) &&
      typeof problem.loc.at(-1) === 'string' &&
      'msg' in problem &&
      typeof problem.msg === 'string'
    ) {
      return [{ field: problem.loc.at(-1) as string, reason: problem.msg }]
    }
    return []
  })

  return problems.length > 0 ? problems : null
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

function jsonHeaders(token: string): HeadersInit {
  return { ...authHeaders(token), 'Content-Type': 'application/json' }
}

export async function listMyEventRequests(token: string): Promise<EventRequest[]> {
  const response = await fetch('/api/event-requests', { headers: authHeaders(token) })
  if (!response.ok) {
    throw new Error(`/api/event-requests responded ${response.status}`)
  }
  return (await response.json()) as EventRequest[]
}

export async function listRequestsForReview(token: string): Promise<EventRequest[]> {
  const response = await fetch('/api/event-requests/reviewable', { headers: authHeaders(token) })
  if (!response.ok) throw new Error(`Could not load submitted requests (${response.status})`)
  return (await response.json()) as EventRequest[]
}

export async function listBookableEventRequests(token: string): Promise<EventRequest[]> {
  const response = await fetch('/api/event-requests/bookable', { headers: authHeaders(token) })
  if (!response.ok) throw new Error(`Could not load bookable requests (${response.status})`)
  return (await response.json()) as EventRequest[]
}

/** SCRUM-101: one row of the Coordinator Lead unassigned queue (AC2 fields only). */
export interface UnassignedEventRequest {
  id: string
  name: string | null
  organiser_id: string
  start_at: string | null
  end_at: string | null
  expected_attendance: number | null
  submitted_at: string | null
}

export async function listUnassignedEventRequests(
  token: string,
): Promise<UnassignedEventRequest[]> {
  const response = await fetch('/api/event-requests/unassigned', {
    headers: authHeaders(token),
  })
  if (!response.ok) throw new Error(`Could not load unassigned requests (${response.status})`)
  return (await response.json()) as UnassignedEventRequest[]
}

export async function createEventRequest(
  token: string,
  request: EventRequestCreate,
): Promise<EventRequest> {
  const response = await fetch('/api/event-requests', {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify(request),
  })
  if (response.status === 422) {
    const problems = parseValidationProblems(await response.json())
    if (problems) throw new EventRequestValidationError(problems)
  }
  if (!response.ok) {
    throw new Error(`Could not create event request (${response.status})`)
  }
  return (await response.json()) as EventRequest
}

export async function listDraftEventRequests(token: string): Promise<EventRequest[]> {
  const response = await fetch('/api/event-requests/drafts', { headers: authHeaders(token) })
  if (!response.ok) {
    throw new Error(`/api/event-requests/drafts responded ${response.status}`)
  }
  return (await response.json()) as EventRequest[]
}

export async function getEventRequest(token: string, id: string): Promise<EventRequest> {
  const response = await fetch(`/api/event-requests/${id}`, { headers: authHeaders(token) })
  if (!response.ok) {
    throw new Error(`Could not load event request (${response.status})`)
  }
  return (await response.json()) as EventRequest
}

export async function createDraft(
  token: string,
  draft: EventRequestDraftInput,
): Promise<EventRequest> {
  const response = await fetch('/api/event-requests/drafts', {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify(draft),
  })
  if (!response.ok) {
    throw new Error(`Draft save failed (${response.status})`)
  }
  return (await response.json()) as EventRequest
}

export async function updateDraft(
  token: string,
  id: string,
  draft: EventRequestDraftInput,
): Promise<EventRequest> {
  const response = await fetch(`/api/event-requests/${id}`, {
    method: 'PATCH',
    headers: jsonHeaders(token),
    body: JSON.stringify(draft),
  })
  if (!response.ok) {
    throw new Error(`Draft save failed (${response.status})`)
  }
  return (await response.json()) as EventRequest
}

export async function submitEventRequest(token: string, id: string): Promise<EventRequest> {
  const response = await fetch(`/api/event-requests/${id}/submit`, {
    method: 'POST',
    headers: authHeaders(token),
  })
  if (response.status === 422) {
    const problems = parseValidationProblems(await response.json())
    if (problems) throw new SubmissionRejectedError(problems)
  }
  if (!response.ok) {
    throw new Error(`Submission failed (${response.status})`)
  }
  return (await response.json()) as EventRequest
}

export async function approveEventRequest(token: string, id: string): Promise<EventRequest> {
  const response = await fetch(`/api/event-requests/${id}/approve`, {
    method: 'POST',
    headers: authHeaders(token),
  })
  if (!response.ok) throw new Error(`Approval failed (${response.status})`)
  return (await response.json()) as EventRequest
}

export async function rejectEventRequest(
  token: string,
  id: string,
  reason: string,
): Promise<EventRequest> {
  const response = await fetch(`/api/event-requests/${id}/reject`, {
    method: 'POST',
    headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
  if (!response.ok) throw new Error(`Rejection failed (${response.status})`)
  return (await response.json()) as EventRequest
}

async function readBookingResponse<T>(response: Response): Promise<T> {
  const body = (await response.json().catch(() => null)) as unknown
  if (response.status === 422) {
    const problems = parseValidationProblems(body)
    if (problems) throw new EventRequestValidationError(problems)
  }
  if (!response.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string'
        ? body.detail
        : `Booking request failed (${response.status})`
    throw new Error(detail)
  }
  return body as T
}

export async function getVenueSuitability(
  token: string,
  eventId: string,
  venueId: string,
): Promise<VenueSuitability> {
  const query = new URLSearchParams({ venue_id: venueId })
  return readBookingResponse(
    await fetch(`/api/event-requests/${eventId}/venue-bookings/suitability?${query}`, {
      headers: authHeaders(token),
    }),
  )
}

export async function submitVenueBooking(
  token: string,
  eventId: string,
  venueId: string,
): Promise<VenueBookingSubmission> {
  return readBookingResponse(
    await fetch(`/api/event-requests/${eventId}/venue-bookings`, {
      method: 'POST',
      headers: jsonHeaders(token),
      body: JSON.stringify({ venue_id: venueId }),
    }),
  )
}

export async function listVenueBookings(token: string, eventId: string): Promise<VenueBooking[]> {
  return readBookingResponse(
    await fetch(`/api/event-requests/${eventId}/venue-bookings`, {
      headers: authHeaders(token),
    }),
  )
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
