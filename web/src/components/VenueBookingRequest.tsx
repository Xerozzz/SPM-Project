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
    mutationFn: () => submitVenueBooking(token ?? '', event.id, venueId),
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
        disabled={!venueId || isSuitabilityPending || isSubmitPending || hasSubmitted}
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
