import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  approveVenueBookingRequest,
  describeConflict,
  listVenueBookingRequests,
  MAX_REASON_LENGTH,
  rejectVenueBookingRequest,
  STATUS_LABELS,
  type VenueBookingDecision,
} from '../api/venueBookingDecisions'
import { useAuth } from '../auth/useAuth'

/** SCRUM-40: Venue Staff review pending booking requests and reject them.
 * SCRUM-75: they also see any clash and approve requests that have none. */
export default function VenueBookingDecisions() {
  const { token } = useAuth()
  const client = useQueryClient()
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [outcome, setOutcome] = useState<string | null>(null)
  const queryKey = ['venue-bookings', token]
  const requests = useQuery({
    queryKey,
    queryFn: () => listVenueBookingRequests(token ?? ''),
    enabled: token !== null,
  })
  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      rejectVenueBookingRequest(token ?? '', id, reason),
    onSuccess: (booking) => {
      setOutcome(`The request for ${booking.venue_name} has been rejected.`)
      void client.invalidateQueries({ queryKey })
    },
  })
  const approve = useMutation({
    mutationFn: (id: string) => approveVenueBookingRequest(token ?? '', id),
    onSuccess: () => {
      setOutcome('The request has been approved.')
      void client.invalidateQueries({ queryKey })
    },
  })
  const busy = reject.isPending || approve.isPending
  const pending = requests.data?.filter((booking) => booking.status === 'pending') ?? []
  const decided = requests.data?.filter((booking) => booking.status !== 'pending') ?? []

  return (
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Venue booking requests</h2>
      {requests.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {requests.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          Could not load booking requests: {requests.error.message}
        </p>
      )}
      {requests.isSuccess && pending.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No booking requests are waiting.</p>
      )}
      {pending.map((booking) => (
        <article key={booking.id} className="mt-4 rounded border border-slate-200 p-3">
          <BookingDetails booking={booking} />
          {booking.conflict && (
            <p className="mt-2 rounded bg-amber-50 p-2 text-sm text-amber-800">
              {describeConflict(booking.conflict)} It cannot be approved.
            </p>
          )}
          <label className="mt-3 block text-sm font-medium" htmlFor={`reason-${booking.id}`}>
            Reason for the Coordinator (optional)
          </label>
          <textarea
            id={`reason-${booking.id}`}
            maxLength={MAX_REASON_LENGTH}
            value={reasons[booking.id] ?? ''}
            onChange={(event) => setReasons({ ...reasons, [booking.id]: event.target.value })}
            className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
          />
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => {
                reject.reset()
                approve.mutate(booking.id)
              }}
              disabled={busy || booking.conflict !== null}
              className="rounded bg-green-700 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              Approve
            </button>
            <button
              type="button"
              onClick={() => {
                approve.reset()
                reject.mutate({ id: booking.id, reason: reasons[booking.id] ?? '' })
              }}
              disabled={busy}
              className="rounded bg-red-700 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              Reject
            </button>
          </div>
          {reject.isError && reject.variables?.id === booking.id && (
            <p role="alert" className="mt-2 text-sm text-red-600">
              {reject.error.message}
            </p>
          )}
          {approve.isError && approve.variables === booking.id && (
            <p role="alert" className="mt-2 text-sm text-red-600">
              Could not approve: {approve.error.message}
            </p>
          )}
        </article>
      ))}
      {outcome && (
        <p role="status" className="mt-4 rounded bg-green-50 p-3 text-sm text-green-800">
          {outcome}
        </p>
      )}
      {decided.length > 0 && (
        <>
          <h3 className="mt-6 text-sm font-medium">Decided</h3>
          {decided.map((booking) => (
            <article key={booking.id} className="mt-2 rounded border border-slate-100 p-3">
              <BookingDetails booking={booking} />
              <p className="mt-1 text-sm">
                {STATUS_LABELS[booking.status]}
                {booking.decided_at && ` on ${new Date(booking.decided_at).toLocaleString()}`}
                {booking.decision_reason && `: ${booking.decision_reason}`}
              </p>
            </article>
          ))}
        </>
      )}
    </section>
  )
}

function BookingDetails({ booking }: { booking: VenueBookingDecision }) {
  const rows: [string, string | number | null][] = [
    ['Venue', `${booking.venue_name}, ${booking.venue_location}`],
    [
      'When',
      `${new Date(booking.start_at).toLocaleString()} to ${new Date(booking.end_at).toLocaleString()}`,
    ],
    ['Attendance', booking.expected_attendance],
    ['Venue type', booking.venue_requirement],
    ['Accessibility', booking.accessibility_requirement],
    ['Equipment', booking.equipment_requirement],
    ['Layout', booking.layout_requirement],
  ]
  return (
    <>
      <h3 className="font-medium">{booking.event_name ?? 'Untitled event'}</h3>
      <dl className="mt-2 text-sm text-slate-600">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="inline font-medium">{label}: </dt>
            <dd className="inline">{value ?? 'Not given'}</dd>
          </div>
        ))}
      </dl>
    </>
  )
}
