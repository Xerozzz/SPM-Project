import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import {
  listActiveAssignments,
  listAssignableCoordinators,
  reassignEventRequest,
} from '../api/eventRequests'
import { formatDisplayTime } from '../presentation/dates'
import { useAuth } from '../auth/useAuth'
import { useEventSelection } from '../hooks/useEventSelection'
import AssignmentHistory from './AssignmentHistory'
import { EventHistoryToggle } from './EventHistory'

/**
 * SCRUM-100: the Coordinator Lead active-assignment overview. Read-only list of every
 * active request with its current coordinator (or Unassigned) — event ID, name,
 * status, organiser and event time. Current ownership only; history belongs to
 * SCRUM-97. SCRUM-97 adds a per-row history view below each request plus a
 * reassignment picker for assigned rows.
 */
export default function ActiveAssignments({
  targetEventId = null,
}: { targetEventId?: string | null } = {}) {
  const { token } = useAuth()
  const client = useQueryClient()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [selected, setSelected] = useState<Record<string, string>>({})
  const [outcome, setOutcome] = useState<string | null>(null)
  const openedFrom = useRef<string | null>(null)
  const detailsHeading = useRef<HTMLHeadingElement>(null)
  const overviewKey = ['event-requests', 'active-assignments', token]
  const overview = useQuery({
    queryKey: overviewKey,
    queryFn: () => listActiveAssignments(token ?? ''),
    enabled: token !== null,
  })
  const [selectedId, setSelectedId] = useEventSelection(targetEventId, overview.data)
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
  const visibleRequests =
    overview.data?.filter((request) => !selectedId || request.id === selectedId) ?? []

  useEffect(() => {
    if (selectedId) detailsHeading.current?.focus()
    else document.getElementById(openedFrom.current ?? '')?.focus()
  }, [selectedId])

  return (
    <section aria-label="Active requests">
      {selectedId && (
        <button type="button" className="cs-button-secondary" onClick={() => setSelectedId(null)}>
          ← Back to Active Assignments
        </button>
      )}
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
        <ul className={`mt-5 grid gap-4 ${selectedId ? '' : 'md:grid-cols-2 xl:grid-cols-3'}`}>
          {visibleRequests.map((request) => (
            <li
              key={request.id}
              className="flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-5 text-sm"
            >
              <StatusLabel status={request.status} />
              {selectedId ? (
                <h2 ref={detailsHeading} tabIndex={-1} className="mt-3 break-words">
                  {titleOf(request.name)}
                </h2>
              ) : (
                <h3 className="mt-3 break-words text-lg font-semibold tracking-normal">
                  {titleOf(request.name)}
                </h3>
              )}
              <dl className="mt-4 flex-1 space-y-3">
                <div>
                  <dt className="text-xs text-slate-500">Schedule · Singapore time</dt>
                  <dd className="mt-1">
                    {request.start_at
                      ? formatDisplayTime(request.start_at)
                      : 'Date to be confirmed'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Coordinator</dt>
                  <dd className="mt-1 break-words">{request.coordinator_email ?? 'Unassigned'}</dd>
                </div>
              </dl>
              {selectedId ? (
                <div className="mt-6 border-t border-slate-100 pt-5">
                  <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
                    <dt className="text-xs text-slate-500">Event ID</dt>
                    <dd className="break-all font-medium text-slate-700">{request.id}</dd>
                    <dt className="text-xs text-slate-500">Status</dt>
                    <dd className="font-medium text-slate-700">{request.status}</dd>
                    <dt className="text-xs text-slate-500">Organiser</dt>
                    <dd className="break-words font-medium text-slate-700">
                      {request.organiser_email}
                    </dd>
                    <dt className="text-xs text-slate-500">Start</dt>
                    <dd className="font-medium text-slate-700">{request.start_at ?? '—'}</dd>
                    <dt className="text-xs text-slate-500">End</dt>
                    <dd className="font-medium text-slate-700">{request.end_at ?? '—'}</dd>
                    <dt className="text-xs text-slate-500">Coordinator</dt>
                    <dd className="break-words font-medium text-slate-700">
                      {request.coordinator_email ?? 'Unassigned'}
                    </dd>
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
                    onClick={() =>
                      setExpanded({ ...expanded, [request.id]: !expanded[request.id] })
                    }
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
                </div>
              ) : (
                <button
                  type="button"
                  id={`view-assignment-${request.id}`}
                  className="cs-button-secondary mt-5 w-full"
                  aria-label={`View details for ${titleOf(request.name)}`}
                  onClick={(event) => {
                    openedFrom.current = event.currentTarget.id
                    setSelectedId(request.id)
                  }}
                >
                  View details →
                </button>
              )}
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

function StatusLabel({ status }: { status: string }) {
  const styles: Record<string, string> = {
    submitted: 'bg-amber-50 text-amber-800',
    approved: 'bg-sky-50 text-sky-800',
    confirmed: 'bg-emerald-50 text-emerald-800',
    completed: 'bg-indigo-50 text-indigo-800',
  }
  return (
    <span
      className={`inline-flex self-start rounded-md px-2 py-0.5 text-xs font-medium ${styles[status] ?? 'bg-slate-100 text-slate-700'}`}
    >
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  )
}

function titleOf(name: string | null) {
  return name ?? 'Untitled request'
}
