import { useQuery } from '@tanstack/react-query'

import { listAssignmentHistory } from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-97: one request's assignment history, oldest first. Each entry shows the
 * previous owner (or "First assignment" when there was none), the new owner, the
 * acting Lead and the timezone-aware time. An empty list is a normal state for
 * requests assigned before this story's migration landed — not an error.
 */
export default function AssignmentHistory({ requestId, requestName }: { requestId: string; requestName: string | null }) {
  const { token } = useAuth()
  const history = useQuery({
    queryKey: ['event-requests', requestId, 'assignment-history', token],
    queryFn: () => listAssignmentHistory(token ?? '', requestId),
    enabled: token !== null,
  })

  return (
    <div className="mt-2 rounded border border-slate-100 p-2">
      <p className="font-medium text-slate-500">Assignment history</p>
      {history.isPending && <p className="mt-1 text-sm">Loading history…</p>}
      {history.isError && (
        <p role="alert" className="mt-1 text-sm text-red-600">
          Could not load history: {history.error.message}
        </p>
      )}
      {history.data?.length === 0 && (
        <p className="mt-1 text-sm text-slate-500">
          No assignment history for {requestName ?? requestId} yet.
        </p>
      )}
      {history.data && history.data.length > 0 && (
        <ol className="mt-1 space-y-1 text-slate-600">
          {history.data.map((entry) => (
            <li key={entry.id}>
              {entry.previous_coordinator_id ?? 'First assignment'} → {entry.new_coordinator_id} by{' '}
              {entry.acted_by_id} at {entry.assigned_at}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
