/**
 * SCRUM-40: Venue Staff read booking requests and reject them.
 * SCRUM-75: they also see what would block approval, and approve.
 * Mirrors schemas/venue_booking_decisions.py on the API.
 */

export type BookingStatus = 'pending' | 'tentative' | 'confirmed' | 'rejected' | 'cancelled'

/** How each status is shown to Venue Staff. */
export const STATUS_LABELS: Record<BookingStatus, string> = {
  pending: 'Pending',
  tentative: 'Tentative hold',
  confirmed: 'Confirmed',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
}

/** SCRUM-75 AC1: what the SCRUM-73 check says would block approval. SCRUM-83: `hold`
 * when it is a tentative hold rather than a confirmed booking. */
export interface BookingConflict {
  kind: 'booking' | 'hold' | 'unavailability'
  id: string
  start_at: string
  end_at: string
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
  start_at: string
  end_at: string
  expected_attendance: number | null
  venue_requirement: string | null
  accessibility_requirement: string | null
  equipment_requirement: string | null
  layout_requirement: string | null
  requested_by_id: string
  decided_by_id: string | null
  decided_at: string | null
  decision_reason: string | null
  /** SCRUM-83: the hold, if Venue Staff placed one, and the Coordinator it is for. */
  expires_at?: string | null
  held_by_id?: string | null
  held_at?: string | null
  coordinator_id?: string | null
  conflict: BookingConflict | null
}

/** What Venue Staff are told about a clash, in plain words, in Singapore time. */
export function describeConflict(conflict: BookingConflict): string {
  const sgt = (value: string) =>
    new Date(value).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })
  const period = `${sgt(conflict.start_at)} to ${sgt(conflict.end_at)}`
  if (conflict.kind === 'booking') return `Clashes with a confirmed booking from ${period}.`
  if (conflict.kind === 'hold') return `Clashes with a tentative hold from ${period}.`
  return `The venue is closed from ${period}.`
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

/** SCRUM-75: approve through the SCRUM-74 route. The list is reloaded afterwards. */
export async function approveVenueBookingRequest(
  token: string,
  id: string,
): Promise<{ id: string; status: BookingStatus }> {
  return readDecisionResponse(
    await fetch(`/api/venue-bookings/${id}/approve`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    }),
  )
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
