import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  type EventRequest,
  FIELD_LABELS,
  type FieldProblem,
  getEventRequest,
  listMyEventRequests,
  submitEventRequest,
  SubmissionRejectedError,
} from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'
import { acceptsChangeRequest } from '../validation/eventChange'
import { AssignmentHistoryToggle } from './AssignmentHistory'
import CancellationRecord from './CancellationRecord'
import ChangeRequestList from './ChangeRequestList'
import ClosureRecord from './ClosureRecord'
import ProposeChange from './ProposeChange'
import RegistrationIntakeControls from './RegistrationIntakeControls'
import RegistrationReviewList from './RegistrationReviewList'
import RequestCancellation from './RequestCancellation'

/**
 * SCRUM-46: an organiser's event requests, each with a Submit action while it is a draft.
 * Submitting a complete draft shows confirmation (AC1); an incomplete one lists the fields
 * to fix (AC2); a submitted request shows it is locked (AC3). No business rules live here —
 * the API decides, this component only shows the outcome.
 *
 * SCRUM-35: what to offer comes from the request's `status_permits`, so the status machine
 * stays the only place that knows what a status permits. Submit and edit are separate
 * permissions, so the locked message keys off `edit`, not off the absence of `submit`.
 * SCRUM-46/SCRUM-29: an organiser's event requests. Draft completeness and submission
 * rules live in the API; this component only sends organiser actions and shows outcomes.
 * SCRUM-112 (ADR-0039): drafts are no longer shared within an organisation, so there is no
 * separate organisation drafts list; the organiser's own drafts are listed here.
 */
