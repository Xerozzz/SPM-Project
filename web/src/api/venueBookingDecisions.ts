/**
 * SCRUM-40: Venue Staff read booking requests and reject them.
 * SCRUM-75: they also see what would block approval, and approve.
 * Mirrors schemas/venue_booking_decisions.py on the API.
 */

import { formatSingaporeTime } from './venueCalendar'

export type BookingStatus =
  'pending' | 'tentative' | 'confirmed' | 'rejected' | 'cancelled' | 'expired'

/** How each status is shown to Venue Staff. */
export const STATUS_LABELS: Record<BookingStatus, string> = {
  pending: 'Pending',
  tentative: 'Tentative hold',
  confirmed: 'Confirmed',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
  // SCRUM-108: a hold that ran out before it was approved.
  expired: 'Expired hold',
}

/** SCRUM-75 AC1: what the SCRUM-73 check says would block approval. SCRUM-83: `hold`
 * when it is a tentative hold rather than a confirmed booking. */
export interface BookingConflict {
  kind: 'booking' | 'hold' | 'unavailability'
  id: string
  start_at: string
  end_at: string
  /**
   * SCRUM-82: the period the venue is actually held for. Same as the event period for a
   * closure, which is not widened, and for a venue with no buffers.
   */
  effective_start_at: string
  effective_end_at: string
  message: string
}

export interface VenueBookingDecision {
  id: string
  status: BookingStatus
  venue_id: string
  venue_name: string
  venue_location: string
  event_request_id: string
  event_name: string | null
  /** SCRUM-111: which session of the event this request is for. */
  session_label: string
  start_at: string
  end_at: string
  expected_attendance: number | null
  venue_requirement: string | null
  accessibility_requirement: string | null
  /**
   * SCRUM-43: what the event needs now, from the records the Coordinator maintains,
   * each as "Projector x2". Not the organiser's single captured string, which nothing
   * writes back to and which goes stale the moment a requirement changes (ADR-0033).
   */
  equipment_requirements: string[]
  layout_requirement: string | null
  requested_by_id: string
  decided_by_id: string | null
  decided_at: string | null
  decision_reason: string | null
  /** SCRUM-82 AC3: this request's own held period, and the buffers behind it. */
  effective_start_at: string
  effective_end_at: string
  setup_minutes: number
  turnaround_minutes: number
  /** SCRUM-83: the hold, if Venue Staff placed one, and the Coordinator it is for. */
  expires_at?: string | null
  held_by_id?: string | null
  held_at?: string | null
  coordinator_id?: string | null
  conflict: BookingConflict | null
}

/**
 * What Venue Staff are told about a clash, in plain words, in Singapore time.
 *
 * The held period leads, not the event period. SCRUM-82 compares the periods the venue
 * is occupied for, so quoting the event period alone made refusals read as nonsense: a
 * request at 9:14 pm was reported as clashing with a booking from 6 pm to 8 pm, which
 * looks like no clash at all until the 45 minutes of turnaround are visible.
 */
export function describeConflict(conflict: BookingConflict): string {
  const held = `${formatSingaporeTime(conflict.effective_start_at)} to ${formatSingaporeTime(
    conflict.effective_end_at,
  )}`
  if (conflict.kind === 'unavailability') return `The venue is closed from ${held}.`
  const what = conflict.kind === 'hold' ? 'a tentative hold' : 'a confirmed booking'
  const event = `${formatSingaporeTime(conflict.start_at)} to ${formatSingaporeTime(conflict.end_at)}`
  // Only worth spelling out when the two differ. With no buffers they are the same and
  // the second clause would just repeat the first (AC7).
  if (held === event) return `Clashes with ${what} from ${event}.`
  return `Clashes with ${what} holding the venue ${held} (event ${event}, plus setup and turnaround).`
}

/** Longest reason the API accepts (MAX_REASON_LENGTH in domain/venue_booking_decision.py). */
export const MAX_REASON_LENGTH = 1000

async function readDecisionResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail =
      body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string'
        ? body.detail
        : `Request failed (${response.status})`
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export async function listVenueBookingRequests(token: string): Promise<VenueBookingDecision[]> {
  return readDecisionResponse(
    await fetch('/api/venue-bookings', { headers: { Authorization: `Bearer ${token}` } }),
  )
}

export async function rejectVenueBookingRequest(
  token: string,
  id: string,
  reason: string,
): Promise<VenueBookingDecision> {
  return readDecisionResponse(
    await fetch(`/api/venue-bookings/${id}/reject`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(reason.trim() ? { reason } : {}),
    }),
  )
}

/** SCRUM-110: approval creates a time-limited tentative hold, so it takes the same
 * expiry the hold route takes. The list is reloaded afterwards. */
export async function approveVenueBookingRequest(
  token: string,
  id: string,
  expiresAt: string,
): Promise<VenueBookingDecision> {
  const response = await fetch(`/api/venue-bookings/${id}/approve`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ expires_at: expiresAt }),
  })
  if (response.status === 422) {
    const body: unknown = await response.json().catch(() => null)
    if (body && typeof body === 'object' && 'detail' in body && Array.isArray(body.detail)) {
      const reasons = body.detail.flatMap((problem: unknown) =>
        problem && typeof problem === 'object' && 'reason' in problem
          ? [`Expiry ${String(problem.reason)}`]
          : [],
      )
      if (reasons.length > 0) throw new Error(reasons.join(', '))
    }
  }
  return readDecisionResponse(response)
}

/**
 * SCRUM-83: a `datetime-local` value read as Singapore wall-clock time, the same
 * assumption the calendar makes, sent to the API as a UTC instant.
 */
export function singaporeLocalToUtc(value: string): string {
  return new Date(`${value}:00+08:00`).toISOString()
}

/** SCRUM-83 AC1: put a pending request on a tentative hold until `expiresAt` (UTC). */
export async function holdVenueBookingRequest(
  token: string,
  id: string,
  expiresAt: string,
): Promise<VenueBookingDecision> {
  const response = await fetch(`/api/venue-bookings/${id}/hold`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ expires_at: expiresAt }),
  })
  if (response.status === 422) {
    const body: unknown = await response.json().catch(() => null)
    if (body && typeof body === 'object' && 'detail' in body && Array.isArray(body.detail)) {
      const reasons = body.detail.flatMap((problem: unknown) =>
        problem && typeof problem === 'object' && 'reason' in problem
          ? [`Expiry ${String(problem.reason)}`]
          : [],
      )
      if (reasons.length > 0) throw new Error(reasons.join(', '))
    }
  }
  return readDecisionResponse(response)
}

/** SCRUM-107: a hold whose expiry has passed can no longer be approved (the API refuses it). */
export function holdHasExpired(booking: VenueBookingDecision, now: Date): boolean {
  return booking.expires_at != null && new Date(booking.expires_at).getTime() <= now.getTime()
}
