import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  approveEventRequest,
  type EventRequest,
  listBookableEventRequests,
  listRequestsForReview,
  rejectEventRequest,
} from '../api/eventRequests'
import { useAuth } from '../auth/useAuth'
import { hasReviewNote } from '../validation/eventRequestReview'
import { acceptsOrdinaryUpdate } from '../validation/planningInfo'
import ClarificationThread from './ClarificationThread'
import EventEquipmentRequirements from './EventEquipmentRequirements'
import PlanningInfoEditor from './PlanningInfoEditor'
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
  const queryKey = ['event-requests', 'coordinator', token]
  const requests = useQuery({
    queryKey,
    queryFn: async () => {
      const [reviewable, bookable] = await Promise.all([
        listRequestsForReview(token ?? ''),
        listBookableEventRequests(token ?? ''),
      ])
      // Disjoint by construction: /reviewable is SUBMITTED only, /bookable is APPROVED only.
      return [...reviewable, ...bookable]
    },
    enabled: token !== null,
  })
  const refresh = () => void client.invalidateQueries({ queryKey })
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
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Coordinator events</h2>
      {requests.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {requests.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          Could not load requests: {requests.error.message}
        </p>
      )}
      {requests.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">No coordinator events are available.</p>
      )}
      {requests.data?.map((request) => (
        <ReviewCard
          key={request.id}
          request={request}
          reason={reason[request.id] ?? ''}
          onReasonChange={(value) => setReason({ ...reason, [request.id]: value })}
          onApprove={() => approve.mutate(request.id)}
          onReject={() => reject.mutate({ id: request.id, reason: reason[request.id] ?? '' })}
          pending={approve.isPending || reject.isPending}
        />
      ))}
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

function ReviewCard({
  request,
  reason,
  onReasonChange,
  onApprove,
  onReject,
  pending,
}: {
  request: EventRequest
  reason: string
  onReasonChange: (value: string) => void
  onApprove: () => void
  onReject: () => void
  pending: boolean
}) {
  return (
    <article className="mt-4 rounded border border-slate-200 p-3">
      <h3 className="font-medium">{request.name}</h3>
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
          <dt className="inline font-medium">Equipment: </dt>
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
    </article>
  )
}
