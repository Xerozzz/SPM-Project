import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import {
  approveEventRequest,
  type EventRequest,
  listBookableEventRequests,
  listConfirmedEventRequests,
  listRequestsForReview,
  rejectEventRequest,
} from '../api/eventRequests'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'
import { hasReviewNote } from '../validation/eventRequestReview'
import { acceptsOrdinaryUpdate } from '../validation/planningInfo'
import { AssignmentHistoryToggle } from './AssignmentHistory'
import CancelEvent from './CancelEvent'
import ChangeRequestList from './ChangeRequestList'
import ClarificationThread from './ClarificationThread'
import CompleteEvent from './CompleteEvent'
import ConfirmEvent from './ConfirmEvent'
import ReminderSchedule from './ReminderSchedule'
import { EventHistoryToggle } from './EventHistory'
import EventEquipmentRequirements from './EventEquipmentRequirements'
import PlanningInfoEditor from './PlanningInfoEditor'
import RegistrationSettingsCard from './RegistrationSettingsCard'
import RegistrationReviewList from './RegistrationReviewList'
import VenueBookingRequest from './VenueBookingRequest'

/**
 * SCRUM-104: the Coordinator list holds only events currently assigned to the viewer.
 * The API scopes `/reviewable` by the authenticated Coordinator ID and refuses
 * unassigned or other Coordinators' events, so every card here is actionable — there
 * is no read-only state for someone else's event. `status_permits` still decides which
 * buttons the status allows; assignment is settled before the response arrives.
 */
export default function EventRequestReview() {
  const { token } = useAuth()
  const client = useQueryClient()
  const [reason, setReason] = useState<Record<string, string>>({})
  const [outcome, setOutcome] = useState<string | null>(null)
  const [selectedStatus, setSelectedStatus] = useState<EventRequest['status'] | 'all'>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const openedFrom = useRef<string | null>(null)
  const detailsHeading = useRef<HTMLHeadingElement>(null)
  const queryKey = ['event-requests', 'coordinator', token]
  const requests = useQuery({
    queryKey,
    queryFn: async () => {
      const [reviewable, bookable, confirmed] = await Promise.all([
        listRequestsForReview(token ?? ''),
        listBookableEventRequests(token ?? ''),
        listConfirmedEventRequests(token ?? ''),
      ])
      // The routes return disjoint Submitted, Approved, and Confirmed sets.
      return [...reviewable, ...bookable, ...confirmed]
    },
    enabled: token !== null,
  })
  const refresh = () => void client.invalidateQueries({ queryKey })
  const groupedRequests = ['submitted', 'approved', 'confirmed']
    .map((status) => ({
      status: status as EventRequest['status'],
      requests: requests.data?.filter((request) => request.status === status) ?? [],
    }))
    .filter((group) => group.requests.length > 0)
  const visibleRequests =
    requests.data?.filter((request) =>
      selectedId
        ? request.id === selectedId
        : selectedStatus === 'all' || request.status === selectedStatus,
    ) ?? []

  useEffect(() => {
    if (selectedId) detailsHeading.current?.focus()
    else document.getElementById(openedFrom.current ?? '')?.focus()
  }, [selectedId])
  const approve = useMutation({
    mutationFn: (id: string) => approveEventRequest(token ?? '', id),
    onSuccess: (request) => {
      setOutcome(`“${request.name}” has been approved.`)
      refresh()
    },
  })
  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      rejectEventRequest(token ?? '', id, reason),
    onSuccess: (request) => {
      setOutcome(`“${request.name}” has been rejected.`)
      refresh()
    },
  })
  return (
    <section>
      {selectedId && (
        <button type="button" className="cs-button-secondary" onClick={() => setSelectedId(null)}>
          ← Back to Review Queue
        </button>
      )}
      {requests.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {requests.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          Could not load requests: {requests.error.message}
        </p>
      )}
      {requests.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No coordinator events are available.</p>
      )}
      {requests.data && requests.data.length > 0 && (
        <div className="mt-5">
          {!selectedId && (
            <div
              role="group"
              aria-label="Filter coordinator events by status"
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
                    {group.status === 'all' ? 'All events' : statusTitle(group.status)}{' '}
                    <span className="ml-1 opacity-70">{group.requests.length}</span>
                  </button>
                ),
              )}
            </div>
          )}
          {visibleRequests.length === 0 && (
            <p className="py-8 text-sm text-slate-500">
              No events in this status. Choose All events to see the rest.
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
                        ? formatSingaporeTime(request.start_at)
                        : 'Date to be confirmed'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">Venue preference</dt>
                    <dd className="mt-1 break-words">
                      {request.venue_requirement || 'Not specified'}
                    </dd>
                  </div>
                </dl>
                {selectedId ? (
                  <ReviewDetails
                    request={request}
                    reason={reason[request.id] ?? ''}
                    onReasonChange={(value) => setReason({ ...reason, [request.id]: value })}
                    onApprove={() => approve.mutate(request.id)}
                    onReject={() =>
                      reject.mutate({ id: request.id, reason: reason[request.id] ?? '' })
                    }
                    onConfirmed={(message) => {
                      setOutcome(message)
                      refresh()
                    }}
                    pending={approve.isPending || reject.isPending}
                  />
                ) : (
                  <button
                    type="button"
                    id={`view-review-${request.id}`}
                    className="cs-button-secondary mt-5 w-full"
                    aria-label={`View details for ${titleOf(request)}`}
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
        </div>
      )}
      {outcome && (
        <p role="status" className="mt-4 rounded bg-green-50 p-3 text-sm text-green-800">
          {outcome}
        </p>
      )}
      {(approve.isError || reject.isError) && (
        <p role="alert" className="mt-4 text-sm text-red-600">
          The decision could not be recorded.
        </p>
      )}
    </section>
  )
}

