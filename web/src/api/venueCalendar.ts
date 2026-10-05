/**
 * SCRUM-54: the venue availability calendar. Mirrors api/schemas/venue_calendar.py.
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
}

/** AC1: how each kind of entry is labelled so they can be told apart. */
export const CALENDAR_LABELS: Record<CalendarStatus, string> = {
  confirmed: 'Confirmed booking',
  pending: 'Pending request',
  unavailable: 'Unavailable',
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
  const response = await fetch(`/api/venue-calendar?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
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
  return (await response.json()) as CalendarEntry[]
}
