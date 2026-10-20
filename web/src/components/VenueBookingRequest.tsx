import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  EventRequestValidationError,
  getVenueSuitability,
  listVenueBookings,
  submitVenueBooking,
  type EventRequest,
  type VenueBooking,
  type VenueSuitability,
} from '../api/eventRequests'
import { listVenues, type Venue } from '../api/venues'
import { describeConflict } from '../api/venueBookingDecisions'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'

export default function VenueBookingRequest({ event }: { event: EventRequest }) {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [venueId, setVenueId] = useState('')
  // SCRUM-111: each request is for one labelled session with its own period,
  // defaulting to the whole event so a single-session event reads as before.
  const [sessionLabel, setSessionLabel] = useState('')
  const [sessionStart, setSessionStart] = useState(event.start_at ?? '')
  const [sessionEnd, setSessionEnd] = useState(event.end_at ?? '')
  const venueBookings = useQuery({
    queryKey: ['venue-bookings', event.id],
    queryFn: () => listVenueBookings(token ?? '', event.id),
    enabled: token !== null,
  })
  const venues = useQuery({
    queryKey: ['venues'],
    queryFn: () => listVenues(token ?? ''),
    enabled: token !== null && venueBookings.isSuccess,
  })
  const suitability = useQuery({
    queryKey: ['venue-suitability', event.id, venueId],
    queryFn: () => getVenueSuitability(token ?? '', event.id, venueId),
    enabled: token !== null && venueBookings.isSuccess && venueId !== '',
  })
  const submit = useMutation({
    mutationFn: () =>
      submitVenueBooking(token ?? '', event.id, venueId, {
        session_label: sessionLabel,
        start_at: new Date(sessionStart).toISOString(),
        end_at: new Date(sessionEnd).toISOString(),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['venue-bookings', event.id] })
    },
  })
  const result = submit.data?.suitability ?? suitability.data
  const error = submit.error ?? suitability.error ?? venues.error

  if (venueBookings.isPending) {
    return (
      <div className="mt-3 border-t border-slate-200 pt-3 text-sm text-slate-600">
        Loading venue booking requests…
      </div>
    )
  }

  if (venueBookings.isError) {
    return (
      <div role="alert" className="mt-3 border-t border-slate-200 pt-3 text-sm text-red-700">
        Could not load existing venue booking requests: {venueBookings.error.message}
      </div>
    )
  }

  return (
    <div className="mt-3 border-t border-slate-200 pt-3">
      {venueBookings.data.length > 0 && (
        <ExistingVenueBookings bookings={venueBookings.data} venues={venues.data ?? []} />
      )}
      <VenueBookingForm
        venueId={venueId}
        onVenueChange={(value) => {
          setVenueId(value)
          submit.reset()
        }}
        sessionLabel={sessionLabel}
        onSessionLabelChange={setSessionLabel}
        sessionStart={sessionStart}
        onSessionStartChange={setSessionStart}
        sessionEnd={sessionEnd}
        onSessionEndChange={setSessionEnd}
        venues={venues.data ?? []}
        result={result}
        error={error}
        isSuitabilityPending={suitability.isPending}
        isSubmitPending={submit.isPending}
        hasSubmitted={submit.data !== undefined}
        onSubmit={() => submit.mutate()}
        submittedStatus={submit.data?.status}
      />
    </div>
  )
}

function VenueBookingForm({
  venueId,
  onVenueChange,
  sessionLabel,
  onSessionLabelChange,
  sessionStart,
  onSessionStartChange,
  sessionEnd,
  onSessionEndChange,
  venues,
  result,
  error,
  isSuitabilityPending,
  isSubmitPending,
  hasSubmitted,
  onSubmit,
  submittedStatus,
}: {
  venueId: string
  onVenueChange: (value: string) => void
  sessionLabel: string
  onSessionLabelChange: (value: string) => void
  sessionStart: string
  onSessionStartChange: (value: string) => void
  sessionEnd: string
  onSessionEndChange: (value: string) => void
  venues: Venue[]
  result: VenueSuitability | undefined
  error: Error | null
  isSuitabilityPending: boolean
  isSubmitPending: boolean
  hasSubmitted: boolean
  onSubmit: () => void
  submittedStatus: string | undefined
}) {
  return (
    <>
      <h4 className="font-medium">Venue booking request</h4>
      <label className="mt-2 grid gap-1 text-sm">
        Active venue
        <select
          value={venueId}
          onChange={(change) => onVenueChange(change.target.value)}
          className="rounded border border-slate-300 px-2 py-1.5"
        >
          <option value="">Select a venue</option>
          {venues.map((venue) => (
            <option key={venue.id} value={venue.id}>
              {venue.name}
            </option>
          ))}
        </select>
      </label>
      <label className="mt-2 grid gap-1 text-sm">
        Session label
        <input
          value={sessionLabel}
          onChange={(change) => onSessionLabelChange(change.target.value)}
          placeholder="Morning workshop"
          maxLength={120}
          className="rounded border border-slate-300 px-2 py-1.5"
        />
      </label>
      <div className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
        <label className="grid gap-1">
          Session start
          <input
            type="datetime-local"
            value={toLocalInput(sessionStart)}
            onChange={(change) => onSessionStartChange(fromLocalInput(change.target.value))}
            className="rounded border border-slate-300 px-2 py-1.5"
          />
        </label>
        <label className="grid gap-1">
          Session end
          <input
            type="datetime-local"
            value={toLocalInput(sessionEnd)}
            onChange={(change) => onSessionEndChange(fromLocalInput(change.target.value))}
            className="rounded border border-slate-300 px-2 py-1.5"
          />
        </label>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        The session must sit inside the event period; the venue is held for the session only.
      </p>
      {result && <Suitability result={result} />}
      {error && (
        <div role="alert" className="mt-2 text-sm text-red-700">
          {error instanceof EventRequestValidationError
            ? error.problems.map((problem) => `${problem.field}: ${problem.reason}`).join('; ')
            : error.message}
        </div>
      )}
      <button
        type="button"
        disabled={
          !venueId ||
          sessionLabel.trim() === '' ||
          !sessionStart ||
          !sessionEnd ||
          isSuitabilityPending ||
          isSubmitPending ||
          hasSubmitted
        }
        onClick={onSubmit}
        className="mt-3 rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        Submit booking request
      </button>
      {submittedStatus && (
        <p role="status" className="mt-2 bg-green-50 p-2 text-sm text-green-800">
          Booking request submitted. Status: {submittedStatus}.
        </p>
      )}
    </>
  )
}

