import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import {
  EventRequestValidationError,
  getVenueSuitability,
  submitVenueBooking,
  type EventRequest,
  type VenueSuitability,
} from '../api/eventRequests'
import { listVenues } from '../api/venues'
import { useAuth } from '../auth/useAuth'

export default function VenueBookingRequest({ event }: { event: EventRequest }) {
  const { token } = useAuth()
  const [venueId, setVenueId] = useState('')
  const venues = useQuery({
    queryKey: ['venues'],
    queryFn: () => listVenues(token ?? ''),
    enabled: token !== null,
  })
  const suitability = useQuery({
    queryKey: ['venue-suitability', event.id, venueId],
    queryFn: () => getVenueSuitability(token ?? '', event.id, venueId),
    enabled: token !== null && venueId !== '',
  })
  const submit = useMutation({
    mutationFn: () => submitVenueBooking(token ?? '', event.id, venueId),
  })
  const result = submit.data?.suitability ?? suitability.data
  const error = submit.error ?? suitability.error ?? venues.error

  return (
    <div className="mt-3 border-t border-slate-200 pt-3">
      <h4 className="font-medium">Venue booking request</h4>
      <label className="mt-2 grid gap-1 text-sm">
        Active venue
        <select
          value={venueId}
          onChange={(change) => {
            setVenueId(change.target.value)
            submit.reset()
          }}
          className="rounded border border-slate-300 px-2 py-1.5"
        >
          <option value="">Select a venue</option>
          {venues.data?.map((venue) => (
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
        disabled={!venueId || suitability.isPending || submit.isPending || !!submit.data}
        onClick={() => submit.mutate()}
        className="mt-3 rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        Submit booking request
      </button>
      {submit.data && (
        <p role="status" className="mt-2 bg-green-50 p-2 text-sm text-green-800">
          Booking request submitted. Status: {submit.data.status}.
        </p>
      )}
    </div>
  )
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
