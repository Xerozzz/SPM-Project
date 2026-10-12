import { useQuery } from '@tanstack/react-query'

import { listActiveAssignments } from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-100: the Coordinator Lead active-assignment overview. Read-only list of every
 * active request with its current coordinator (or Unassigned) — event ID, name,
 * status, organiser and event time. Current ownership only; history belongs to
 * SCRUM-97. Reassignment belongs to SCRUM-97; this story is read-only.
 */
export default function ActiveAssignments() {
  const { token } = useAuth()
  const overview = useQuery({
    queryKey: ['event-requests', 'active-assignments', token],
    queryFn: () => listActiveAssignments(token ?? ''),
    enabled: token !== null,
  })

  return (
    <section
      aria-label="Active assignments"
      className="mt-6 rounded-lg border border-slate-200 p-4"
    >
      <h2 className="font-medium">Active assignments</h2>
      {overview.isPending && <p className="mt-2 text-sm">Loading assignments…</p>}
      {overview.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          Could not load assignments: {overview.error.message}
        </p>
      )}
      {overview.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No active requests.</p>
      )}
      {overview.data && overview.data.length > 0 && (
        <ul className="mt-2 space-y-3">
          {overview.data.map((request) => (
            <li key={request.id} className="rounded border border-slate-200 p-3 text-sm">
              <p className="font-medium">{request.name ?? 'Untitled request'}</p>
              <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-slate-600">
                <dt className="font-medium text-slate-500">Event ID</dt>
                <dd>{request.id}</dd>
                <dt className="font-medium text-slate-500">Status</dt>
                <dd>{request.status}</dd>
                <dt className="font-medium text-slate-500">Organiser</dt>
                <dd>{request.organiser_email}</dd>
                <dt className="font-medium text-slate-500">Start</dt>
                <dd>{request.start_at ?? '—'}</dd>
                <dt className="font-medium text-slate-500">End</dt>
                <dd>{request.end_at ?? '—'}</dd>
                <dt className="font-medium text-slate-500">Coordinator</dt>
                <dd>{request.coordinator_email ?? 'Unassigned'}</dd>
              </dl>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
