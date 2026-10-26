import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  listActiveAssignments,
  listAssignableCoordinators,
  reassignEventRequest,
} from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'
import AssignmentHistory from './AssignmentHistory'
import { EventHistoryToggle } from './EventHistory'

/**
 * SCRUM-100: the Coordinator Lead active-assignment overview. Read-only list of every
 * active request with its current coordinator (or Unassigned) — event ID, name,
 * status, organiser and event time. Current ownership only; history belongs to
 * SCRUM-97. SCRUM-97 adds a per-row history view below each request plus a
 * reassignment picker for assigned rows.
 */
export default function ActiveAssignments() {
  const { token } = useAuth()
  const client = useQueryClient()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [selected, setSelected] = useState<Record<string, string>>({})
  const [outcome, setOutcome] = useState<string | null>(null)
  const overviewKey = ['event-requests', 'active-assignments', token]
  const overview = useQuery({
    queryKey: overviewKey,
    queryFn: () => listActiveAssignments(token ?? ''),
    enabled: token !== null,
  })
  const coordinators = useQuery({
    queryKey: ['event-requests', 'assignable-coordinators', token],
    queryFn: () => listAssignableCoordinators(token ?? ''),
    enabled: token !== null,
  })
  const reassign = useMutation({
    mutationFn: ({
      id,
      coordinatorId,
      expectedCurrentCoordinatorId,
    }: {
      id: string
      coordinatorId: string
      expectedCurrentCoordinatorId: string
    }) => reassignEventRequest(token ?? '', id, coordinatorId, expectedCurrentCoordinatorId),
    onSuccess: (request) => {
      setOutcome(`“${request.name ?? request.id}” has been reassigned.`)
      void client.invalidateQueries({ queryKey: overviewKey })
      void client.invalidateQueries({
        queryKey: ['event-requests', request.id, 'assignment-history'],
      })
    },
  })

  return (
    <section
      aria-label="Active requests"
      className="mt-6 rounded-lg border border-slate-200 p-4"
    >
      <h2 className="font-medium">Active requests</h2>
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
              {request.coordinator_id !== null && (
                <div className="mt-2 flex items-center gap-2">
                  <label className="text-slate-500">
                    New coordinator{' '}
                    <select
                      aria-label={`New coordinator for ${request.name ?? request.id}`}
                      value={selected[request.id] ?? ''}
                      onChange={(event) =>
                        setSelected({ ...selected, [request.id]: event.target.value })
                      }
                      className="rounded border border-slate-300 px-2 py-1"
                    >
                      <option value="">Select a coordinator</option>
                      {(coordinators.data ?? []).map((coordinator) => (
                        <option key={coordinator.id} value={coordinator.id}>
                          {coordinator.email}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    disabled={!selected[request.id] || reassign.isPending}
                    onClick={() =>
                      selected[request.id] &&
                      reassign.mutate({
                        id: request.id,
                        coordinatorId: selected[request.id],
                        expectedCurrentCoordinatorId: request.coordinator_id ?? '',
                      })
                    }
                    className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
                  >
                    Reassign
                  </button>
                </div>
              )}
              <button
                type="button"
                onClick={() => setExpanded({ ...expanded, [request.id]: !expanded[request.id] })}
                className="mt-2 rounded border border-slate-300 px-3 py-1.5 text-sm"
              >
                {expanded[request.id] ? 'Hide history' : 'Show history'}
              </button>
              {expanded[request.id] && (
                <AssignmentHistory requestId={request.id} requestName={request.name} />
              )}
              {/* SCRUM-88: a Lead may read any event's history. */}
              <div className="mt-2">
                <EventHistoryToggle eventId={request.id} eventName={request.name} />
              </div>
            </li>
          ))}
        </ul>
      )}
      {outcome && (
        <p role="status" className="mt-4 rounded bg-green-50 p-3 text-sm text-green-800">
          {outcome}
        </p>
      )}
      {reassign.isError && (
        <p role="alert" className="mt-4 text-sm text-red-600">
          The reassignment could not be recorded: {reassign.error.message}
        </p>
      )}
    </section>
  )
}
