import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { type AssignmentHistoryEntry, listAssignmentHistory } from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-97: one request's assignment history, oldest first. Each entry shows the
 * previous owner (or "First assignment" when there was none), the new owner, the
 * acting Lead and the timezone-aware time. An empty list is a normal state for
 * requests assigned before this story's migration landed — not an error.
 *
 * SCRUM-105 (ADR-0047): people are shown by email, or "Unknown user" when the API has
 * none for them, and the time in the viewer's local time zone (AGENTS.md §3).
 */
export default function AssignmentHistory({
  requestId,
  requestName,
}: {
  requestId: string
  requestName: string | null
}) {
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
              {previousOwner(entry)} → {entry.new_coordinator_email ?? UNKNOWN_USER} by{' '}
              {entry.acted_by_email ?? UNKNOWN_USER} at{' '}
              <time dateTime={entry.assigned_at}>
                {new Date(entry.assigned_at).toLocaleString()}
              </time>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

/**
 * SCRUM-105: the history behind a button, for the Organiser's request list and the
 * Coordinator's review card. It mounts — and so fetches — only once opened, so a long
 * list does not send one history request per row.
 */
export function AssignmentHistoryToggle({
  requestId,
  requestName,
}: {
  requestId: string
  requestName: string | null
}) {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="text-sm text-slate-600 underline"
      >
        {open ? 'Hide assignment history' : 'View assignment history'}
      </button>
      {open && <AssignmentHistory requestId={requestId} requestName={requestName} />}
    </div>
  )
}

const UNKNOWN_USER = 'Unknown user'

/** No previous id is the first assignment; an id without an email is a missing user. */
function previousOwner(entry: AssignmentHistoryEntry): string {
  if (entry.previous_coordinator_id === null) return 'First assignment'
  return entry.previous_coordinator_email ?? UNKNOWN_USER
}
