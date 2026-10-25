import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { cancelEvent, declineCancellation, readCancellation } from '../api/eventCancellation'
import type { EventRequest } from '../api/eventRequests'
import { formatSingaporeTime } from '../api/venueCalendar'
import { useAuth } from '../auth/useAuth'

/**
 * SCRUM-115: the assigned Coordinator cancels the event, or applies or declines the
 * Organiser's request to.
 *
 * Closed until opened, so nothing is fetched for a card nobody is cancelling. A refusal
 * is shown as the API words it.
 */
export default function CancelEvent({
  event,
  onCancelled,
}: {
  event: EventRequest
  /** Told to the parent, because a cancelled event leaves the Coordinator's list. */
  onCancelled: (message: string) => void
}) {
  const { token } = useAuth()
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const key = ['event-cancellation', event.id, token]
  const record = useQuery({
    queryKey: key,
    queryFn: () => readCancellation(token ?? '', event.id),
    enabled: open && token !== null,
  })
  const pending = record.data?.requests.find((row) => row.status === 'pending') ?? null
  const done = `“${event.name}” is cancelled. Its venue, equipment and registrations are released.`
  const cancel = useMutation({
    mutationFn: (requestId: string | null) =>
      cancelEvent(token ?? '', event.id, {
        reason: reason.trim() === '' ? null : reason,
        request_id: requestId,
      }),
    onSuccess: () => onCancelled(done),
  })
  const decline = useMutation({
    mutationFn: (requestId: string) => declineCancellation(token ?? '', event.id, requestId, note),
    onSuccess: () => {
      setNote('')
      void client.invalidateQueries({ queryKey: key })
    },
  })

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-4 rounded border border-red-300 px-3 py-1.5 text-sm text-red-700"
      >
        Cancel this event…
      </button>
    )
  }

  return (
    <section className="mt-4 rounded border border-red-200 p-3 text-sm">
      <h3 className="font-medium">Cancel this event</h3>
      <p className="mt-1 text-slate-500">
        This cannot be undone. Venue bookings and holds are cancelled, equipment is released,
        registration closes and live registrations are cancelled.
      </p>
      {record.isPending && <p className="mt-2">Checking for a request…</p>}
      {record.isError && (
        <p role="alert" className="mt-2 text-red-600">
          {record.error.message}
        </p>
      )}
      {pending && (
        <div className="mt-2 rounded bg-amber-50 p-2">
          <p>
            The Organiser asked to cancel on {formatSingaporeTime(pending.requested_at)}:{' '}
            <q>{pending.reason}</q>
          </p>
          <button
            type="button"
            disabled={cancel.isPending}
            onClick={() => cancel.mutate(pending.id)}
            className="mt-2 rounded bg-red-700 px-3 py-1.5 text-white disabled:opacity-50"
          >
            Cancel the event as asked
          </button>
          <label className="mt-2 block">
            Why you are declining
            <textarea
              value={note}
              onChange={(change) => setNote(change.target.value)}
              rows={2}
              className="mt-1 block w-full rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <button
            type="button"
            disabled={decline.isPending}
            onClick={() => decline.mutate(pending.id)}
            className="mt-2 rounded border border-slate-300 px-3 py-1.5 disabled:opacity-50"
          >
            Decline request
          </button>
          {decline.isError && (
            <p role="alert" className="mt-2 text-red-600">
              {decline.error.message}
            </p>
          )}
        </div>
      )}
      <label className="mt-2 block">
        Reason for cancelling
        <textarea
          value={reason}
          onChange={(change) => setReason(change.target.value)}
          rows={2}
          className="mt-1 block w-full rounded border border-slate-300 px-2 py-1"
        />
      </label>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={cancel.isPending}
          onClick={() => cancel.mutate(null)}
          className="rounded bg-red-700 px-3 py-1.5 text-white disabled:opacity-50"
        >
          Cancel event
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded border border-slate-300 px-3 py-1.5"
        >
          Keep event
        </button>
      </div>
      {cancel.isError && (
        <p role="alert" className="mt-2 text-red-600">
          {cancel.error.message}
        </p>
      )}
    </section>
  )
}
