import { useQuery } from '@tanstack/react-query'

import { listUnassignedEventRequests } from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-101: the Coordinator Lead unassigned queue. Read-only triage list showing every
 * required field (event ID, name, organiser, start/end, expected attendance, submission
 * time) oldest submission first. Assignment itself is SCRUM-98.
 */
export default function UnassignedQueue() {
  const { token } = useAuth()
  const queue = useQuery({
    queryKey: ['event-requests', 'unassigned', token],
    queryFn: () => listUnassignedEventRequests(token ?? ''),
    enabled: token !== null,
  })

  return (
    <section aria-label="Unassigned requests" className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Unassigned requests</h2>
      {queue.isPending && <p className="mt-2 text-sm">Loading unassigned requests…</p>}
      {queue.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          Could not load unassigned requests: {queue.error.message}
        </p>
      )}
      {queue.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No unassigned requests.</p>
      )}
      {queue.data && queue.data.length > 0 && (
        <ul className="mt-2 space-y-3">
          {queue.data.map((request) => (
            <li key={request.id} className="rounded border border-slate-200 p-3 text-sm">
              <p className="font-medium">{request.name ?? 'Untitled request'}</p>
              <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-slate-600">
                <dt className="font-medium text-slate-500">Event ID</dt>
                <dd>{request.id}</dd>
                <dt className="font-medium text-slate-500">Organiser</dt>
                <dd>{request.organiser_id}</dd>
                <dt className="font-medium text-slate-500">Start</dt>
                <dd>{request.start_at ?? '—'}</dd>
                <dt className="font-medium text-slate-500">End</dt>
                <dd>{request.end_at ?? '—'}</dd>
                <dt className="font-medium text-slate-500">Expected attendance</dt>
                <dd>{request.expected_attendance ?? '—'}</dd>
                <dt className="font-medium text-slate-500">Submitted</dt>
                <dd>{request.submitted_at ?? '—'}</dd>
              </dl>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
