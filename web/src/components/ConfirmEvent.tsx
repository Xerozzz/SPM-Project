import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import type { EventRequest } from '../api/eventRequests'
import {
  confirmEvent,
  describeArrangementBlocker,
  describeBlockers,
  describeSafetyBlocker,
  NotConfirmableError,
  readConfirmationReadiness,
} from '../api/eventConfirmation'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-80: the assigned Coordinator commits a planned event.
 *
 * Shown with its reasons rather than as a button that fails: on a real board an event
 * waits on three different people, and a Coordinator who can see all three at once
 * chases them in one go instead of learning about the next after each refusal.
 *
 * Every rule stays on the API. What is missing, and whether the Safety Officer's
 * approval still applies to the plan as it stands (AC7), are its answers; this shows
 * them and sends the one action.
 */
export default function ConfirmEvent({
  event,
  onConfirmed,
}: {
  event: EventRequest
  /**
   * Told to the parent rather than shown here. A confirmed event leaves the
   * Coordinator's list, so this card unmounts the moment it succeeds and anything it
   * displayed would vanish with it — pressing the button appeared to do nothing at all.
   */
  onConfirmed: (message: string) => void
}) {
  const { token } = useAuth()
  const client = useQueryClient()
  const [failure, setFailure] = useState<{ text: string; reasons: string[] } | null>(null)

  const readinessKey = ['event-confirmation', event.id, token]
  const readiness = useQuery({
    queryKey: readinessKey,
    queryFn: () => readConfirmationReadiness(token ?? '', event.id),
    enabled: token !== null,
  })

  const confirm = useMutation({
    mutationFn: () => confirmEvent(token ?? '', event.id),
    onError: (error: Error) => {
      setFailure({
        text: error.message,
        reasons:
          error instanceof NotConfirmableError
            ? [
                ...error.arrangementBlockers.map(describeArrangementBlocker),
                ...error.safetyBlockers.map(describeSafetyBlocker),
              ]
            : [],
      })
      // A refusal means something moved after this card loaded: a hold ran out, a
      // requirement was added, the Officer looked again. Reload so the reasons shown
      // are the ones that are true now.
      void client.invalidateQueries({ queryKey: readinessKey })
    },
    onSuccess: (confirmed) => {
      const committed = confirmed.confirmed_bookings.length
      setFailure(null)
      onConfirmed(
        committed === 1
          ? `“${event.name}” is confirmed. Its venue booking is now committed.`
          : `“${event.name}” is confirmed. ${committed} venue bookings are now committed.`,
      )
    },
  })

  return (
    <section className="mt-4 rounded border border-slate-200 p-3">
      <h3 className="text-sm font-medium">Confirm this event</h3>
      <p className="mt-1 text-sm text-slate-500">
        Confirming commits the venue holds as real bookings. It needs every arrangement in place and
        the Safety Officer&apos;s approval of the plan as it stands.
      </p>

      {readiness.isPending && <p className="mt-2 text-sm">Checking…</p>}
      {readiness.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {readiness.error.message}
        </p>
      )}

      {readiness.data && !readiness.data.may_confirm && (
        <div className="mt-2 rounded bg-amber-50 p-2 text-sm text-amber-900">
          <p className="font-medium">Not ready to confirm.</p>
          <ul className="mt-1 list-disc pl-5">
            {describeBlockers(readiness.data).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {readiness.data && (
        <button
          type="button"
          disabled={!readiness.data.may_confirm || confirm.isPending}
          aria-label={`Confirm ${event.name}`}
          onClick={() => {
            setFailure(null)
            confirm.mutate()
          }}
          className="mt-2 rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          Confirm event
        </button>
      )}

      {failure && (
        <div role="alert" className="mt-2 text-sm text-red-600">
          <p>{failure.text}</p>
          {failure.reasons.length > 0 && (
            <ul className="mt-1 list-disc pl-5">
              {failure.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
