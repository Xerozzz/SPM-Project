import { useQuery } from '@tanstack/react-query'

import { describeConflict } from '../api/venueBookingDecisions'
import { listBookingProblems } from '../api/venues'
import { useAuth } from '../auth/useAuth'

/** The same Singapore formatter the calendar and the decisions panel use. */
function singaporeTime(value: string): string {
  return new Date(value).toLocaleString('en-SG', { timeZone: 'Asia/Singapore' })
}

/**
 * SCRUM-89 AC4: every confirmed booking that cannot stand under its venue's buffers.
 *
 * The API works this out on each request rather than reading a stored flag, so nothing
 * here has to be refreshed or cleared when a buffer is lowered or a clashing booking is
 * cancelled: the next load simply returns less (AC7).
 */
export default function BookingProblems() {
  const { token } = useAuth()
  const problems = useQuery({
    queryKey: ['booking-problems', token],
    queryFn: () => listBookingProblems(token ?? ''),
    enabled: token !== null,
  })

  return (
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Bookings needing attention</h2>
      <p className="mt-1 text-sm text-slate-500">
        Confirmed bookings and tentative holds that no longer fit the setup and turnaround
        times their venue needs. Nothing has been cancelled: the Coordinator decides what
        moves.
      </p>
      {problems.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {problems.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {problems.error.message}
        </p>
      )}
      {problems.isSuccess && problems.data.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">
          Nothing needs attention. Everything held at every venue fits its buffers.
        </p>
      )}
      {problems.data?.map((venue) => (
        <article key={venue.venue_id} className="mt-4 rounded border border-slate-200 p-3">
          <h3 className="font-medium">
            {venue.venue_name}, {venue.venue_location}
            {!venue.is_active && <span className="text-slate-500"> (deactivated)</span>}
          </h3>
          <p className="text-sm text-slate-500">
            {venue.setup_minutes} min setup, {venue.turnaround_minutes} min turnaround
          </p>
          <ul className="mt-2 space-y-2 text-sm">
            {venue.problems.map((problem) => (
              <li key={problem.booking_id} className="rounded bg-amber-50 p-2 text-amber-800">
                <span className="font-medium">{problem.event_name ?? 'Untitled event'}</span>
                {problem.status === 'tentative' && (
                  <span className="ml-2 rounded bg-violet-100 px-1.5 py-0.5 text-xs text-violet-800">
                    Tentative hold
                  </span>
                )}
                <br />
                {singaporeTime(problem.start_at)} to {singaporeTime(problem.end_at)}
                <br />
                {describeConflict(problem.conflict)}
              </li>
            ))}
          </ul>
        </article>
      ))}
    </section>
  )
}
