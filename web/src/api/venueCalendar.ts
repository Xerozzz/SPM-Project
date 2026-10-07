import type { EventRequest } from './eventRequests'

/**
 * SCRUM-54: the venue availability calendar. SCRUM-76: whether one venue is free.
 * SCRUM-77: one entry in full. Mirrors api/schemas/venue_calendar.py.
 */

export type CalendarStatus = 'confirmed' | 'pending' | 'unavailable'

export interface CalendarEntry {
  kind: 'booking' | 'unavailability'
  id: string
  venue_id: string
  venue_name: string
  start_at: string
  end_at: string
  status: CalendarStatus
  /**
   * SCRUM-82: the period the venue is actually held, the event widened by the venue's
   * setup and turnaround. Equal to the event period when the venue has no buffers, and
   * always for a closure.
   */
  effective_start_at: string
  effective_end_at: string
}

/** SCRUM-82: whether an entry holds the venue for longer than its own event period. */
export function hasBuffer(entry: CalendarEntry): boolean {
  return entry.effective_start_at !== entry.start_at || entry.effective_end_at !== entry.end_at
}

/** AC1: how each kind of entry is labelled so they can be told apart. */
export const CALENDAR_LABELS: Record<CalendarStatus, string> = {
  confirmed: 'Confirmed booking',
  pending: 'Pending request',
  unavailable: 'Unavailable',
}

/** SCRUM-77: an entry opened in full can be any booking, rejected and cancelled included. */
export type DetailsStatus = CalendarStatus | 'rejected' | 'cancelled'

export const DETAILS_LABELS: Record<DetailsStatus, string> = {
  ...CALENDAR_LABELS,
  rejected: 'Rejected request',
  cancelled: 'Cancelled request',
}

/** Days are Singapore days, the same assumption venue search makes. */
export function singaporeDayStart(date: string): string {
  return new Date(`${date}T00:00:00+08:00`).toISOString()
}

/** The instant after the last day: the range is [first day start, last day end). */
export function singaporeDayEnd(date: string): string {
  const start = new Date(`${date}T00:00:00+08:00`)
  return new Date(start.getTime() + 24 * 60 * 60 * 1000).toISOString()
}

/** A Singapore wall-clock time for display. */
export function formatSingaporeTime(value: string): string {
  return new Date(value).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })
}

/** SCRUM-76: the verdict for one venue and period, with the entries behind it. */
export interface VenueAvailability {
  venue_id: string
  start_at: string
  end_at: string
  available: boolean
  entries: CalendarEntry[]
}

async function readCalendarResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail =
      body && typeof body === 'object' && 'detail' in body && Array.isArray(body.detail)
        ? (body.detail as { field: string; reason: string }[])
            .map((problem) => `${problem.field} ${problem.reason}`)
            .join(', ')
        : `status ${response.status}`
    throw new Error(`Could not load the calendar (${detail})`)
  }
  return (await response.json()) as T
}

export async function getVenueCalendar(
  token: string,
  firstDay: string,
  lastDay: string,
  venueId: string | null,
): Promise<CalendarEntry[]> {
  const params = new URLSearchParams({
    start_at: singaporeDayStart(firstDay),
    end_at: singaporeDayEnd(lastDay),
  })
  if (venueId) params.set('venue_id', venueId)
  return readCalendarResponse(
    await fetch(`/api/venue-calendar?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    }),
  )
}

export async function getVenueAvailability(
  token: string,
  venueId: string,
  firstDay: string,
  lastDay: string,
): Promise<VenueAvailability> {
  const params = new URLSearchParams({
    venue_id: venueId,
    start_at: singaporeDayStart(firstDay),
    end_at: singaporeDayEnd(lastDay),
  })
  return readCalendarResponse(
    await fetch(`/api/venue-calendar/availability?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    }),
  )
}

/** SCRUM-77: one calendar entry in full. */
export interface CalendarEntryDetails {
  kind: 'booking' | 'unavailability'
  id: string
  venue_id: string
  venue_name: string
  venue_location: string
  start_at: string
  end_at: string
  status: DetailsStatus
  reason: string | null
  event_request_id: string | null
}

export async function getCalendarEntry(
  token: string,
  entry: Pick<CalendarEntry, 'kind' | 'id'>,
): Promise<CalendarEntryDetails> {
  const path = entry.kind === 'booking' ? 'bookings' : 'unavailabilities'
  return readCalendarResponse(
    await fetch(`/api/venue-calendar/${path}/${entry.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    }),
  )
}

/**
 * SCRUM-77 AC2 and AC3: the event behind a booking, or null when this user may not see
 * it. The event request endpoint decides that with require_event_access(VIEW).
 * Only a 403 means "no access". A missing event or a failed request throws, so it is
 * shown as an error rather than as a permission problem.
 */
export async function getEntryEvent(token: string, eventId: string): Promise<EventRequest | null> {
  const response = await fetch(`/api/event-requests/${eventId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (response.status === 403) return null
  if (response.status === 404) throw new Error('The event for this booking no longer exists.')
  if (!response.ok) throw new Error(`Could not load the event (status ${response.status}).`)
  return (await response.json()) as EventRequest
}
