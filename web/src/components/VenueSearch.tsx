import { useState, type FormEvent } from 'react'

import { ROOM_LAYOUTS, searchVenues, type Venue } from '../api/venues'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-55: coordinator venue search.
 *
 * Every filter is optional except the date and time slot; strict matching means a venue
 * must satisfy every supplied criterion to appear. An empty result is guidance, not a
 * dead end: the copy tells the coordinator to adjust the filters (AC7).
 */
export default function VenueSearch() {
  const { token } = useAuth()
  const [date, setDate] = useState('2026-12-01')
  const [startTime, setStartTime] = useState('10:00')
  const [endTime, setEndTime] = useState('12:00')
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
        date,
        startTime,
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
        Find active venues that fit the event requirements and are free for the slot.
      </p>

      <form onSubmit={onSearch} className="mt-3 grid gap-3">
        <label className="grid gap-1 text-sm">
          Date
          <input
            type="date"
            value={date}
            onChange={(event) => setDate(event.target.value)}
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
