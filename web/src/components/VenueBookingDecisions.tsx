import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

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
import { formatDateRange, formatDisplayTime, sessionOnDay } from '../presentation/dates'
import { matchesSearch } from '../presentation/search'
import { useEventSelection } from '../hooks/useEventSelection'

type BookingTab = 'pending' | 'held' | 'decided'

/** SCRUM-40: Venue Staff review pending booking requests and reject them.
 * SCRUM-75: they also see any clash and approve requests that have none.
 * SCRUM-110: approval creates a time-limited tentative hold, so it needs an expiry. */
export default function VenueBookingDecisions({
  targetBookingId = null,
}: { targetBookingId?: string | null } = {}) {
  const { token } = useAuth()
  const client = useQueryClient()
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [holdUntil, setHoldUntil] = useState<Record<string, string>>({})
  const [outcome, setOutcome] = useState<string | null>(null)
  const [selectedTab, setSelectedTab] = useState<BookingTab>('pending')
  const [search, setSearch] = useState('')
  const [venueId, setVenueId] = useState('')
  const [sessionDay, setSessionDay] = useState('')
  const panel = useRef<HTMLElement>(null)
  const openedFrom = useRef<string | null>(null)
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
      setHoldUntil((values) => ({ ...values, [booking.id]: '' }))
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
  const [selectedId, setSelectedId] = useEventSelection(targetBookingId, requests.data)
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
  const visibleBookings = (
    tabGroups.find((group) => group.id === selectedTab)?.bookings ?? []
  ).filter(
    (booking) =>
      matchesSearch(search, booking.event_name, booking.venue_name, booking.session_label) &&
      (!venueId || booking.venue_id === venueId) &&
      (!sessionDay || sessionOnDay(booking.start_at, booking.end_at, sessionDay)),
  )
  const filtered = Boolean(search || venueId || sessionDay)
  const venues = [
    ...new Map(requests.data?.map((booking) => [booking.venue_id, booking.venue_name])).entries(),
  ]
  const pendingDetails = pending.filter((booking) => booking.id === selectedId)
  const heldDetails = held.filter((booking) => booking.id === selectedId)
  const decidedDetails = decided.filter((booking) => booking.id === selectedId)
  useEffect(() => {
    if (selectedId) panel.current?.focus()
    else
      (
        document.getElementById(openedFrom.current ?? '') ??
        document.getElementById(`booking-tab-${selectedTab}`)
      )?.focus()
  }, [selectedId, selectedTab])

  return (
    <section
      ref={panel}
      tabIndex={selectedId ? -1 : undefined}
      aria-label={selectedId ? 'Booking details' : 'Booking requests'}
      className="mt-0"
    >
      {selectedId && (
        <button
          type="button"
          className="cs-button-secondary mb-5"
          disabled={busy}
          onClick={() => setSelectedId(null)}
        >
          ← Back to bookings
        </button>
      )}
      {outcome && (
        <p role="status" className="mb-5 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
          {outcome}
        </p>
      )}
      {requests.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {requests.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          Could not load booking requests: {requests.error.message}
        </p>
      )}
      {!selectedId && (
        <div className="mt-5 grid gap-3 text-sm sm:grid-cols-3">
          <label>
            Search bookings
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Event, venue or session"
              className="cs-field"
            />
          </label>
          <label>
            Venue
            <select
              value={venueId}
              onChange={(event) => setVenueId(event.target.value)}
              className="cs-field"
            >
              <option value="">All venues</option>
              {venues.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Session date (Singapore)
            <input
              type="date"
              value={sessionDay}
              onChange={(event) => setSessionDay(event.target.value)}
              className="cs-field"
            />
          </label>
        </div>
      )}
      {filtered && !selectedId && (
        <button
          type="button"
          className="mt-3 text-sm text-sky-800 underline"
          onClick={() => {
            setSearch('')
            setVenueId('')
            setSessionDay('')
          }}
        >
          Clear filters
        </button>
      )}
      {requests.isSuccess && !selectedId && (
        <div
          role="group"
          aria-label="Booking request status"
          className="mt-5 flex gap-2 overflow-x-auto border-b border-slate-200 pb-3"
        >
          {tabGroups.map((group) => (
            <button
              key={group.id}
              id={`booking-tab-${group.id}`}
              type="button"
              aria-pressed={selectedTab === group.id}
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
      {!selectedId &&
        !filtered &&
        selectedTab === 'pending' &&
        requests.isSuccess &&
        pending.length === 0 && (
          <p className="mt-5 text-sm text-slate-500">No booking requests are waiting.</p>
        )}
      {!selectedId && (
        <div className="mt-5 grid gap-4 xl:grid-cols-2">
          {visibleBookings.map((booking) => (
            <BookingSummary
              key={booking.id}
              booking={booking}
              onOpen={() => {
                openedFrom.current = `view-booking-${booking.id}`
                resetAll()
                setOutcome(null)
                setSelectedId(booking.id)
              }}
            />
          ))}
        </div>
      )}
      {!selectedId && filtered && requests.isSuccess && visibleBookings.length === 0 && (
        <p className="mt-5 text-sm text-slate-500">No bookings match your filters.</p>
      )}
      {selectedId &&
        pendingDetails.map((booking) => (
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
                    Reserve this session provisionally while the Coordinator finalises the event.
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
                      Approve and place hold
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
      {selectedId && heldDetails.length > 0 && (
        <>
          <h3 className="sr-only">Tentative holds</h3>
          {heldDetails.map((booking) => (
            <HeldDetails
              key={booking.id}
              booking={booking}
              holdUntil={holdUntil[booking.id] ?? ''}
              setHoldUntil={(value) => setHoldUntil({ ...holdUntil, [booking.id]: value })}
              busy={busy}
              onUpdate={() => {
                resetAll()
                updateExpiry.mutate({ booking, until: holdUntil[booking.id] ?? '' })
              }}
              error={
                updateExpiry.isError && updateExpiry.variables?.booking.id === booking.id
                  ? updateExpiry.error.message
                  : null
              }
            />
          ))}
        </>
      )}
      {!selectedId &&
        !filtered &&
        selectedTab === 'held' &&
        requests.isSuccess &&
        held.length === 0 && (
          <p className="mt-5 text-sm text-slate-500">There are no tentative holds.</p>
        )}
      {selectedId && decidedDetails.length > 0 && (
        <>
          <h3 className="sr-only">Decided</h3>
          {decidedDetails.map((booking) => (
            <DecidedDetails key={booking.id} booking={booking} />
          ))}
        </>
      )}
      {!selectedId &&
        !filtered &&
        selectedTab === 'decided' &&
        requests.isSuccess &&
        decided.length === 0 && (
          <p className="mt-5 text-sm text-slate-500">There are no decided booking requests.</p>
        )}
    </section>
  )
}

function BookingSummary({
  booking,
  onOpen,
}: {
  booking: VenueBookingDecision
  onOpen: () => void
}) {
  const styles: Record<VenueBookingDecision['status'], string> = {
    pending: 'bg-amber-50 text-amber-800',
    tentative: 'bg-violet-50 text-violet-800',
    confirmed: 'bg-emerald-50 text-emerald-800',
    rejected: 'bg-red-50 text-red-800',
    cancelled: 'bg-slate-100 text-slate-700',
    expired: 'bg-slate-100 text-slate-700',
  }
  return (
    <article className="flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
        <span className={`rounded-md px-2 py-1 ${styles[booking.status]}`}>
          {STATUS_LABELS[booking.status]}
        </span>
        {booking.conflict && (
          <span className="rounded-md bg-amber-50 px-2 py-1 text-amber-800">
            Conflict needs attention
          </span>
        )}
      </div>
      <h3 className="mt-3 break-words text-lg font-semibold tracking-normal">
        {booking.event_name ?? 'Untitled event'}
      </h3>
      <p className="mt-1 text-sm text-slate-600">
        {booking.venue_name} · {booking.session_label}
      </p>
      <dl className="mt-4 flex-1 space-y-3 text-sm">
        <div>
          <dt className="text-xs text-slate-500">Session · Singapore time</dt>
          <dd className="mt-1">{formatDateRange(booking.start_at, booking.end_at)}</dd>
        </div>
        {booking.status === 'tentative' && booking.expires_at && (
          <div>
            <dt className="text-xs text-slate-500">Hold expires</dt>
            <dd className="mt-1">{formatDisplayTime(booking.expires_at)}</dd>
          </div>
        )}
        {booking.status !== 'pending' && booking.status !== 'tentative' && (
          <div>
            <dt className="text-xs text-slate-500">Decision made</dt>
            <dd className="mt-1 break-words">{decisionOf(booking, true)}</dd>
          </div>
        )}
      </dl>
      <button
        type="button"
        id={`view-booking-${booking.id}`}
        className="cs-button-secondary mt-5 w-full"
        aria-label={`View booking for ${booking.event_name ?? 'Untitled event'} at ${booking.venue_name}`}
        onClick={onOpen}
      >
        {booking.status === 'pending' ? 'Review request →' : 'View details →'}
      </button>
    </article>
  )
}

function HeldDetails({
  booking,
  holdUntil,
  setHoldUntil,
  busy,
  onUpdate,
  error,
}: {
  booking: VenueBookingDecision
  holdUntil: string
  setHoldUntil: (value: string) => void
  busy: boolean
  onUpdate: () => void
  error: string | null
}) {
  return (
    <article className="mt-5 rounded-2xl border border-violet-200 bg-white p-5 shadow-sm">
      <BookingDetails booking={booking} />
      {holdHasExpired(booking, new Date()) ? (
        <p className="mt-2 rounded bg-slate-100 p-2 text-sm text-slate-700">
          This hold has expired.
        </p>
      ) : (
        <>
          <p className="mt-1 text-sm text-violet-900">
            {STATUS_LABELS.tentative}
            {booking.expires_at && ` until ${formatSingaporeTime(booking.expires_at)}`}
          </p>
          {booking.conflict && (
            <p className="mt-2 rounded bg-amber-50 p-2 text-sm text-amber-800">
              {describeConflict(booking.conflict)}
            </p>
          )}
          <label className="mt-3 block text-sm font-medium" htmlFor={`hold-${booking.id}`}>
            New expiry (Singapore time)
          </label>
          <div className="mt-1 flex flex-wrap gap-2">
            <input
              id={`hold-${booking.id}`}
              type="datetime-local"
              value={holdUntil}
              onChange={(event) => setHoldUntil(event.target.value)}
              className="rounded-lg border border-slate-300 p-2 text-sm shadow-sm"
            />
            <button
              type="button"
              onClick={onUpdate}
              disabled={busy || !holdUntil}
              className="rounded-lg bg-violet-700 px-3.5 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-violet-800 disabled:opacity-50"
            >
              Update expiry
            </button>
          </div>
          {error && (
            <p role="alert" className="mt-2 text-sm text-red-600">
              Could not update expiry: {error}
            </p>
          )}
        </>
      )}
    </article>
  )
}

function DecidedDetails({ booking }: { booking: VenueBookingDecision }) {
  return (
    <article className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <BookingDetails booking={booking} />
      <p className="mt-1 text-sm">{decisionOf(booking)}</p>
    </article>
  )
}

function decisionOf(booking: VenueBookingDecision, compact = false) {
  const formatTime = compact ? formatDisplayTime : formatSingaporeTime
  return `${STATUS_LABELS[booking.status]}${booking.status === 'expired' && booking.expires_at ? ` at ${formatTime(booking.expires_at)}` : ''}${booking.decided_at ? ` on ${formatTime(booking.decided_at)}` : ''}${booking.decision_reason ? `: ${booking.decision_reason}` : ''}`
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
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Event</p>
        <h3 className="mt-1 text-xl font-semibold tracking-tight text-slate-950">
          {booking.event_name ?? 'Untitled event'}
        </h3>
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
