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
  return offeredWhile('approved', event, viewerId) && isCancellable(booking, now)
}

/**
 * SCRUM-118: the same offer on a Confirmed event, where cancelling an arrangement is a
 * venue change that returns the event to planning (ADR-0066). The booking rule is SCRUM-109's.
 */
export function canOfferVenueChange(
  booking: VenueBooking,
  event: Pick<EventRequest, 'status' | 'coordinator_id'>,
  viewerId: string | null,
  now: Date = new Date(),
): boolean {
  return offeredWhile('confirmed', event, viewerId) && isCancellable(booking, now)
}

function offeredWhile(
  status: EventRequest['status'],
  event: Pick<EventRequest, 'status' | 'coordinator_id'>,
  viewerId: string | null,
) {
  return event.status === status && viewerId !== null && event.coordinator_id === viewerId
}

function isCancellable(booking: VenueBooking, now: Date) {
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
