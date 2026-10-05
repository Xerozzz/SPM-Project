import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import {
  CALENDAR_LABELS,
  formatSingaporeTime,
  getVenueAvailability,
  getVenueCalendar,
  type CalendarStatus,
} from '../api/venueCalendar'
import { listVenues } from '../api/venues'
import { useAuth } from '../auth/useAuth'

const STATUS_STYLES: Record<CalendarStatus, string> = {
  confirmed: 'border-blue-300 bg-blue-50 text-blue-900',
  pending: 'border-amber-300 bg-amber-50 text-amber-900',
  unavailable: 'border-slate-300 bg-slate-100 text-slate-800',
}

/** Today in Singapore as YYYY-MM-DD, plus `days`. */
function singaporeDate(days = 0): string {
  const shifted = new Date(Date.now() + 8 * 60 * 60 * 1000 + days * 24 * 60 * 60 * 1000)
  return shifted.toISOString().slice(0, 10)
}

/**
 * SCRUM-54: Coordinators and Venue Staff see confirmed bookings, pending requests and
 * unavailability across a date range, for every venue or one chosen venue.
 * SCRUM-76: with one venue chosen, it also says whether the venue is free for the range.
 */
export default function VenueCalendar() {
  const { token } = useAuth()
  const [venueId, setVenueId] = useState('')
  const [firstDay, setFirstDay] = useState(() => singaporeDate())
  const [lastDay, setLastDay] = useState(() => singaporeDate(6))
  const venues = useQuery({
    queryKey: ['venues', token],
    queryFn: () => listVenues(token ?? ''),
    enabled: token !== null,
  })
  const calendar = useQuery({
    queryKey: ['venue-calendar', token, venueId, firstDay, lastDay],
    queryFn: () => getVenueCalendar(token ?? '', firstDay, lastDay, venueId || null),
    enabled: token !== null && firstDay !== '' && lastDay !== '',
  })

  const availability = useQuery({
    queryKey: ['venue-availability', token, venueId, firstDay, lastDay],
    queryFn: () => getVenueAvailability(token ?? '', venueId, firstDay, lastDay),
    enabled: token !== null && venueId !== '' && firstDay !== '' && lastDay !== '',
  })

  return (
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Venue calendar</h2>
      <div className="mt-2 grid grid-cols-3 gap-2 text-sm">
        <label className="flex flex-col">
          Venue
          <select
            value={venueId}
            onChange={(event) => setVenueId(event.target.value)}
            className="mt-1 rounded border border-slate-300 p-1"
          >
            <option value="">All venues</option>
            {venues.data?.map((venue) => (
              <option key={venue.id} value={venue.id}>
                {venue.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col">
          From
          <input
            type="date"
            value={firstDay}
            onChange={(event) => setFirstDay(event.target.value)}
            className="mt-1 rounded border border-slate-300 p-1"
          />
        </label>
        <label className="flex flex-col">
          To
          <input
            type="date"
            value={lastDay}
            onChange={(event) => setLastDay(event.target.value)}
            className="mt-1 rounded border border-slate-300 p-1"
          />
        </label>
      </div>
      {availability.data && (
        <p
          role="status"
          className={`mt-3 rounded p-2 text-sm font-medium ${
            availability.data.available ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
          }`}
        >
          {availability.data.available
            ? 'No confirmed booking or closure in this range. Pending requests do not block it. Opening hours are not considered.'
            : 'This venue is not available for all of this range.'}
        </p>
      )}
      {calendar.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {calendar.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {calendar.error.message}
        </p>
      )}
      {calendar.isSuccess && calendar.data.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">Nothing is booked or blocked in this range.</p>
      )}
      <ul className="mt-2 space-y-2">
        {calendar.data?.map((entry) => (
          <li
            key={entry.id}
            className={`rounded border p-2 text-sm ${STATUS_STYLES[entry.status]}`}
          >
            <span className="font-medium">{CALENDAR_LABELS[entry.status]}</span>
            {' · '}
            {entry.venue_name}
            <br />
            {formatSingaporeTime(entry.start_at)} to {formatSingaporeTime(entry.end_at)}
          </li>
        ))}
      </ul>
    </section>
  )
}
