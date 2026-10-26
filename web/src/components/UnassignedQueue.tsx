import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  assignEventRequest,
  listAssignableCoordinators,
  listUnassignedEventRequests,
} from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'
import { EventHistoryToggle } from './EventHistory'

/**
 * SCRUM-101: the Coordinator Lead unassigned queue. Read-only triage list showing every
 * required field (event ID, name, organiser, start/end, expected attendance, submission
 * time) oldest submission first. SCRUM-98 adds assignment: the Lead picks an eligible
 * coordinator per row, confirms, and the request leaves the queue.
 */
export default function UnassignedQueue() {
  const { token } = useAuth()
  const client = useQueryClient()
  const [selected, setSelected] = useState<Record<string, string>>({})
  const [outcome, setOutcome] = useState<string | null>(null)
  const queueKey = ['event-requests', 'unassigned', token]
  // SCRUM-100: the active-assignment overview caches its own snapshot. Assigning
  // moves the row there, so the overview must refetch too — otherwise it keeps
  // showing the stale `coordinator_id: null` ("Unassigned") until a manual refresh.
  const activeKey = ['event-requests', 'active-assignments', token]
  const queue = useQuery({
    queryKey: queueKey,
    queryFn: () => listUnassignedEventRequests(token ?? ''),
    enabled: token !== null,
  })
  const coordinators = useQuery({
    queryKey: ['event-requests', 'assignable-coordinators', token],
    queryFn: () => listAssignableCoordinators(token ?? ''),
    enabled: token !== null,
  })
  const assign = useMutation({
    mutationFn: ({ id, coordinatorId }: { id: string; coordinatorId: string }) =>
      assignEventRequest(token ?? '', id, coordinatorId),
    onSuccess: (request) => {
      setOutcome(`“${request.name ?? request.id}” has been assigned.`)
      void client.invalidateQueries({ queryKey: queueKey })
      void client.invalidateQueries({ queryKey: activeKey })
    },
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
                <dd>{request.organiser_email}</dd>
                <dt className="font-medium text-slate-500">Start</dt>
                <dd>{request.start_at ?? '—'}</dd>
                <dt className="font-medium text-slate-500">End</dt>
                <dd>{request.end_at ?? '—'}</dd>
                <dt className="font-medium text-slate-500">Expected attendance</dt>
                <dd>{request.expected_attendance ?? '—'}</dd>
                <dt className="font-medium text-slate-500">Submitted</dt>
                <dd>{request.submitted_at ?? '—'}</dd>
              </dl>
              <div className="mt-2 flex items-center gap-2">
                <label className="text-slate-500">
                  Coordinator{' '}
                  <select
                    aria-label={`Coordinator for ${request.name ?? request.id}`}
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
                  disabled={!selected[request.id] || assign.isPending}
                  onClick={() =>
                    selected[request.id] &&
                    assign.mutate({ id: request.id, coordinatorId: selected[request.id] })
                  }
                  className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
                >
                  Assign
                </button>
              </div>
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
      {assign.isError && (
        <p role="alert" className="mt-4 text-sm text-red-600">
          The assignment could not be recorded: {assign.error.message}
        </p>
      )}
    </section>
  )
}
