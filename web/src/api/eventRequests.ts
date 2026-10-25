import type { BookingConflict } from './venueBookingDecisions'

/**
 * Event request API calls for organisers. Mirrors api/schemas/event_requests.py.
 */

export type EventStatus =
  'draft' | 'submitted' | 'approved' | 'rejected' | 'confirmed' | 'completed'

export type EventAction =
  'edit' | 'submit' | 'approve' | 'reject' | 'replan' | 'confirm' | 'complete'

export interface EventCalendarEntry {
  id: string
  name: string | null
  start_at: string
  end_at: string
  status: EventStatus
}

export async function listOrganisationCalendar(token: string): Promise<EventCalendarEntry[]> {
  const response = await fetch('/api/event-requests/organisation-calendar', {
    headers: authHeaders(token),
  })
  if (!response.ok) throw new Error(`Could not load organisation calendar (${response.status})`)
  return (await response.json()) as EventCalendarEntry[]
}

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
  /** SCRUM-80 AC6: when the assigned Coordinator confirmed it, if they have. */
  confirmed_at?: string | null
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

export type BookingStatus =
  'pending' | 'tentative' | 'confirmed' | 'rejected' | 'cancelled' | 'expired'

export interface VenueBookingSubmission {
  id: string
  venue_id: string
  /** SCRUM-111: which session of the event this request is for. */
  session_label: string
  start_at: string
  end_at: string
  status: BookingStatus
  suitability: VenueSuitability
}

export interface VenueBooking {
  id: string
  venue_id: string
  /** SCRUM-111: which session of the event this request is for. */
  session_label: string
  start_at: string
  end_at: string
  status: BookingStatus
  /**
   * SCRUM-82 AC3: the period the venue is actually held for, setup and turnaround
   * included. Null only for an API that predates this field.
   */
  effective_start_at?: string | null
  effective_end_at?: string | null
  /** SCRUM-83 AC2: when a tentative hold on this request ends. */
  expires_at?: string | null
  /** SCRUM-116 AC3: the affected arrangement this request replaces, if it is one. */
  replaces_booking_id?: string | null
  /** SCRUM-133: who adopted this replacement and when, if it has been adopted. */
  adopted_by_id?: string | null
  adopted_at?: string | null
  /** SCRUM-109 AC2: who cancelled this arrangement, when, and why. Null unless cancelled. */
  cancelled_by_id?: string | null
  cancelled_at?: string | null
  cancellation_reason?: string | null
  /**
   * SCRUM-89 AC4: what this booking now clashes with at its venue, or null when nothing.
   * Derived by the API on every read, so it appears and clears on its own as the venue's
   * setup and turnaround times change.
   */
  conflict: BookingConflict | null
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

export async function listEquipmentRequirementTypes(token: string): Promise<string[]> {
  const response = await fetch('/api/event-requests/equipment-types', {
    headers: authHeaders(token),
  })
  if (!response.ok) throw new Error(`Could not load equipment types (${response.status})`)
  return (await response.json()) as string[]
}

export async function listVenueRequirementNames(token: string): Promise<string[]> {
  const response = await fetch('/api/event-requests/venue-names', {
    headers: authHeaders(token),
  })
  if (!response.ok) throw new Error(`Could not load venue names (${response.status})`)
  return (await response.json()) as string[]
}

export async function listRequestsForReview(token: string): Promise<EventRequest[]> {
  const response = await fetch('/api/event-requests/reviewable', { headers: authHeaders(token) })
  if (!response.ok) throw new Error(`Could not load submitted requests (${response.status})`)
  return (await response.json()) as EventRequest[]
}

/** Confirmed events assigned to this Coordinator for read-only operational settings. */
export async function listConfirmedEventRequests(token: string): Promise<EventRequest[]> {
  const response = await fetch('/api/event-requests/assigned-confirmed', {
    headers: authHeaders(token),
  })
  if (!response.ok) throw new Error(`Could not load confirmed events (${response.status})`)
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
  organiser_email: string
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

/** SCRUM-100: one row of the Lead active-assignment overview (AC1 fields only).
 * SCRUM-97 adds `coordinator_id` — the current owner's id (None when unassigned) —
 * so the UI can send it back as `expected_current_coordinator_id` (ADR-0021). */
export interface ActiveAssignment {
  id: string
  name: string | null
  status: EventStatus
  organiser_email: string
  start_at: string | null
  end_at: string | null
  coordinator_id: string | null
  coordinator_email: string | null
}

export async function listActiveAssignments(token: string): Promise<ActiveAssignment[]> {
  const response = await fetch('/api/event-requests/active-assignments', {
    headers: authHeaders(token),
  })
  if (!response.ok) throw new Error(`Could not load assignments (${response.status})`)
  return (await response.json()) as ActiveAssignment[]
}

/** SCRUM-98: one eligible owner the Lead may pick — active Event Coordinators only. */
export interface AssignableCoordinator {
  id: string
  email: string
}

export async function listAssignableCoordinators(token: string): Promise<AssignableCoordinator[]> {
  const response = await fetch('/api/event-requests/assignable-coordinators', {
    headers: authHeaders(token),
  })
  if (!response.ok) throw new Error(`Could not load coordinators (${response.status})`)
  return (await response.json()) as AssignableCoordinator[]
}

/** SCRUM-98: a Lead assigns an unassigned Submitted request to an active coordinator. */
export async function assignEventRequest(
  token: string,
  id: string,
  coordinatorId: string,
): Promise<EventRequest> {
  const response = await fetch(`/api/event-requests/${id}/assign`, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify({ coordinator_id: coordinatorId }),
  })
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: unknown) =>
        body && typeof body === 'object' && 'detail' in body
          ? String((body as { detail: unknown }).detail)
          : `Assignment failed (${response.status})`,
      )
      .catch(() => `Assignment failed (${response.status})`)
    throw new Error(detail)
  }
  return (await response.json()) as EventRequest
}