function ReviewDetails({
  request,
  reason,
  onReasonChange,
  onApprove,
  onReject,
  onConfirmed,
  pending,
}: {
  request: EventRequest
  reason: string
  onReasonChange: (value: string) => void
  onApprove: () => void
  onReject: () => void
  onConfirmed: (message: string) => void
  pending: boolean
}) {
  return (
    <div className="mt-6 border-t border-slate-100 pt-5">
      <p className="mt-1 text-sm">{request.purpose}</p>
      <p className="mt-1 text-sm">{request.description}</p>
      <dl className="mt-2 text-sm text-slate-600">
        <div>
          <dt className="inline font-medium">When: </dt>
          <dd className="inline">
            {request.start_at} to {request.end_at}
          </dd>
        </div>
        <div>
          <dt className="inline font-medium">Attendance: </dt>
          <dd className="inline">{request.expected_attendance}</dd>
        </div>
        <div>
          <dt className="inline font-medium">Venue: </dt>
          <dd className="inline">{request.venue_requirement}</dd>
        </div>
        <div>
          <dt className="inline font-medium">Accessibility: </dt>
          <dd className="inline">{request.accessibility_requirement}</dd>
        </div>
        <div>
          {/* SCRUM-43: what the organiser asked for, which is not what the event needs
              now. The Coordinator maintains the requirements in the editor below and
              nothing writes back to this field (ADR-0033), so calling it "Equipment"
              put a stale answer directly above the live one: remove the projector and
              the card still said the event wanted one. */}
          <dt className="inline font-medium">Equipment requested: </dt>
          <dd className="inline">{request.equipment_requirement}</dd>
        </div>
        <div>
          <dt className="inline font-medium">Layout: </dt>
          <dd className="inline">{request.layout_requirement}</dd>
        </div>
        <div>
          <dt className="inline font-medium">Registration: </dt>
          <dd className="inline">{request.registration_requirement}</dd>
        </div>
      </dl>
      <label className="mt-3 block text-sm font-medium" htmlFor={`reason-${request.id}`}>
        Coordinator note
      </label>
      <textarea
        id={`reason-${request.id}`}
        value={reason}
        onChange={(event) => onReasonChange(event.target.value)}
        className="mt-1 w-full rounded border border-slate-300 p-2 text-sm"
      />
      <div className="mt-3 flex gap-2">
        {request.status_permits.includes('approve') && (
          <button
            type="button"
            onClick={onApprove}
            disabled={pending}
            className="rounded bg-green-700 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Approve
          </button>
        )}
        {request.status_permits.includes('reject') && (
          <button
            type="button"
            onClick={onReject}
            disabled={pending || !hasReviewNote(reason)}
            className="rounded bg-red-700 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Reject
          </button>
        )}
      </div>
      {acceptsOrdinaryUpdate(request.status) && <PlanningInfoEditor request={request} />}
      {/* SCRUM-37 AC6 and SCRUM-47: change requests, current next to proposed, decided here. */}
      <ChangeRequestList eventId={request.id} canDecide />
      {/* SCRUM-105: this list holds only events assigned to the viewer (SCRUM-104). */}
      <AssignmentHistoryToggle requestId={request.id} requestName={request.name} />
      {/* SCRUM-88: likewise only events currently assigned to the viewer. */}
      <EventHistoryToggle eventId={request.id} eventName={request.name} />
      <ClarificationThread
        eventRequestId={request.id}
        canRequest={request.status === 'submitted'}
      />
      {request.status === 'approved' && <VenueBookingRequest event={request} />}
      {/* SCRUM-43 AC2: while the event is being planned. The assignment half of AC10 is
          no longer checked here: SCRUM-104 made this list hold only events assigned to
          the viewer, and `EventAccess.MAINTAIN_EQUIPMENT` is what actually refuses
          anyone else on the API. */}
      {request.status === 'approved' && <EventEquipmentRequirements event={request} />}
      {/* SCRUM-80: the assigned Coordinator commits the event once every arrangement
          and the Safety Officer's approval are in order. */}
      {/* Only while the event is still being planned: `list_bookable_for_coordinator`
          holds Approved events, so a confirmed one leaves this list altogether. */}
      {request.status === 'approved' && <ConfirmEvent event={request} onConfirmed={onConfirmed} />}
      {/* SCRUM-85: the Coordinator's own reminders about outstanding arrangements. */}
      {request.status === 'approved' && <ReminderSchedule event={request} />}
      {request.status === 'confirmed' && (
        <>
          <RegistrationSettingsCard event={request} />
          <RegistrationReviewList eventId={request.id} />
        </>
      )}
      {/* SCRUM-86: close the event once it has run, then keep its record correctable. */}
      {request.status === 'confirmed' && (
        <CompleteEvent event={request} onCompleted={onConfirmed} />
      )}
      {/* SCRUM-115: cancel the event, or answer the Organiser's request to. */}
      {request.status_permits.includes('cancel') && (
        <CancelEvent event={request} onCancelled={onConfirmed} />
      )}
    </div>
  )
}

function StatusLabel({ status }: { status: EventRequest['status'] }) {
  const styles: Partial<Record<EventRequest['status'], string>> = {
    submitted: 'bg-amber-50 text-amber-800',
    approved: 'bg-sky-50 text-sky-800',
    confirmed: 'bg-emerald-50 text-emerald-800',
  }
  return (
    <span
      className={`inline-flex self-start rounded-md px-2 py-0.5 text-xs font-medium ${styles[status] ?? 'bg-slate-100 text-slate-700'}`}
    >
      {statusTitle(status)}
    </span>
  )
}

function statusTitle(status: EventRequest['status']) {
  return status.charAt(0).toUpperCase() + status.slice(1)
}
function titleOf(request: EventRequest) {
  return request.name ?? 'Untitled event'
}
