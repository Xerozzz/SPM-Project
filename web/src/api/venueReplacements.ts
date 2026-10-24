/** SCRUM-133: the assigned Coordinator adopts an approved replacement venue request. */
import type { VenueBooking } from './eventRequests'

export async function adoptReplacement(
  token: string,
  eventId: string,
  replacementId: string,
): Promise<VenueBooking> {
  const response = await fetch(
    `/api/event-requests/${eventId}/venue-bookings/${replacementId}/adopt`,
    { method: 'POST', headers: { Authorization: `Bearer ${token}` } },
  )
  const body = (await response.json().catch(() => null)) as unknown
  if (!response.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string'
        ? body.detail
        : `The replacement could not be adopted (${response.status})`
    throw new Error(detail)
  }
  return body as VenueBooking
}
