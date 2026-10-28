import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { listVenueArrangements, type EventRequest } from '../api/eventRequests'
import { formatSingaporeTime } from '../api/venueCalendar'
import { listVenues } from '../api/venues'
import { useAuth } from '../auth/useAuth'
import { canOfferVenueChange } from '../validation/venueCancellation'
import CancelArrangementDialog from './CancelArrangementDialog'

/**
 * SCRUM-118: a Confirmed event's arrangements, each cancellable by the assigned
 * Coordinator as a venue change. Cancelling one returns the event to planning (ADR-0066),
 * so the parent is told and refreshes: the event leaves the confirmed list and comes back
 * as Approved, where SCRUM-109's list shows the cancelled arrangement.
 */
export default function VenueArrangements({
  event,
  onVenueChanged,
}: {
  event: EventRequest
  onVenueChanged: (message: string) => void
}) {
  const { token, userId } = useAuth()
  const [cancelling, setCancelling] = useState<string | null>(null)
  const arrangements = useQuery({
    queryKey: ['venue-arrangements', event.id],
    queryFn: () => listVenueArrangements(token ?? '', event.id),
    enabled: token !== null,
  })
  const venues = useQuery({
    queryKey: ['venues'],
    queryFn: () => listVenues(token ?? ''),
    enabled: token !== null && arrangements.isSuccess,
  })
  const venueNames = new Map((venues.data ?? []).map((venue) => [venue.id, venue.name]))

  return (
    <section className="mt-4 rounded border border-slate-200 p-3 text-sm">
      <h3 className="font-medium">Arrangements</h3>
      {arrangements.isPending && <p className="mt-2">Loading…</p>}
      {arrangements.isError && (
        <p role="alert" className="mt-2 text-red-600">
          Could not load arrangements: {arrangements.error.message}
        </p>
      )}
      {arrangements.data?.length === 0 && (
        <p className="mt-2 text-slate-500">This event has no venue arrangements.</p>
      )}
      <ul className="mt-2 space-y-2 text-slate-600">
        {arrangements.data?.map((booking) => {
          const venueName = venueNames.get(booking.venue_id) ?? 'the selected venue'
          return (
            <li key={booking.id} className="rounded border border-slate-200 p-2">
              <p>
                <span className="font-medium">{booking.session_label}</span> at {venueName},{' '}
                {formatSingaporeTime(booking.start_at)} to {formatSingaporeTime(booking.end_at)}
              </p>
              <p>Status: {booking.status}</p>
              {canOfferVenueChange(booking, event, userId) && cancelling !== booking.id && (
                <button
                  type="button"
                  onClick={() => setCancelling(booking.id)}
                  aria-label={`Cancel arrangement for ${booking.session_label}`}
                  className="mt-2 block rounded border border-red-300 px-2 py-1 text-red-800"
                >
                  Cancel arrangement
                </button>
              )}
              {cancelling === booking.id && (
                <CancelArrangementDialog
                  eventId={event.id}
                  booking={booking}
                  venueName={venueName}
                  onClose={() => setCancelling(null)}
                  onVenueChanged={() =>
                    onVenueChanged(
                      `“${event.name}” is back in planning. ${booking.session_label} at ${venueName} is cancelled.`,
                    )
                  }
                />
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
