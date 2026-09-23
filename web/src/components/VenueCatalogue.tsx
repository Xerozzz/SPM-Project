import { useQuery } from '@tanstack/react-query'

import { listVenues, type Venue } from '../api/venues'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-59: the venue catalogue, as everyone who plans with it sees it.
 *
 * Read-only here. Venue Staff maintain the catalogue, and those controls land with the
 * stories that add them; the server enforces the split either way, so a missing button is
 * presentation and not the authorisation rule.
 */
export default function VenueCatalogue() {
  const { token } = useAuth()
  const venues = useQuery({
    queryKey: ['venues', token],
    queryFn: () => listVenues(token ?? ''),
    enabled: token !== null,
  })

  return (
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Venue catalogue</h2>
      <p className="mt-1 text-sm text-slate-500">
        Venues available for planning. Venue Staff maintain this list.
      </p>

      {venues.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {venues.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {venues.error.message}
        </p>
      )}
      {venues.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No venues in the catalogue yet.</p>
      )}

      {venues.data && venues.data.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-200">
          {venues.data.map((venue) => (
            <VenueRow key={venue.id} venue={venue} />
          ))}
        </ul>
      )}
    </section>
  )
}

function VenueRow({ venue }: { venue: Venue }) {
  return (
    <li className="flex flex-wrap items-start justify-between gap-4 py-3">
      <div>
        <p className="font-medium">{venue.name}</p>
        <p className="text-sm text-slate-500">
          {venue.location} · up to {venue.maximum_capacity} people · {shortTime(venue.opens_at)} to{' '}
          {shortTime(venue.closes_at)}
        </p>
        <p className="text-sm text-slate-500">Layouts: {venue.supported_layouts.join(', ')}</p>
        {venue.facilities.length > 0 && (
          <p className="text-sm text-slate-500">Facilities: {venue.facilities.join(', ')}</p>
        )}
        {venue.accessibility_features.length > 0 && (
          <p className="text-sm text-slate-500">
            Accessibility: {venue.accessibility_features.join(', ')}
          </p>
        )}
      </div>
    </li>
  )
}

/** "08:00:00" reads better as "08:00" in a list. */
function shortTime(value: string): string {
  return value.slice(0, 5)
}