export default function MyEventRequests({
  onEditDraft = () => {},
}: {
  /** Hands a draft to the form above, so there is only ever one form on the page. */
  onEditDraft?: (request: EventRequest) => void
} = {}) {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [proposing, setProposing] = useState<string | null>(null)

  // The token is part of the key: the list is per-user, and without it a sign-out and
  // sign-in as someone else on the same tab could briefly show the previous user's data
  // from the cache.
  const queryKey = ['event-requests', 'mine', token]
  const requests = useQuery({
    queryKey,
    queryFn: () => listMyEventRequests(token ?? ''),
    enabled: token !== null,
  })

  // The mutation variable carries the request id plus its current name, so validation
  // feedback can name the request even when the API refuses submission.
  const submit = useMutation({
    mutationFn: (request: SubmitTarget) => submitEventRequest(token ?? '', request.id),
    onSuccess: (request) => {
      setOutcome({ kind: 'submitted', request })
      void queryClient.invalidateQueries({ queryKey })
      void queryClient.invalidateQueries({ queryKey: ['organisation-calendar', token] })
    },
    onError: (error, request) => {
      if (error instanceof SubmissionRejectedError) {
        setOutcome({ kind: 'incomplete', name: request.name, problems: error.problems })
      } else {
        setOutcome({ kind: 'failed', message: error.message })
      }
    },
  })

  // The list carries a summary, so the full request is fetched before the form above is
  // filled in. Editing happens there, not here: one form on the page, not two.
  const reopen = useMutation({
    mutationFn: (id: string) => getEventRequest(token ?? '', id),
    onSuccess: (request) => {
      setOutcome(null)
      onEditDraft(request)
    },
    onError: (error) => {
      setOutcome({ kind: 'failed', message: error.message })
    },
  })

  return (
    <section className="mt-6 space-y-4">
      <div className="rounded-lg border border-slate-200 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-medium">My event requests</h2>
        </div>

        {requests.isPending && <p className="mt-2 text-sm">Loading...</p>}
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
              <li
                key={request.id}
                className="flex flex-wrap items-center justify-between gap-4 py-3"
              >
                <div>
                  <p className="font-medium">{titleOf(request)}</p>
                  <p className="text-sm text-slate-500">
                    <StatusLabel status={request.status} />
                  </p>
                  {request.status === 'rejected' && request.rejection_reason && (
                    <p className="mt-1 text-sm text-red-700">
                      Rejection reason: {request.rejection_reason}
                    </p>
                  )}
                  {(request.status === 'draft' || request.status === 'rejected') && (
                    <p className="mt-1 text-xs text-slate-500">
                      To change this request, edit it and submit it again.
                    </p>
                  )}
                </div>
                {request.status_permits.includes('edit') ? (
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => reopen.mutate(request.id)}
                      disabled={reopen.isPending}
                      aria-label={`Edit draft ${titleOf(request)}`}
                      className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
                    >
                      Edit draft
                    </button>
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
                  </div>
                ) : acceptsChangeRequest(request.status) ? (
                  // SCRUM-37: after submission, significant changes are proposed, not edited.
                  <button
                    type="button"
                    onClick={() => setProposing(request.id)}
                    aria-label={`Propose a change to ${titleOf(request)}`}
                    className="rounded border border-slate-300 px-3 py-1.5 text-sm"
                  >
                    Propose a change
                  </button>
                ) : request.status === 'cancelled' ? null : (
                  <span className="text-sm text-slate-500">
                    Locked - ask your coordinator to request changes
                  </span>
                )}
                {acceptsChangeRequest(request.status) && (
                  <div className="w-full">
                    {proposing === request.id && (
                      <ProposeChange eventId={request.id} onClose={() => setProposing(null)} />
                    )}
                    <ChangeRequestList eventId={request.id} />
                  </div>
                )}
                {request.status === 'confirmed' && (
                  <div className="w-full">
                    <RegistrationIntakeControls event={request} />
                    <RegistrationReviewList eventId={request.id} canDecide />
                  </div>
                )}
                {/* SCRUM-86 AC4: the owning Organiser reads the closure record. */}
                {request.status === 'completed' && (
                  <div className="w-full">
                    <ClosureRecord eventId={request.id} />
                  </div>
                )}
                {/* SCRUM-115: ask the Coordinator to cancel, or see why it was cancelled. */}
                {request.status_permits.includes('cancel') && (
                  <div className="w-full">
                    <RequestCancellation event={request} />
                  </div>
                )}
                {request.status === 'cancelled' && (
                  <div className="w-full">
                    <CancellationRecord eventId={request.id} />
                  </div>
                )}
                {/* SCRUM-105: a draft has never been submitted, so it has no history. */}
                {request.status !== 'draft' && (
                  <div className="w-full">
                    <AssignmentHistoryToggle requestId={request.id} requestName={request.name} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {outcome && <OutcomeMessage outcome={outcome} />}
    </section>
  )
}

type Outcome =
  | { kind: 'incomplete'; name: string | null; problems: FieldProblem[] }
  | { kind: 'submitted'; request: EventRequest }
  | { kind: 'failed'; message: string }

type SubmitTarget = Pick<EventRequest, 'id' | 'name'>

function StatusLabel({ status }: { status: EventRequest['status'] }) {
  if (status === 'submitted') return <>Submitted</>
  if (status === 'approved') return <>Approved</>
  if (status === 'rejected') return <>Rejected</>
  if (status === 'confirmed') return <>Confirmed</>
  if (status === 'completed') return <>Completed</>
  if (status === 'cancelled') return <>Cancelled</>
  return <>Draft</>
}

function OutcomeMessage({ outcome }: { outcome: Outcome }) {
  if (outcome.kind === 'submitted') {
    return (
      <p role="status" className="rounded bg-green-50 p-3 text-sm text-green-800">
        “{titleOf(outcome.request)}” has been submitted for review. Its status is now Submitted.
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
    <p role="alert" className="rounded bg-red-50 p-3 text-sm text-red-800">
      {outcome.message}
    </p>
  )
}

function titleOf(request: EventRequest): string {
  return request.name ?? 'Untitled request'
}
