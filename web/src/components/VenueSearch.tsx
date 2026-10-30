import { useState, type FormEvent } from 'react'

import { ROOM_LAYOUTS, searchVenues, type Venue } from '../api/venues'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-55: coordinator venue search.
 *
 * Every filter is optional except the requested period; strict matching means a venue
 * must satisfy every supplied criterion to appear. An empty result is guidance, not a
 * dead end: the copy tells the coordinator to adjust the filters (AC7).
 */
/**
 * Singapore is a fixed +08:00 with no daylight saving, which is the same assumption
 * `singaporeWallClockToUtc` in api/venues.ts already makes when it reads these fields back.
 * Shifting the instant by the offset gives a Date whose *UTC* fields read as Singapore
 * wall clock, so the helpers below deliberately use the getUTC* accessors.
 */
const SGT_OFFSET_MS = 8 * 60 * 60 * 1000

function toDateInput(value: Date): string {
  const year = value.getUTCFullYear()
  const month = String(value.getUTCMonth() + 1).padStart(2, '0')
  const day = String(value.getUTCDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function toTimeInput(value: Date): string {
  const hours = String(value.getUTCHours()).padStart(2, '0')
  const minutes = String(value.getUTCMinutes()).padStart(2, '0')
  return `${hours}:${minutes}`
}

/**
 * The slot the form opens on: the next full Singapore hour, rolled forward to the next
 * morning when that would land outside the hours any venue keeps.
 *
 * Two bugs live here, so both are worth stating. The original default was simply "one hour
 * from now", so from late evening until morning the form opened on a period every venue is
 * closed for, and the first search returned nothing while the empty-state copy blamed the
 * filters. The first attempt at a fix clamped the hours but still derived them from the
 * *browser's* clock, while the API client reads the very same fields as Singapore wall
 * clock. For a browser west of SGT that produced a default period which had already ended,
 * and the search then answers 422 rather than merely returning nothing. Everything below is
 * therefore computed in Singapore time regardless of where the coordinator is sitting.
 */
const EARLIEST_HOUR = 9
const LATEST_START_HOUR = 17

function defaultSearchPeriod(): { date: string; start: string; end: string } {
  const start = new Date(Date.now() + SGT_OFFSET_MS)
  start.setUTCMinutes(0, 0, 0)
  start.setUTCHours(start.getUTCHours() + 1)
  if (start.getUTCHours() >= LATEST_START_HOUR) {
    start.setUTCDate(start.getUTCDate() + 1)
    start.setUTCHours(EARLIEST_HOUR)
  } else if (start.getUTCHours() < EARLIEST_HOUR) {
    start.setUTCHours(EARLIEST_HOUR)
  }
  const end = new Date(start.getTime() + 60 * 60 * 1000)
  return { date: toDateInput(start), start: toTimeInput(start), end: toTimeInput(end) }
}

export default function VenueSearch() {
  const { token } = useAuth()
  const [defaults] = useState(defaultSearchPeriod)
  const [startDate, setStartDate] = useState(defaults.date)
  const [startTime, setStartTime] = useState(defaults.start)
  const [endDate, setEndDate] = useState(defaults.date)
  const [endTime, setEndTime] = useState(defaults.end)
  const [minimumCapacity, setMinimumCapacity] = useState('')
  const [location, setLocation] = useState('')
  const [accessibility, setAccessibility] = useState('')
  const [facility, setFacility] = useState('')
  const [layout, setLayout] = useState('')
  const [results, setResults] = useState<Venue[] | null>(null)
  const [searched, setSearched] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isSearching, setIsSearching] = useState(false)

  async function onSearch(event: FormEvent) {
    event.preventDefault()
    setIsSearching(true)
    setError(null)
    try {
      const venues = await searchVenues(token ?? '', {
        startDate,
        startTime,
        endDate,
        endTime,
        minimumCapacity: minimumCapacity === '' ? undefined : Number(minimumCapacity),
        location: location === '' ? undefined : location,
        accessibility: accessibility === '' ? undefined : accessibility,
        facility: facility === '' ? undefined : facility,
        layout: layout === '' ? undefined : layout,
      })
      setResults(venues)
      setSearched(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The search could not be completed')
    } finally {
      setIsSearching(false)
    }
  }

  return (
    <section aria-label="Venue search" className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Venue search</h2>
      <p className="mt-1 text-sm text-slate-500">
        Find active venues that fit the event requirements.
      </p>

      <form onSubmit={onSearch} className="mt-3 grid gap-3">
        <label className="grid gap-1 text-sm">
          Start date
          <input
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
            className="rounded border border-slate-300 px-2 py-1.5"
          />
        </label>
        <label className="grid gap-1 text-sm">
          Start time
          <input
            type="time"
            value={startTime}
            onChange={(event) => setStartTime(event.target.value)}
            className="rounded border border-slate-300 px-2 py-1.5"
          />
        </label>
        <label className="grid gap-1 text-sm">
          End date
          <input
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
            className="rounded border border-slate-300 px-2 py-1.5"
          />
        </label>
        <label className="grid gap-1 text-sm">
          End time
          <input
            type="time"
            value={endTime}
            onChange={(event) => setEndTime(event.target.value)}
            className="rounded border border-slate-300 px-2 py-1.5"
          />
        </label>
        <label className="grid gap-1 text-sm">
          Minimum capacity
          <input
            type="number"
            min={1}
            value={minimumCapacity}
            onChange={(event) => setMinimumCapacity(event.target.value)}
            className="rounded border border-slate-300 px-2 py-1.5"
          />
        </label>
        <label className="grid gap-1 text-sm">
          Location
          <input
            type="text"
            value={location}
            onChange={(event) => setLocation(event.target.value)}
            className="rounded border border-slate-300 px-2 py-1.5"
          />
        </label>
        <label className="grid gap-1 text-sm">
          Accessibility needs
          <input
            type="text"
            value={accessibility}
            onChange={(event) => setAccessibility(event.target.value)}
            className="rounded border border-slate-300 px-2 py-1.5"
          />
        </label>
        <label className="grid gap-1 text-sm">
          Facilities
          <input
            type="text"
            value={facility}
            onChange={(event) => setFacility(event.target.value)}
            className="rounded border border-slate-300 px-2 py-1.5"
          />
        </label>
        <label className="grid gap-1 text-sm">
          Room layout
          <select
            value={layout}
            onChange={(event) => setLayout(event.target.value)}
            className="rounded border border-slate-300 px-2 py-1.5"
          >
            <option value="">Any layout</option>
            {ROOM_LAYOUTS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          disabled={isSearching}
          className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          Search venues
        </button>
      </form>

      {error && (
        <p role="alert" className="mt-3 text-sm text-red-600">
          {error}
        </p>
      )}

      {searched && results !== null && (
        <div className="mt-4">
          {results.length === 0 ? (
            <>
              <p className="text-sm">No matching venue was found for these requirements.</p>
              <p className="mt-1 text-sm text-slate-500">
                Try adjusting the filters, for example by removing a criterion.
              </p>
            </>
          ) : (
            <ul className="divide-y divide-slate-200">
              {results.map((venue) => (
                <li key={venue.id} className="py-2 text-sm">
                  {venue.name} · {venue.location} · seats {venue.maximum_capacity}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
