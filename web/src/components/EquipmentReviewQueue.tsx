import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  listRequirementsForReview,
  type RequirementForReview,
  reserveEquipment,
  reviewRequirement,
  type ReviewOutcome,
} from '../api/equipmentReview'
import { REVIEW_LABELS } from '../api/equipmentRequirements'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-44 and SCRUM-53: what Technical Support Staff have to assess, and what they do
 * about it.
 *
 * The routes behind this have existed since SCRUM-44 merged; nothing reached them, so
 * neither story could be shown through the UI. This is that screen.
 *
 * Every rule stays on the API. What may be reviewed (AC2: only while the event is in
 * planning), how much may be reserved and why a reservation is refused are its
 * decisions; this sends the action and shows the answer, refusals included.
 */
export default function EquipmentReviewQueue() {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const [outcome, setOutcome] = useState<string | null>(null)
  const [failure, setFailure] = useState<string | null>(null)

  const queryKey = ['equipment-review', token]
  const queue = useQuery({
    queryKey,
    queryFn: () => listRequirementsForReview(token ?? ''),
    enabled: token !== null,
  })

  function starting() {
    setOutcome(null)
    setFailure(null)
  }

  function refresh() {
    void queryClient.invalidateQueries({ queryKey })
  }

  const record = useMutation({
    mutationFn: (input: { requirement: RequirementForReview; verdict: ReviewOutcome }) =>
      reviewRequirement(token ?? '', input.requirement.id, input.verdict),
    onError: (error: Error) => setFailure(error.message),
    onSuccess: (_void, input) => {
      setOutcome(
        `${input.requirement.equipment_type} recorded as ${REVIEW_LABELS[
          input.verdict
        ].toLowerCase()}.`,
      )
      refresh()
    },
  })

  const reserve = useMutation({
    mutationFn: (requirement: RequirementForReview) =>
      reserveEquipment(token ?? '', requirement.event_request_id, requirement.id),
    onError: (error: Error) => setFailure(error.message),
    onSuccess: (result) => {
      // What was reserved now, and whether anything is still outstanding: reserving is
      // allowed to be partial (SCRUM-53), so "reserved" on its own would overstate it.
      setOutcome(
        result.outstanding > 0
          ? `Reserved ${result.reserved_now} ${result.equipment_type}. ${result.outstanding} still outstanding.`
          : `Reserved ${result.reserved_now} ${result.equipment_type}. Nothing outstanding.`,
      )
      refresh()
    },
  })

  const busy = record.isPending || reserve.isPending

  return (
    <section className="mt-6 rounded-lg border border-slate-200 p-4">
      <h2 className="font-medium">Equipment to assess</h2>
      <p className="mt-1 text-sm text-slate-500">
        What events being planned have asked for. Recording an outcome says whether it can
        be fulfilled; reserving commits equipment for the event&apos;s period.
      </p>

      {queue.isPending && <p className="mt-2 text-sm">Loading…</p>}
      {queue.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {queue.error.message}
        </p>
      )}
      {queue.data?.length === 0 && (
        <p className="mt-2 text-sm text-slate-500">Nothing is waiting to be assessed.</p>
      )}

      {queue.data && queue.data.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-200">
          {queue.data.map((requirement) => (
            <li key={requirement.id} className="py-3 text-sm">
              <p className="font-medium">
                {requirement.equipment_type} &times;{requirement.quantity}
                <span className="ml-2 font-normal text-slate-500">
                  for {requirement.event_name ?? 'Untitled event'}
                </span>
              </p>
              {requirement.event_start_at && requirement.event_end_at && (
                <p className="text-slate-500">
                  {formatSingaporeTime(requirement.event_start_at)} to{' '}
                  {formatSingaporeTime(requirement.event_end_at)}
                </p>
              )}
              {requirement.technical_requirements && (
                <p className="text-slate-500">{requirement.technical_requirements}</p>
              )}
              <p className="mt-1 flex flex-wrap items-center gap-2">
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">
                  {REVIEW_LABELS[requirement.review_status]}
                </span>
                {requirement.reserved_quantity > 0 && (
                  <span className="text-xs text-slate-500">
                    {requirement.reserved_quantity} of {requirement.quantity} reserved
                  </span>
                )}
                {/* SCRUM-43 AC6: the requirement changed after something was reserved
                    against it. The reservation is not released; this is the half of AC6
                    addressed to Technical Support, who decide what happens to it. */}
                {requirement.has_flagged_reservation && (
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                    Reservation to reconsider
                  </span>
                )}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busy}
                  aria-label={`Reserve equipment for ${requirement.equipment_type} on ${requirement.event_name ?? 'Untitled event'}`}
                  onClick={() => {
                    starting()
                    reserve.mutate(requirement)
                  }}
                  className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
                >
                  Reserve
                </button>
                <label className="flex items-center gap-1">
                  <span className="sr-only">
                    Outcome for {requirement.equipment_type} on{' '}
                    {requirement.event_name ?? 'Untitled event'}
                  </span>
                  <select
                    defaultValue=""
                    disabled={busy}
                    aria-label={`Outcome for ${requirement.equipment_type} on ${requirement.event_name ?? 'Untitled event'}`}
                    onChange={(changed) => {
                      const verdict = changed.target.value as ReviewOutcome
                      if (!verdict) return
                      starting()
                      record.mutate({ requirement, verdict })
                    }}
                    className="rounded border border-slate-300 p-1.5 text-sm disabled:opacity-50"
                  >
                    <option value="">Record an outcome</option>
                    <option value="available">Available</option>
                    <option value="partially_available">Partially available</option>
                    <option value="unavailable">Unavailable</option>
                  </select>
                </label>
              </div>
            </li>
          ))}
        </ul>
      )}

      {failure && (
        <p role="alert" className="mt-3 text-sm text-red-600">
          {failure}
        </p>
      )}
      {outcome && (
        <p role="status" className="mt-3 text-sm text-green-700">
          {outcome}
        </p>
      )}
    </section>
  )
}