function ExistingVenueBookings({
  bookings,
  venues,
}: {
  bookings: VenueBooking[]
  venues: Venue[]
}) {
  const venueNames = new Map(venues.map((venue) => [venue.id, venue.name]))
  return (
    <div className="mb-3 text-sm">
      <h4 className="font-medium">Existing venue booking requests</h4>
      <ul className="mt-2 space-y-2 text-slate-600">
        {bookings.map((booking) => (
          <li key={booking.id} className="rounded border border-slate-200 p-2">
            <dl>
              <div>
                <dt className="inline font-medium">Status: </dt>
                <dd className="inline">
                  {booking.status === 'tentative' && booking.expires_at
                    ? `tentative hold until ${formatBookingTime(booking.expires_at)}`
                    : booking.status === 'expired' && booking.expires_at
                      ? `tentative hold expired at ${formatBookingTime(booking.expires_at)}`
                      : booking.status}
                </dd>
              </div>
              <div>
                <dt className="inline font-medium">Selected venue: </dt>
                <dd className="inline">{venueNames.get(booking.venue_id) ?? booking.venue_id}</dd>
              </div>
              <div>
                <dt className="inline font-medium">Session: </dt>
                <dd className="inline">{booking.session_label}</dd>
              </div>
              <div>
                <dt className="inline font-medium">When: </dt>
                <dd className="inline">
                  {formatBookingTime(booking.start_at)} to {formatBookingTime(booking.end_at)}
                </dd>
              </div>
              {heldPeriod(booking) && (
                <div>
                  <dt className="inline font-medium">Venue held: </dt>
                  <dd className="inline">{heldPeriod(booking)}</dd>
                </div>
              )}
            </dl>
            {booking.conflict && (
              <p className="mt-2 rounded bg-amber-50 p-2 text-amber-800" role="status">
                Needs attention. {describeConflict(booking.conflict)} Venue Staff have been told;
                contact them to agree what moves.
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

function formatBookingTime(value: string) {
  // Singapore time, like every other time on this page. A bare toLocaleString() uses the
  // reader's own machine, which put two different timezones in one sentence next to a
  // clash the API had already described in Singapore time.
  return formatSingaporeTime(value)
}

/**
 * SCRUM-111: datetime-local needs a local wall-clock string, while the API speaks UTC
 * instants. Conversions happen at the boundary so state stays in API shape.
 */
function toLocalInput(value: string): string {
  if (!value) return ''
  const date = new Date(value)
  const offset = date.getTimezoneOffset()
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 16)
}

function fromLocalInput(value: string): string {
  if (!value) return ''
  return new Date(value).toISOString()
}

/**
 * SCRUM-82 AC3: how long the venue is really held, when that is wider than the event.
 *
 * Shown only when it differs, so a venue with no buffers reads exactly as it did (AC7).
 * Without this a clash reads as nonsense on this screen too: a booking at 9:14 pm told
 * it clashes with one holding the venue until 8:45 pm looks like no clash at all.
 */
function heldPeriod(booking: VenueBooking): string | null {
  const { effective_start_at: from, effective_end_at: to } = booking
  if (!from || !to) return null
  if (from === booking.start_at && to === booking.end_at) return null
  return `${formatSingaporeTime(from)} to ${formatSingaporeTime(to)}`
}

function Suitability({ result }: { result: VenueSuitability }) {
  const capacityWarning = result.mismatch_codes.includes('CAPACITY_EXCEEDED')
  const hasWarning = capacityWarning || result.unavailable_facilities.length > 0
  return (
    <div className="mt-3 text-sm">
      {capacityWarning && (
        <p className="text-amber-800">
          Capacity mismatch: {result.expected_attendance} attendees, {result.venue_capacity} seats.
        </p>
      )}
      {result.unavailable_facilities.length > 0 && (
        <p className="text-amber-800">
          Missing facilities: {result.unavailable_facilities.join(', ')}
        </p>
      )}
      {!hasWarning && <p className="text-green-800">Capacity and facilities are suitable.</p>}
      <p>Accessibility needed: {result.accessibility_need || 'None recorded'}</p>
      <p>Venue accessibility: {result.venue_accessibility.join(', ') || 'None recorded'}</p>
      <p>Layout needed: {result.layout_need || 'None recorded'}</p>
      <p>Supported layouts: {result.venue_layouts.join(', ') || 'None recorded'}</p>
    </div>
  )
}
