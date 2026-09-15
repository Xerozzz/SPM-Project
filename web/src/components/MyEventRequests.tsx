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
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-46: an organiser's event requests, each with a Submit action while it is a draft.
 * Submitting a complete draft shows confirmation (AC1); an incomplete one lists the fields
 * to fix (AC2); a submitted request shows it is locked (AC3). No business rules live here —
 * the API decides, this component only shows the outcome.
 *
 * SCRUM-35: what to offer comes from the request's `status_permits`, so the status machine
 * stays the only place that knows what a status permits. Submit and edit are separate
 * permissions, so the locked message keys off `edit`, not off the absence of `submit`.
 */
export default function MyEventRequests() {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [outcome, setOutcome] = useState<Outcome | null>(null)

  // The token is part of the key: the list is per-user, and without it a sign-out and
  // sign-in as someone else on the same tab could briefly show the previous user's data
  // from the cache.
  const queryKey = ['event-requests', 'mine', token]
  const requests = useQuery({
    queryKey,
    queryFn: () => listMyEventRequests(token ?? ''),
    enabled: token !== null,
  })

  // The mutation variable is the whole request, so the outcome message can name it
  // without looking it up in the list again afterwards.
  const submit = useMutation({
    mutationFn: (request: EventRequest) => submitEventRequest(token ?? '', request.id),
    onSuccess: (submitted) => {
      setOutcome({ kind: 'submitted', name: submitted.name })
      void queryClient.invalidateQueries({ queryKey })
    },
    onError: (error, request) => {
      if (error instanceof SubmissionRejectedError) {
        setOutcome({ kind: 'incomplete', name: request.name, problems: error.problems })
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
                  {request.status === 'submitted' ? 'Submitted' : 'Draft'}
                </p>
              </div>
              {request.status_permits.includes('submit') && (
                <button
                  type="button"
                  onClick={() => submit.mutate(request)}
                  disabled={submit.isPending}
                  className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
                >
                  Submit for review
                </button>
              )}
              {!request.status_permits.includes('edit') && (
                <span className="text-sm text-slate-500">
                  Locked — ask your coordinator to request changes
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {outcome && <OutcomeMessage outcome={outcome} />}
    </section>
  )
}

type Outcome =
  | { kind: 'submitted'; name: string | null }
  | { kind: 'incomplete'; name: string | null; problems: FieldProblem[] }
  | { kind: 'failed'; message: string }

function OutcomeMessage({ outcome }: { outcome: Outcome }) {
  if (outcome.kind === 'submitted') {
    return (
      <p role="status" className="mt-4 rounded bg-green-50 p-3 text-sm text-green-800">
        “{outcome.name ?? 'Your request'}” has been submitted for review. Its status is now
        Submitted.
      </p>
    )
  }
  if (outcome.kind === 'incomplete') {
    return (
      <div role="alert" className="mt-4 rounded bg-amber-50 p-3 text-sm text-amber-900">
        <p>“{outcome.name ?? 'This request'}” cannot be submitted yet. Please correct:</p>
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
