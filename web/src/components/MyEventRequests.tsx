import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import {
  type EventRequest,
  FIELD_LABELS,
  type FieldProblem,
  getEventRequest,
  listMyEventRequests,
  submitEventRequest,
  SubmissionRejectedError,
} from '../api/eventRequests'
import { formatDateRange, formatDisplayTime } from '../presentation/dates'
import { matchesSearch } from '../presentation/search'
import { useAuth } from '../auth/useAuth'
import { useEventSelection } from '../hooks/useEventSelection'
import { acceptsChangeRequest } from '../validation/eventChange'
import { AssignmentHistoryToggle } from './AssignmentHistory'
import CancellationRecord from './CancellationRecord'
import ChangeRequestList from './ChangeRequestList'
import ClosureRecord from './ClosureRecord'
import { EventHistoryToggle } from './EventHistory'
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
  onCreateEvent = () => {},
  targetEventId = null,
}: {
  /** Opens the existing form with the full saved draft. */
  onEditDraft?: (request: EventRequest) => void
  onCreateEvent?: () => void
  targetEventId?: string | null
} = {}) {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [proposing, setProposing] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [selectedStatus, setSelectedStatus] = useState<EventRequest['status'] | 'all'>('all')
  const detailsHeading = useRef<HTMLHeadingElement>(null)
  const openedFrom = useRef<string | null>(null)

  // The token is part of the key: the list is per-user, and without it a sign-out and
  // sign-in as someone else on the same tab could briefly show the previous user's data
  // from the cache.
  const queryKey = ['event-requests', 'mine', token]
  const requests = useQuery({
    queryKey,
    queryFn: () => listMyEventRequests(token ?? ''),
    enabled: token !== null,
  })
  const [selectedId, setSelectedId] = useEventSelection(targetEventId, requests.data)
  const groupedRequests = STATUS_ORDER.map((status) => ({
    status,
    requests: requests.data?.filter((request) => request.status === status) ?? [],
  })).filter((group) => group.requests.length > 0)
  const visibleRequests =
    requests.data?.filter((request) =>
      selectedId
        ? request.id === selectedId
        : (selectedStatus === 'all' || request.status === selectedStatus) &&
          matchesSearch(search, request.name, request.venue_requirement),
    ) ?? []
  useEffect(() => {
    if (selectedId) detailsHeading.current?.focus()
    else document.getElementById(openedFrom.current ?? '')?.focus()
  }, [selectedId])

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

  // Fetch the full saved request before opening the existing editing form.
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
    <section className="mt-0 space-y-4">
      {selectedId ? (
        <button type="button" className="cs-button-secondary" onClick={() => setSelectedId(null)}>
          ← Back to My Events
        </button>
      ) : (
        <div className="flex flex-wrap items-end justify-between gap-3">
          <label className="block max-w-md flex-1 text-sm font-medium">
            Search my events
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Event name or venue"
              className="cs-field"
            />
          </label>
          <button type="button" className="cs-button" onClick={onCreateEvent}>
            + Create event
          </button>
        </div>
      )}
      <div>
        {requests.isPending && <p className="mt-2 text-sm">Loading...</p>}
        {requests.isError && (
          <p className="mt-2 text-sm text-red-600" role="alert">
            Could not load your requests: {requests.error.message}
          </p>
        )}
        {requests.data && requests.data.length === 0 && (
          <p className="mt-2 text-sm text-slate-500">
            No events yet. Create your first event to get started.
          </p>
        )}

        {requests.data && requests.data.length > 0 && (
          <div className="mt-5">
            {!selectedId && (
              <div
                role="group"
                aria-label="Filter events by status"
                className="flex gap-2 overflow-x-auto border-b border-slate-200 pb-3"
              >
                {[{ status: 'all' as const, requests: requests.data }, ...groupedRequests].map(
                  (group) => (
                    <button
                      key={group.status}
                      type="button"
                      aria-pressed={selectedStatus === group.status}
                      onClick={() => setSelectedStatus(group.status)}
                      className={`shrink-0 rounded-lg px-4 py-2 text-sm font-medium ${selectedStatus === group.status ? 'bg-[#202124] text-white' : 'bg-white text-slate-600 hover:bg-slate-100'}`}
                    >
                      {group.status === 'all' ? 'All events' : STATUS_TITLES[group.status]}{' '}
                      <span className="ml-1 opacity-70">{group.requests.length}</span>
                    </button>
                  ),
                )}
              </div>
            )}
            {visibleRequests.length === 0 && (
              <p className="py-8 text-sm text-slate-500">
                No events match your search or status filter.
              </p>
            )}
            <ul className={`mt-5 grid gap-4 ${selectedId ? '' : 'md:grid-cols-2 xl:grid-cols-3'}`}>
              {visibleRequests.map((request) => (
                <li
                  key={request.id}
                  className="flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-5"
                >
                  <StatusLabel status={request.status} />
                  {selectedId ? (
                    <h2 ref={detailsHeading} tabIndex={-1} className="mt-3 break-words">
                      {titleOf(request)}
                    </h2>
                  ) : (
                    <h3 className="mt-3 break-words text-lg font-semibold tracking-normal">
                      {titleOf(request)}
                    </h3>
                  )}
                  <dl className="mt-4 flex-1 space-y-3 text-sm">
                    <div>
                      <dt className="text-xs text-slate-500">Schedule · Singapore time</dt>
                      <dd className="mt-1">
                        {request.start_at
                          ? request.end_at
                            ? formatDateRange(request.start_at, request.end_at)
                            : formatDisplayTime(request.start_at)
                          : 'Date to be confirmed'}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-slate-500">Venue preference</dt>
                      <dd className="mt-1 break-words">
                        {request.venue_requirement || 'Not specified'}
                      </dd>
                    </div>
                    {selectedId && (
                      <div>
                        <dt className="text-xs text-slate-500">Expected attendance</dt>
                        <dd className="mt-1">{request.expected_attendance ?? 'Not specified'}</dd>
                      </div>
                    )}
                  </dl>
                  {!selectedId ? (
                    <button
                      type="button"
                      id={`view-event-${request.id}`}
                      className="cs-button-secondary mt-5 w-full"
                      aria-label={`View details for ${titleOf(request)}`}
                      onClick={(event) => {
                        openedFrom.current = event.currentTarget.id
                        setOutcome(null)
                        setProposing(null)
                        setSelectedId(request.id)
                      }}
                    >
                      View details →
                    </button>
                  ) : (
                    <div className="mt-6 space-y-5 border-t border-slate-100 pt-5">
                      <p className="whitespace-pre-wrap break-words text-sm text-slate-600">
                        {request.description || 'No description added yet.'}
                      </p>
                      {request.status === 'rejected' && request.rejection_reason && (
                        <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
                          Rejection reason: {request.rejection_reason}
                        </p>
                      )}
                      {(request.status === 'draft' || request.status === 'rejected') && (
                        <p className="text-sm text-slate-500">
                          To change this request, edit it and submit it again.
                        </p>
                      )}
                      <section aria-label="Manage event" className="space-y-5">
                        <div className="mt-4">
                          {request.status_permits.includes('edit') ? (
                            <div className="flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => reopen.mutate(request.id)}
                                disabled={reopen.isPending}
                                aria-label={`Edit draft ${titleOf(request)}`}
                                className="cs-button-secondary"
                              >
                                Edit draft
                              </button>
                              {request.status_permits.includes('submit') && (
                                <button
                                  type="button"
                                  onClick={() => submit.mutate(request)}
                                  disabled={submit.isPending}
                                  className="cs-button"
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
                              className="cs-button-secondary"
                            >
                              Propose a change
                            </button>
                          ) : request.status === 'cancelled' ? null : (
                            <span className="text-sm text-slate-500">
                              Locked - ask your coordinator to request changes
                            </span>
                          )}
                        </div>
                        {acceptsChangeRequest(request.status) && (
                          <div className="w-full">
                            {proposing === request.id && (
                              <ProposeChange
                                eventId={request.id}
                                onClose={() => setProposing(null)}
                              />
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
                            <AssignmentHistoryToggle
                              requestId={request.id}
                              requestName={request.name}
                            />
                          </div>
                        )}
                        {/* SCRUM-88: this list holds only the viewer's own requests, drafts included. */}
                        <div className="w-full">
                          <EventHistoryToggle eventId={request.id} eventName={request.name} />
                        </div>
                      </section>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
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

const STATUS_ORDER: EventRequest['status'][] = [
  'draft',
  'submitted',
  'approved',
  'confirmed',
  'completed',
  'rejected',
  'cancelled',
]

const STATUS_TITLES: Record<EventRequest['status'], string> = {
  draft: 'Drafts',
  submitted: 'Submitted',
  approved: 'Approved',
  confirmed: 'Confirmed',
  completed: 'Completed',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
}

function StatusLabel({ status }: { status: EventRequest['status'] }) {
  const styles: Record<EventRequest['status'], string> = {
    draft: 'bg-slate-100 text-slate-700',
    submitted: 'bg-amber-50 text-amber-800',
    approved: 'bg-sky-50 text-sky-800',
    rejected: 'bg-red-50 text-red-800',
    confirmed: 'bg-emerald-50 text-emerald-800',
    completed: 'bg-indigo-50 text-indigo-800',
    cancelled: 'bg-slate-200 text-slate-700',
  }
  return (
    <span
      className={`inline-flex self-start rounded-md px-2 py-0.5 text-xs font-medium ${styles[status]}`}
    >
      {status === 'draft' ? 'Draft' : STATUS_TITLES[status]}
    </span>
  )
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
