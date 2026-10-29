import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { formatSingaporeTime } from '../api/venueCalendar'
import {
  approveVenueBookingRequest,
  describeConflict,
  holdHasExpired,
  listVenueBookingRequests,
  MAX_REASON_LENGTH,
  rejectVenueBookingRequest,
  singaporeLocalToUtc,
  STATUS_LABELS,
  type VenueBookingDecision,
  updateVenueHoldExpiry,
} from '../api/venueBookingDecisions'
import { useAuth } from '../auth/useAuth'

/** SCRUM-40: Venue Staff review pending booking requests and reject them.
 * SCRUM-75: they also see any clash and approve requests that have none.
 * SCRUM-110: approval creates a time-limited tentative hold, so it needs an expiry. */
export default function VenueBookingDecisions() {
  const { token } = useAuth()
  const client = useQueryClient()
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [holdUntil, setHoldUntil] = useState<Record<string, string>>({})
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
    mutationFn: ({ booking, until }: { booking: VenueBookingDecision; until: string }) =>
      approveVenueBookingRequest(token ?? '', booking.id, singaporeLocalToUtc(until)),
    // The approve response has no venue name, so it is read off the card that was clicked.
    onSuccess: (_held, { booking }) => {
      setOutcome(`The request for ${booking.venue_name} is on a tentative hold.`)
      void client.invalidateQueries({ queryKey })
    },
    // A refusal usually means the list was out of date: a closure or another approval
    // landed after it loaded. Reload it so the card can name the clash.
    onError: () => {
      void client.invalidateQueries({ queryKey })
    },
  })
  const updateExpiry = useMutation({
    mutationFn: ({ booking, until }: { booking: VenueBookingDecision; until: string }) =>
      updateVenueHoldExpiry(token ?? '', booking.id, singaporeLocalToUtc(until)),
    onSuccess: (_held, { booking }) => {
      setOutcome(`The hold expiry for ${booking.venue_name} was updated.`)
      setHoldUntil((values) => ({ ...values, [booking.id]: '' }))
      void client.invalidateQueries({ queryKey })
    },
    onError: () => {
      void client.invalidateQueries({ queryKey })
    },
  })
  const busy = reject.isPending || approve.isPending || updateExpiry.isPending
  const resetAll = () => {
    reject.reset()
    approve.reset()
    updateExpiry.reset()
  }
  const pending = requests.data?.filter((booking) => booking.status === 'pending') ?? []
  const held = requests.data?.filter((booking) => booking.status === 'tentative') ?? []
  const decided =
    requests.data?.filter(
      (booking) => booking.status !== 'pending' && booking.status !== 'tentative',
    ) ?? []

  return (
    <section id="venue-booking-decisions" className="mt-6 rounded-lg border border-slate-200 p-4">
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
                resetAll()
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
          {/* Once the reloaded card shows its clash, that line explains the refusal in
              Singapore time, so the raw API message (which only has an id) is not repeated. */}
          {/* SCRUM-110: approval creates a time-limited tentative hold, so the expiry
              is required before the request can be approved. */}
          <label className="mt-3 block text-sm font-medium" htmlFor={`hold-${booking.id}`}>
            Hold until (Singapore time)
          </label>
          <div className="mt-1 flex gap-2">
            <input
              id={`hold-${booking.id}`}
              type="datetime-local"
              value={holdUntil[booking.id] ?? ''}
              onChange={(event) => setHoldUntil({ ...holdUntil, [booking.id]: event.target.value })}
              className="rounded border border-slate-300 p-1.5 text-sm"
            />
            <button
              type="button"
              onClick={() => {
                resetAll()
                approve.mutate({ booking, until: holdUntil[booking.id] ?? '' })
              }}
              disabled={busy || booking.conflict !== null || !holdUntil[booking.id]}
              className="rounded bg-green-700 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              Approve
            </button>
          </div>
          {approve.isError &&
            approve.variables?.booking.id === booking.id &&
            booking.conflict === null && (
              <p role="alert" className="mt-2 text-sm text-red-600">
                Could not approve: {approve.error.message}
              </p>
            )}
        </article>
      ))}
      {held.length > 0 && (
        <>
          <h3 className="mt-6 text-sm font-medium">Tentative holds</h3>
          {held.map((booking) => (
            <article key={booking.id} className="mt-2 rounded border border-violet-200 p-3">
              <BookingDetails booking={booking} />
              <p className="mt-1 text-sm text-violet-900">
                {STATUS_LABELS.tentative}
                {booking.expires_at && ` until ${formatSingaporeTime(booking.expires_at)}`}
              </p>
              {/* SCRUM-110: a hold is terminal until it expires or is confirmed by the
                  SCRUM-80 flow, so there is no approval control here. */}
              {holdHasExpired(booking, new Date()) ? (
                <p className="mt-2 rounded bg-slate-100 p-2 text-sm text-slate-700">
                  This hold has expired.
                </p>
              ) : (
                <>
                  {booking.conflict && (
                    <p className="mt-2 rounded bg-amber-50 p-2 text-sm text-amber-800">
                      {describeConflict(booking.conflict)}
                    </p>
                  )}
                  <label className="mt-3 block text-sm font-medium" htmlFor={`hold-${booking.id}`}>
                    New expiry (Singapore time)
                  </label>
                  <div className="mt-1 flex gap-2">
                    <input
                      id={`hold-${booking.id}`}
                      type="datetime-local"
                      value={holdUntil[booking.id] ?? ''}
                      onChange={(event) =>
                        setHoldUntil({ ...holdUntil, [booking.id]: event.target.value })
                      }
                      className="rounded border border-slate-300 p-1.5 text-sm"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        resetAll()
                        updateExpiry.mutate({ booking, until: holdUntil[booking.id] ?? '' })
                      }}
                      disabled={busy || !holdUntil[booking.id]}
                      className="rounded bg-violet-700 px-3 py-1.5 text-sm text-white disabled:opacity-50"
                    >
                      Update expiry
                    </button>
                  </div>
                  {updateExpiry.isError && updateExpiry.variables?.booking.id === booking.id && (
                    <p role="alert" className="mt-2 text-sm text-red-600">
                      Could not update expiry: {updateExpiry.error.message}
                    </p>
                  )}
                </>
              )}
            </article>
          ))}
        </>
      )}
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
                {booking.status === 'expired' &&
                  booking.expires_at &&
                  ` at ${formatSingaporeTime(booking.expires_at)}`}
                {booking.decided_at && ` on ${formatSingaporeTime(booking.decided_at)}`}
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
  // SCRUM-82 AC3: the venue is held wider than the event runs, and a refusal quotes the
  // held period. Without this line the two do not add up on screen: a request at 9:14 pm
  // refused for clashing with a booking that ends at 8:00 pm reads as a bug.
  const held =
    booking.setup_minutes > 0 || booking.turnaround_minutes > 0
      ? `${formatSingaporeTime(booking.effective_start_at)} to ${formatSingaporeTime(
          booking.effective_end_at,
        )} (${booking.setup_minutes} min setup, ${booking.turnaround_minutes} min turnaround)`
      : null
  const rows: [string, string | number | null][] = [
    ['Venue', `${booking.venue_name}, ${booking.venue_location}`],
    ['Session', booking.session_label],
    [
      'When',
      `${formatSingaporeTime(booking.start_at)} to ${formatSingaporeTime(booking.end_at)}`,
    ],
    // Omitted rather than shown empty when the venue has no buffers: the row renders
    // "Not given" for a null, and there is nothing missing here (AC7).
    ...(held ? ([['Venue held', held]] as [string, string][]) : []),
    ['Attendance', booking.expected_attendance],
    ['Venue type', booking.venue_requirement],
    ['Accessibility', booking.accessibility_requirement],
    // Joined rather than listed: this is a definition list of short facts, and an
    // event needing three things is still one answer to "what does it need".
    // "None recorded" rather than the row's "Not given", which would read as missing
    // information when the Coordinator has genuinely recorded nothing.
    [
      'Equipment',
      booking.equipment_requirements.length > 0
        ? booking.equipment_requirements.join(', ')
        : 'None recorded',
    ],
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
