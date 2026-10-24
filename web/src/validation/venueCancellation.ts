import type { EventRequest, VenueBooking } from '../api/eventRequests'

/**
 * SCRUM-109: whether to offer "Cancel arrangement" on a booking. A display rule only; the
 * API decides (ADR-0056). Offered to the event's assigned Coordinator while the event is
 * Approved, on a pending request, a confirmed booking, or a hold that has not yet reached
 * its expiry. A hold at its expiry counts as expired, as it does on the API.
 */
export function canOfferCancel(
  booking: VenueBooking,
  event: Pick<EventRequest, 'status' | 'coordinator_id'>,
  viewerId: string | null,
  now: Date = new Date(),
): boolean {
  if (event.status !== 'approved' || viewerId === null || event.coordinator_id !== viewerId) {
    return false
  }
  if (booking.status === 'pending' || booking.status === 'confirmed') return true
  if (booking.status !== 'tentative' || !booking.expires_at) return false
  return new Date(booking.expires_at).getTime() > now.getTime()
}

/** SCRUM-109 AC2: who cancelled, without showing another user's id. */
export function describeCanceller(
  cancelledById: string | null | undefined,
  viewerId: string | null,
) {
  return cancelledById && cancelledById === viewerId
    ? 'Cancelled by you'
    : 'Cancelled by another coordinator'
}
