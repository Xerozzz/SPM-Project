import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

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

type BookingTab = 'pending' | 'held' | 'decided'

/** SCRUM-40: Venue Staff review pending booking requests and reject them.
 * SCRUM-75: they also see any clash and approve requests that have none.
 * SCRUM-110: approval creates a time-limited tentative hold, so it needs an expiry. */
export default function VenueBookingDecisions() {
  const { token } = useAuth()
  const client = useQueryClient()
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [holdUntil, setHoldUntil] = useState<Record<string, string>>({})
  const [outcome, setOutcome] = useState<string | null>(null)
  const [selectedTab, setSelectedTab] = useState<BookingTab>('pending')
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
  const tabGroups = [
    { id: 'pending' as const, label: 'Pending review', bookings: pending },
    { id: 'held' as const, label: 'Tentative holds', bookings: held },
    { id: 'decided' as const, label: 'Decided', bookings: decided },
  ]
  const populatedTabs = tabGroups.filter((group) => group.bookings.length > 0)

  // Keep the current view useful after a decision moves its card to another status.
  useEffect(() => {
    if (populatedTabs.length && !populatedTabs.some((group) => group.id === selectedTab)) {
      setSelectedTab(populatedTabs[0].id)
    }
  }, [populatedTabs, selectedTab])

  return (
    <section className="mt-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4">
        <div>
          <h2 className="font-medium">Venue booking requests</h2>
          <p className="mt-1 text-sm text-slate-500">
            Review each request, record a reason when needed, and set a hold before approval.
          </p>
        </div>
        {pending.length > 0 && (
          <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-sm font-medium text-amber-800">
            {pending.length} awaiting review
          </span>
        )}
      </div>
      {requests.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {requests.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          Could not load booking requests: {requests.error.message}
        </p>
      )}
      {requests.isSuccess && (
        <div
          role="tablist"
          aria-label="Booking request status"
          className="mt-5 flex gap-2 overflow-x-auto border-b border-slate-200 pb-3"
        >
          {tabGroups.map((group) => (
            <button
              key={group.id}
              type="button"
              role="tab"
              aria-selected={selectedTab === group.id}
              onClick={() => setSelectedTab(group.id)}
              className={`shrink-0 rounded-lg px-4 py-2 text-sm font-medium ${
                selectedTab === group.id
                  ? 'bg-[#202124] text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {group.label} <span className="ml-1 opacity-70">{group.bookings.length}</span>
            </button>
          ))}
        </div>
      )}
      {selectedTab === 'pending' && requests.isSuccess && pending.length === 0 && (
        <p className="mt-5 text-sm text-slate-500">No booking requests are waiting.</p>
      )}
      {selectedTab === 'pending' &&
        pending.map((booking) => (
          <article
            key={booking.id}
            className="mt-5 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
          >
            <div className="p-5">
              <BookingDetails booking={booking} />
              {booking.conflict && (
                <p className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                  {describeConflict(booking.conflict)} It cannot be approved.
                </p>
              )}
              <div className="mt-5 grid gap-5 border-t border-slate-100 pt-5 lg:grid-cols-2">
                <div>
                  <label
                    className="block text-sm font-medium text-slate-800"
                    htmlFor={`reason-${booking.id}`}
                  >
                    Reason for the Coordinator (optional)
                  </label>
                  <textarea
                    id={`reason-${booking.id}`}
                    maxLength={MAX_REASON_LENGTH}
                    value={reasons[booking.id] ?? ''}
                    onChange={(event) =>
                      setReasons({ ...reasons, [booking.id]: event.target.value })
                    }
                    className="mt-2 min-h-24 w-full rounded-lg border border-slate-300 p-2.5 text-sm shadow-sm focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                  />
                  <div className="mt-3 flex gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        resetAll()
                        reject.mutate({ id: booking.id, reason: reasons[booking.id] ?? '' })
                      }}
                      disabled={busy}
                      className="rounded-lg border border-red-200 bg-white px-3.5 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50 disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                  {reject.isError && reject.variables?.id === booking.id && (
                    <p role="alert" className="mt-2 text-sm text-red-600">
                      {reject.error.message}
                    </p>
                  )}
                </div>
                {/* Once the reloaded card shows its clash, that line explains the refusal in
              Singapore time, so the raw API message (which only has an id) is not repeated. */}
                {/* SCRUM-110: approval creates a time-limited tentative hold, so the expiry
              is required before the request can be approved. */}
                <div className="rounded-xl bg-slate-50 p-4">
                  <label
                    className="block text-sm font-medium text-slate-800"
                    htmlFor={`hold-${booking.id}`}
                  >
                    Hold until (Singapore time)
                  </label>
                  <p className="mt-1 text-sm text-slate-500">
                    Approval creates a tentative venue hold.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <input
                      id={`hold-${booking.id}`}
                      type="datetime-local"
                      value={holdUntil[booking.id] ?? ''}
                      onChange={(event) =>
                        setHoldUntil({ ...holdUntil, [booking.id]: event.target.value })
                      }
                      className="rounded-lg border border-slate-300 bg-white p-2 text-sm shadow-sm"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        resetAll()
                        approve.mutate({ booking, until: holdUntil[booking.id] ?? '' })
                      }}
                      disabled={busy || booking.conflict !== null || !holdUntil[booking.id]}
                      className="cs-button disabled:opacity-50"
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
                </div>
              </div>
            </div>
          </article>
        ))}
      {selectedTab === 'held' && held.length > 0 && (
        <>
          <h3 className="sr-only">Tentative holds</h3>
          {held.map((booking) => (
            <article
              key={booking.id}
              className="mt-5 rounded-2xl border border-violet-200 bg-white p-5 shadow-sm"
            >
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
                      className="rounded-lg border border-slate-300 p-2 text-sm shadow-sm"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        resetAll()
                        updateExpiry.mutate({ booking, until: holdUntil[booking.id] ?? '' })
                      }}
                      disabled={busy || !holdUntil[booking.id]}
                      className="rounded-lg bg-violet-700 px-3.5 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-violet-800 disabled:opacity-50"
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
      {selectedTab === 'held' && requests.isSuccess && held.length === 0 && (
        <p className="mt-5 text-sm text-slate-500">There are no tentative holds.</p>
      )}
      {selectedTab === 'decided' && decided.length > 0 && (
        <>
          <h3 className="sr-only">Decided</h3>
          {decided.map((booking) => (
            <article
              key={booking.id}
              className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
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
      {selectedTab === 'decided' && requests.isSuccess && decided.length === 0 && (
        <p className="mt-5 text-sm text-slate-500">There are no decided booking requests.</p>
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
    ['When', `${formatSingaporeTime(booking.start_at)} to ${formatSingaporeTime(booking.end_at)}`],
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
  const fullWidthLabels = new Set(['When', 'Venue held', 'Equipment'])
  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Event</p>
          <h3 className="mt-1 text-xl font-semibold tracking-tight text-slate-950">
            {booking.event_name ?? 'Untitled event'}
          </h3>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-700">
          {booking.session_label}
        </span>
      </div>
      <dl className="mt-5 grid gap-x-8 gap-y-4 text-sm sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className={fullWidthLabels.has(label) ? 'sm:col-span-2' : undefined}>
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {label}:
            </dt>
            <dd className="mt-1 font-medium text-slate-700">{value ?? 'Not given'}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
