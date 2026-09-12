import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  type EventRequest,
  FIELD_LABELS,
  type FieldProblem,
  listMyEventRequests,
  submitEventRequest,
  SubmissionRejectedError,
} from '../api/eventRequests'
import { useAuth } from '../auth/context'

/**
 * SCRUM-46: an organiser's event requests, each with a Submit action while it is a draft.
 * Submitting a complete draft shows confirmation (AC1); an incomplete one lists the fields
 * to fix (AC2); a submitted request shows it is locked (AC3). No business rules live here —
 * the API decides, this component only shows the outcome.
 */
export default function MyEventRequests() {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [outcome, setOutcome] = useState<Outcome | null>(null)

  const requests = useQuery({
    queryKey: ['event-requests', 'mine'],
    queryFn: () => listMyEventRequests(token ?? ''),
    enabled: token !== null,
  })

  const submit = useMutation({
    mutationFn: (id: string) => submitEventRequest(token ?? '', id),
    onSuccess: (request) => {
      setOutcome({ kind: 'submitted', request })
      void queryClient.invalidateQueries({ queryKey: ['event-requests', 'mine'] })
    },
    onError: (error, id) => {
      if (error instanceof SubmissionRejectedError) {
        setOutcome({ kind: 'incomplete', id, problems: error.problems })
      } else {
        setOutcome({ kind: 'failed', message: error.message })
      }
    },
  })

  return (
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">My event requests</h2>

      {requests.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {requests.isError && (
        <p className="mt-2 text-sm text-red-600" role="alert">
          Could not load your requests: {requests.error.message}
        </p>
      )}
      {requests.data && requests.data.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">You have no event requests yet.</p>
      )}

      {requests.data && requests.data.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-200">
          {requests.data.map((request) => (
            <li key={request.id} className="flex items-center justify-between gap-4 py-3">
              <div>
                <p className="font-medium">{request.name ?? 'Untitled request'}</p>
                <p className="text-sm text-slate-500">
                  <StatusLabel status={request.status} />
                </p>
              </div>
              {request.status === 'draft' ? (
                <button
                  type="button"
                  onClick={() => submit.mutate(request.id)}
                  disabled={submit.isPending}
                  className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
                >
                  Submit for review
                </button>
              ) : (
                <span className="text-sm text-slate-500">
                  Locked — ask your coordinator to request changes
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {outcome && <OutcomeMessage outcome={outcome} requests={requests.data ?? []} />}
    </section>
  )
}

type Outcome =
  | { kind: 'submitted'; request: EventRequest }
  | { kind: 'incomplete'; id: string; problems: FieldProblem[] }
  | { kind: 'failed'; message: string }

function StatusLabel({ status }: { status: EventRequest['status'] }) {
  return status === 'submitted' ? <>Submitted</> : <>Draft</>
}

function OutcomeMessage({ outcome, requests }: { outcome: Outcome; requests: EventRequest[] }) {
  if (outcome.kind === 'submitted') {
    return (
      <p role="status" className="mt-4 rounded bg-green-50 p-3 text-sm text-green-800">
        “{outcome.request.name}” has been submitted for review. Its status is now Submitted.
      </p>
    )
  }
  if (outcome.kind === 'incomplete') {
    const name = requests.find((r) => r.id === outcome.id)?.name ?? 'This request'
    return (
      <div role="alert" className="mt-4 rounded bg-amber-50 p-3 text-sm text-amber-900">
        <p>“{name}” cannot be submitted yet. Please correct:</p>
        <ul className="mt-2 list-disc pl-5">
          {outcome.problems.map((problem) => (
            <li key={problem.field}>
              {FIELD_LABELS[problem.field] ?? problem.field} {problem.reason}
            </li>
          ))}
        </ul>
      </div>
    )
  }
  return (
    <p role="alert" className="mt-4 rounded bg-red-50 p-3 text-sm text-red-800">
      {outcome.message}
    </p>
  )
}