/** SCRUM-97: one immutable assignment entry, oldest first. */
export interface AssignmentHistoryEntry {
  id: string
  previous_coordinator_id: string | null
  /** SCRUM-105: null when there is no previous coordinator or their user row is missing. */
  previous_coordinator_email: string | null
  new_coordinator_id: string
  new_coordinator_email: string | null
  acted_by_id: string
  acted_by_email: string | null
  assigned_at: string
}

export async function listAssignmentHistory(
  token: string,
  id: string,
): Promise<AssignmentHistoryEntry[]> {
  const response = await fetch(`/api/event-requests/${id}/assignment-history`, {
    headers: authHeaders(token),
  })
  if (!response.ok) throw new Error(`Could not load assignment history (${response.status})`)
  return (await response.json()) as AssignmentHistoryEntry[]
}

/** SCRUM-97: a Lead moves an active assigned request to another active coordinator. */
export async function reassignEventRequest(
  token: string,
  id: string,
  coordinatorId: string,
  expectedCurrentCoordinatorId: string,
): Promise<EventRequest> {
  const response = await fetch(`/api/event-requests/${id}/reassign`, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify({
      coordinator_id: coordinatorId,
      expected_current_coordinator_id: expectedCurrentCoordinatorId,
    }),
  })
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: unknown) =>
        body && typeof body === 'object' && 'detail' in body
          ? String((body as { detail: unknown }).detail)
          : `Reassignment failed (${response.status})`,
      )
      .catch(() => `Reassignment failed (${response.status})`)
    throw new Error(detail)
  }
  return (await response.json()) as EventRequest
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

/**
 * SCRUM-36: the assigned coordinator updates ordinary planning information. Sends only
 * the changed fields. A 422 carries the field problems, and anything else gives the API's
 * message when it has one.
 */
export async function updatePlanningInfo(
  token: string,
  id: string,
  changes: Partial<
    Pick<
      EventRequest,
      | 'name'
      | 'purpose'
      | 'description'
      | 'accessibility_requirement'
      | 'layout_requirement'
      | 'registration_requirement'
    >
  >,
): Promise<EventRequest> {
  const response = await fetch(`/api/event-requests/${id}/planning-info`, {
    method: 'PATCH',
    headers: jsonHeaders(token),
    body: JSON.stringify(changes),
  })
  const body = (await response.json().catch(() => null)) as unknown
  if (response.status === 422) {
    const problems = parseValidationProblems(body)
    if (problems) throw new EventRequestValidationError(problems)
  }
  if (!response.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string'
        ? body.detail
        : `Update failed (${response.status})`
    throw new Error(detail)
  }
  return body as EventRequest
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
  session: {
    session_label: string
    start_at: string
    end_at: string
    /** SCRUM-116: set when this request replaces an affected arrangement. */
    replaces_booking_id?: string
  },
): Promise<VenueBookingSubmission> {
  return readBookingResponse(
    await fetch(`/api/event-requests/${eventId}/venue-bookings`, {
      method: 'POST',
      headers: jsonHeaders(token),
      body: JSON.stringify({ venue_id: venueId, ...session }),
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

/** SCRUM-109: the assigned Coordinator cancels one arrangement, with a reason. */
export async function cancelVenueArrangement(
  token: string,
  eventId: string,
  bookingId: string,
  reason: string,
): Promise<VenueBooking> {
  return readBookingResponse(
    await fetch(`/api/event-requests/${eventId}/venue-bookings/${bookingId}/cancel`, {
      method: 'POST',
      headers: jsonHeaders(token),
      body: JSON.stringify({ reason }),
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
